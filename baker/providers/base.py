"""Provider adapter interface.

Each adapter is the ONLY place that knows its provider's wire format,
auth, and rate limits. Adapters emit NormalizedStory and nothing else.
"""

from __future__ import annotations

from typing import Protocol

from ..models import NormalizedStory


class Provider(Protocol):
    name: str

    def fetch(self) -> list[NormalizedStory]:
        """Fetch all configured sections. Must not raise on partial
        failure — log and return what succeeded."""
        ...
