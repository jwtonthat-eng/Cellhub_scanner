"""
Table builder: applies bill-type regex schemas to extracted page text,
producing a pandas DataFrame with one row per matched line item.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
from datetime import datetime
from typing import Any, Generator

import pandas as pd

from core.pdf_extractor import PageText
from patterns.pattern_manager import BillTypeSchema, ColumnPattern

logger = logging.getLogger(__name__)

REGEX_TIMEOUT_SECONDS = 2.0
TRANSFORM_FNS: dict[str, Any] = {
    "strip": str.strip,
    "upper": str.upper,
    "lower": str.lower,
    "remove_commas": lambda s: s.replace(",", ""),
    "remove_spaces": lambda s: s.replace(" ", ""),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TableBuilder:
    def __init__(self) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def build(
        self,
        pages: Generator[PageText, None, None] | list[PageText],
        schema: BillTypeSchema,
        progress_callback: "Callable[[int], None] | None" = None,
    ) -> pd.DataFrame:
        """
        Process all pages and return a DataFrame of extracted rows.

        progress_callback(rows_so_far) is called after each page.
        """
        all_rows: list[dict[str, Any]] = []
        pending_text: str = ""   # unfinished row carried from previous page

        for page in pages:
            raw = pending_text + "\n" + page.raw_text if pending_text else page.raw_text
            rows, pending_text = self._extract_rows(raw, schema)
            all_rows.extend(rows)
            if progress_callback:
                progress_callback(len(all_rows))

        # Try to process any leftover text from the last page
        if pending_text.strip():
            row = self._extract_single_row(pending_text.strip(), schema)
            if any(v != col.default_value for col, v in zip(schema.columns, row.values())):
                all_rows.append(row)

        if not all_rows:
            return pd.DataFrame(columns=[col.name for col in schema.columns])

        df = pd.DataFrame(all_rows)
        df = self._cast_dtypes(df, schema)
        return df

    # ------------------------------------------------------------------
    # Row extraction
    # ------------------------------------------------------------------

    def _extract_rows(
        self, text: str, schema: BillTypeSchema
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Split text on row_split_pattern; apply column patterns to each block.
        Returns (completed_rows, pending_leftover).
        """
        if not schema.row_split_pattern:
            return [], ""

        try:
            compiled = re.compile(schema.row_split_pattern, re.MULTILINE)
        except re.error as exc:
            logger.error("Invalid row_split_pattern: %s", exc)
            return [], ""

        matches = list(compiled.finditer(text))
        if not matches:
            return [], ""

        rows = []
        spans = [(m.start(), m.end()) for m in matches]

        for i, (start, _) in enumerate(spans):
            end = spans[i + 1][0] if i + 1 < len(spans) else len(text)
            block = text[start:end].strip()
            row = self._extract_single_row(block, schema)
            rows.append(row)

        # The last block is kept as pending (might continue on next page)
        pending = ""
        if rows:
            last_start = spans[-1][0]
            last_block = text[last_start:].strip()
            # Heuristic: if any required column (default_value=="") is empty,
            # treat last row as pending and remove it from completed rows.
            last_row = rows[-1]
            is_incomplete = any(
                col.default_value == "" and last_row.get(col.name, "") == ""
                for col in schema.columns
                if col.dtype != "date"  # date often absent in continuation rows
            )
            if is_incomplete and len(rows) > 1:
                rows.pop()
                pending = last_block

        return rows, pending

    def _extract_single_row(
        self, block: str, schema: BillTypeSchema
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for col in schema.columns:
            row[col.name] = self._match_column(block, col)
        return row

    def _match_column(self, block: str, col: ColumnPattern) -> str:
        if not col.regex:
            return col.default_value

        match = self._safe_search(col.regex, block)
        if match is None:
            return col.default_value

        try:
            value = match.group(col.capture_group)
        except IndexError:
            value = match.group(0)

        if value is None:
            return col.default_value

        value = str(value)

        # Apply transform
        if col.transform and col.transform in TRANSFORM_FNS:
            value = TRANSFORM_FNS[col.transform](value)

        return value.strip()

    # ------------------------------------------------------------------
    # Regex with timeout
    # ------------------------------------------------------------------

    def _safe_search(
        self, pattern: str, text: str
    ) -> "re.Match | None":
        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error:
            return None
        future = self._executor.submit(compiled.search, text)
        try:
            return future.result(timeout=REGEX_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            logger.warning("Regex timeout: pattern=%r", pattern[:60])
            return None

    # ------------------------------------------------------------------
    # Type casting
    # ------------------------------------------------------------------

    @staticmethod
    def _cast_dtypes(df: pd.DataFrame, schema: BillTypeSchema) -> pd.DataFrame:
        for col in schema.columns:
            if col.name not in df.columns:
                continue
            series = df[col.name]
            try:
                if col.dtype == "float":
                    df[col.name] = pd.to_numeric(series, errors="coerce")
                elif col.dtype == "int":
                    df[col.name] = pd.to_numeric(series, errors="coerce").astype("Int64")
                elif col.dtype == "date" and col.date_format:
                    df[col.name] = pd.to_datetime(
                        series, format=col.date_format, errors="coerce"
                    )
            except Exception as exc:
                logger.warning("dtype cast failed for column '%s': %s", col.name, exc)
        return df

    def __del__(self) -> None:
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
