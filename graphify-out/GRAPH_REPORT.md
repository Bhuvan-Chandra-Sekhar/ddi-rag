# Graph Report - .  (2026-08-26)

## Corpus Check
- Corpus is ~27,722 words - fits in a single context window. You may not need a graph.

## Summary
- 482 nodes · 1329 edges · 27 communities (21 shown, 6 thin omitted)
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 549 edges (avg confidence: 0.53)
- Token cost: 188,621 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Domain Model Tables|Domain Model Tables]]
- [[_COMMUNITY_Safety Case Intervention Routes|Safety Case Intervention Routes]]
- [[_COMMUNITY_MCP Server Interface|MCP Server Interface]]
- [[_COMMUNITY_Aho-Corasick Drug Matcher|Aho-Corasick Drug Matcher]]
- [[_COMMUNITY_Flask App Core Routes|Flask App Core Routes]]
- [[_COMMUNITY_Guest Self-Check Routes|Guest Self-Check Routes]]
- [[_COMMUNITY_openFDA Data Preprocessing|openFDA Data Preprocessing]]
- [[_COMMUNITY_LLM Faithfulness Eval Helpers|LLM Faithfulness Eval Helpers]]
- [[_COMMUNITY_Deterministic Clinical Rule Engine|Deterministic Clinical Rule Engine]]
- [[_COMMUNITY_pgvector Evidence Store|pgvector Evidence Store]]
- [[_COMMUNITY_Patient Portal Self-Check UI|Patient Portal Self-Check UI]]
- [[_COMMUNITY_Clinical Regression Eval Metrics|Clinical Regression Eval Metrics]]
- [[_COMMUNITY_Clinical Console Case Actions|Clinical Console Case Actions]]
- [[_COMMUNITY_Clinical Console Auth and Explain|Clinical Console Auth and Explain]]
- [[_COMMUNITY_Clinical Console Finding Cards|Clinical Console Finding Cards]]
- [[_COMMUNITY_Clinical Console Query Console|Clinical Console Query Console]]
- [[_COMMUNITY_Clinical Console Nav and Patients|Clinical Console Nav and Patients]]
- [[_COMMUNITY_Severity Warning Indicators|Severity Warning Indicators]]
- [[_COMMUNITY_Duplicated Severity Ranking Logic|Duplicated Severity Ranking Logic]]
- [[_COMMUNITY_Tenant Isolation Pattern|Tenant Isolation Pattern]]
- [[_COMMUNITY_JWT Token Storage Helpers|JWT Token Storage Helpers]]
- [[_COMMUNITY_Central Config Constants|Central Config Constants]]
- [[_COMMUNITY_Groq Model Fallback Rationale|Groq Model Fallback Rationale]]
- [[_COMMUNITY_RxNorm Interaction API Retirement|RxNorm Interaction API Retirement]]
- [[_COMMUNITY_getUser() Session Helper|getUser() Session Helper]]
- [[_COMMUNITY_panelHeader() UI Helper|panelHeader() UI Helper]]

## God Nodes (most connected - your core abstractions)
1. `SafetyCaseState` - 45 edges
2. `Severity` - 45 edges
3. `SafetyCase` - 43 edges
4. `DispensingStatus` - 38 edges
5. `ReviewStatus` - 37 edges
6. `PrescriberDecision` - 35 edges
7. `Finding` - 33 edges
8. `Intervention` - 30 edges
9. `PatientCommunication` - 30 edges
10. `PrescriberResponse` - 29 edges

## Surprising Connections (you probably didn't know these)
- `clean_text()` --semantically_similar_to--> `_normalize (salt-suffix stripping)`  [INFERRED] [semantically similar]
  ddi_rag/data_preprocessing.py → C:/Users/C V REDDY/Downloads/ddi_rag/ddi_rag/drug_categorization.py
- `fda_sync.py disabled sync module` --semantically_similar_to--> `init_lookups()`  [INFERRED] [semantically similar]
  C:/Users/C V REDDY/Downloads/ddi_rag/ddi_rag/fda_sync.py → ddi_rag/prescription_parsing.py
- `/api/self-check endpoint` --conceptually_related_to--> `evaluate_case()`  [INFERRED]
  ddi_rag/static/patient/index.html → ddi_rag/services/clinical_rules.py
- `/api/explain endpoint` --conceptually_related_to--> `explain_finding()`  [INFERRED]
  ddi_rag/static/patient/index.html → ddi_rag/services/evidence.py
- `/v1/findings/{id}/explain endpoint` --conceptually_related_to--> `explain_finding()`  [INFERRED]
  ddi_rag/static/clinical/index.html → ddi_rag/services/evidence.py

## Import Cycles
- 1-file cycle: `ddi_rag/models.py -> ddi_rag/models.py`
- 1-file cycle: `ddi_rag/routes_clinical.py -> ddi_rag/routes_clinical.py`

## Hyperedges (group relationships)
- **Tenant Isolation via Organization-Scoped 404 Pattern** — ddi_rag_app__authorized_case_or_error, ddi_rag_routes_clinical__authorized_case, ddi_rag_models_safetycase [INFERRED 0.85]
- **Registration/Login Authentication Flow** — ddi_rag_auth_configure_jwt, ddi_rag_app_register, ddi_rag_app_login, ddi_rag_auth_register_user, ddi_rag_auth_authenticate_user [EXTRACTED 1.00]
- **LLM-Explains-Never-Determines-Severity Governance Boundary** — ddi_rag_routes_public_self_check, ddi_rag_routes_public_explain_self_check_finding, ddi_rag_routes_clinical_explain_case_finding [INFERRED 0.85]
- **Safety case analysis, review, and audit-trail workflow** — services_professional_workflow_run_case_analysis, services_clinical_rules_evaluate_case, services_safety_case_transition_case, services_audit_record_audit_event [INFERRED 0.85]
- **CRAG evidence retrieval and constrained explanation pipeline** — services_rag_pipeline_retrieve_chunks, services_evidence_store_search, services_evidence_retrieve_supporting_evidence, services_evidence_explain_finding [INFERRED 0.85]
- **Shared Finding contract (type/severity/clinical_effect) produced and rendered** — services_clinical_rules_evaluate_ddi_pairs, clinical_index_findingcard, patient_index_findingcard [INFERRED 0.75]

## Communities (27 total, 6 thin omitted)

### Community 0 - "Domain Model Tables"
Cohesion: 0.21
Nodes (70): Base, ClinicalProfileSnapshot, str, bool, DeliveryChannel, DispensingStatus, FindingType, PrescriberDecision (+62 more)

### Community 1 - "Safety Case Intervention Routes"
Cohesion: 0.08
Nodes (59): AuditEvent, /v1/safety-cases REST resource, assess_case_findings(), _authorized_case_or_error(), create_intervention_route(), Return (case, None) if case_id exists and belongs to the caller's     organizati, respond_to_intervention(), safety_case_timeline() (+51 more)

### Community 2 - "MCP Server Interface"
Cohesion: 0.08
Nodes (41): list_drug_warnings(), str, query_drug_interactions(), mcp_server.py — DrugSafe AI MCP Server  Exposes DrugSafe AI capabilities as MC, Check for known interactions between two specific drugs.      Searches the DDI, Query FDA label data and DDI pair database for drug interaction information., DataFrame, float (+33 more)

### Community 3 - "Aho-Corasick Drug Matcher"
Cohesion: 0.07
Nodes (34): AhoCorasick, AhoCorasick.find_all, is_word_boundary_match(), _is_word_char(), Match, bool, int, str (+26 more)

### Community 4 - "Flask App Core Routes"
Cohesion: 0.07
Nodes (31): Batched-query-count optimization (rationale), clinical_app(), handle_exception(), list_organizations(), login(), _max_severity(), app.py Flask API module, my_cases() (+23 more)

### Community 5 - "Guest Self-Check Routes"
Cohesion: 0.09
Nodes (32): _resolve_and_evaluate, _needs_doctor_visit(), _overall_severity(), _patient_guidance(), bool, int, str, routes_public.py — Unauthenticated "guest self-check" endpoints.  Lets a patient (+24 more)

### Community 6 - "openFDA Data Preprocessing"
Cohesion: 0.09
Nodes (24): clean_text(), load_and_clean_data(), DataFrame, str, data_preprocessing.py — Load and clean the openFDA DDI dataset.  Usage:     f, Apply the same cleaning pipeline used on the CSV dataset to a single     text s, Load the clean_ddi_dataset CSV, apply all text normalization steps,     derive, _normalize (salt-suffix stripping) (+16 more)

### Community 7 - "LLM Faithfulness Eval Helpers"
Cohesion: 0.11
Nodes (22): int, str, bool, float, str, score_faithfulness is a v1 lexical-overlap placeholder, not a validated measure, Patient-supplied notes treated as unverified background, never allowed to change a fixed finding, _evidence_hash (+14 more)

### Community 8 - "Deterministic Clinical Rule Engine"
Cohesion: 0.15
Nodes (21): str, Batched IN-query pair lookup to avoid quadratic per-pair queries, In-memory pair_key set for 160K-row DDInter ingest dedup, DRAFT rule produces UNKNOWN/PENDING finding, never a trusted severity, _pair_key, _unique_unordered_pairs, evaluate_case(), evaluate_ddi_pairs() (+13 more)

### Community 9 - "pgvector Evidence Store"
Cohesion: 0.17
Nodes (20): DataFrame, float, int, str, Evidence store kept on separate psycopg2 connection from SQLAlchemy Base, HNSW chosen over IVFFlat for evidence index, _get_connection, _to_pgvector_literal (+12 more)

### Community 10 - "Patient Portal Self-Check UI"
Cohesion: 0.16
Nodes (16): /api/self-check endpoint, checkingFieldHtml, getUser, medChipsHtml, overallBanner, renderChecker, renderHome, renderResults (+8 more)

### Community 11 - "Clinical Regression Eval Metrics"
Cohesion: 0.17
Nodes (12): float, Severity, Report sensitivity/false-negative rate separately per severity; aggregate accuracy is insufficient, _finding_key, aggregate(), _finding_key(), services/eval_metrics.py — Clinical regression evaluation metrics (architecture, Identity used to match a gold-expected finding to an actual one —     by rule ty (+4 more)

### Community 12 - "Clinical Console Case Actions"
Cohesion: 0.33
Nodes (10): api, fmtDate, interventionCard, renderCaseDetail, renderClose, renderCommunicate, renderDispense, renderEscalation (+2 more)

### Community 13 - "Clinical Console Auth and Explain"
Cohesion: 0.22
Nodes (10): esc, /api/explain endpoint, api, caseCard, mdLite, renderAuth, renderDashboard, runExplain (+2 more)

### Community 14 - "Clinical Console Finding Cards"
Cohesion: 0.25
Nodes (9): explainBlock, findingCard, ledBadge, recentCases, renderFindings, renderRecentList, /v1/findings/{id}/explain endpoint, findingCard (+1 more)

### Community 15 - "Clinical Console Query Console"
Cohesion: 0.25
Nodes (9): log, queryResultCard, renderAuth, renderQueryConsole, renderShell, setToken, setUser, /api/query endpoint (+1 more)

### Community 16 - "Clinical Console Nav and Patients"
Cohesion: 0.28
Nodes (9): nav, parseList, pushRecentCase, queueRow, renderNewCase, renderPatients, renderQueue, renderView (+1 more)

### Community 17 - "Severity Warning Indicators"
Cohesion: 0.50
Nodes (4): interactionWarningBanner, warningIcon, worstSeverity, findingUrgency

### Community 18 - "Duplicated Severity Ranking Logic"
Cohesion: 0.50
Nodes (4): _max_severity helper, _SEVERITY_RANK dict (app.py), _overall_severity, _SEVERITY_RANK dict (routes_public.py)

### Community 19 - "Tenant Isolation Pattern"
Cohesion: 1.00
Nodes (3): _authorized_case_or_error, Tenant isolation via 404-not-403 (rationale), _authorized_case

## Knowledge Gaps
- **45 isolated node(s):** `int`, `DataFrame`, `int`, `bool`, `int` (+40 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `safe_str()` connect `Safety Case Intervention Routes` to `MCP Server Interface`, `Aho-Corasick Drug Matcher`, `Flask App Core Routes`, `LLM Faithfulness Eval Helpers`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Why does `get_session()` connect `Safety Case Intervention Routes` to `Aho-Corasick Drug Matcher`, `Flask App Core Routes`, `Guest Self-Check Routes`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `explain_finding()` connect `LLM Faithfulness Eval Helpers` to `Safety Case Intervention Routes`, `MCP Server Interface`, `Clinical Console Auth and Explain`, `Clinical Console Finding Cards`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `SafetyCaseState` (e.g. with `ClinicalProfileSnapshot` and `AuditEvent`) actually correct?**
  _`SafetyCaseState` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Severity` (e.g. with `str` and `AuditEvent`) actually correct?**
  _`Severity` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `SafetyCase` (e.g. with `ClinicalProfileSnapshot` and `str`) actually correct?**
  _`SafetyCase` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `DispensingStatus` (e.g. with `AuditEvent` and `ClinicalProfileSnapshot`) actually correct?**
  _`DispensingStatus` has 35 INFERRED edges - model-reasoned connections that need verification._