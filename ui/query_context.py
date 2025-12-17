from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass(frozen=True)
class QueryContext:
    raw: str
    q_lower: str
    neg_casting: bool
    has_in_process: bool
    combined_mode: bool

def build_query_context(query: str) -> QueryContext:
    q_lower = (query or "").lower()
    neg_casting = bool(re.search(r"(not\s+casting|no\s+casting|not\s+ready\s+casting|casting\s+not\s+ready)", q_lower))
    has_in_process = bool(re.search(r"\bin\s+(production|process|progress)\b", q_lower))
    combined_mode = bool(neg_casting and has_in_process)
    return QueryContext(
        raw=query or "",
        q_lower=q_lower,
        neg_casting=neg_casting,
        has_in_process=has_in_process,
        combined_mode=combined_mode,
    )
