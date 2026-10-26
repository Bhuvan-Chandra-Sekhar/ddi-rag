# Hazard Register

A hazard here is a specific way this system could mislead a patient or
clinician about medication safety, leak data across a trust boundary, or
lose the ability to reconstruct what happened after an incident. Each row
names the hazard, the harm if it occurred uncontrolled, the control that
exists against it, and the automated test(s) that would fail if the
control broke.

**This file is itself checked for drift.**
`tests/test_hazard_register_coverage.py` parses the table below and fails
the suite if any listed test function doesn't exist, or exists but isn't
collected by pytest — a hazard with a test that got renamed or deleted
goes back to being an unguarded hazard, silently, unless something catches
that. Keep `Test(s)` entries as exact `path::function_name` references.

| ID | Hazard | Harm if uncontrolled | Control | Test(s) |
|----|--------|----------------------|---------|---------|
| H1 | LLM-generated explanation changes a finding's severity or recommended action | A plain-language explanation could override the deterministic verdict a patient/clinician actually sees acted on | `explain_finding()` is structurally return-shape-limited — no code path returns severity/action | `tests/test_evidence.py` (Phase 4 exit gate suite) |
| H2 | An unreviewed (DRAFT) rule is silently treated as "cleared" | A real, undocumented interaction reads as "nothing found" | DRAFT rules produce an explicit `UNKNOWN`-severity finding, never silence | `tests/test_public_routes.py::test_self_check_surfaces_reported_severity_for_unreviewed_ddi_pair` |
| H3 | A medication pair with no matching rule at all is indistinguishable from "checked and clear" | "No findings" reads as a safety guarantee when the knowledge base simply has no data | `ddi_coverage_report()` reports `pairs_with_no_rule` separately from "nothing found" | `tests/test_authz_and_governance.py::test_pair_with_no_rule_at_all_is_reported_as_a_coverage_gap` |
| H4 | A previously-APPROVED rule is retired and the interaction becomes invisible | A once-confirmed interaction looks identical to "never studied" after retirement | RETIRED rules still produce an `UNKNOWN` finding, same non-silent treatment as DRAFT | `tests/test_rule_retirement_and_resilience.py::test_retired_rule_produces_an_unknown_finding_not_silence` |
| H5 | A rule is retired without ever having been clinically approved | Retirement becomes a way to bypass review entirely (approve-then-retire isn't the only path if RETIRED were reachable from DRAFT) | `review_rule()` only allows the RETIRED transition from a currently-APPROVED rule | `tests/test_rule_retirement_and_resilience.py::test_cannot_retire_a_draft_rule`, `::test_cannot_retire_a_rejected_rule` |
| H6 | The explanation service (Groq) fails and a fabricated-looking "explanation" reaches the user as if it were real clinical content | A patient reads "Generation error: ..." or a timeout message as a real medical explanation; worse, raw exception text could leak | `explain_finding()` raises `ExplanationUnavailable` on a known failure string instead of returning it as content; both HTTP routes turn that into an explicit 503 | `tests/test_rule_retirement_and_resilience.py::test_guest_explain_endpoint_returns_503_not_500_on_outage`, `::test_explain_finding_raises_explanation_unavailable_without_leaking_raw_exception_text` |
| H7 | An explanation-service failure corrupts or partially overwrites a Finding row | A clinician-facing Finding ends up in an inconsistent state after a failed explain attempt | The route only writes `finding.explanation`/etc. after `explain_finding()` returns successfully; the `ExplanationUnavailable` exception is raised before any write | `tests/test_rule_retirement_and_resilience.py::test_clinical_explain_endpoint_returns_503_and_leaves_finding_untouched` |
| H8 | A user in one organization can see or act on another organization's case | Cross-tenant PHI exposure | `authz.py`'s `authorized_case()` returns 404 (not 403) on cross-tenant access, never leaking existence | `tests/test_authz_and_governance.py::test_cross_org_pharmacist_gets_404_not_403_regardless_of_role` |
| H9 | A patient-role account performs a pharmacist/prescriber-only action within their own org | Unqualified account overrides or dismisses a clinical finding | `require_role()` gates every clinical-workflow route by role, independent of org membership | `tests/test_authz_and_governance.py::test_patient_cannot_assess_findings_even_in_their_own_org`, `::test_patient_cannot_dispense` |
| H10 | `/v1/my/cases` returns another patient's cases | Cross-patient PHI exposure | Route scopes strictly to the calling patient's own linked record | `tests/test_patient_portal.py` |
| H11 | A prompt-injection attempt (e.g. in patient-typed notes) changes an explanation's clinical content | An attacker-controlled instruction embedded in free text alters what a patient is told about their medications | System prompt + structural return-shape limits; patient notes are explicitly labeled "unverified background only" | `tests/test_llm_safety_evals.py` |
| H12 | An ambiguous medication name is silently auto-confirmed as a specific drug | Wrong-drug identity drives a wrong interaction check | Approximate RxNorm matches come back `identity_confirmed: false`, never silently trusted | `tests/test_medication_identity.py` |
| H13 | A closed/dispensed SafetyCase is modified after closure | Audit trail no longer reflects what was actually decided and when | Closed-case immutability enforced in the state machine | `tests/test_safety_case_state_machine.py` |
| H14 | Concurrent writes to the same case/finding silently clobber each other | Two staff members' conflicting actions produce a corrupted, unexplainable final state | Optimistic concurrency check on case/finding writes | `tests/test_safety_enforcement.py` |
| H15 | A MAJOR/CRITICAL finding is dismissed or overridden without a documented reason | An unexplained override of a serious finding, no accountable rationale on record | Dismissal/override requires rationale text; enforced server-side, not just a UI field | `tests/test_safety_enforcement.py` |
| H16 | The guest self-check and authentication endpoints have no audit trail | An incident (abuse, a disputed result) can't be reconstructed after the fact | `record_audit_event()` calls on self-check, explain, login (success + failure), and register (success + failure) | `tests/test_rule_retirement_and_resilience.py::test_guest_self_check_writes_an_audit_event`, `::test_login_success_is_audited_with_actor_user_id`, `::test_login_failure_is_audited_without_a_real_user_subject_id`, `::test_register_success_and_failure_are_both_audited` |
| H17 | An unexpected error in the guest self-check path leaks exception detail to the end user | Internal exception messages (stack traces, library errors) reach an unauthenticated caller | Generic error message to the client; exception logged server-side only | `tests/test_rule_retirement_and_resilience.py::test_guest_self_check_error_is_audited_and_returns_500_not_a_leak` |
| H18 | User-facing copy makes an absolute safety claim ("safe", "guaranteed", "clinically validated") | A marketing/UI headline reads as a clinical guarantee the system cannot actually make, contradicting every other safety control in this table | Denylist scan of frontend source for known-dangerous absolute-claim phrases | `tests/test_hazard_register_coverage.py::test_no_unsafe_absolute_claims_in_frontend_copy` |
| H19 | A real patient's name + medication/allergy/condition history is entered before the system has been clinically validated | PHI-shaped data about a real person sits in an unvalidated prototype with no privacy/retention policy yet | `config.PROTOTYPE_MODE` (default on) requires an explicit `synthetic_data_acknowledged: true` on every `POST /v1/patients` call, or the record is refused outright | `tests/test_rule_retirement_and_resilience.py::test_creating_a_patient_without_acknowledgment_is_refused_in_prototype_mode`, `::test_creating_a_patient_with_acknowledgment_succeeds_in_prototype_mode` |
| H20 | An evidence chunk's embedding is silently incomparable to others after `COHERE_EMBED_MODEL` changes | Cosine-similarity search mixes vectors from two different embedding models with no way to tell — a meaningless score presented as a real relevance ranking | `evidence_chunks` rows carry `embedding_model`/`chunk_version`/`source_dataset`/`ingested_at`, written on every upsert and backfilled onto the existing table via idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` | `tests/test_evidence_store.py::test_upsert_chunks_writes_provenance_and_current_embedding_model` |
| H21 | A database outage during error-handling itself crashes past the safe error response | An infra outage (the most important case to degrade gracefully for) instead produces an unhandled 500 with no audit trail and a possible stack-trace leak — the opposite of what the error handling was built for | `_try_audit()` (app.py, routes_public.py) wraps every audit write in its own try/except so a DB-unreachable failure during error-handling can't propagate past an already-decided response | `tests/test_rule_retirement_and_resilience.py::test_self_check_survives_database_outage_during_both_the_lookup_and_the_audit_write`, `::test_login_survives_database_outage_during_the_audit_write` |
| H22 | Patient-typed free text (e.g. "patient_notes") or a login password ends up stored in the audit trail | Free-text health disclosures or credentials persist somewhere beyond the request that collected them, with weaker access control than the original form | Audit payloads are built from structural fields only (counts, rule IDs, severities) — never from request free-text fields | `tests/test_rule_retirement_and_resilience.py::test_explain_endpoint_never_persists_patient_notes_text_in_audit`, `::test_login_failure_audit_never_includes_the_attempted_password` |
| H23 | A bad Groq response or data-corruption issue in self-check/explain can't be mitigated faster than a full code fix + deploy | A known-bad feature keeps serving incorrect results for the duration of a deploy cycle | `KILL_SWITCH_SELF_CHECK`/`KILL_SWITCH_EXPLAIN` (config.py) return an explicit 503 immediately, independently togglable | `tests/test_rule_retirement_and_resilience.py::test_self_check_kill_switch_returns_503_when_active`, `::test_kill_switches_are_independent_of_each_other` |
| H24 | The platform's own liveness probe depends on the database, so a transient DB blip triggers an unnecessary process restart | A slow/flaky database connection cascades into repeated app restarts, making a minor DB hiccup look like a full outage | `/api/health` (Render's `healthCheckPath`) never touches the database; `/api/health/deep` is the separate, DB-dependent check | `tests/test_rule_retirement_and_resilience.py::test_shallow_health_check_never_touches_the_database`, `::test_deep_health_check_reports_degraded_when_database_is_unreachable` |

See `docs/INCIDENT_RUNBOOK.md` for how these are actually used during an
incident, including the parts (alerting, backup verification) that are
still manual/dashboard steps rather than automated.

## Known gaps not yet covered by an automated test

These are real, acknowledged gaps — listed here rather than omitted, so the
register stays honest about what it doesn't cover yet:

- **No field-level encryption at rest.** Relies entirely on the hosting
  database's own disk encryption; nothing in this codebase enforces or
  tests that.
- **No monitoring/alerting integration** (Sentry/Datadog/equivalent) — a
  production incident currently has no automated detection path beyond
  whatever the hosting platform itself surfaces.
- **No backup-verification check** — nothing in this codebase confirms a
  recent backup exists or is restorable; this depends entirely on the
  hosting database provider's own default policy.
- **The PROTOTYPE_MODE gate (H19) requires an honest caller.** It stops a
  well-behaved clinical-console client from creating a real-PHI record by
  accident, and leaves a clear audit trail either way — but a caller that
  deliberately sends `synthetic_data_acknowledged: true` against real
  patient data isn't technically prevented, only dishonestly represented.
  A full fix needs actual field-level validation (e.g. rejecting DOB/MRN
  patterns that look real) or an org-level admin approval step, not yet
  built.
