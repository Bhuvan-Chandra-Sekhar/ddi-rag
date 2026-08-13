"""
services/llm_eval.py — LLM safety eval helpers (architecture doc section 13
"LLM safety": faithfulness, citation grounding, prohibited severity/action
changes, prompt-injection resistance).

score_faithfulness() is a v1 heuristic (lexical overlap) — a placeholder
until a live LLM-judge model can run against real retrieved evidence
(Groq is live; the pgvector evidence store still needs real data
ingested — see scripts/ingest_evidence.py). It only catches gross
fabrication (an explanation sharing almost no words with the evidence
it's grounded in); it is not a validated faithfulness measure and
should not be reported as clinical evidence on its own.
"""

import re
from typing import List

_WORD_RE = re.compile(r"[a-z0-9]+")

# Common words that would inflate overlap without meaning anything —
# excluded so the score reflects substantive grounding, not filler.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "this", "that", "it", "as", "by",
    "may", "can", "has", "have", "not", "no",
}


def _content_words(text: str) -> set:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def score_faithfulness(explanation: str, evidence_texts: List[str]) -> float:
    """
    Fraction of the explanation's distinct content words that also appear
    in the evidence. 1.0 = fully grounded vocabulary; 0.0 = no overlap
    (likely fabricated). Coarse v1 heuristic — does not catch subtle
    unfaithfulness (e.g. correct words, wrong claim).
    """
    explanation_words = _content_words(explanation)
    if not explanation_words:
        return 0.0
    evidence_words = _content_words(" ".join(evidence_texts))
    if not evidence_words:
        return 0.0
    return len(explanation_words & evidence_words) / len(explanation_words)


def citations_are_grounded(citations: List[dict], retrieved_evidence: List[dict]) -> bool:
    """Every citation returned must be one of the passages actually
    retrieved for this explanation — never fabricated or out-of-band."""
    retrieved_texts = {e["text"] for e in retrieved_evidence}
    return all(c.get("text") in retrieved_texts for c in citations)
