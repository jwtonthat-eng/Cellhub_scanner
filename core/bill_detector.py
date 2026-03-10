"""
Bill type detector: scores PDF text against keyword lists to identify bill type.
"""
from __future__ import annotations

from patterns.pattern_manager import BillTypeSchema, PatternManager


class BillDetector:
    def __init__(self, pattern_manager: PatternManager) -> None:
        self._pm = pattern_manager

    def detect(self, full_text: str) -> str | None:
        """
        Score the full PDF text against all registered bill type keyword lists.

        Returns the bill_type key of the best match if it meets min_keyword_score,
        otherwise returns None (unknown bill type).
        """
        lower_text = full_text.lower()
        best_type: str | None = None
        best_score = 0

        for bill_type, schema in self._pm.all_schemas().items():
            score = self._score(lower_text, schema)
            if score >= schema.min_keyword_score and score > best_score:
                best_score = score
                best_type = bill_type

        return best_type

    @staticmethod
    def _score(lower_text: str, schema: BillTypeSchema) -> int:
        return sum(1 for kw in schema.detection_keywords if kw in lower_text)
