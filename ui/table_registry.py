from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Any

class TableRenderer(Protocol):
    def __call__(self, df: Any, query: str, **kwargs: Any) -> None: ...

@dataclass(frozen=True)
class TableSpec:
    id: str
    title: str
    render: TableRenderer
    when: Callable[[str], bool] = lambda _q: True  # default: always show
