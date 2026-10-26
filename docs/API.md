# API Reference

Endpoint list grouped by where each one is defined. "Auth" is what
`@jwt_required()`/role checks actually enforce, not just a description —
see `core/authz.py` for what `require_role`/`authorized_case` do (404,
not 403, on a cross-tenant case; 403 on same-tenant-wrong-role).

**Response envelope convention:** success responses are endpoint-specific
JSON. Errors are always `{"error": "<code-or-message>"}`, sometimes with
an added `"message"` field for a longer, safe-to-display explanation
(used for the 503s below). No error response ever includes raw exception
text — see `docs/HAZARD_REGISTER.md` H17/H25.

## `app.py` (no blueprint prefix)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/health` | none | Shallow liveness only — Render's restart trigger, never touches the DB |
| GET | `/api/health/deep` | none | Real `SELECT 1` DB check + kill-switch states; 503 if DB unreachable |
| GET | `/patient` | none | Serves the patient SPA |
| GET | `/clinical` | none | Serves the clinical console SPA |
| GET | `/v1/organizations` | none | Org names only, for a signup picker |
| POST | `/api/auth/register` | none | Creates an account |
| POST | `/api/auth/login` | none | 10/min rate limit (brute-force target) |
| POST | `/api/query` | JWT optional | Free-text prescription query, works anonymously too |
| GET | `/v1/safety-cases/queue` | JWT, `CLINICAL_STAFF` | Pharmacist/prescriber/safety-officer queue |
| GET | `/v1/safety-cases/<id>/timeline` | JWT, `CLINICAL_STAFF` | |
| POST | `/v1/safety-cases/<id>/findings/assess` | JWT, `PHARMACIST_REVIEW` | |
| POST | `/v1/interventions` | JWT, `PHARMACIST_REVIEW` | |
| POST | `/v1/interventions/<id>/response` | JWT, prescriber only | |
| GET | `/v1/my/cases` | JWT, `PATIENT` role | Scoped strictly to the caller's own linked Patient record |

## `routes/clinical.py` (`clinical_bp`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/v1/staff` | JWT, `CLINICAL_STAFF` | |
| GET | `/v1/patients` | JWT, `CLINICAL_STAFF` | |
| POST | `/v1/patients` | JWT, `CLINICAL_STAFF` | Refused (400) unless `synthetic_data_acknowledged: true` while `PROTOTYPE_MODE` is on |
| POST | `/v1/prescriptions` | JWT, `CLINICAL_STAFF` | |
| POST | `/v1/safety-cases` | JWT, `CLINICAL_STAFF` | Creates a case and runs the deterministic rule engine against it |
| GET | `/v1/safety-cases/<id>` | JWT, `CLINICAL_STAFF` | Full case detail |
| POST | `/v1/safety-cases/<id>/dispense` | JWT, `PHARMACIST_REVIEW` | |
| POST | `/v1/safety-cases/<id>/communicate` | JWT, `PHARMACIST_REVIEW` | |
| POST | `/v1/safety-cases/<id>/close` | JWT, `PHARMACIST_REVIEW` | 400 if the transition is invalid or the case is already closed |
| POST | `/v1/safety-cases/<id>/resolve-escalation` | JWT, `PHARMACIST_REVIEW` | |
| POST | `/v1/findings/<id>/explain` | JWT, `CLINICAL_STAFF` | 503 `explanation_unavailable` if the LLM call fails — the Finding row is left untouched |
| GET | `/v1/clinical-rules/pending` | JWT, `RULE_REVIEWERS` | DRAFT candidate rules |
| GET | `/v1/clinical-rules/approved` | JWT, `RULE_REVIEWERS` | Currently-APPROVED rules (the list to pick a rule to retire from) |
| POST | `/v1/clinical-rules/<id>/review` | JWT, `RULE_REVIEWERS` | decision: `approved` / `rejected` / `retired` (retired only reachable from approved) |

## `routes/public.py` (`public_bp`)

Unauthenticated, lower-trust pathway — no pharmacist ever reviews these
results. Both routes return 503 `temporarily_unavailable`/
`explanation_unavailable` if their kill switch is on (`KILL_SWITCH_SELF_CHECK`/
`KILL_SWITCH_EXPLAIN`, see `docs/INCIDENT_RUNBOOK.md`).

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/self-check` | none | 15/min rate limit. Deterministic findings only, no LLM/embedding calls, no persistence |
| POST | `/api/explain` | none | 10/min rate limit. On-demand explanation for one self-check finding (Cohere + Groq call) |

## Role groups referenced above

Defined independently in `app.py` and `routes/clinical.py` (small,
stable sets — see each file's own comment for why they aren't shared
across a potential `app.py` ↔ `routes/clinical.py` circular import):

- `CLINICAL_STAFF`: pharmacist, prescriber, safety officer
- `PHARMACIST_REVIEW`: pharmacist, safety officer
- `RULE_REVIEWERS`: pharmacist, safety officer (same set as
  `PHARMACIST_REVIEW`, named separately in `routes/clinical.py` for
  what the action is, not which set happens to match)
- `PRESCRIBER_ONLY`: prescriber only
