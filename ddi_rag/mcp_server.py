"""
mcp_server.py — DrugSafe AI MCP Server

Exposes DrugSafe AI capabilities as MCP tools so any MCP-compatible client
(Claude Desktop, Cursor, etc.) can query drug interactions.

Note: this is a research/operations interface, not the hospital production
boundary — the architecture doc explicitly says not to expose the MCP
server as the primary clinical API (that's app.py).

Tools:
    query_drug_interactions  — RAG pipeline: retrieve FDA evidence + Groq answer
    list_drug_warnings       — Quick interaction summary for a drug pair

Run (stdio transport — used by Claude Desktop):
    python mcp_server.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "drugsafe": {
          "command": "python",
          "args": ["C:/Users/C V REDDY/Downloads/ddi_rag/ddi_rag/mcp_server.py"]
        }
      }
    }
"""

import logging
import sys
from pathlib import Path

# Allow imports from the ddi_rag package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

log = logging.getLogger("ddi.mcp")
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# ── Create MCP server ─────────────────────────────────────────────────────────

mcp = FastMCP(
    name         = "DrugSafe AI",
    instructions = (
        "FDA-powered drug interaction checker. "
        "Query drug-drug interactions using pgvector RAG + Llama 3.1 via Groq."
    ),
)

# Note: there used to be a lazy _ensure_rag()/load_models() step here to
# load a local embedding model on first use. Embeddings are now a Cohere
# API call (services/evidence_store.py) — nothing local to preload.

# ── Tool 1: Query drug interactions ──────────────────────────────────────────

@mcp.tool()
def query_drug_interactions(
    drug_name: str,
    history_context: str = "",
):
    # No `-> str` return annotation: mcp==1.27.0's structured-output model
    # generation raises a PydanticUserError for bare `str` return types on
    # tool functions with this pydantic version. The docstring below still
    # documents the return value for callers.
    """
    Query FDA label data and DDI pair database for drug interaction information.

    Uses pgvector similarity search (Cohere embeddings) + Llama 3.1 via Groq
    to provide clinically relevant interaction warnings and contraindications.

    Args:
        drug_name       : Generic drug name to query (e.g. "warfarin", "aspirin")
        history_context : Optional — comma-separated list of patient's current
                          medications (e.g. "warfarin 5mg, lisinopril 10mg")
                          Used to personalise interaction warnings.

    Returns:
        Clinical summary of drug interactions, warnings, and contraindications.
    """
    from services.rag_pipeline import answer_ddi

    if not drug_name or not drug_name.strip():
        return "Error: drug_name is required."

    drug_clean = drug_name.strip().lower()
    log.info("MCP tool call: query_drug_interactions('%s')", drug_clean)

    result = answer_ddi(
        drug_name       = drug_clean,
        section         = "drug_interactions",
        top_k           = 5,
        history_context = history_context.strip(),
    )

    answer  = result.get("answer", "No information found.")
    sources = result.get("sources", [])

    # Format sources as a readable list
    src_lines = []
    for i, s in enumerate(sources[:5], 1):
        section  = (s.get("section") or "").replace("_", " ").title()
        score    = float(s.get("score", 0))
        drug     = s.get("generic_name", "")
        src_lines.append(f"  [{i}] {section} | {drug} | similarity={score:.3f}")

    output = f"## Drug Interaction Summary: {drug_name.title()}\n\n{answer}"
    if src_lines:
        output += "\n\n### FDA Evidence Sources\n" + "\n".join(src_lines)

    return output


# ── Tool 2: List drug warnings for a pair ────────────────────────────────────

@mcp.tool()
def list_drug_warnings(
    drug_1: str,
    drug_2: str,
):
    # See query_drug_interactions() above for why there's no -> str here.
    """
    Check for known interactions between two specific drugs.

    Searches the DDI pairs database (187k+ pairwise interactions) and FDA
    label data for documented warnings between drug_1 and drug_2.

    Args:
        drug_1 : First drug name  (e.g. "warfarin")
        drug_2 : Second drug name (e.g. "aspirin")

    Returns:
        Known interaction descriptions and severity information.
    """
    from services.rag_pipeline import retrieve_chunks

    d1 = drug_1.strip().lower()
    d2 = drug_2.strip().lower()
    log.info("MCP tool call: list_drug_warnings('%s', '%s')", d1, d2)

    query = f"{d1} and {d2} drug interaction warning"
    chunks = retrieve_chunks(query=query, top_k=5)

    if chunks.empty:
        return f"No documented interactions found between {drug_1} and {drug_2} in the database."

    lines = [f"## Interaction Check: {drug_1.title()} + {drug_2.title()}\n"]
    for i, (_, row) in enumerate(chunks.iterrows(), 1):
        section = (row.get("section") or "").replace("_", " ").title()
        text    = (row.get("text") or "")[:400]
        score   = float(row.get("score", 0))
        lines.append(f"**Source {i}** ({section}, relevance={score:.3f}):\n{text}\n")

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting DrugSafe AI MCP server (stdio transport)...")
    mcp.run(transport="stdio")
