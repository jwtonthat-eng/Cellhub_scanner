"""
Exporter: converts a pandas DataFrame to CSV or Excel (.xlsx).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from core.audit_report import AuditReport


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

    # ------------------------------------------------------------------
    # Audit report export
    # ------------------------------------------------------------------

    @staticmethod
    def to_audit_excel(report: "AuditReport", path: str | Path) -> None:  # noqa: F821
        """
        Export an AuditReport to a multi-sheet Excel workbook:
          Sheet 1 — Executive Summary
          Sheet 2 — All Findings (line-level detail)
          Sheet 3 — Risk Flags
          Sheet 4 — Action Plan
        """
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()

        # Colour palette
        HDR_FILL   = PatternFill("solid", fgColor="1F4E79")   # dark blue
        HDR_FONT   = Font(bold=True, color="FFFFFF", size=10)
        HDR_ALIGN  = Alignment(horizontal="center", vertical="center")
        TITLE_FONT = Font(bold=True, size=12)
        SEV_COLORS = {
            "high":   "FEE2E2",
            "medium": "FFEDD5",
            "low":    "FEF9C3",
            "info":   "DBEAFE",
        }

        def _write_header(ws, columns: list[str], row: int = 1) -> None:
            for ci, name in enumerate(columns, 1):
                c = ws.cell(row=row, column=ci, value=name)
                c.font  = HDR_FONT
                c.fill  = HDR_FILL
                c.alignment = HDR_ALIGN

        def _autosize(ws) -> None:
            for col in ws.columns:
                width = max((len(str(cell.value or "")) for cell in col), default=10)
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(width + 2, 60)

        # ── Sheet 1: Executive Summary ──────────────────────────────────
        ws1 = wb.active
        ws1.title = "Executive Summary"
        es = report.executive_summary

        def _kv(ws, row: int, key: str, value) -> None:
            kc = ws.cell(row=row, column=1, value=key)
            kc.font = Font(bold=True)
            ws.cell(row=row, column=2, value=value)

        ws1.cell(row=1, column=1, value="Telecom Bill Audit — Executive Summary").font = Font(bold=True, size=14)
        ws1.merge_cells("A1:D1")
        r = 3
        _kv(ws1, r, "Bill Type",              report.bill_type or "Unknown"); r += 1
        _kv(ws1, r, "Months Analysed",        report.months_analyzed);        r += 1
        _kv(ws1, r, "Month Labels",           ", ".join(report.month_labels)); r += 1
        totals = es.get("monthly_totals", [])
        for i, (lbl, tot) in enumerate(zip(report.month_labels, totals)):
            _kv(ws1, r, f"  {lbl} — Total Spend", f"R{tot:,.2f}"); r += 1
        _kv(ws1, r, "Average Monthly Spend",        f"R{report.total_monthly_avg:,.2f}"); r += 1
        r += 1
        _kv(ws1, r, "Total Findings",               es.get("total_findings", len(report.findings))); r += 1
        _kv(ws1, r, "High-Priority Findings",       es.get("high_priority_findings", 0)); r += 1
        _kv(ws1, r, "Medium-Priority Findings",     es.get("medium_priority_findings", 0)); r += 1
        r += 1
        _kv(ws1, r, "Est. Monthly Savings Opportunity", f"R{report.total_estimated_monthly_savings:,.2f}"); r += 1
        _kv(ws1, r, "Est. Annual Savings Opportunity",  f"R{report.total_estimated_annual_savings:,.2f}"); r += 1
        r += 1
        _kv(ws1, r, "Export Date", datetime.now().strftime("%Y-%m-%d %H:%M")); r += 1
        ws1.column_dimensions["A"].width = 38
        ws1.column_dimensions["B"].width = 28

        # ── Sheet 2: All Findings ───────────────────────────────────────
        ws2 = wb.create_sheet("All Findings")
        cols2 = ["Category", "Severity", "Title", "Description",
                 "Est. Monthly Saving (R)", "Est. Annual Saving (R)", "Affected Lines", "Action"]
        _write_header(ws2, cols2)
        for ri, f in enumerate(report.findings, 2):
            row_data = [
                f.category,
                f.severity.upper(),
                f.title,
                f.description,
                round(f.estimated_monthly_savings, 2) if f.estimated_monthly_savings else "",
                round(f.estimated_annual_savings, 2)  if f.estimated_annual_savings  else "",
                ", ".join(f.affected_lines[:10]),
                f.action,
            ]
            for ci, val in enumerate(row_data, 1):
                cell = ws2.cell(row=ri, column=ci, value=val)
                bg = SEV_COLORS.get(f.severity)
                if bg:
                    cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws2.freeze_panes = "A2"
        ws2.row_dimensions[1].height = 20
        for ri in range(2, len(report.findings) + 2):
            ws2.row_dimensions[ri].height = 45
        _autosize(ws2)

        # ── Sheet 3: Risk Flags ─────────────────────────────────────────
        ws3 = wb.create_sheet("Risk Flags")
        cols3 = ["Severity", "Category", "Risk", "Description", "Action"]
        _write_header(ws3, cols3)
        risk_findings = report.risk_flags
        if not risk_findings:
            # Fallback: high + medium findings across all categories
            risk_findings = [f for f in report.findings if f.severity in ("high", "medium")]
        for ri, f in enumerate(risk_findings, 2):
            row_data = [f.severity.upper(), f.category, f.title, f.description, f.action]
            for ci, val in enumerate(row_data, 1):
                cell = ws3.cell(row=ri, column=ci, value=val)
                bg = SEV_COLORS.get(f.severity)
                if bg:
                    cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws3.freeze_panes = "A2"
        _autosize(ws3)

        # ── Sheet 4: Action Plan ────────────────────────────────────────
        ws4 = wb.create_sheet("Action Plan")
        cols4 = ["Priority", "Category", "Action", "Est. Monthly Saving (R)", "Affected Lines"]
        _write_header(ws4, cols4)
        for ri, item in enumerate(report.action_plan, 2):
            row_data = [
                item["priority"],
                item["category"],
                item["action"],
                round(item["estimated_monthly_saving"], 2) if item["estimated_monthly_saving"] else "",
                item["affected_lines"],
            ]
            for ci, val in enumerate(row_data, 1):
                cell = ws4.cell(row=ri, column=ci, value=val)
                sev = item["priority"].lower()
                bg  = SEV_COLORS.get(sev)
                if bg:
                    cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws4.freeze_panes = "A2"
        _autosize(ws4)

        wb.save(str(path))
