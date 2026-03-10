"""
PDF text extractor: reads characters from pdfplumber, clusters by y-position
into visual lines, reconstructs line text with proper spacing.

Handles:
  - Single-column and two-column bill layouts
  - Cross-page text continuity (caller stitches pages together)
  - Memory efficiency: yields one PageText at a time (generator)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

@dataclass
class CharToken:
    char: str
    x0: float
    x1: float
    top: float   # distance from top of page
    size: float  # font size in points


@dataclass
class LineText:
    text: str
    top: float   # y-coordinate of the line
    x0: float    # leftmost char x


@dataclass
class PageText:
    page_num: int        # 1-based
    raw_text: str        # full reconstructed text of the page
    lines: list[LineText]


# ---------------------------------------------------------------------------
# PdfExtractor
# ---------------------------------------------------------------------------

class PdfExtractor:
    # Fraction of char height used as tolerance for same-line grouping
    LINE_TOLERANCE_FACTOR = 0.5
    # Multiplier of median char width for inserting a space between words
    SPACE_GAP_FACTOR = 0.8
    # Minimum gap (points) between two x-clusters to be considered 2-column
    TWO_COL_GAP_THRESHOLD = 100.0
    # Fraction of lines that must show the two-column gap pattern
    TWO_COL_LINE_FRACTION = 0.30

    def __init__(self) -> None:
        if pdfplumber is None:
            raise ImportError("pdfplumber is required. Install it with: pip install pdfplumber")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def extract_pages(
        self,
        path: str | Path,
        page_callback: "Callable[[int, int], None] | None" = None,
    ) -> Generator[PageText, None, None]:
        """
        Generator that yields a PageText for each page of the PDF.

        Args:
            path: Path to the PDF file.
            page_callback: Optional callable(current_page, total_pages) for
                           progress reporting. Called after each page.
        """
        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                chars = page.chars
                page_text = self._process_page(i, chars)
                yield page_text
                if page_callback:
                    page_callback(i, total)

    def page_count(self, path: str | Path) -> int:
        with pdfplumber.open(str(path)) as pdf:
            return len(pdf.pages)

    # ------------------------------------------------------------------
    # Internal: page processing
    # ------------------------------------------------------------------

    def _process_page(self, page_num: int, chars: list[dict]) -> PageText:
        if not chars:
            return PageText(page_num=page_num, raw_text="", lines=[])

        tokens = self._to_tokens(chars)
        if not tokens:
            return PageText(page_num=page_num, raw_text="", lines=[])

        # Detect two-column layout
        if self._is_two_column(tokens):
            left_tokens, right_tokens = self._split_two_columns(tokens)
            left_lines = self._cluster_to_lines(left_tokens)
            right_lines = self._cluster_to_lines(right_tokens)
            lines = self._merge_columns(left_lines, right_lines)
        else:
            lines = self._cluster_to_lines(tokens)

        raw_text = "\n".join(ln.text for ln in lines)
        return PageText(page_num=page_num, raw_text=raw_text, lines=lines)

    # ------------------------------------------------------------------
    # Internal: char token conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_tokens(chars: list[dict]) -> list[CharToken]:
        tokens = []
        for c in chars:
            text = c.get("text", "")
            if not text or text == " ":
                continue
            tokens.append(CharToken(
                char=text,
                x0=float(c.get("x0", 0)),
                x1=float(c.get("x1", 0)),
                top=float(c.get("top", 0)),
                size=float(c.get("size", 10)),
            ))
        return tokens

    # ------------------------------------------------------------------
    # Internal: line clustering
    # ------------------------------------------------------------------

    def _cluster_to_lines(self, tokens: list[CharToken]) -> list[LineText]:
        if not tokens:
            return []

        # Sort by top (y), then x0
        sorted_tokens = sorted(tokens, key=lambda c: (c.top, c.x0))

        lines_tokens: list[list[CharToken]] = []
        current: list[CharToken] = [sorted_tokens[0]]

        for tok in sorted_tokens[1:]:
            ref = current[-1]
            tolerance = ref.size * self.LINE_TOLERANCE_FACTOR
            if abs(tok.top - ref.top) <= tolerance:
                current.append(tok)
            else:
                lines_tokens.append(current)
                current = [tok]
        lines_tokens.append(current)

        # Compute median char width across the page for space-insertion
        all_widths = [t.x1 - t.x0 for t in tokens if t.x1 > t.x0]
        median_width = statistics.median(all_widths) if all_widths else 5.0
        space_threshold = median_width * self.SPACE_GAP_FACTOR

        result: list[LineText] = []
        for line_toks in lines_tokens:
            line_toks_sorted = sorted(line_toks, key=lambda t: t.x0)
            text_parts = [line_toks_sorted[0].char]
            for prev, curr in zip(line_toks_sorted, line_toks_sorted[1:]):
                gap = curr.x0 - prev.x1
                if gap > space_threshold:
                    text_parts.append(" ")
                text_parts.append(curr.char)
            text = "".join(text_parts)
            result.append(LineText(
                text=text,
                top=line_toks_sorted[0].top,
                x0=line_toks_sorted[0].x0,
            ))

        return result

    # ------------------------------------------------------------------
    # Internal: two-column detection and splitting
    # ------------------------------------------------------------------

    def _is_two_column(self, tokens: list[CharToken]) -> bool:
        """
        Detect if >TWO_COL_LINE_FRACTION of lines have a large gap in x-coordinates,
        suggesting a two-column layout.
        """
        lines_tokens = self._rough_line_groups(tokens)
        if len(lines_tokens) < 4:
            return False

        two_col_count = 0
        for line_toks in lines_tokens:
            if len(line_toks) < 2:
                continue
            xs = sorted(t.x0 for t in line_toks)
            max_gap = max(xs[i + 1] - xs[i] for i in range(len(xs) - 1))
            if max_gap > self.TWO_COL_GAP_THRESHOLD:
                two_col_count += 1

        return two_col_count / len(lines_tokens) >= self.TWO_COL_LINE_FRACTION

    def _rough_line_groups(self, tokens: list[CharToken]) -> list[list[CharToken]]:
        sorted_tokens = sorted(tokens, key=lambda c: c.top)
        groups: list[list[CharToken]] = []
        current = [sorted_tokens[0]]
        for tok in sorted_tokens[1:]:
            if abs(tok.top - current[-1].top) <= current[-1].size * self.LINE_TOLERANCE_FACTOR:
                current.append(tok)
            else:
                groups.append(current)
                current = [tok]
        groups.append(current)
        return groups

    def _split_two_columns(
        self, tokens: list[CharToken]
    ) -> tuple[list[CharToken], list[CharToken]]:
        """Find the main vertical gap and split tokens into left / right columns."""
        all_x = sorted(t.x0 for t in tokens)
        best_gap = 0.0
        split_x = 0.0
        for i in range(len(all_x) - 1):
            gap = all_x[i + 1] - all_x[i]
            if gap > best_gap:
                best_gap = gap
                split_x = (all_x[i] + all_x[i + 1]) / 2.0

        left = [t for t in tokens if t.x0 < split_x]
        right = [t for t in tokens if t.x0 >= split_x]
        return left, right

    @staticmethod
    def _merge_columns(
        left_lines: list[LineText], right_lines: list[LineText]
    ) -> list[LineText]:
        """
        Interleave left and right column lines by y-position so the combined
        text reads top-to-bottom, left column first on each row.
        """
        merged: list[LineText] = []
        li, ri = 0, 0
        while li < len(left_lines) and ri < len(right_lines):
            lt = left_lines[li]
            rt = right_lines[ri]
            # If they're on the same visual row, combine them
            if abs(lt.top - rt.top) <= 12.0:
                merged.append(LineText(
                    text=lt.text + "  " + rt.text,
                    top=lt.top,
                    x0=lt.x0,
                ))
                li += 1
                ri += 1
            elif lt.top < rt.top:
                merged.append(lt)
                li += 1
            else:
                merged.append(rt)
                ri += 1
        merged.extend(left_lines[li:])
        merged.extend(right_lines[ri:])
        return merged
