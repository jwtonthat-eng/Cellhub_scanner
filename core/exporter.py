"""
Exporter: converts a pandas DataFrame to CSV or Excel (.xlsx).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    pass  # AuditOutput imported lazily inside to_audit_excel


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
    # Audit report export  (works with AuditOutput from audit/report/)
    # ------------------------------------------------------------------

    @staticmethod
    def to_audit_excel(output, path: str | Path) -> None:
        """
        Export an AuditOutput to a multi-sheet Excel workbook:
          Sheet 1 — Executive Summary
          Sheet 2 — Line Findings
          Sheet 3 — Risk Flags
          Sheet 4 — Action Plan
          Sheet 5 — Scope & Limitations
        """
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()

        HDR_FILL = PatternFill("solid", fgColor="1F4E79")
        HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
        HDR_ALIGN = Alignment(horizontal="center", vertical="center")
        WRAP = Alignment(wrap_text=True, vertical="top")
        PRIO_COLORS = {
            "DISCONNECT":      "FEE2E2",
            "DOWNGRADE":       "FFEDD5",
            "REMOVE_ADDON":    "EDE9FE",
            "CARRIER_INQUIRY": "FEF9C3",
            "REVIEW":          "DBEAFE",
            "MONITOR":         "DCFCE7",
        }
        SEV_COLORS = {
            "high": "FEE2E2", "medium": "FFEDD5",
            "low":  "FEF9C3", "info":   "DBEAFE",
        }

        def _hdr(ws, cols: list[str]) -> None:
            for ci, name in enumerate(cols, 1):
                c = ws.cell(row=1, column=ci, value=name)
                c.font, c.fill, c.alignment = HDR_FONT, HDR_FILL, HDR_ALIGN

        def _autosize(ws) -> None:
            for col in ws.columns:
                w = max((len(str(cell.value or "")) for cell in col), default=10)
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 2, 60)

        def _kv(ws, row: int, key: str, value) -> None:
            kc = ws.cell(row=row, column=1, value=key)
            kc.font = Font(bold=True)
            ws.cell(row=row, column=2, value=value)

        es = output.executive_summary

        # ── Sheet 1: Executive Summary ──────────────────────────────────
        ws1 = wb.active
        ws1.title = "Executive Summary"
        ws1.cell(row=1, column=1, value="Telecom Bill Audit — Executive Summary").font = Font(bold=True, size=14)
        ws1.merge_cells("A1:D1")
        r = 3
        _kv(ws1, r, "Bill Type",             es.bill_type or "Unknown"); r += 1
        _kv(ws1, r, "Months Analysed",       es.months_analyzed);        r += 1
        _kv(ws1, r, "Month Labels",          ", ".join(es.month_labels)); r += 1
        for lbl, tot in zip(es.month_labels, es.monthly_totals):
            _kv(ws1, r, f"  {lbl} — Total Spend", f"R{tot:,.2f}"); r += 1
        _kv(ws1, r, "Average Monthly Spend", f"R{es.avg_monthly_spend:,.2f}"); r += 1
        r += 1
        _kv(ws1, r, "Total Lines Analysed",     es.total_lines_analyzed);       r += 1
        _kv(ws1, r, "Disconnect Candidates",    es.disconnect_candidates);      r += 1
        _kv(ws1, r, "Downgrade Candidates",     es.downgrade_candidates);       r += 1
        _kv(ws1, r, "Add-On Removals",          es.addon_removal_candidates);   r += 1
        r += 1
        _kv(ws1, r, "Est. Monthly Savings",  f"R{es.estimated_monthly_savings:,.2f}"); r += 1
        _kv(ws1, r, "Est. Annual Savings",   f"R{es.estimated_annual_savings:,.2f}");  r += 1
        r += 1
        _kv(ws1, r, "High Risk Flags",   es.high_risk_flags);   r += 1
        _kv(ws1, r, "Medium Risk Flags", es.medium_risk_flags); r += 1
        r += 1
        _kv(ws1, r, "Generated", es.generated_at); r += 1
        ws1.column_dimensions["A"].width = 38
        ws1.column_dimensions["B"].width = 28

        # ── Sheet 2: Line Findings ──────────────────────────────────────
        ws2 = wb.create_sheet("Line Findings")
        cols2 = ["MSISDN", "Line Type", "Flag", "Plan", "Avg GB",
                 "Avg Charge (R)", "Est. Monthly Saving (R)", "Est. Annual Saving (R)",
                 "Detail", "Action"]
        _hdr(ws2, cols2)
        for ri, f in enumerate(output.line_findings, 2):
            row_data = [
                f.msisdn, f.line_type, f.flag.replace("_", " ").title(),
                f.plan_name, round(f.avg_usage_gb, 2),
                round(f.avg_charge, 2),
                round(f.estimated_monthly_saving, 2) if f.estimated_monthly_saving else "",
                round(f.estimated_annual_saving, 2)  if f.estimated_annual_saving  else "",
                f.detail, f.action,
            ]
            flag_bg = {
                "zero_use": "FEE2E2", "inactive_eia": "FEE2E2",
                "low_use": "FFEDD5", "over_provisioned": "FEF9C3",
                "near_limit": "DBEAFE", "addon": "EDE9FE",
            }.get(f.flag)
            for ci, val in enumerate(row_data, 1):
                cell = ws2.cell(row=ri, column=ci, value=val)
                if flag_bg:
                    cell.fill = PatternFill("solid", fgColor=flag_bg)
                cell.alignment = WRAP
        ws2.freeze_panes = "A2"
        _autosize(ws2)

        # ── Sheet 3: Risk Flags ─────────────────────────────────────────
        ws3 = wb.create_sheet("Risk Flags")
        cols3 = ["Severity", "Flag Type", "Title", "Description",
                 "Impact (R)", "Months", "Action"]
        _hdr(ws3, cols3)
        for ri, f in enumerate(output.risk_flags, 2):
            row_data = [
                f.severity.upper(), f.flag_type, f.title, f.description,
                round(f.delta_rands, 2) if f.delta_rands else "",
                ", ".join(f.months), f.action,
            ]
            for ci, val in enumerate(row_data, 1):
                cell = ws3.cell(row=ri, column=ci, value=val)
                bg = SEV_COLORS.get(f.severity)
                if bg:
                    cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = WRAP
        ws3.freeze_panes = "A2"
        _autosize(ws3)

        # ── Sheet 4: Action Plan ────────────────────────────────────────
        ws4 = wb.create_sheet("Action Plan")
        cols4 = ["Priority", "Category", "MSISDN",
                 "Action", "Est. Monthly Saving (R)", "Est. Annual Saving (R)"]
        _hdr(ws4, cols4)
        for ri, item in enumerate(output.action_plan, 2):
            row_data = [
                item.priority, item.category, item.msisdn, item.description,
                round(item.estimated_monthly_saving, 2) if item.estimated_monthly_saving else "",
                round(item.estimated_annual_saving,  2) if item.estimated_annual_saving  else "",
            ]
            for ci, val in enumerate(row_data, 1):
                cell = ws4.cell(row=ri, column=ci, value=val)
                bg = PRIO_COLORS.get(item.priority)
                if bg:
                    cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = WRAP
        ws4.freeze_panes = "A2"
        _autosize(ws4)

        # ── Sheet 5: Scope & Limitations ────────────────────────────────
        ws5 = wb.create_sheet("Scope & Limitations")
        ws5.cell(row=1, column=1,
                 value="What This Audit Does Not Claim to Do").font = Font(bold=True, size=12)
        for ri, lim in enumerate(output.scope_limitations, 3):
            cell = ws5.cell(row=ri, column=1, value=lim)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws5.row_dimensions[ri].height = 30
        ws5.column_dimensions["A"].width = 100

        wb.save(str(path))
