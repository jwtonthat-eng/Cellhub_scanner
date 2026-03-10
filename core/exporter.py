"""
Exporter: converts a pandas DataFrame to CSV or Excel (.xlsx).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


class Exporter:
    @staticmethod
    def to_csv(df: pd.DataFrame, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(str(path), index=False, encoding="utf-8-sig")

    @staticmethod
    def to_excel(
        df: pd.DataFrame,
        path: str | Path,
        bill_type: str = "",
        accuracy_score: float | None = None,
    ) -> None:
        """
        Write DataFrame to Excel with:
          - Auto-sized columns (capped at 60 chars)
          - Frozen + bold header row
          - Metadata sheet (bill type, accuracy, export date)
        """
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()

        # ── Data sheet ──────────────────────────────────────────────────
        ws = wb.active
        ws.title = "Extracted Data"

        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=False)

        # Write headers
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=str(col_name))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        # Write data rows
        for row_idx, row in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=row_idx, column=col_idx)
                if pd.isna(value) if not isinstance(value, str) else False:
                    cell.value = ""
                elif isinstance(value, (int, float)):
                    cell.value = value
                elif hasattr(value, "strftime"):
                    cell.value = value
                    cell.number_format = "DD/MM/YYYY"
                else:
                    cell.value = str(value)

        # Auto-size columns
        for col_idx, col_name in enumerate(df.columns, start=1):
            col_letter = get_column_letter(col_idx)
            col_data = df.iloc[:, col_idx - 1].astype(str)
            max_len = max(len(str(col_name)), col_data.str.len().max() if not col_data.empty else 0)
            ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

        # Freeze header row
        ws.freeze_panes = "A2"

        # ── Metadata sheet ───────────────────────────────────────────────
        meta_ws = wb.create_sheet("Metadata")
        meta_font = Font(bold=True)
        meta_rows: list[tuple[str, Any]] = [
            ("Bill Type", bill_type or "Unknown"),
            ("Export Date", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("Total Rows", len(df)),
            ("Total Columns", len(df.columns)),
        ]
        if accuracy_score is not None:
            meta_rows.append(("Accuracy Score", f"{accuracy_score * 100:.1f}%"))

        for r_idx, (label, value) in enumerate(meta_rows, start=1):
            lc = meta_ws.cell(row=r_idx, column=1, value=label)
            lc.font = meta_font
            meta_ws.cell(row=r_idx, column=2, value=value)

        meta_ws.column_dimensions["A"].width = 20
        meta_ws.column_dimensions["B"].width = 30

        wb.save(str(path))
