"""Weekly Postgres → Cloudflare R2 backup.

Runs as a Railway cron service (or as a maintenance step). Dumps the
Neon Postgres database via pg_dump, gzips, uploads to R2 with a
date-stamped key, then prunes anything older than 30 weeks.

R2 free tier: 10 GB storage, 1 M Class-A operations/mo. Doornegar's
DB is currently ~50-100 MB compressed; 30 weekly snapshots = ~3 GB
worst-case. Comfortably inside free tier.

Required env vars (all set in Railway):
  DATABASE_URL              -- the Neon connection string
  R2_ACCOUNT_ID             -- Cloudflare account ID
  R2_BUCKET                 -- R2 bucket name (e.g. "doornegar-backups")
  R2_ACCESS_KEY_ID          -- R2 API token access key
  R2_SECRET_ACCESS_KEY      -- R2 API token secret

Usage (manual smoke test):
  python scripts/r2_db_backup.py
  python scripts/r2_db_backup.py --no-prune    # skip the prune step

The script returns 0 on success, non-zero on any failure. Railway
cron sees the exit code and surfaces it in the run log.

Restore from a backup (manual, requires psql + gunzip):
  aws s3 cp \\
    --endpoint-url https://<account>.r2.cloudflarestorage.com \\
    s3://doornegar-backups/2026-05-13.sql.gz - \\
    | gunzip | psql $DATABASE_URL
"""
from __future__ import annotations

import argparse
import gzip
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("r2_db_backup")

RETENTION_WEEKS = 30


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error(f"Missing required env var: {name}")
        sys.exit(2)
    return val


def _parse_db_url(url: str) -> dict:
    """Parse DATABASE_URL into individual pg_dump args + env-var bag.

    pg_dump's libpq URI parser is stricter than asyncpg/psycopg2 and chokes
    on some Neon-style query strings (e.g. on 2026-05-06 it errored with
    'missing key/value separator "=" in URI query parameter: "sslmo"' on a
    URL that asyncpg parsed without complaint). Bypassing URI parsing by
    passing host/port/user/dbname individually + PGPASSWORD/PGSSLMODE via
    env sidesteps the issue entirely. Neon requires SSL, hardcode
    sslmode=require.
    """
    p = urlparse(url)
    if p.scheme not in ("postgres", "postgresql"):
        raise ValueError(f"Unexpected scheme: {p.scheme!r}")
    return {
        "host": p.hostname or "",
        "port": str(p.port or 5432),
        "user": unquote(p.username) if p.username else "",
        "password": unquote(p.password) if p.password else "",
        "dbname": (p.path or "/").lstrip("/"),
    }


def _make_dump(db_url: str, out_path: Path) -> None:
    """Stream pg_dump → gzip → file. No intermediate uncompressed file."""
    log.info(f"pg_dump → {out_path}")
    if shutil.which("pg_dump") is None:
        log.error("pg_dump not found in PATH. Install postgresql-client in the Railway service.")
        sys.exit(3)

    parts = _parse_db_url(db_url)
    log.info(f"pg_dump target: host={parts['host']} port={parts['port']} dbname={parts['dbname']} user={parts['user']}")

    # Pass connection details via env + individual flags. Avoids libpq URI
    # parsing entirely (which has been finicky on Neon connection strings).
    env = {**os.environ, "PGPASSWORD": parts["password"], "PGSSLMODE": "require"}

    # --no-owner + --no-privileges keep the dump portable across Postgres
    # users. --format=plain is restorable via psql, no pg_restore needed.
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "-h", parts["host"],
        "-p", parts["port"],
        "-U", parts["user"],
        "-d", parts["dbname"],
    ]
    with gzip.open(out_path, "wb") as gz:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        assert proc.stdout is not None
        # Order matters: copy until EOF, wait for pg_dump to finish on
        # its own (so we get the real exit code), THEN close stdout.
        # Closing stdout before wait() can SIGPIPE pg_dump and silently
        # truncate the dump while reporting rc=0 (or rc=141 SIGPIPE).
        try:
            shutil.copyfileobj(proc.stdout, gz)
            rc = proc.wait()
        finally:
            proc.stdout.close()
        if rc != 0:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            log.error(f"pg_dump exited {rc}. stderr:\n{stderr}")
            sys.exit(4)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    log.info(f"dump complete: {size_mb:.1f} MB compressed")


def _r2_client(account_id: str, access_key: str, secret_key: str):
    """Build an S3-compatible boto3 client for R2."""
    try:
        import boto3
    except ImportError:
        log.error("boto3 not installed. Run: pip install boto3")
        sys.exit(5)

    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def _upload(client, bucket: str, key: str, path: Path) -> None:
    log.info(f"upload → s3://{bucket}/{key}")
    with open(path, "rb") as f:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType="application/gzip",
        )
    log.info("upload complete")


def _prune_old(client, bucket: str, retention_weeks: int = RETENTION_WEEKS) -> int:
    """Delete backups older than retention_weeks. Returns count deleted."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(weeks=retention_weeks)
    log.info(f"prune: delete backups before {cutoff.date().isoformat()}")
    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            # Keys are date-prefixed: YYYY-MM-DD.sql.gz
            try:
                stem = key.split(".")[0]  # "2026-05-06"
                obj_date = datetime.strptime(stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                log.warning(f"skipping non-dated key: {key}")
                continue
            if obj_date < cutoff:
                log.info(f"  delete: {key}")
                client.delete_object(Bucket=bucket, Key=key)
                deleted += 1
    log.info(f"prune complete: {deleted} deleted")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly DB backup → Cloudflare R2")
    parser.add_argument("--no-prune", action="store_true", help="Skip the retention prune step")
    parser.add_argument("--retention-weeks", type=int, default=RETENTION_WEEKS)
    args = parser.parse_args()

    db_url = _require_env("DATABASE_URL")
    account_id = _require_env("R2_ACCOUNT_ID")
    bucket = _require_env("R2_BUCKET")
    access_key = _require_env("R2_ACCESS_KEY_ID")
    secret_key = _require_env("R2_SECRET_ACCESS_KEY")

    today = datetime.now(tz=timezone.utc).date().isoformat()
    key = f"{today}.sql.gz"

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / key
        _make_dump(db_url, out_path)
        client = _r2_client(account_id, access_key, secret_key)
        _upload(client, bucket, key, out_path)

    if not args.no_prune:
        _prune_old(client, bucket, retention_weeks=args.retention_weeks)

    log.info(f"backup complete: {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
