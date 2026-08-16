"""
aho_corasick.py — Multi-pattern string matching in a single text pass.

Used by app.py's parse_prescription() to find every known drug name in
free-text prescription input. Scanning the text once per known drug name
(a separate regex `finditer` call each time) is O(n_patterns *
text_length). Building one automaton from all patterns up front
(O(total_pattern_length)) lets every pattern be found in a single
O(text_length + n_matches) pass, regardless of how many patterns are
registered — the difference matters once the pattern list is hundreds or
thousands of drug names, not a handful.

Not word-boundary aware by itself — Aho-Corasick matches substrings
(it would match "aspirin" inside "acetylsalicylic-aspirin-blend" AND
inside a hypothetical longer unrelated word). Callers that need whole-
word semantics, like parse_prescription(), filter with
is_word_boundary_match() below — the same semantics as regex \\bpattern\\b.
"""

from collections import deque
from typing import Dict, Iterable, List, NamedTuple


class Match(NamedTuple):
    start: int
    end: int
    pattern: str


class AhoCorasick:
    """Build once from a pattern list (expensive: O(total pattern
    length)), then call find_all() as many times as needed (cheap: O(text
    length + matches) per call, independent of pattern count)."""

    def __init__(self, patterns: Iterable[str]):
        self._goto: List[Dict[str, int]] = [{}]
        self._fail: List[int] = [0]
        self._output: List[List[str]] = [[]]

        for pattern in dict.fromkeys(patterns):  # dedupe, keep first-seen order
            if not pattern:
                continue
            node = 0
            for ch in pattern:
                nxt = self._goto[node].get(ch)
                if nxt is None:
                    self._goto.append({})
                    self._fail.append(0)
                    self._output.append([])
                    nxt = len(self._goto) - 1
                    self._goto[node][ch] = nxt
                node = nxt
            self._output[node].append(pattern)

        self._build_fail_links()

    def _build_fail_links(self) -> None:
        """Standard Aho-Corasick BFS construction: each node's fail link
        points to the longest proper suffix of its path that is also a
        prefix of some pattern (i.e. reachable from the root) — this is
        what lets a failed match resume without rescanning the text."""
        root = 0
        queue: deque = deque()
        for ch, nxt in self._goto[root].items():
            self._fail[nxt] = root
            queue.append(nxt)

        while queue:
            node = queue.popleft()
            for ch, nxt in self._goto[node].items():
                queue.append(nxt)
                fallback = self._fail[node]
                while fallback != root and ch not in self._goto[fallback]:
                    fallback = self._fail[fallback]
                candidate = self._goto[fallback].get(ch, root)
                self._fail[nxt] = candidate if candidate != nxt else root
                self._output[nxt] = self._output[nxt] + self._output[self._fail[nxt]]

    def find_all(self, text: str) -> List[Match]:
        """Every occurrence of every registered pattern in `text`, in one
        pass. May include overlapping matches (e.g. a short pattern that's
        also a substring of a longer one both matching around the same
        position) — callers resolve precedence themselves."""
        node = 0
        matches: List[Match] = []
        for i, ch in enumerate(text):
            while node != 0 and ch not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(ch, 0)
            for pattern in self._output[node]:
                matches.append(Match(i - len(pattern) + 1, i + 1, pattern))
        return matches


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def is_word_boundary_match(text: str, start: int, end: int) -> bool:
    """True if text[start:end] is a whole word in `text` — no word
    character immediately before `start` or immediately after `end`.
    Same semantics as regex \\bpattern\\b, checked after the fact since
    Aho-Corasick itself only matches substrings."""
    before_ok = start == 0 or not _is_word_char(text[start - 1])
    after_ok = end == len(text) or not _is_word_char(text[end])
    return before_ok and after_ok
