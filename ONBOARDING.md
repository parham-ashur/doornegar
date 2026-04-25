# Doornegar — Onboarding for Collaborators

Welcome. This file is the single entry point for anyone joining the project.

## What is Doornegar?
A free, bilingual (Persian/English) media transparency platform for Iranian news. It aggregates articles from ~28 outlets, clusters them into stories, and reveals bias, framing differences, blind spots, and Telegram reactions.

- Live frontend: https://frontend-tau-six-36.vercel.app
- Backend API: https://doornegar-production.up.railway.app
- Repo: https://github.com/parham-ashur/doornegar

## Where to start (read in this order)
1. `CLAUDE.md` — one-page overview of the whole system
2. `project-management/PROJECT_STATUS.md` — current state, data metrics, infra
3. `project-management/ARCHITECTURE.md` — how the pieces fit together
4. `project-management/RUNBOOK.md` — how to run, deploy, troubleshoot
5. `project-management/BACKLOG.md` — prioritized open work
6. `DEVLOG.md` — most recent session notes

## What you need installed
- Python 3.12, Node 20+, Docker Desktop, Railway CLI, Vercel CLI, git
- `pip install -e ".[dev,nlp,llm]"` inside `backend/`
- `npm install` inside `frontend/`

## Local dev (quick path)
```bash
cd doornegar && docker compose up -d db redis
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```

## Credentials
Ask Parham directly. Do **not** commit secrets. Rotate on arrival — some credentials have been exposed in prior chat history and need new values for any new collaborator.

## Communication & task tracking
- Code work: GitHub issues on the repo
- Non-code work (strategy, content, partnerships, legal): Notion workspace "Doornegar" (Parham will invite you)
- Session summaries: append to `DEVLOG.md`
- Decisions with long-term consequence: add to `project-management/DECISION_LOG.md`

## Ground rules
- Persian text is always normalized with `app.nlp.persian.normalize()` before storage
- All DB ops are async (SQLAlchemy 2 + asyncpg)
- Do not ship destructive DB migrations without a backup and Parham's explicit confirmation
- Frontend changes: test on mobile before merging (most Iranian users are on phones)
- Do not push secrets, tokens, or personal identifiers of Iranian users

## Who to ask
- Product, editorial, partnerships: Parham
- Pipeline / NLP / infra: start with `RUNBOOK.md`, then ask Parham
- Architecture decisions: open a GitHub issue tagged `rfc`
