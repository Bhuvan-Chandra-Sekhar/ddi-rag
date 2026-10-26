# Incident Runbook

What exists today for monitoring, kill switches, rollback, and backups —
written honestly: some of this is real automated tooling, some is a
documented manual procedure because the automated version doesn't exist
yet (and would need credentials/accounts this codebase doesn't have).

## Detecting an incident

- **`GET /api/health`** — shallow liveness only (Render's own
  `healthCheckPath`). Returns `200 {"status": "ok"}` whenever the Flask
  process is up, deliberately independent of the database — see its
  docstring in `app.py` for why it must stay that way.
- **`GET /api/health/deep`** — actually checks database connectivity
  (`SELECT 1`) and reports both kill switches' current state. Returns
  `503 {"status": "degraded", ...}` when the database is unreachable.
  Not wired into any automated alerting — check it manually, or point an
  external uptime monitor (e.g. a free UptimeRobot/cron-job.org check) at
  it if you want a page when it goes red. **This is the gap**: there is
  no automated alerting today. No Sentry/Datadog/equivalent is
  integrated — Render's own log stream (`render.com` dashboard → the
  `ddi-rag` service → Logs) is the only place exceptions currently
  surface, and nothing pages anyone when one happens.
- **Audit trail** (`AuditEvent` table) — `guest_self_check_error`,
  `auth.login_failed`, `guest_explain_unavailable`, etc. are all real,
  queryable rows (see `docs/HAZARD_REGISTER.md` H16/H21 for what's
  covered). Querying this table directly is currently the only way to
  see error *volume* over time — there's no dashboard over it.

## Kill switches

Two independent, env-var-controlled switches (`config.py`):

| Switch | Env var | Effect when `true` |
|---|---|---|
| Self-check | `KILL_SWITCH_SELF_CHECK` | `POST /api/self-check` returns `503 {"error": "temporarily_unavailable"}` immediately, before touching the rule engine |
| Explanations | `KILL_SWITCH_EXPLAIN` | `POST /api/explain` returns the same `503`, before calling Groq/Cohere |

**To use one:** set the env var on Render (dashboard → `ddi-rag` →
Environment → add/edit → the service restarts automatically) or locally,
and restart the process. This requires a restart, not a hot-reload — there
is no runtime-togglable store (Redis, a feature-flag service) behind
these; they're read once from the environment at `config.py` import time.
For a true zero-restart kill switch, this would need to move to something
polled at request time (a tiny DB-backed flags table, or a Redis key) —
not built, because it adds a new infrastructure dependency this project
doesn't otherwise have.

**What's NOT covered by a kill switch:** the authenticated clinical
workflow (`routes_clinical.py` — case creation, dispense, intervention,
rule review). An incident there currently has no faster mitigation than a
code fix and redeploy, or rolling back (below). The existing `RuleStatus`
machinery (`RETIRED`/`REJECTED`) IS a real per-rule kill switch — if one
specific interaction rule is wrong, retiring/rejecting it takes effect
immediately with no deploy at all.

## Rollback

No custom rollback tooling was built — Render's own deployment history
already does this:

1. Render dashboard → `ddi-rag` service → **Deploys** tab.
2. Find the last known-good deploy.
3. Click **Rollback to this deploy** (or redeploy that specific commit).

This reverts code only. It does **not** revert database schema changes —
there are no Alembic migrations in this project (see README's "Known
limitations"), so a schema change that shipped alongside bad code can't
be automatically rolled back with it. If a deploy included a schema
change, a rollback needs a human to check whether the old code is still
compatible with the new schema before rolling back, not just click the
button.

## Backup verification

**Not automated — this is a real, acknowledged gap** (also listed in
`docs/HAZARD_REGISTER.md`'s "Known gaps"). Nothing in this codebase
confirms a recent backup exists or is restorable. The manual check:

1. Supabase dashboard → the project → **Database** → **Backups**.
2. Confirm a recent backup timestamp exists and matches your plan's
   retention window (free-tier Supabase projects may have no
   point-in-time recovery at all — check the plan).
3. Actually restoring from a backup is a destructive, project-level
   operation in Supabase's own UI — do this only with the user's explicit
   confirmation, never as a routine check.

A real fix here would be a scheduled script hitting Supabase's management
API to confirm backup recency automatically — not built, because it needs
a Supabase management API token this project doesn't currently provision
or store anywhere.

## Incident response checklist

1. Confirm via `/api/health/deep` and Render's log stream whether this is
   a database issue, an upstream API (Groq/Cohere/RxNorm) issue, or an
   application bug.
2. If it's isolated to self-check or explanations specifically, flip the
   relevant kill switch (above) rather than taking the whole app down.
3. If it's a bad deploy, roll back via Render's Deploys tab.
4. Check the audit trail (`AuditEvent` rows for the affected action) to
   scope how many requests were actually affected and since when.
5. Write up what happened — this project has no incident-tracking tool
   integrated; a plain dated entry appended to this file, or a new file
   under `docs/incidents/`, is the lightest honest option until something
   better exists.
