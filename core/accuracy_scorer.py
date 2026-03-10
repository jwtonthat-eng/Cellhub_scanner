"""
Accuracy scorer: compares Gemini-provided sample rows (ground truth) against
the rows extracted by the regex engine.

Algorithm:
  1. Align sample rows to extracted rows using Jaccard token similarity.
  2. Score each column per aligned pair.
  3. Compute weighted overall score.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

ALIGNMENT_THRESHOLD = 0.50
STRING_MATCH_THRESHOLD = 0.80
NUMERIC_TOLERANCE = 0.01
ROW_ALIGN_WEIGHT = 0.40
COL_ACCURACY_WEIGHT = 0.60


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ColumnScore:
    column_name: str
    matched: int
    total: int
    score: float        # matched / total
    color: str          # "green" | "yellow" | "orange" | "red"


@dataclass
class AccuracyReport:
    overall: float
    color_grade: str    # "green" | "yellow" | "orange" | "red"
    aligned_pairs: int
    total_sample: int
    per_column: list[ColumnScore] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def percent(self) -> str:
        return f"{self.overall * 100:.1f}%"

    @property
    def grade_label(self) -> str:
        if self.overall >= 0.90:
            return "Excellent"
        elif self.overall >= 0.70:
            return "Good"
        elif self.overall >= 0.50:
            return "Fair"
        return "Poor"


# ---------------------------------------------------------------------------
# AccuracyScorer
# ---------------------------------------------------------------------------

class AccuracyScorer:
    def score(
        self,
        sample_rows: list[dict[str, str]],
        extracted_df: pd.DataFrame,
        column_dtypes: dict[str, str] | None = None,
    ) -> AccuracyReport:
        """
        Args:
            sample_rows: Ground truth rows from Gemini (list of dicts).
            extracted_df: DataFrame produced by TableBuilder.
            column_dtypes: Mapping column_name → dtype ("str"|"float"|"int"|"date").
        """
        if not sample_rows:
            return AccuracyReport(
                overall=0.0, color_grade="red",
                aligned_pairs=0, total_sample=0)

        if extracted_df.empty:
            return AccuracyReport(
                overall=0.0, color_grade="red",
                aligned_pairs=0, total_sample=len(sample_rows))

        dtypes = column_dtypes or {}

        # Convert extracted rows to list of plain dicts (strings)
        extracted_rows: list[dict[str, str]] = self._df_to_str_rows(extracted_df)

        # Align sample rows to extracted rows
        aligned_pairs, unmatched = self._align(sample_rows, extracted_rows)

        # Per-column scoring
        columns = list(sample_rows[0].keys()) if sample_rows else []
        col_scores: dict[str, list[bool]] = {c: [] for c in columns}

        for sample, extracted in aligned_pairs:
            for col in columns:
                s_val = str(sample.get(col, "")).strip()
                e_val = str(extracted.get(col, "")).strip()
                dtype = dtypes.get(col, "str")
                col_scores[col].append(self._cell_match(s_val, e_val, dtype))

        per_column: list[ColumnScore] = []
        for col, matches in col_scores.items():
            if not matches:
                per_column.append(ColumnScore(col, 0, 0, 0.0, "red"))
                continue
            matched = sum(matches)
            total = len(matches)
            score = matched / total
            per_column.append(ColumnScore(
                column_name=col,
                matched=matched,
                total=total,
                score=score,
                color=_color_for_score(score),
            ))

        # Overall score
        row_ratio = len(aligned_pairs) / len(sample_rows)
        col_mean = (sum(cs.score for cs in per_column) / len(per_column)
                    if per_column else 0.0)
        overall = row_ratio * ROW_ALIGN_WEIGHT + col_mean * COL_ACCURACY_WEIGHT

        # Build detail rows for UI display
        details = [
            {"sample": s, "extracted": e, "aligned": True}
            for s, e in aligned_pairs
        ]
        details += [{"sample": s, "extracted": {}, "aligned": False}
                    for s in unmatched]

        return AccuracyReport(
            overall=overall,
            color_grade=_color_for_score(overall),
            aligned_pairs=len(aligned_pairs),
            total_sample=len(sample_rows),
            per_column=per_column,
            details=details,
        )

    # ------------------------------------------------------------------
    # Row alignment
    # ------------------------------------------------------------------

    def _align(
        self,
        sample_rows: list[dict[str, str]],
        extracted_rows: list[dict[str, str]],
    ) -> tuple[list[tuple[dict, dict]], list[dict]]:
        """Greedy 1:1 alignment: for each sample row find the best extracted row."""
        used_indices: set[int] = set()
        pairs: list[tuple[dict, dict]] = []
        unmatched: list[dict] = []

        # Only search in the first 2x sample rows to avoid false positives
        search_limit = min(len(extracted_rows), max(len(sample_rows) * 2, 10))

        for s_row in sample_rows:
            best_idx = -1
            best_sim = ALIGNMENT_THRESHOLD

            for idx in range(search_limit):
                if idx in used_indices:
                    continue
                sim = self._row_similarity(s_row, extracted_rows[idx])
                if sim > best_sim:
                    best_sim = sim
                    best_idx = idx

            if best_idx >= 0:
                used_indices.add(best_idx)
                pairs.append((s_row, extracted_rows[best_idx]))
            else:
                unmatched.append(s_row)

        return pairs, unmatched

    @staticmethod
    def _row_similarity(a: dict[str, str], b: dict[str, str]) -> float:
        """Average Jaccard similarity across shared columns."""
        shared_keys = set(a.keys()) & set(b.keys())
        if not shared_keys:
            return 0.0
        sims = [_jaccard(str(a[k]), str(b.get(k, ""))) for k in shared_keys]
        return sum(sims) / len(sims)

    # ------------------------------------------------------------------
    # Cell matching
    # ------------------------------------------------------------------

    @staticmethod
    def _cell_match(sample: str, extracted: str, dtype: str) -> bool:
        if not sample and not extracted:
            return True
        if dtype in ("float", "int"):
            return _numeric_close(sample, extracted, NUMERIC_TOLERANCE)
        elif dtype == "date":
            return _date_equal(sample, extracted)
        else:
            return _jaccard(sample, extracted) >= STRING_MATCH_THRESHOLD

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _df_to_str_rows(df: pd.DataFrame) -> list[dict[str, str]]:
        rows = []
        for _, row in df.iterrows():
            rows.append({col: str(val) if pd.notna(val) else ""
                         for col, val in row.items()})
        return rows


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def _jaccard(a: str, b: str) -> float:
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def _numeric_close(a: str, b: str, tolerance: float = NUMERIC_TOLERANCE) -> bool:
    try:
        fa = float(a.replace(",", "").replace("R", "").strip())
        fb = float(b.replace(",", "").replace("R", "").strip())
        return abs(fa - fb) <= tolerance
    except (ValueError, AttributeError):
        return False


def _date_equal(a: str, b: str) -> bool:
    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y"]
    for fmt in formats:
        try:
            da = datetime.strptime(a.strip(), fmt)
            db = datetime.strptime(b.strip(), fmt)
            return da == db
        except ValueError:
            continue
    # Fallback: string equality
    return a.strip() == b.strip()


def _color_for_score(score: float) -> str:
    if score >= 0.90:
        return "green"
    elif score >= 0.70:
        return "yellow"
    elif score >= 0.50:
        return "orange"
    return "red"
