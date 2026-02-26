# ddi-rag

Basic skeleton for a RAG-style project with separate data and notebook directories.

## Structure

- `data/raw` – place original input data files here.
- `data/processed` – place cleaned/processed artifacts here.
- `src/ingest.ipynb` – for data ingestion logic.
- `src/parse.ipynb` – for parsing/feature extraction logic.
- `main.py` – Python entry point for orchestration.

## Setup

```bash
cd ddi-rag
python -m venv .venv
.venv\Scripts\activate  # on Windows
pip install -r requirements.txt
```
