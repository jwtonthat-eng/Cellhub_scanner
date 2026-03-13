"""
AuditResultsPage — displays the AuditOutput produced by the new AuditEngine.

Tabs:
  Executive Summary  — spend cards + savings opportunity cards
  Line Inventory     — scrollable table of all BilledLines with flags
  Risk Flags         — billing consistency + discount anomalies
  Action Plan        — prioritised action list (DISCONNECT / DOWNGRADE / etc.)
  Scope & Limits     — explicit constraints baked into every audit
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from ui.app_window import AppWindow
    from audit.report.report_builder import AuditOutput, LineLevelFinding, RiskFlag, ActionItem

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
_FLAG_COLOR = {
    "zero_use":         ("#dc2626", "#ef4444"),
    "inactive_eia":     ("#dc2626", "#ef4444"),
    "low_use":          ("#ea580c", "#f97316"),
    "over_provisioned": ("#ca8a04", "#eab308"),
    "near_limit":       ("#2563eb", "#60a5fa"),
    "addon":            ("#7c3aed", "#a78bfa"),
}
_PRIORITY_COLOR = {
    "DISCONNECT":      ("#dc2626", "#ef4444"),
    "DOWNGRADE":       ("#ea580c", "#f97316"),
    "REMOVE_ADDON":    ("#7c3aed", "#a78bfa"),
    "INACTIVE_EIA":    ("#dc2626", "#ef4444"),
    "CARRIER_INQUIRY": ("#ca8a04", "#eab308"),
    "REVIEW":          ("#2563eb", "#60a5fa"),
    "MONITOR":         ("#16a34a", "#22c55e"),
}


class AuditResultsPage(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow", **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

    def on_show(self) -> None:
        output: "AuditOutput | None" = self.app.state.get("audit_report")
        if output is None:
            return
        for w in self.winfo_children():
            w.destroy()
        self._build_ui(output)

    # ------------------------------------------------------------------
    # Top-level structure
    # ------------------------------------------------------------------

    def _build_ui(self, output: "AuditOutput") -> None:
        self._build_header(output)

        tabs = ctk.CTkTabview(self, anchor="nw")
        tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        tabs.grid_columnconfigure(0, weight=1)

        for name in ("Executive Summary", "Line Inventory",
                     "Risk Flags", "Action Plan", "Scope & Limits"):
            tabs.add(name)

        self._build_executive_tab(tabs.tab("Executive Summary"), output)
        self._build_line_tab(tabs.tab("Line Inventory"), output)
        self._build_risk_tab(tabs.tab("Risk Flags"), output)
        self._build_action_tab(tabs.tab("Action Plan"), output)
        self._build_scope_tab(tabs.tab("Scope & Limits"), output)

        self._build_footer(output)

    # ── Header bar ────────────────────────────────────────────────────

    def _build_header(self, output: "AuditOutput") -> None:
        es = output.executive_summary
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        hdr.grid_columnconfigure(1, weight=1)

        title_blk = ctk.CTkFrame(hdr, fg_color="transparent")
        title_blk.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_blk, text="Audit Report",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_blk,
            text=f"{es.bill_type or 'Unknown'} · {' | '.join(es.month_labels)}",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", pady=(2, 0))

        # Quick stats
        stats = ctk.CTkFrame(hdr, fg_color="transparent")
        stats.grid(row=0, column=1, sticky="e")
        card_data = [
            ("Lines Analysed",       str(es.total_lines_analyzed),             ("gray20", "gray80")),
            ("Avg Monthly Spend",    f"R{es.avg_monthly_spend:,.2f}",          ("gray20", "gray80")),
            ("Est. Monthly Saving",  f"R{es.estimated_monthly_savings:,.2f}",  ("#16a34a", "#22c55e")),
            ("Est. Annual Saving",   f"R{es.estimated_annual_savings:,.2f}",   ("#16a34a", "#22c55e")),
            ("High Risk Flags",      str(es.high_risk_flags),                  ("#dc2626", "#ef4444")),
        ]
        for label, value, color in card_data:
            self._stat_card(stats, label, value, color).pack(side="left", padx=4)

        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).grid(
            row=0, column=0, sticky="ew", padx=16)

    def _stat_card(self, parent, label: str, value: str, color) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=8, width=110)
        ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=color,
        ).pack(padx=10, pady=(8, 1))
        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(size=9),
            text_color=("gray50", "gray55"),
            wraplength=100,
        ).pack(padx=10, pady=(0, 8))
        return card

    # ── Tab: Executive Summary ────────────────────────────────────────

    def _build_executive_tab(self, tab, output: "AuditOutput") -> None:
        tab.grid_columnconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure((0, 1), weight=1)

        es = output.executive_summary

        # Monthly spend row
        self._section_heading(scroll, "Monthly Spend", row=0, colspan=2)
        spend_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        spend_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        for lbl, total in zip(es.month_labels, es.monthly_totals):
            f = ctk.CTkFrame(spend_frame, corner_radius=8)
            f.pack(side="left", padx=6, pady=4)
            ctk.CTkLabel(f, text=lbl,  font=ctk.CTkFont(size=10), text_color=("gray50","gray55")).pack(padx=12, pady=(6,1))
            ctk.CTkLabel(f, text=f"R{total:,.2f}", font=ctk.CTkFont(size=15, weight="bold")).pack(padx=12, pady=(0,6))

        # Savings opportunity
        self._section_heading(scroll, "Savings Opportunity", row=2, colspan=2)
        sav_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        sav_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        sav_items = [
            ("Disconnect Candidates",    es.disconnect_candidates,    "DISCONNECT"),
            ("Downgrade Candidates",     es.downgrade_candidates,     "DOWNGRADE"),
            ("Add-On Removal Candidates",es.addon_removal_candidates, "REMOVE_ADDON"),
        ]
        for label, count, prio in sav_items:
            color = _PRIORITY_COLOR.get(prio, ("gray40","gray60"))
            f = ctk.CTkFrame(sav_frame, corner_radius=8)
            f.pack(side="left", padx=6, pady=4)
            ctk.CTkLabel(f, text=str(count), font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color).pack(padx=14, pady=(8,1))
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10),
                         text_color=("gray50","gray55"), wraplength=110).pack(padx=14, pady=(0,8))

        # Summary totals
        self._section_heading(scroll, "Estimated Impact", row=4, colspan=2)
        tot_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        tot_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        for label, value in [
            ("Est. Monthly Savings",  f"R{es.estimated_monthly_savings:,.2f}"),
            ("Est. Annual Savings",   f"R{es.estimated_annual_savings:,.2f}"),
            ("High Risk Flags",       str(es.high_risk_flags)),
            ("Medium Risk Flags",     str(es.medium_risk_flags)),
        ]:
            f = ctk.CTkFrame(tot_frame, corner_radius=8)
            f.pack(side="left", padx=6, pady=4)
            ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=("#16a34a","#22c55e")).pack(padx=12, pady=(8,1))
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10),
                         text_color=("gray50","gray55"), wraplength=120).pack(padx=12, pady=(0,8))

    # ── Tab: Line Inventory ───────────────────────────────────────────

    def _build_line_tab(self, tab, output: "AuditOutput") -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Column headers
        cols = ["MSISDN", "Type", "Plan", "Avg GB", "Avg Charge", "Flag", "Action Summary"]
        widths = [120, 90, 180, 64, 90, 120, 0]

        hdr_frame = ctk.CTkFrame(tab, fg_color=("gray85", "gray20"), corner_radius=6)
        hdr_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        for i, (col, w) in enumerate(zip(cols, widths)):
            ctk.CTkLabel(
                hdr_frame, text=col,
                font=ctk.CTkFont(size=11, weight="bold"),
                width=w if w else 0,
                anchor="w",
            ).grid(row=0, column=i, padx=6, pady=4, sticky="ew" if w == 0 else "w")
            if w == 0:
                hdr_frame.grid_columnconfigure(i, weight=1)

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        scroll.grid_columnconfigure(6, weight=1)

        findings = output.line_findings
        if not findings:
            ctk.CTkLabel(scroll, text="No per-line findings detected.",
                         font=ctk.CTkFont(size=12), text_color=("gray50","gray55")).pack(pady=20)
            return

        for ri, f in enumerate(findings):
            bg = ("gray96", "gray14") if ri % 2 == 0 else ("gray91", "gray18")
            row_frame = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row_frame.pack(fill="x", pady=1)
            row_frame.grid_columnconfigure(6, weight=1)

            flag_color = _FLAG_COLOR.get(f.flag, ("gray40","gray60"))
            row_data = [
                (f.msisdn,                    widths[0]),
                (f.line_type or "—",          widths[1]),
                (f.plan_name[:24] or "—",     widths[2]),
                (f"{f.avg_usage_gb:.2f}",     widths[3]),
                (f"R{f.avg_charge:,.2f}",     widths[4]),
                (f.flag.replace("_"," ").title(), widths[5]),
            ]
            for ci, (val, w) in enumerate(row_data):
                color = flag_color if ci == 5 else ("gray10","gray90")
                ctk.CTkLabel(
                    row_frame, text=val,
                    font=ctk.CTkFont(size=11),
                    text_color=color,
                    width=w if w else 0,
                    anchor="w",
                ).grid(row=0, column=ci, padx=6, pady=3, sticky="ew" if w == 0 else "w")

            # Action summary (last column, expandable)
            ctk.CTkLabel(
                row_frame,
                text=f.action[:80] + ("…" if len(f.action) > 80 else ""),
                font=ctk.CTkFont(size=10),
                text_color=("gray40","gray60"),
                anchor="w",
            ).grid(row=0, column=6, padx=6, pady=3, sticky="ew")

    # ── Tab: Risk Flags ───────────────────────────────────────────────

    def _build_risk_tab(self, tab, output: "AuditOutput") -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        flags = output.risk_flags
        if not flags:
            ctk.CTkLabel(scroll, text="No billing risk flags detected.",
                         font=ctk.CTkFont(size=12), text_color=("gray50","gray55")).pack(pady=20)
            return

        for f in flags:
            self._risk_card(scroll, f)

    def _risk_card(self, parent, f: "RiskFlag") -> None:
        color = _SEV_COLOR.get(f.severity, ("gray40","gray60"))
        bg    = _SEV_BG.get(f.severity, ("gray95","gray15"))
        card  = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8)
        card.pack(fill="x", pady=4)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=f.severity.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color, width=60, anchor="center",
        ).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10, sticky="n")

        ctk.CTkLabel(card, text=f.title, font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w", wraplength=680,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 2))

        ctk.CTkLabel(card, text=f.description,
                     font=ctk.CTkFont(size=11), anchor="w", justify="left",
                     text_color=("gray20","gray80"), wraplength=680,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=2)

        if f.action:
            ctk.CTkLabel(
                card,
                text=f"Action: {f.action}",
                font=ctk.CTkFont(size=11),
                text_color=("gray35","gray65"), wraplength=680, anchor="w",
            ).grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(2, 10))

        if f.delta_rands > 0:
            ctk.CTkLabel(
                card,
                text=f"Impact: R{f.delta_rands:,.2f}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#dc2626","#ef4444"),
            ).grid(row=0, column=2, padx=12, pady=10, sticky="ne")

    # ── Tab: Action Plan ──────────────────────────────────────────────

    def _build_action_tab(self, tab, output: "AuditOutput") -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Header row
        col_labels = ["Priority", "Category", "MSISDN", "Description",
                      "Est. Monthly (R)", "Est. Annual (R)"]
        hdr = ctk.CTkFrame(tab, fg_color=("gray85","gray20"), corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        hdr.grid_columnconfigure(3, weight=1)
        for ci, label in enumerate(col_labels):
            ctk.CTkLabel(
                hdr, text=label,
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).grid(row=0, column=ci, padx=8, pady=4, sticky="ew" if ci == 3 else "w")

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        scroll.grid_columnconfigure(3, weight=1)

        items = output.action_plan
        if not items:
            ctk.CTkLabel(scroll, text="No action items generated.",
                         font=ctk.CTkFont(size=12), text_color=("gray50","gray55")).pack(pady=20)
            return

        for ri, item in enumerate(items):
            bg = ("gray96","gray14") if ri % 2 == 0 else ("gray91","gray18")
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)
            row.grid_columnconfigure(3, weight=1)

            prio_color = _PRIORITY_COLOR.get(item.priority, ("gray40","gray60"))
            cells = [
                (item.priority,                                  prio_color,            80),
                (item.category,                                  ("gray20","gray80"),   120),
                (item.msisdn,                                    ("gray20","gray80"),   110),
                (item.description[:70] + ("…" if len(item.description)>70 else ""),
                                                                 ("gray40","gray65"),   0),
                (f"{item.estimated_monthly_saving:,.2f}",       ("#16a34a","#22c55e"), 110),
                (f"{item.estimated_annual_saving:,.2f}",        ("#16a34a","#22c55e"), 110),
            ]
            for ci, (val, color, w) in enumerate(cells):
                ctk.CTkLabel(
                    row, text=val,
                    font=ctk.CTkFont(size=11),
                    text_color=color,
                    anchor="w",
                    width=w if w else 0,
                ).grid(row=0, column=ci, padx=8, pady=3,
                       sticky="ew" if w == 0 else "w")

    # ── Tab: Scope & Limits ───────────────────────────────────────────

    def _build_scope_tab(self, tab, output: "AuditOutput") -> None:
        tab.grid_columnconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            scroll,
            text="What This Audit Does Not Claim to Do",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", pady=(4, 12))

        for lim in output.scope_limitations:
            row = ctk.CTkFrame(scroll, fg_color=("gray93","gray17"), corner_radius=6)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text="⚠", font=ctk.CTkFont(size=13),
                text_color=("#ca8a04","#eab308"), width=28,
            ).pack(side="left", padx=(10, 4), pady=10)
            ctk.CTkLabel(
                row, text=lim,
                font=ctk.CTkFont(size=11),
                text_color=("gray20","gray80"),
                anchor="w", justify="left",
                wraplength=700,
            ).pack(side="left", fill="x", expand=True, padx=(0, 12), pady=10)

    # ── Footer ────────────────────────────────────────────────────────

    def _build_footer(self, output: "AuditOutput") -> None:
        ctk.CTkFrame(self, height=1, fg_color=("gray80","gray30")).grid(
            row=2, column=0, sticky="ew", padx=16)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=12)
        footer.grid_columnconfigure(0, weight=1)

        self._export_status = ctk.StringVar(value="")
        ctk.CTkLabel(
            footer, textvariable=self._export_status,
            font=ctk.CTkFont(size=11), text_color=("gray40","gray60"),
        ).grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_frame.grid(row=0, column=1)

        ctk.CTkButton(
            btn_frame, text="← New Audit",
            width=130, height=40,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            border_color=("gray60","gray45"),
            text_color=("gray20","gray80"),
            command=lambda: self.app.show_page("audit"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Export Audit Report →",
            width=200, height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._export,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section_heading(self, parent, text: str, row: int, colspan: int = 1) -> None:
        frame = ctk.CTkFrame(parent, fg_color=("gray88","gray22"), corner_radius=6)
        frame.grid(row=row, column=0, columnspan=colspan, sticky="ew", padx=4, pady=(12, 4))
        ctk.CTkLabel(
            frame, text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=12, pady=5)

    def _export(self) -> None:
        output: "AuditOutput | None" = self.app.state.get("audit_report")
        if output is None:
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
            Exporter.to_audit_excel(output, path)
            self._export_status.set(f"Saved: {path}")
        except Exception as exc:  # noqa: BLE001
            self._export_status.set(f"Export failed: {exc}")
