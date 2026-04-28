"""Smoke-test the /admin/dashboard health-check system.

Hits the production dashboard endpoint, lists every issue currently
firing, and prints a checklist of the seven known health checks
(H1..H7) showing which are active. Useful as an ops sanity check
after a deploy or before triggering manual maintenance.

Usage:
    cd backend
    ADMIN_TOKEN=<token> python scripts/smoke_health.py
    # optional: API_URL=https://api.doornegar.org python scripts/smoke_health.py
"""

from __future__ import annotations

import os
import sys
import urllib.request
import json


KNOWN_CHECKS = [
    ("H1", "0 new stories", "0 new stories in 24h"),
    ("H2", "NULL embedding", "NULL embeddings in last 24h"),
    ("H3", "Last maintenance had", "Last maintenance had failed steps"),
    ("H4", "Maintenance lock held", "Maintenance lock stuck or running long"),
    ("H5", "failing across consecutive runs", "Steps failing across consecutive runs"),
    ("H6", "active connections", "DB connection pressure"),
    ("H7", "× the recent median", "Step elapsed regression vs baseline"),
]


def main() -> int:
    api = os.environ.get("API_URL", "https://api.doornegar.org").rstrip("/")
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN env var is required.", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        f"{api}/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Dashboard call failed: {e}", file=sys.stderr)
        return 3

    issues = data.get("issues") or []
    print(f"Dashboard returned {len(issues)} issues:")
    print("-" * 70)
    for i in issues:
        sev = (i.get("severity") or "info").upper()
        print(f"  [{sev:<7}] {i.get('message', '')}")
    print()

    print("Health check coverage:")
    print("-" * 70)
    for code, marker, label in KNOWN_CHECKS:
        firing = any(marker.lower() in (i.get("message", "") or "").lower() for i in issues)
        flag = "FIRING" if firing else "  ok  "
        print(f"  {code} {flag}  {label}")

    print()
    msgs = [i.get("message", "") or "" for i in issues]
    unmatched = [
        m for m in msgs
        if not any(marker.lower() in m.lower() for _, marker, _ in KNOWN_CHECKS)
    ]
    if unmatched:
        print(f"Issues not matching any known check ({len(unmatched)}):")
        for m in unmatched[:8]:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
