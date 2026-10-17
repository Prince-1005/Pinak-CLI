"""Real-time substring and fuzzy search filter for media picker."""

from __future__ import annotations

from .scanner import MediaItem


class FuzzyMediaFilter:
    """Filters discovered media items against search queries."""

    @classmethod
    def filter_items(cls, items: list[MediaItem], query: str) -> list[MediaItem]:
        q = query.strip().lower()
        if not q:
            return items

        filtered: list[MediaItem] = []
        for item in items:
            # Always preserve parent directory entry
            if item.name.startswith(".."):
                filtered.append(item)
                continue

            name_lower = item.name.lower()
            if q in name_lower or cls._fuzzy_match(q, name_lower):
                filtered.append(item)

        return filtered

    @classmethod
    def _fuzzy_match(cls, pattern: str, target: str) -> bool:
        """Sequential character matching algorithm."""
        p_idx = 0
        p_len = len(pattern)
        for char in target:
            if char == pattern[p_idx]:
                p_idx += 1
                if p_idx == p_len:
                    return True
        return False
