# Graph Report - .  (2026-08-02)

## Corpus Check
- Corpus is ~41,471 words - fits in a single context window. You may not need a graph.

## Summary
- 727 nodes · 874 edges · 15 communities (12 shown, 3 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 49 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_RAG Pipeline Core|RAG Pipeline Core]]
- [[_COMMUNITY_Flask API Routes|Flask API Routes]]
- [[_COMMUNITY_Data Preprocessing|Data Preprocessing]]
- [[_COMMUNITY_Drug Categorization|Drug Categorization]]
- [[_COMMUNITY_Auth & JWT|Auth & JWT]]
- [[_COMMUNITY_Database Models|Database Models]]
- [[_COMMUNITY_FDA Sync Scheduler|FDA Sync Scheduler]]
- [[_COMMUNITY_Vector Store Clients|Vector Store Clients]]
- [[_COMMUNITY_MCP Server|MCP Server]]
- [[_COMMUNITY_Ingest Pipeline|Ingest Pipeline]]
- [[_COMMUNITY_Config Constants|Config Constants]]
- [[_COMMUNITY_Pharmacy Search|Pharmacy Search]]
- [[_COMMUNITY_Ablation Study|Ablation Study]]
- [[_COMMUNITY_Visualization|Visualization]]
- [[_COMMUNITY_Embedding & Chunking|Embedding & Chunking]]

## God Nodes (most connected - your core abstractions)
1. `brand_to_generic` - 499 edges
2. `_json()` - 13 edges
3. `safe_str()` - 13 edges
4. `retrieve_chunks()` - 13 edges
5. `get_db()` - 12 edges
6. `run_sync()` - 11 edges
7. `query_api()` - 10 edges
8. `str` - 10 edges
9. `DataFrame` - 9 edges
10. `c4_full_crag()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `c1_vanilla_rag()` --calls--> `retrieve_chunks()`  [INFERRED]
  ddi_rag/ablation_study.py → ddi_rag/rag_pipeline.py
- `c2_normalisation()` --calls--> `retrieve_chunks()`  [INFERRED]
  ddi_rag/ablation_study.py → ddi_rag/rag_pipeline.py
- `c3_crag_no_rewrite()` --calls--> `_grade_retrieval()`  [INFERRED]
  ddi_rag/ablation_study.py → ddi_rag/rag_pipeline.py
- `c3_crag_no_rewrite()` --calls--> `retrieve_chunks()`  [INFERRED]
  ddi_rag/ablation_study.py → ddi_rag/rag_pipeline.py
- `c4_full_crag()` --calls--> `_grade_retrieval()`  [INFERRED]
  ddi_rag/ablation_study.py → ddi_rag/rag_pipeline.py

## Import Cycles
- None detected.

## Communities (15 total, 3 thin omitted)

### Community 0 - "RAG Pipeline Core"
Cohesion: 0.00
Nodes (499): brand_to_generic, abacavir sulfate, abiraterone acetate, accentrate pnv, acetaminophen and codeine phosphate, acetylcysteine, acyclovir, adapalene (+491 more)

### Community 1 - "Flask API Routes"
Cohesion: 0.08
Nodes (42): Base, add_medication(), _build_history_warnings(), delete_medication(), _format_history_context(), get_history(), handle_exception(), _json() (+34 more)

### Community 2 - "Data Preprocessing"
Cohesion: 0.10
Nodes (34): answer_ddi(), answer_general(), build_chroma_index(), build_chunk_df(), _cached_answer(), _call_groq_api(), _chunk_text(), _crag_retrieve() (+26 more)

### Community 3 - "Drug Categorization"
Cohesion: 0.17
Nodes (23): c1_vanilla_rag(), c2_normalisation(), c3_crag_no_rewrite(), c4_full_crag(), hit_at_5(), normalise(), peak_score(), DataFrame (+15 more)

### Community 4 - "Auth & JWT"
Cohesion: 0.14
Nodes (19): _ensure_rag(), find_nearby_pharmacies(), list_drug_warnings(), float, str, query_drug_interactions(), mcp_server.py — DrugSafe AI MCP Server  Exposes DrugSafe AI capabilities as MCP, Check for known interactions between two specific drugs.      Searches the DDI p (+11 more)

### Community 5 - "Database Models"
Cohesion: 0.15
Nodes (19): _delete_drug_chunks(), _fetch_page(), _load_last_sync_date(), _parse_label(), bool, int, str, fda_sync.py — Incremental sync from openFDA API into ChromaDB.  How it works: (+11 more)

### Community 6 - "FDA Sync Scheduler"
Cohesion: 0.16
Nodes (14): clean_text(), get_ngrams_sklearn(), get_tfidf_top_terms(), int, str, visualization.py — Plotting utilities for the DDI EDA notebook.  Import this mod, Return the top-k n-gram labels and their counts from a text Series.      Returns, Return the top-k TF-IDF-scored terms and their mean scores from a Series.      R (+6 more)

### Community 7 - "Vector Store Clients"
Cohesion: 0.22
Nodes (12): apply_product_type(), apply_route_column(), categorize_drug(), lookup_route(), _normalize(), DataFrame, str, drug_categorization.py — Drug-name → route and product-type mapping.  Public API (+4 more)

### Community 8 - "MCP Server"
Cohesion: 0.25
Nodes (10): build_pair_records(), _clean_name(), ingest_pairs(), load_and_clean_pairs(), DataFrame, Path, str, ddi_pair_ingest.py — Clean and index the DDI pairs dataset into ChromaDB.  Reads (+2 more)

### Community 9 - "Ingest Pipeline"
Cohesion: 0.31
Nodes (8): _get_engine(), _get_session_factory(), init_db(), ping_db(), bool, database.py — SQLAlchemy engine and session factory.  Usage:     from database i, Create all tables in the database (safe to call multiple times)., Return True if the database is reachable.

### Community 10 - "Config Constants"
Cohesion: 0.25
Nodes (7): build_csv(), _first(), _parse_txt(), Path, Read every .txt file in PROCESSED_FOLDER and write clean_ddi_dataset.csv.      E, Return the first element of a list, or None., Read a processed drug .txt file and return a CSV row dict.      Expected format:

### Community 11 - "Pharmacy Search"
Cohesion: 0.32
Nodes (7): clean_text(), load_and_clean_data(), DataFrame, str, data_preprocessing.py — Load and clean the openFDA DDI dataset.  Usage:     from, Apply the same cleaning pipeline used on the CSV dataset to a single     text st, Load the clean_ddi_dataset CSV, apply all text normalization steps,     derive f

## Knowledge Gaps
- **507 isolated node(s):** `DataFrame`, `bool`, `str`, `amoxicillin and clavulanate potassium`, `truvada` (+502 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `safe_str()` connect `Flask API Routes` to `Data Preprocessing`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Why does `retrieve_chunks()` connect `Data Preprocessing` to `Flask API Routes`, `Drug Categorization`, `Auth & JWT`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `safe_str()` (e.g. with `add_medication()` and `handle_exception()`) actually correct?**
  _`safe_str()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `retrieve_chunks()` (e.g. with `c1_vanilla_rag()` and `c2_normalisation()`) actually correct?**
  _`retrieve_chunks()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `get_db()` (e.g. with `add_medication()` and `delete_medication()`) actually correct?**
  _`get_db()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ablation_study.py — DrugSafe AI Component Ablation Study ======================`, `Replace brand names with INN generics (longest-match, case-insensitive).`, `1 if any chunk scores ≥ HIT_THRESH, else 0.` to the rest of the system?**
  _580 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `RAG Pipeline Core` be split into smaller, more focused modules?**
  _Cohesion score 0.004 - nodes in this community are weakly interconnected._