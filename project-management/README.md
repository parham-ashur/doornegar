# Doornegar Project Management

This folder contains all project management documentation for the Doornegar (دورنگر) Iranian Media Transparency Platform.

## What's in this folder

| File | Purpose |
|------|---------|
| `PROJECT_STATUS.md` | Current state of the project: what works, data metrics, infrastructure |
| `ARCHITECTURE.md` | System architecture, data flow, tech stack, API endpoints |
| `MIGRATION_PLAN.md` | Step-by-step plan for migrating from cloud services to OVHcloud VPS |
| `BACKLOG.md` | Prioritized list of remaining work (Must Have / Should Have / Nice to Have) |
| `RUNBOOK.md` | How to run, deploy, monitor, and troubleshoot the system |
| `CHANGELOG.md` | Log of changes made during each work session |

## How to use these files

- **Before a work session**: Read `PROJECT_STATUS.md` and `BACKLOG.md` to know where things stand and what to work on next.
- **During a work session**: Refer to `RUNBOOK.md` for commands and procedures. Check `ARCHITECTURE.md` if you need to understand how pieces fit together.
- **After a work session**: Update `CHANGELOG.md` with what was done. Update `PROJECT_STATUS.md` if data metrics changed. Check off completed items in `BACKLOG.md`.
- **Planning migration**: Follow `MIGRATION_PLAN.md` step by step when ready to move to OVHcloud.

## Keeping these files up to date

These files are only useful if they stay current. After significant changes:

1. Update `CHANGELOG.md` with a dated entry
2. Update data metrics in `PROJECT_STATUS.md` (run `python manage.py status` to get current numbers)
3. Check off completed items in `BACKLOG.md`
4. Update `ARCHITECTURE.md` if the system structure changes
