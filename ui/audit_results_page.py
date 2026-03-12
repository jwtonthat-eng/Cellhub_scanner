"""
AuditResultsPage — displays the AuditReport produced by AuditEngine.

Layout:
  ┌─ Header ────────────────────────────────────────────────────────────┐
  │  Title  |  Executive summary cards (avg spend, savings, findings)  │
  ├─ Body (scrollable) ─────────────────────────────────────────────────┤
  │  Category section heading  ► findings cards                        │
  └─ Footer ────────────────────────────────────────────────────────────┘
  │  [Export Audit Report]   [← New Audit]                             │
"""
from __future__ import annotations

from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from ui.app_window import AppWindow
    from core.audit_report import AuditReport, AuditFinding

_SEV_COLOR = {
    "high":   ("#dc2626", "#ef4444"),
    "medium": ("#ea580c", "#f97316"),
    "low":    ("#ca8a04", "#eab308"),
    "info":   ("#2563eb", "#60a5fa"),
}
_SEV_BG = {
    "high":   ("#fee2e2", "#3b0a0a"),
    "medium": ("#ffedd5", "#3b1608"),
    "low":    ("#fef9c3", "#3b2f00"),
    "info":   ("#dbeafe", "#0c1e42"),
}


class AuditResultsPage(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow", **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._built = False

    # ------------------------------------------------------------------

    def on_show(self) -> None:
        report = self.app.state.get("audit_report")
        if report is None:
            return
        # Rebuild whenever navigated to (report may have changed)
        for w in self.winfo_children():
            w.destroy()
        self._built = False
        self._build_ui(report)
        self._built = True

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self, report: "AuditReport") -> None:
        self._build_header(report)
        self._build_body(report)
        self._build_footer(report)

    # ── Header ────────────────────────────────────────────────────────

    def _build_header(self, report: "AuditReport") -> None:
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=32, pady=(24, 8))
        hdr.grid_columnconfigure(1, weight=1)

        # Title block
        title_block = ctk.CTkFrame(hdr, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block, text="Audit Report",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w")
        months_str = " · ".join(report.month_labels)
        ctk.CTkLabel(
            title_block,
            text=f"{report.bill_type or 'Unknown'}  |  {months_str}",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", pady=(2, 0))

        # Summary cards
        cards = ctk.CTkFrame(hdr, fg_color="transparent")
        cards.grid(row=0, column=1, sticky="e")
        es = report.executive_summary

        avg_spend = es.get("avg_monthly_spend", report.total_monthly_avg)
        monthly_save = es.get("estimated_monthly_savings", report.total_estimated_monthly_savings)
        annual_save  = es.get("estimated_annual_savings",  report.total_estimated_annual_savings)
        high_count   = es.get("high_priority_findings", 0)
        total_count  = es.get("total_findings", len(report.findings))

        card_data = [
            ("Avg Monthly Spend",        f"R{avg_spend:,.2f}",      ("gray20", "gray80")),
            ("Est. Monthly Savings",     f"R{monthly_save:,.2f}",   ("#16a34a", "#22c55e")),
            ("Est. Annual Savings",      f"R{annual_save:,.2f}",    ("#16a34a", "#22c55e")),
            ("High-Priority Findings",   str(high_count),           ("#dc2626", "#ef4444")),
            ("Total Findings",           str(total_count),          ("gray30", "gray70")),
        ]
        for label, value, color in card_data:
            self._summary_card(cards, label, value, color).pack(side="left", padx=6)

        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).grid(
            row=0, column=0, sticky="ew", padx=24)

    def _summary_card(self, parent, label: str, value: str, color) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=8, width=120)
        ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=color,
        ).pack(padx=12, pady=(8, 2))
        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray55"),
            wraplength=110,
        ).pack(padx=12, pady=(0, 8))
        return card

    # ── Body ──────────────────────────────────────────────────────────

    def _build_body(self, report: "AuditReport") -> None:
        from core.audit_engine import AuditEngine
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        by_cat = report.findings_by_category

        for cat_key, cat_label in AuditEngine.CATEGORY_LABELS.items():
            findings = by_cat.get(cat_key, [])
            self._build_category_section(scroll, cat_label, findings)

    def _build_category_section(
        self,
        parent,
        label: str,
        findings: list["AuditFinding"],
    ) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.pack(fill="x", pady=(16, 0))
        section.grid_columnconfigure(0, weight=1)

        # Section heading
        heading = ctk.CTkFrame(section, fg_color=("gray90", "gray18"), corner_radius=6)
        heading.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            heading, text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=12, pady=6)

        if not findings:
            ctk.CTkLabel(
                section,
                text="No findings for this category.",
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray55"),
            ).pack(anchor="w", padx=12, pady=4)
            return

        for finding in findings:
            self._build_finding_card(section, finding)

    def _build_finding_card(self, parent, finding: "AuditFinding") -> None:
        sev   = finding.severity
        color = _SEV_COLOR.get(sev, ("gray40", "gray60"))
        bg    = _SEV_BG.get(sev,   ("gray95", "gray15"))

        card = ctk.CTkFrame(parent, corner_radius=8, fg_color=bg)
        card.pack(fill="x", pady=4, padx=4)
        card.grid_columnconfigure(1, weight=1)

        # Severity badge
        badge = ctk.CTkLabel(
            card,
            text=sev.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color,
            width=64, anchor="center",
        )
        badge.grid(row=0, column=0, rowspan=3, padx=(12, 8), pady=12, sticky="n")

        # Title
        ctk.CTkLabel(
            card, text=finding.title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            wraplength=700,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 2))

        # Description
        ctk.CTkLabel(
            card, text=finding.description,
            font=ctk.CTkFont(size=11),
            anchor="w",
            justify="left",
            text_color=("gray20", "gray80"),
            wraplength=700,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=2)

        # Action row
        action_frame = ctk.CTkFrame(card, fg_color="transparent")
        action_frame.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(2, 10))

        if finding.action:
            ctk.CTkLabel(
                action_frame,
                text=f"Action: {finding.action}",
                font=ctk.CTkFont(size=11),
                text_color=("gray35", "gray65"),
                wraplength=680,
                anchor="w",
                justify="left",
            ).pack(side="left", fill="x", expand=True)

        if finding.estimated_monthly_savings > 0:
            ctk.CTkLabel(
                action_frame,
                text=f"≈ R{finding.estimated_monthly_savings:,.2f}/mo  "
                     f"(R{finding.estimated_annual_savings:,.2f}/yr)",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#16a34a", "#22c55e"),
            ).pack(side="right")

        if finding.affected_lines:
            lines_str = ", ".join(finding.affected_lines[:6])
            if len(finding.affected_lines) > 6:
                lines_str += f" +{len(finding.affected_lines) - 6} more"
            ctk.CTkLabel(
                card,
                text=f"Lines: {lines_str}",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray60"),
                anchor="w",
            ).grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=(0, 8))

    # ── Footer ────────────────────────────────────────────────────────

    def _build_footer(self, report: "AuditReport") -> None:
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).grid(
            row=2, column=0, sticky="ew", padx=24)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=32, pady=16)
        footer.grid_columnconfigure(0, weight=1)

        self._export_status = ctk.StringVar(value="")
        ctk.CTkLabel(
            footer, textvariable=self._export_status,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_frame.grid(row=0, column=1)

        ctk.CTkButton(
            btn_frame, text="← New Audit",
            width=130, height=40,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            border_color=("gray60", "gray45"),
            text_color=("gray20", "gray80"),
            command=lambda: self.app.show_page("audit"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Export Audit Report →",
            width=200, height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._export,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export(self) -> None:
        report = self.app.state.get("audit_report")
        if report is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save Audit Report",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")],
            initialfile="audit_report.xlsx",
        )
        if not path:
            return
        try:
            from core.exporter import Exporter
            Exporter.to_audit_excel(report, path)
            self._export_status.set(f"Saved: {path}")
        except Exception as exc:  # noqa: BLE001
            self._export_status.set(f"Export failed: {exc}")
