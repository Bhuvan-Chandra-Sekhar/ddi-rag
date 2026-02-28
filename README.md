# ddi-rag

Basic skeleton for a RAG-style project with separate data and notebook directories.

## Data

The cleaned DDI dataset (`clean_ddi_dataset.csv`) is too large for GitHub. Download it from Google Drive and place it in `data/` or `src/` before running the ingest notebook:

**[clean_ddi_dataset.csv](https://drive.google.com/file/d/1pvO8-Un6mTetikGciF2hyPmeTIYIT89H/view?usp=drive_link)**

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
