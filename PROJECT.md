# MedSafe Interaction Portal — Project Documentation

> **Status:** Active Development  
> **Last Updated:** 2026-05-01  
> **CTO Owner:** C V Reddy  
> **Codename:** `ddi_rag` (Drug-Drug Interaction RAG System)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Frontend — Design System](#3-frontend--design-system)
4. [Screen Inventory](#4-screen-inventory)
5. [Backend — Core Modules](#5-backend--core-modules)
6. [API Reference](#6-api-reference)
7. [Data Sources & Pipeline](#7-data-sources--pipeline)
8. [Authentication & Security](#8-authentication--security)
9. [Infrastructure & Deployment](#9-infrastructure--deployment)
10. [CI/CD Pipeline (Planned)](#10-cicd-pipeline-planned)
11. [Integration Map (Frontend ↔ Backend)](#11-integration-map-frontend--backend)
12. [Future Roadmap](#12-future-roadmap)
13. [Environment Variables](#13-environment-variables)
14. [Glossary](#14-glossary)

---

## 1. Project Overview

**MedSafe Interaction Portal** (internally `ddi_rag`) is a clinical-grade, AI-powered Drug-Drug Interaction (DDI) checker. It combines FDA-sourced pharmaceutical data, vector search, and large language model generation to answer drug interaction questions with cited, evidence-based responses.

### Core Value Proposition

| Capability | Description |
|---|---|
| **AI-Powered DDI Lookup** | CRAG (Corrective RAG) pipeline retrieves FDA evidence and generates natural language answers |
| **930,000+ FDA Vectors** | Full label text chunked and embedded in Qdrant Cloud |
| **187,000+ DDI Pairs** | Pre-processed interaction pairs from FDA datasets |
| **Real-Time FDA Sync** | Nightly incremental sync from openFDA API |
| **Medication Management** | Personal medication list with history tracking |
| **Pharmacy Finder** | Nearest pharmacies via OpenStreetMap Overpass API |
| **Multi-Interface** | Flask Web SPA, Streamlit App, Claude Desktop MCP |

### Target Users

- **Patients** — checking safety of their current medication list
- **Pharmacists** — rapid interaction lookup with cited FDA sources
- **Physicians** — clinical decision support at point of care
- **Researchers** — structured DDI data access via API

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                  │
│                                                                      │
│   MedTrust Connect (HTML/CSS/JS)    Streamlit App    MCP Server      │
│   Flask SPA · Dark Cinematic UI     Standalone UI    Claude Desktop  │
└─────────────────────────┬────────────────────────────────────────────┘
                          │  HTTP / REST
┌─────────────────────────▼────────────────────────────────────────────┐
│                      FLASK API LAYER  (app.py)                       │
│                                                                      │
│   /api/auth/*    /api/query    /api/medications    /api/history      │
│   /api/nearby-pharmacy         /api/sync                             │
└──────────┬────────────────────────────┬─────────────────────────────┘
           │                            │
┌──────────▼──────────┐    ┌────────────▼────────────────────────────┐
│   RAG PIPELINE      │    │          DATABASE LAYER                  │
│   rag_pipeline.py   │    │                                          │
│                     │    │   PostgreSQL (prod) / SQLite (dev)       │
│   1. Embed query    │    │   SQLAlchemy ORM                         │
│   2. Retrieve       │    │                                          │
│   3. CRAG Grade     │    │   Models:                                │
│   4. Correct        │    │   · User (JWT auth, bcrypt)              │
│   5. Generate       │    │   · Medication (active med list)         │
└──────────┬──────────┘    │   · QueryHistory (JSON results)          │
           │               └─────────────────────────────────────────┘
┌──────────▼──────────┐
│   VECTOR STORES     │
│                     │
│   Qdrant Cloud      │  ← 930,000 FDA label chunks (production)
│   ChromaDB (local)  │  ← 187,000 DDI pairs (dev/ingest)
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   LLM GENERATION    │
│                     │
│   Groq API          │  ← Llama 3.1 8B Instant (512 token output)
│   (llama-3.1-8b)   │
└─────────────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| API Framework | Flask + flask-jwt-extended | Latest |
| Vector DB (prod) | Qdrant Cloud | Latest |
| Vector DB (dev) | ChromaDB | Latest |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 384-dim |
| LLM | Groq API — Llama 3.1 8B | Instant |
| Database | PostgreSQL (prod) / SQLite (dev) | PG 15 |
| ORM | SQLAlchemy | Latest |
| Auth | JWT + bcrypt (cost=12) | Latest |
| Scheduler | APScheduler | Latest |
| Containerization | Docker + docker-compose | Latest |
| Tunnel | Cloudflare cloudflared | Auto |
| Frontend | HTML + Tailwind CSS + Material Symbols | CDN |
| Design Tool | Google Stitch | Cloud |

---

## 3. Frontend — Design System

**Design System Name:** `Clinical Clarity`  
**Stitch Project:** `MedSafe Interaction Portal`  
**Project ID:** `18296921636950024011`

### Design Philosophy

> *"Controlled Support"* — feels both high-tech and deeply human. Clinical Minimalism with Corporate Modernism. Reduces cognitive load while instilling confidence.

### Color Palette

| Role | Token | Hex | Usage |
|---|---|---|---|
| Primary | `primary` | `#00355F` | Headers, primary buttons, branding |
| Primary Container | `primary-container` | `#0F4C81` | Cards, backgrounds |
| Primary Fixed Dim | `primary-fixed-dim` | `#A0C9FF` | Accent text, icons |
| Secondary | `secondary` | `#006C50` | Health-positive actions |
| Secondary Container | `secondary-container` | `#93F2CD` | Confirmation states |
| Background | `background` | `#F9F9FF` | Page background |
| Surface | `surface` | `#F9F9FF` | Card surfaces |
| Error | `error` | `#BA1A1A` | Errors, warnings |

**Drug Interaction Status Colors:**

| Status | Color | Usage |
|---|---|---|
| ✅ Safe | High-contrast Green | No known interactions |
| ⚠️ Caution | Amber Yellow | Minor / potential interactions |
| 🔴 Warning | Burnt Orange | Dangerous interactions (high visibility) |

### Typography

| Style | Font | Size | Weight | Use |
|---|---|---|---|---|
| `headline-xl` | Public Sans | 40px / 48px lh | 700 | Hero headlines |
| `headline-lg` | Public Sans | 32px / 40px lh | 600 | Section titles |
| `headline-md` | Public Sans | 24px / 32px lh | 600 | Card headers |
| `body-lg` | Public Sans | 18px / 28px lh | 400 | Primary body |
| `body-md` | Public Sans | 16px / 24px lh | 400 | Secondary body |
| `label-bold` | Manrope | 14px / 20px lh | 700 | Buttons, badges |
| `label-sm` | Manrope | 12px / 16px lh | 500 | Captions, tags |

### Spacing Scale (8px rhythm)

| Token | Value | Use |
|---|---|---|
| `xs` | 4px | Micro gaps |
| `sm` | 8px | Icon-to-label gaps |
| `md` | 16px | Internal component padding |
| `lg` | 24px | Between related elements |
| `gutter` | 24px | Column gutters |
| `xl` | 40px | Between sections |
| `margin` | 32px | Page horizontal safe area |

### Shape Language

| Element | Radius |
|---|---|
| Primary Buttons | 4px (Soft) |
| Form Inputs | 4px (Soft) |
| Cards | 4px (Soft) |
| Map Containers | 8px (Large) |
| Status Pills | 9999px (Full) |

### Elevation System

| Level | Treatment |
|---|---|
| 0 — Base | Light gray / white background |
| 1 — Cards | White + 1px soft border (#E2E8F0) |
| 2 — Active/Hover | Ambient shadow: `0px 4px 12px rgba(15,76,129,0.08)` |
| 3 — Modals | 20% opacity backdrop blur |

---

## 4. Screen Inventory

All screens live in Stitch project `18296921636950024011`.

| # | Screen Title | Screen ID | Status | Route |
|---|---|---|---|---|
| 1 | Primary Secure Entrance | `d6995eac831a4c3bb188cd6911d4418a` | ✅ Active | `GET /` |
| 2 | Customer Login (Updated) | `ace0a2573e0b4d079c825a2ad89aef33` | ✅ Active | `GET /login` |
| 3 | Home & Interaction Tool (Updated) | `e8de9355f24d4b9a929bf78c2e800a88` | ✅ Active | `GET /app` |
| 4 | Redesigned Home & Interaction Hero | `943931cb5f2849a48d9ba385c8487f69` | ✅ Active | `GET /` (alt) |
| 5 | Medication Search State | `0a1a4d7ac28442bfa61cd5e1375ca3bb` | ✅ Active | `GET /app#search` |
| 6 | AI Analysis State | `0e7c359fb4f04936a9e3dd175ef3d2ff` | ✅ Active | `GET /app#analyzing` |
| 7 | Interaction Results (Updated) | `c940f2bdd97e4455b72ea504bc420837` | ✅ Active | `GET /app#results` |
| 8 | Medication Dashboard (Updated) | `3729820987cd4f6ebfe2a78244dc19b9` | ✅ Active | `GET /medications` |
| 9 | Pharmacy Detail State | `cb98a44bc9f64c1fa121a63ac4f723a2` | ✅ Active | `GET /pharmacy` |
| 10 | MedTrust Connect — Health Manager | `875a747ef9d543d69e38c978efabeef0` | ✅ Active | `GET /dashboard` |
| 11 | Investor-Ready Landing Page | `97ffcbc43c29466992e318dcb18c76c2` | ✅ Active | `GET /about` |

### Screen Flow

```
[Primary Secure Entrance]
        │
        ▼
[Customer Login] ─────────────────────────────────────────┐
        │                                                  │
        ▼                                                  │ (Guest mode)
[Home & Interaction Tool]                                  │
        │                                                  │
        ├──→ [Medication Search State]                     │
        │            │                                     │
        │            ▼                                     │
        │    [AI Analysis State]                           │
        │            │                                     │
        │            ▼                                     │
        │    [Interaction Results]                         │
        │                                                  │
        ├──→ [Medication Dashboard] ◄──────────────────────┘
        │
        ├──→ [Pharmacy Detail State]
        │
        └──→ [Investor-Ready Landing Page]
```

---

## 5. Backend — Core Modules

### Module Map

| File | Responsibility |
|---|---|
| `config.py` | All configuration constants (single source of truth) |
| `run.py` | App entry point — startup orchestration |
| `app.py` | Flask REST API + HTML frontend routing |
| `rag_pipeline.py` | CRAG retrieval + Groq LLM generation |
| `data_preprocessing.py` | Text cleaning, chunking, normalization |
| `drug_categorization.py` | Drug → route/type fuzzy lookup |
| `database.py` | SQLAlchemy engine + context manager |
| `models.py` | ORM: User, Medication, QueryHistory |
| `auth.py` | JWT issuance + bcrypt hashing |
| `fda_sync.py` | APScheduler nightly FDA sync job |
| `ingest.py` | Raw JSON → .txt → CSV pipeline |
| `ddi_pair_ingest.py` | DDI pairs CSV → ChromaDB upsert |
| `upload_to_qdrant.py` | ChromaDB → Qdrant Cloud migration |
| `mcp_server.py` | Claude Desktop / Cursor MCP server |
| `pharmacy_search.py` | OpenStreetMap Overpass pharmacy search |
| `ablation_study.py` | CRAG threshold tuning / pipeline testing |

### CRAG Pipeline (The Brain)

```
User Query
  │
  ▼  embed (SentenceTransformer, 384-dim)
  │
  ▼  Qdrant cosine similarity search (top-K)
  │
  ▼  CRAG Grading:
       score ≥ 0.65  →  CORRECT   → use chunks as-is
       score < 0.40  →  INCORRECT → Groq rewrites query → retry
       0.40–0.65     →  AMBIGUOUS → broaden (no filter, 2× top_k)
  │
  ▼  Build context (top-3 graded chunks)
  │
  ▼  Groq Llama 3.1 generation (512 token max)
  │
  ▼  Return: answer + cited FDA sources
```

### Key Configuration (config.py)

```python
EMBEDDING_MODEL   = "all-MiniLM-L6-v2"   # 384 dimensions
CHUNK_SIZE        = 120                    # words per chunk
CHUNK_OVERLAP     = 30                     # word overlap
RELEVANCE_HIGH    = 0.65                   # accept threshold
RELEVANCE_LOW     = 0.40                   # rewrite threshold
GROQ_MODEL        = "llama-3.1-8b-instant"
GENERATION_MAX_NEW = 512                   # output tokens
JWT_ACCESS_TOKEN_MINS = 1440              # 24-hour tokens
SYNC_HOUR         = 2                      # nightly sync at 2AM UTC
DEFAULT_TOP_K     = 5
MAX_TOP_K         = 10
```

---

## 6. API Reference

### Authentication

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/auth/register` | POST | None | Create new user account |
| `/api/auth/login` | POST | None | Login, receive JWT token |

**Login Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Login Response:**
```json
{
  "access_token": "eyJ...",
  "user": { "id": "uuid", "email": "...", "full_name": "..." }
}
```

### Core Query

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/query` | POST | Optional | Drug interaction query (RAG) |

**Request:**
```json
{
  "prescription": "warfarin 5mg daily, aspirin 81mg",
  "top_k": 5
}
```

**Response:**
```json
{
  "detected_drugs": ["warfarin", "aspirin"],
  "history_warnings": [],
  "results": [
    {
      "drug": "warfarin",
      "answer": "FDA evidence indicates...",
      "sources": [
        {
          "generic_name": "warfarin",
          "section": "drug_interactions",
          "score": 0.82,
          "text": "..."
        }
      ],
      "mode": "rag"
    }
  ]
}
```

### Medication Management

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/medications` | GET | JWT | List user's active medications |
| `/api/medications` | POST | JWT | Add new medication |
| `/api/medications/<id>` | PUT | JWT | Update medication |
| `/api/medications/<id>` | DELETE | JWT | Remove medication |

### Utility

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/history` | GET | JWT | Query history (last 20-100) |
| `/api/nearby-pharmacy` | GET | None | Find pharmacies by GPS |
| `/api/sync` | POST | None | Trigger manual FDA sync |

---

## 7. Data Sources & Pipeline

### Current Sources

| Source | Data Type | Volume | Sync |
|---|---|---|---|
| openFDA API | Drug labels (full text) | 30,000+ drugs | Nightly |
| FDA DDI Pairs CSV | Pairwise interactions | 187,000+ pairs | Manual ingest |

### Data Pipeline

```
openFDA API (nightly)
    │
    ▼  ingest.py
raw JSON → per-drug .txt files
    │
    ▼  data_preprocessing.py
clean text (lowercase, strip bullets, normalize whitespace)
    │
    ▼  rag_pipeline.py: build_chunk_df()
120-word chunks, 30-word overlap
Columns: generic_name, brand_name, product_type, route, section, text
    │
    ▼  SentenceTransformer embed (batch=1024)
    │
    ▼  Qdrant Cloud upsert
930,000+ vectors @ 384 dimensions
```

### Recommended Future Data Sources (Priority Order)

| Priority | Source | Data Added | Access |
|---|---|---|---|
| 🥇 1 | **DrugBank** | Mechanism-level DDIs, CYP450 pathways | Free academic API |
| 🥇 2 | **FDA FAERS** | Real-world adverse event reports | Quarterly bulk CSV |
| 🥈 3 | **PharmGKB** | Pharmacogenomics, drug-gene relationships | Free download |
| 🥈 4 | **RxNorm API (NLM)** | Drug name normalization, canonical IDs | Free REST API |
| 🥉 5 | **SIDER 4.1** | Side effects from package inserts | Bulk CSV |
| 🥉 6 | **ChEMBL** | Drug targets, binding affinities | REST API |
| 🥉 7 | **CredibleMeds** | QT prolongation risk classification | Free (register) |

---

## 8. Authentication & Security

### JWT Flow

```
Register/Login → bcrypt verify (cost=12) → sign JWT (HS256)
               → return token (valid 1440 min = 24h)

Protected routes → @jwt_required() decorator
               → verify HMAC-SHA256 signature
               → check exp claim
               → extract user_id from sub claim
```

### Security Standards

| Standard | Implementation |
|---|---|
| Password hashing | bcrypt, cost factor 12 (2¹² rounds) |
| Token signing | HMAC-SHA256 with 256-bit secret |
| Token lifetime | 1440 minutes (1 day) |
| CORS | Enabled on Flask (flask-cors) |
| HTTPS | Enforced via Cloudflare tunnel |
| Compliance target | HIPAA-aligned (audit logs planned) |

---

## 9. Infrastructure & Deployment

### Docker Compose Services

```yaml
services:
  api:        Flask (port 5000) — main application
  postgres:   PostgreSQL 15 alpine — relational data
  redis:      Redis 7 alpine — optional query cache

volumes:
  pg_data:      PostgreSQL persistence
  chroma_data:  ChromaDB local persistence
```

### Startup Sequence

```
1.  Load & clean FDA CSV
2.  Categorize drugs (route + product type)
3.  Build 120-word chunk DataFrame
4.  Load SentenceTransformer model (~20s, cached)
5.  Init PostgreSQL (create tables if missing)
6.  Build drug name regex lookup tables
7.  Start APScheduler (nightly FDA sync at 2AM UTC)
8.  Start Flask on port 5000 (daemon thread)
9.  Start Cloudflare tunnel → print public URL
10. Main thread sleep loop (keep alive)
```

### MCP Integrations

| MCP | Purpose | Status |
|---|---|---|
| **Google Stitch** | UI design generation & management | ✅ Connected |
| **Google Drive** | Asset & document storage | ✅ Connected |
| **Vibe Prospecting** | Lead & prospecting data | ✅ Connected |
| **Orion by Gravity** | (Needs authentication) | ⚠️ Pending |
| **Google Calendar** | Scheduling | ⚠️ Needs auth |
| **Gmail** | Communications | ⚠️ Needs auth |

---

## 10. CI/CD Pipeline (Planned)

### Target Architecture

```
Developer Push
      │
      ▼
GitHub Actions — Trigger on: push to main, PRs
      │
      ├──[1. LINT & TYPE CHECK]
      │       flake8, mypy, black --check
      │
      ├──[2. UNIT TESTS]
      │       pytest tests/ --cov=ddi_rag
      │       Test containers: PostgreSQL, ChromaDB
      │
      ├──[3. INTEGRATION TESTS]
      │       RAG pipeline smoke test
      │       API endpoint tests (httpx)
      │       Qdrant connection test
      │
      ├──[4. DOCKER BUILD]
      │       docker build -t medsafe:sha-{GITHUB_SHA} .
      │       docker push registry/medsafe:sha-{GITHUB_SHA}
      │
      ├──[5. STAGING DEPLOY]  ← Requires: tests green
      │       Deploy to staging environment
      │       Run smoke tests against staging URL
      │
      └──[6. PRODUCTION DEPLOY]  ← Requires: manual approval
              Blue/green deployment
              Health check: GET /api/health
              Rollback on failure
```

### GitHub Actions Secrets Required

| Secret | Value |
|---|---|
| `GROQ_API_KEY` | Groq API key |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant API key |
| `DATABASE_URL` | Production PostgreSQL URL |
| `JWT_SECRET_KEY` | Long random string (256-bit) |
| `DOCKER_REGISTRY` | Container registry URL |
| `CLOUDFLARE_TUNNEL_TOKEN` | Tunnel auth token |

### Branch Strategy

| Branch | Purpose | Auto-deploy |
|---|---|---|
| `main` | Production-ready code | → Production (manual gate) |
| `staging` | Pre-production integration | → Staging (auto) |
| `feature/*` | Feature development | → PR only |
| `fix/*` | Bug fixes | → PR only |

---

## 11. Integration Map (Frontend ↔ Backend)

| Screen | UI Element | API Endpoint | Method |
|---|---|---|---|
| Primary Secure Entrance | "Begin Secure Session" button | `/api/auth/login` | POST |
| Primary Secure Entrance | "Register" link | `/api/auth/register` | POST |
| Customer Login | Login form | `/api/auth/login` | POST |
| Home & Interaction Tool | Search bar (drug name) | `/api/query` | POST |
| AI Analysis State | Loading state | `/api/query` (pending) | POST |
| Interaction Results | Results + sources display | `/api/query` (response) | POST |
| Medication Dashboard | Medication list | `/api/medications` | GET |
| Medication Dashboard | Add medication form | `/api/medications` | POST |
| Medication Dashboard | Edit medication | `/api/medications/<id>` | PUT |
| Medication Dashboard | Delete medication | `/api/medications/<id>` | DELETE |
| Pharmacy Detail State | Pharmacy map + list | `/api/nearby-pharmacy` | GET |
| Header — Notifications icon | History sidebar | `/api/history` | GET |
| Header — Settings icon | Account settings | `/api/medications` | GET |

---

## 12. Future Roadmap

### Phase 1 — Foundation (Current)
- [x] CRAG RAG pipeline with Qdrant
- [x] Flask REST API
- [x] JWT authentication
- [x] Medication management
- [x] Nightly FDA sync
- [x] MCP server for Claude Desktop
- [x] Streamlit UI
- [x] Docker deployment
- [x] MedTrust Connect homepage design

### Phase 2 — Integration (Next Sprint)
- [ ] Integrate MedTrust Connect frontend into Flask
- [ ] Wire all Stitch screens to API endpoints
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Staging environment
- [ ] Self-host 3D capsule hero image

### Phase 3 — Data Enrichment
- [ ] DrugBank integration (mechanism-level DDIs)
- [ ] FDA FAERS integration (real-world adverse events)
- [ ] RxNorm drug name normalization
- [ ] Biomedical embedding model upgrade (`PubMedBERT`)
- [ ] Hybrid BM25 + vector search (Qdrant sparse vectors)

### Phase 4 — Scale & Compliance
- [ ] HIPAA audit logging
- [ ] GDPR privacy mode (opt-out of query history)
- [ ] Multi-language support
- [ ] Redis caching layer (production)
- [ ] APM / observability (Datadog or OpenTelemetry)
- [ ] Load testing (locust)
- [ ] API rate limiting

### Phase 5 — Clinical Features
- [ ] Pharmacogenomics integration (PharmGKB)
- [ ] QT prolongation risk scoring (CredibleMeds)
- [ ] Drug-allergy cross-check
- [ ] Dosage adjustment recommendations
- [ ] Provider portal (B2B tier)

---

## 13. Environment Variables

Create a `.env` file in the project root:

```env
# === LLM ===
GROQ_API_KEY=gsk_...

# === Vector DB ===
QDRANT_URL=https://your-cluster.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_key

# === Database ===
DATABASE_URL=postgresql://ddi_user:password@localhost:5432/ddi_rag
# For local dev:
# DATABASE_URL=sqlite:///drugsafe.db

# === Auth ===
JWT_SECRET_KEY=your_256_bit_random_secret_here

# === Server ===
PORT=5000
FLASK_ENV=production

# === openFDA ===
OPENFDA_API_KEY=optional_for_higher_rate_limits
```

---

## 14. Glossary

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation — LLM answers grounded in retrieved documents |
| **CRAG** | Corrective RAG — grades retrieved chunks and corrects low-quality retrievals before generation |
| **DDI** | Drug-Drug Interaction — how two or more drugs affect each other when taken together |
| **Qdrant** | Production vector database hosted on cloud for semantic similarity search |
| **ChromaDB** | Local/dev vector database for DDI pairs |
| **Cosine Similarity** | Score [0–1] measuring semantic closeness between query and chunk embeddings |
| **Embedding** | 384-dimensional vector representation of text produced by SentenceTransformer |
| **Chunk** | 120-word sliding window excerpt of FDA label text stored as a vector |
| **FDA Label** | Official prescribing information filed with the US Food & Drug Administration |
| **openFDA** | Public FDA API providing drug label, adverse event, and recall data |
| **FAERS** | FDA Adverse Event Reporting System — post-market drug safety reports |
| **MCP** | Model Context Protocol — standard for connecting AI models to external tools |
| **JWT** | JSON Web Token — stateless authentication token signed with HMAC-SHA256 |
| **HIPAA** | Health Insurance Portability and Accountability Act — US healthcare data privacy law |
| **APScheduler** | Python library for scheduling background jobs (nightly FDA sync) |
| **LRU Cache** | Least Recently Used cache — memoizes expensive function results (512-entry limit) |
| **Clinical Clarity** | Name of the Stitch design system used for all frontend screens |
| **MedSafe** | Product name for the MedTrust Connect portal (public-facing brand) |

---

*This document is the single source of truth for the MedSafe Interaction Portal project.*  
*Update this file whenever architecture, APIs, or design decisions change.*  
*Cross-check this documentation against Codex and Gemini analysis when available.*
