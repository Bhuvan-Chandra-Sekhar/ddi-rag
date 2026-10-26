"""
Two things:

  1. A denylist regression test over frontend copy — the concrete bug an
     audit found (the Home hero literally read "Uncovering what's safe to
     take together") needs a test, or it can silently come back the next
     time someone rewrites that screen. This is H18 in
     docs/HAZARD_REGISTER.md.

  2. A test that the hazard register itself doesn't drift from reality:
     every `path::function_name` reference in docs/HAZARD_REGISTER.md must
     point at a test function that actually exists. A hazard whose test
     got renamed or deleted silently becomes an unguarded hazard again —
     this is the check that would catch that.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exact absolute-claim phrases a safety-critical UI must never state as
# fact — distinct from correctly-hedged uses of "safe" elsewhere in this
# codebase ("not a safe combination", "we never call something safe just
# because we don't know"), which don't match any of these substrings.
_BANNED_PHRASES = [
    "what's safe", "whats safe", "is safe to", "are safe to", "safe to take",
    "guaranteed safe", "100% safe", "completely safe", "perfectly safe",
    "definitely safe", "always safe", "clinically validated", "clinically proven",
]

_SCAN_GLOBS = [
    "frontend-patient/src/**/*.jsx",
    "frontend-patient/src/**/*.js",
    "ddi_rag/static/patient/index.html",
    "ddi_rag/static/clinical/index.html",
]


def test_no_unsafe_absolute_claims_in_frontend_copy():
    hits = []
    for pattern in _SCAN_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for phrase in _BANNED_PHRASES:
                if phrase in text:
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {phrase!r}")
    assert not hits, (
        "Absolute safety-claim wording found in user-facing copy (see "
        "docs/HAZARD_REGISTER.md H18) — rephrase to something hedged, e.g. "
        "'what to know' instead of 'what's safe':\n" + "\n".join(hits)
    )


_REGISTER_PATH = REPO_ROOT / "docs" / "HAZARD_REGISTER.md"
_TEST_REF_RE = re.compile(r"`(tests/[\w./]+\.py)(?:::(\w+))?`")


def test_hazard_register_test_references_all_exist():
    text = _REGISTER_PATH.read_text(encoding="utf-8")
    refs = _TEST_REF_RE.findall(text)
    assert refs, "No test references found in docs/HAZARD_REGISTER.md — did the format change?"

    missing = []
    for rel_path, func_name in refs:
        test_path = REPO_ROOT / rel_path
        if not test_path.exists():
            missing.append(f"{rel_path} does not exist")
            continue
        if func_name:
            source = test_path.read_text(encoding="utf-8")
            if not re.search(rf"^def {re.escape(func_name)}\(", source, re.MULTILINE):
                missing.append(f"{rel_path}::{func_name} — function not found in file")

    assert not missing, (
        "docs/HAZARD_REGISTER.md references tests that no longer exist — "
        "the hazard(s) these covered have silently lost their test:\n"
        + "\n".join(missing)
    )
