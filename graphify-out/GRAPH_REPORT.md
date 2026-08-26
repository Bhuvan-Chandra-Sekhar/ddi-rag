# Graph Report - .  (2026-08-26)

## Corpus Check
- 27 files · ~27,722 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1095 nodes · 2086 edges · 39 communities (27 shown, 12 thin omitted)
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 585 edges (avg confidence: 0.54)
- Token cost: 303,335 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Drug Name Lookup Data|Drug Name Lookup Data]]
- [[_COMMUNITY_Domain Model Tables|Domain Model Tables]]
- [[_COMMUNITY_STALE Ablation Study Script|[STALE] Ablation Study Script]]
- [[_COMMUNITY_openFDA Data Preprocessing|openFDA Data Preprocessing]]
- [[_COMMUNITY_Clinical App Medication Routes|Clinical App Medication Routes]]
- [[_COMMUNITY_STALE DDI Pair Ingest Script|[STALE] DDI Pair Ingest Script]]
- [[_COMMUNITY_RAG Pipeline Core|RAG Pipeline Core]]
- [[_COMMUNITY_Clinical Console Case Cards|Clinical Console Case Cards]]
- [[_COMMUNITY_Clinical Console Severity Badges|Clinical Console Severity Badges]]
- [[_COMMUNITY_Safety Case Intervention Routes|Safety Case Intervention Routes]]
- [[_COMMUNITY_Duplicated Severity Ranking Logic|Duplicated Severity Ranking Logic]]
- [[_COMMUNITY_pgvector Evidence Store|pgvector Evidence Store]]
- [[_COMMUNITY_Aho-Corasick Drug Matcher|Aho-Corasick Drug Matcher]]
- [[_COMMUNITY_RxNorm Medication Identity|RxNorm Medication Identity]]
- [[_COMMUNITY_Auth Login and Registration|Auth Login and Registration]]
- [[_COMMUNITY_Drug Route Categorization|Drug Route Categorization]]
- [[_COMMUNITY_Clinical Regression Eval Metrics|Clinical Regression Eval Metrics]]
- [[_COMMUNITY_STALE Visualization Script|[STALE] Visualization Script]]
- [[_COMMUNITY_Grounded Finding Explanation|Grounded Finding Explanation]]
- [[_COMMUNITY_Database Engine Setup|Database Engine Setup]]
- [[_COMMUNITY_STALE Pharmacy Search Script|[STALE] Pharmacy Search Script]]
- [[_COMMUNITY_LLM Faithfulness Scoring|LLM Faithfulness Scoring]]
- [[_COMMUNITY_openFDA JSON Ingest (src)|openFDA JSON Ingest (src/)]]
- [[_COMMUNITY_Flask App Bootstrap|Flask App Bootstrap]]
- [[_COMMUNITY_Prescription Text Parsing|Prescription Text Parsing]]
- [[_COMMUNITY_Patient Safety Case Queries|Patient Safety Case Queries]]
- [[_COMMUNITY_STALE Run Entry Point Script|[STALE] Run Entry Point Script]]
- [[_COMMUNITY_Central Config Constants|Central Config Constants]]
- [[_COMMUNITY_Groq Model Fallback Rationale|Groq Model Fallback Rationale]]
- [[_COMMUNITY_STALE Run Visualization Script|[STALE] Run Visualization Script]]
- [[_COMMUNITY_esc() HTML Escaping Helper|esc() HTML Escaping Helper]]
- [[_COMMUNITY_fmtDate() Formatting Helper|fmtDate() Formatting Helper]]
- [[_COMMUNITY_getUser() Session Helper|getUser() Session Helper]]
- [[_COMMUNITY_parseList() Input Parsing Helper|parseList() Input Parsing Helper]]
- [[_COMMUNITY_JWT Token Storage (Clinical)|JWT Token Storage (Clinical)]]
- [[_COMMUNITY_JWT Token Storage (Patient)|JWT Token Storage (Patient)]]
- [[_COMMUNITY_Content-Word Tokenizer Helper|Content-Word Tokenizer Helper]]
- [[_COMMUNITY_RxNorm RXCUI Lookup Helper|RxNorm RXCUI Lookup Helper]]

## God Nodes (most connected - your core abstractions)
1. `brand_to_generic` - 490 edges
2. `SafetyCaseState` - 45 edges
3. `Severity` - 45 edges
4. `DispensingStatus` - 38 edges
5. `ReviewStatus` - 37 edges
6. `PrescriberDecision` - 35 edges
7. `Finding` - 33 edges
8. `Intervention` - 30 edges
9. `PatientCommunication` - 30 edges
10. `PrescriberResponse` - 29 edges

## Surprising Connections (you probably didn't know these)
- `findingCard` --semantically_similar_to--> `explain_finding()`  [INFERRED] [semantically similar]
  static/clinical/index.html → ddi_rag/services/evidence.py
- `runExplain` --semantically_similar_to--> `explain_finding()`  [INFERRED] [semantically similar]
  static/patient/index.html → ddi_rag/services/evidence.py
- `renderQueryConsole` --shares_data_with--> `answer_ddi()`  [INFERRED]
  static/clinical/index.html → ddi_rag/services/rag_pipeline.py
- `toggleDrugInfo` --shares_data_with--> `answer_ddi()`  [INFERRED]
  static/patient/index.html → ddi_rag/services/rag_pipeline.py
- `User` --uses--> `User`  [INFERRED]
  ddi_rag/auth.py → ddi_rag/models.py

## Import Cycles
- 1-file cycle: `ddi_rag/models.py -> ddi_rag/models.py`
- 1-file cycle: `ddi_rag/routes_clinical.py -> ddi_rag/routes_clinical.py`

## Hyperedges (group relationships)
- **Tenant Isolation via Organization-Scoped 404 Pattern** — ddi_rag_app__authorized_case_or_error, ddi_rag_routes_clinical__authorized_case, ddi_rag_models_safetycase [INFERRED 0.85]
- **LLM-Explains-Never-Determines-Severity Governance Boundary** — ddi_rag_routes_public_self_check, ddi_rag_routes_public_explain_self_check_finding, ddi_rag_routes_clinical_explain_case_finding [INFERRED 0.85]
- **Registration/Login Authentication Flow** — ddi_rag_auth_configure_jwt, ddi_rag_app_register, ddi_rag_app_login, ddi_rag_auth_register_user, ddi_rag_auth_authenticate_user [EXTRACTED 1.00]
- **CRAG Retrieval Pipeline (retrieve/grade/correct/generate)** — services_rag_pipeline_retrieve_chunks, services_rag_pipeline__grade_retrieval, services_rag_pipeline__rewrite_query, services_rag_pipeline__crag_retrieve, services_rag_pipeline__cached_answer [EXTRACTED 1.00]
- **Deterministic clinical safety rule engine** — services_clinical_rules_evaluate_duplicate_ingredients, services_clinical_rules_evaluate_drug_allergy, services_clinical_rules_evaluate_ddi_pairs, services_clinical_rules_evaluate_case [EXTRACTED 1.00]
- **SafetyCase state-machine audit lifecycle** — services_safety_case_transition_case, services_safety_case_create_case, services_professional_workflow_run_case_analysis, services_professional_workflow_assess_findings_and_route, services_professional_workflow_record_prescriber_response, services_professional_workflow_resolve_escalation, services_audit_record_audit_event [INFERRED 0.85]

## Communities (39 total, 12 thin omitted)

### Community 0 - "Drug Name Lookup Data"
Cohesion: 0.00
Nodes (490): brand_to_generic, abacavir sulfate, abiraterone acetate, accentrate pnv, acetaminophen and codeine phosphate, acetylcysteine, acyclovir, adapalene (+482 more)

### Community 1 - "Domain Model Tables"
Cohesion: 0.13
Nodes (93): AuditEvent, Base, ClinicalProfileSnapshot, int, str, bool, DeliveryChannel, DispensingStatus (+85 more)

### Community 2 - "[STALE] Ablation Study Script"
Cohesion: 0.05
Nodes (68): c1_vanilla_rag(), c2_normalisation(), c3_crag_no_rewrite(), c4_full_crag(), hit_at_5(), normalise(), peak_score(), DataFrame (+60 more)

### Community 3 - "openFDA Data Preprocessing"
Cohesion: 0.09
Nodes (30): trigger_sync(), clean_text(), load_and_clean_data(), DataFrame, str, data_preprocessing.py — Load and clean the openFDA DDI dataset.  Usage:     from, Apply the same cleaning pipeline used on the CSV dataset to a single     text st, Load the clean_ddi_dataset CSV, apply all text normalization steps,     derive f (+22 more)

### Community 4 - "Clinical App Medication Routes"
Cohesion: 0.11
Nodes (27): add_medication(), _build_history_warnings(), clinical_app(), delete_medication(), _format_history_context(), get_history(), handle_exception(), _json() (+19 more)

### Community 5 - "[STALE] DDI Pair Ingest Script"
Cohesion: 0.11
Nodes (29): build_pair_records(), _clean_name(), ingest_pairs(), load_and_clean_pairs(), DataFrame, Path, str, ddi_pair_ingest.py — Clean and index the DDI pairs dataset into ChromaDB.  Reads (+21 more)

### Community 6 - "RAG Pipeline Core"
Cohesion: 0.13
Nodes (30): DataFrame, float, int, str, _cached_answer, _call_groq_api, _chunk_text, _crag_retrieve (+22 more)

### Community 7 - "Clinical Console Case Cards"
Cohesion: 0.14
Nodes (29): api, explainBlock, findingCard, interventionCard, log, nav, panelHeader, pushRecentCase (+21 more)

### Community 8 - "Clinical Console Severity Badges"
Cohesion: 0.10
Nodes (29): interactionWarningBanner, ledBadge, queueRow, warningIcon, worstSeverity, api, caseCard, checkingFieldHtml (+21 more)

### Community 9 - "Safety Case Intervention Routes"
Cohesion: 0.19
Nodes (26): assess_case_findings(), _authorized_case_or_error(), create_intervention_route(), Return (case, None) if case_id exists and belongs to the caller's     organizati, respond_to_intervention(), safety_case_timeline(), Tenant isolation via 404-not-403 (rationale), get_session() (+18 more)

### Community 10 - "Duplicated Severity Ranking Logic"
Cohesion: 0.14
Nodes (21): _max_severity helper, _SEVERITY_RANK dict (app.py), _SEVERITY_RANK dict (routes_public.py), _clean_str_list(), explain_self_check_finding(), _needs_doctor_visit(), _overall_severity(), _patient_guidance() (+13 more)

### Community 11 - "pgvector Evidence Store"
Cohesion: 0.19
Nodes (18): DataFrame, float, int, str, _get_connection, _to_pgvector_literal, embed_texts(), _get_connection() (+10 more)

### Community 12 - "Aho-Corasick Drug Matcher"
Cohesion: 0.18
Nodes (12): is_word_boundary_match(), _is_word_char(), Match, bool, int, str, aho_corasick.py — Multi-pattern string matching in a single text pass.  Used by, True if text[start:end] is a whole word in `text` — no word     character immedi (+4 more)

### Community 13 - "RxNorm Medication Identity"
Cohesion: 0.19
Nodes (15): str, _fetch_ingredients, _lookup_approximate_rxcui, _lookup_exact_rxcui, clear_caches(), _fetch_ingredients(), get_or_create_medication(), _lookup_approximate_rxcui() (+7 more)

### Community 14 - "Auth Login and Registration"
Cohesion: 0.20
Nodes (14): login(), register(), authenticate_user(), get_current_user(), hash_password(), init_jwt(), str, auth.py — JWT authentication helpers and Flask-JWT-Extended setup.  Provides: (+6 more)

### Community 15 - "Drug Route Categorization"
Cohesion: 0.18
Nodes (13): apply_product_type(), apply_route_column(), categorize_drug(), lookup_route(), _normalize(), DataFrame, str, drug_categorization.py — Drug-name → route and product-type mapping.  Public API (+5 more)

### Community 16 - "Clinical Regression Eval Metrics"
Cohesion: 0.19
Nodes (11): float, Severity, _finding_key, aggregate(), _finding_key(), services/eval_metrics.py — Clinical regression evaluation metrics (architecture, Identity used to match a gold-expected finding to an actual one —     by rule ty, Compare one gold case's expected findings against the rule engine's     actual f (+3 more)

### Community 17 - "[STALE] Visualization Script"
Cohesion: 0.16
Nodes (14): clean_text(), get_ngrams_sklearn(), get_tfidf_top_terms(), int, str, visualization.py — Plotting utilities for the DDI EDA notebook.  Import this mod, Return the top-k n-gram labels and their counts from a text Series.      Returns, Return the top-k TF-IDF-scored terms and their mean scores from a Series.      R (+6 more)

### Community 18 - "Grounded Finding Explanation"
Cohesion: 0.25
Nodes (10): int, str, _evidence_hash, _evidence_hash(), explain_finding(), services/evidence.py — Evidence retrieval + constrained explanation (architectur, Thin wrapper over rag_pipeline.retrieve_chunks — the evidence-service     bounda, Stable hash over the frozen finding + the exact evidence passages used,     so a (+2 more)

### Community 19 - "Database Engine Setup"
Cohesion: 0.27
Nodes (9): _get_engine(), _get_session_factory(), init_db(), ping_db(), bool, database.py — SQLAlchemy engine and session factory.  Usage:     from database i, Create all tables. Call once at startup, before serving requests., Create all tables in the database (safe to call multiple times). (+1 more)

### Community 20 - "[STALE] Pharmacy Search Script"
Cohesion: 0.31
Nodes (9): find_pharmacies(), _format_distance(), _haversine(), float, int, str, pharmacy_search.py — Find nearby pharmacies using OpenStreetMap Overpass API.  F, Return distance in km between two (lat, lon) pairs. (+1 more)

### Community 21 - "LLM Faithfulness Scoring"
Cohesion: 0.24
Nodes (9): bool, float, str, citations_are_grounded(), _content_words(), services/llm_eval.py — LLM safety eval helpers (architecture doc section 13 "LLM, Fraction of the explanation's distinct content words that also appear     in the, Every citation returned must be one of the passages actually     retrieved for t (+1 more)

### Community 22 - "openFDA JSON Ingest (src/)"
Cohesion: 0.25
Nodes (7): build_csv(), _first(), _parse_txt(), Path, Read every .txt file in PROCESSED_FOLDER and write clean_ddi_dataset.csv.      E, Return the first element of a list, or None., Read a processed drug .txt file and return a CSV row dict.      Expected format:

### Community 23 - "Flask App Bootstrap"
Cohesion: 0.25
Nodes (8): app.py Flask API module, configure_jwt(), Wire flask-jwt-extended into the app with a validated secret key., fda_sync.py disabled sync module, mcp_server.py MCP server module, init_lookups(), Build the brand→generic map and the Aho-Corasick matcher from every     distinct, routes_clinical.py clinical console module

### Community 24 - "Prescription Text Parsing"
Cohesion: 0.33
Nodes (5): AhoCorasick.find_all, parse_prescription(), str, prescription_parsing.py — Detect known drug names in free-text prescription inpu, Longest-match extraction of recognised drug names from prescription     text. Br

### Community 25 - "Patient Safety Case Queries"
Cohesion: 0.33
Nodes (6): Batched-query-count optimization (rationale), _max_severity(), my_cases(), Batched to a fixed number of queries regardless of queue size — this     used to, A patient's own safety cases, scoped strictly to the Patient record     linked t, safety_case_queue()

## Knowledge Gaps
- **542 isolated node(s):** `DataFrame`, `bool`, `str`, `amoxicillin and clavulanate potassium`, `truvada` (+537 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `query_api()` connect `Clinical App Medication Routes` to `Domain Model Tables`, `[STALE] Ablation Study Script`, `RAG Pipeline Core`, `Safety Case Intervention Routes`, `Prescription Text Parsing`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `run_sync()` connect `openFDA Data Preprocessing` to `[STALE] Ablation Study Script`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `SafetyCaseState` (e.g. with `ClinicalProfileSnapshot` and `AuditEvent`) actually correct?**
  _`SafetyCaseState` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Severity` (e.g. with `str` and `AuditEvent`) actually correct?**
  _`Severity` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `DispensingStatus` (e.g. with `AuditEvent` and `ClinicalProfileSnapshot`) actually correct?**
  _`DispensingStatus` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `ReviewStatus` (e.g. with `str` and `AuditEvent`) actually correct?**
  _`ReviewStatus` has 34 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ablation_study.py — DrugSafe AI Component Ablation Study ======================`, `Replace brand names with INN generics (longest-match, case-insensitive).`, `1 if any chunk scores ≥ HIT_THRESH, else 0.` to the rest of the system?**
  _695 weakly-connected nodes found - possible documentation gaps or missing edges._