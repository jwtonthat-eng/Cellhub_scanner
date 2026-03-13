"""
ReportBuilder — assembles all module outputs into a single AuditOutput.

AuditOutput contains the four client-facing sections defined in the brief:
  1. Executive Summary
  2. Line-Level Findings
  3. Billing Risk Flags
  4. Action Plan

It also carries an explicit scope_limitations list so the output never
overstates what a 3-bill audit can deliver.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audit.parser.line_extractor import BilledLine
    from audit.analysis.usage_analyzer import UsageFinding
    from audit.analysis.addon_auditor import AddOnFinding
    from audit.billing.consistency_checker import BillingFlag
    from audit.billing.discount_validator import DiscountFlag
    from core.audit_report import AuditFinding

# ---------------------------------------------------------------------------
# Explicit scope constraints — printed verbatim in every export
# ---------------------------------------------------------------------------

SCOPE_LIMITATIONS: list[str] = [
    "Without the signed contract we cannot verify compliance against agreed pricing.",
    "We cannot confirm employment status or terminated-employee lines — HR data required.",
    "Three months of bills is insufficient to assess seasonal usage patterns.",
    "Tax recommendations are limited to consistency flagging; statutory taxes cannot be eliminated.",
    "Feature usage validation (insurance, voicemail, etc.) requires end-user confirmation — "
    "bill data alone cannot confirm whether a feature was actively used.",
    "Device lifecycle, refresh cycles, and competitive carrier benchmarking are outside scope.",
    "Any vendor claiming full strategic optimisation from 3 bills alone is overstating scope.",
]


# ---------------------------------------------------------------------------
# Output data classes
# ---------------------------------------------------------------------------

@dataclass
class LineLevelFinding:
    """Represents one actionable finding about a specific line."""
    msisdn:         str
    line_type:      str
    flag:           str
    avg_usage_gb:   float
    plan_name:      str
    avg_charge:     float
    estimated_monthly_saving: float
    estimated_annual_saving:  float
    detail:         str
    action:         str
    category:       str   # "usage" | "addon" | "installment"


@dataclass
class RiskFlag:
    severity:    str
    flag_type:   str
    title:       str
    description: str
    delta_rands: float
    action:      str
    months:      list[str]


@dataclass
class ActionItem:
    priority:        str   # DISCONNECT | DOWNGRADE | REMOVE_ADDON | REVIEW | MONITOR
    category:        str
    msisdn:          str
    description:     str
    estimated_monthly_saving: float
    estimated_annual_saving:  float


@dataclass
class ExecutiveSummary:
    bill_type:              str
    months_analyzed:        int
    month_labels:           list[str]
    monthly_totals:         list[float]
    avg_monthly_spend:      float
    total_lines_analyzed:   int
    # Savings breakdown
    disconnect_candidates:    int
    downgrade_candidates:     int
    addon_removal_candidates: int
    estimated_monthly_savings: float
    estimated_annual_savings:  float
    # Risk counts
    high_risk_flags:   int
    medium_risk_flags: int
    # Timestamps
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))


@dataclass
class AuditOutput:
    executive_summary:  ExecutiveSummary
    line_findings:      list[LineLevelFinding]
    risk_flags:         list[RiskFlag]
    action_plan:        list[ActionItem]
    scope_limitations:  list[str]

    # ------------------------------------------------------------------
    # Convenience groupings
    # ------------------------------------------------------------------

    @property
    def disconnect_candidates(self) -> list[LineLevelFinding]:
        return [f for f in self.line_findings if f.flag == "zero_use"]

    @property
    def downgrade_candidates(self) -> list[LineLevelFinding]:
        return [f for f in self.line_findings if f.flag in ("low_use", "over_provisioned")]

    @property
    def addon_removal_candidates(self) -> list[LineLevelFinding]:
        return [f for f in self.line_findings if f.category == "addon"]

    @property
    def carrier_inquiry_items(self) -> list[RiskFlag]:
        return [f for f in self.risk_flags if f.flag_type in
                ("credit_drop", "reduced_discount", "tax_anomaly", "charge_volatility")]

    @property
    def total_estimated_monthly_savings(self) -> float:
        return sum(f.estimated_monthly_saving for f in self.action_plan)

    @property
    def total_estimated_annual_savings(self) -> float:
        return sum(f.estimated_annual_saving for f in self.action_plan)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class ReportBuilder:

    def build(
        self,
        *,
        bill_type:       str,
        month_labels:    list[str],
        monthly_totals:  list[float],
        billed_lines:    list["BilledLine"],
        usage_findings:  list["UsageFinding"],
        addon_findings:  list["AddOnFinding"],
        billing_flags:   list["BillingFlag"],
        discount_flags:  list["DiscountFlag"],
    ) -> AuditOutput:

        line_findings = self._build_line_findings(usage_findings, addon_findings)
        risk_flags    = self._build_risk_flags(billing_flags, discount_flags)
        action_plan   = self._build_action_plan(usage_findings, addon_findings, billing_flags)
        summary       = self._build_summary(
            bill_type, month_labels, monthly_totals,
            billed_lines, line_findings, risk_flags,
        )

        return AuditOutput(
            executive_summary=summary,
            line_findings=line_findings,
            risk_flags=risk_flags,
            action_plan=action_plan,
            scope_limitations=SCOPE_LIMITATIONS,
        )

    # ------------------------------------------------------------------

    def _build_line_findings(
        self,
        usage: list["UsageFinding"],
        addons: list["AddOnFinding"],
    ) -> list[LineLevelFinding]:
        results: list[LineLevelFinding] = []

        for f in usage:
            results.append(LineLevelFinding(
                msisdn=f.msisdn,
                line_type=f.line_type,
                flag=f.flag,
                avg_usage_gb=f.avg_usage_gb,
                plan_name=f.plan_name,
                avg_charge=f.avg_monthly_charge,
                estimated_monthly_saving=f.estimated_monthly_saving,
                estimated_annual_saving=f.estimated_annual_saving,
                detail=f.detail,
                action=f.action,
                category="usage",
            ))

        for f in addons:
            results.append(LineLevelFinding(
                msisdn=f.msisdn,
                line_type="",
                flag="addon",
                avg_usage_gb=0.0,
                plan_name=f.add_on,
                avg_charge=f.avg_monthly_charge,
                estimated_monthly_saving=f.estimated_monthly_saving,
                estimated_annual_saving=f.estimated_annual_saving,
                detail=f.detail,
                action=f.action,
                category="addon",
            ))

        # Sort: zero_use first, then low_use, over_provisioned, addons, rest
        order = {"zero_use": 0, "inactive_eia": 1, "low_use": 2,
                 "over_provisioned": 3, "addon": 4, "near_limit": 5}
        results.sort(key=lambda x: (order.get(x.flag, 9), x.msisdn))
        return results

    def _build_risk_flags(
        self,
        billing: list["BillingFlag"],
        discount: list["DiscountFlag"],
    ) -> list[RiskFlag]:
        results: list[RiskFlag] = []
        sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}

        for f in billing:
            results.append(RiskFlag(
                severity=f.severity,
                flag_type=f.flag_type,
                title=f.title,
                description=f.description,
                delta_rands=f.delta_rands,
                action=f.action,
                months=f.months,
            ))
        for f in discount:
            results.append(RiskFlag(
                severity=f.severity,
                flag_type=f.flag_type,
                title=f.title,
                description=f.description,
                delta_rands=0.0,
                action=f.action,
                months=f.months,
            ))

        results.sort(key=lambda x: sev_order.get(x.severity, 9))
        return results

    def _build_action_plan(
        self,
        usage:   list["UsageFinding"],
        addons:  list["AddOnFinding"],
        billing: list["BillingFlag"],
    ) -> list[ActionItem]:
        items: list[ActionItem] = []

        # Disconnect candidates
        for f in usage:
            if f.flag == "zero_use":
                items.append(ActionItem(
                    priority="DISCONNECT",
                    category="Line Inventory",
                    msisdn=f.msisdn,
                    description=f.action,
                    estimated_monthly_saving=f.estimated_monthly_saving,
                    estimated_annual_saving=f.estimated_annual_saving,
                ))

        # Downgrade candidates
        for f in usage:
            if f.flag in ("low_use", "over_provisioned"):
                items.append(ActionItem(
                    priority="DOWNGRADE",
                    category="Rate Plan",
                    msisdn=f.msisdn,
                    description=f.action,
                    estimated_monthly_saving=f.estimated_monthly_saving,
                    estimated_annual_saving=f.estimated_annual_saving,
                ))

        # Inactive EIA
        for f in usage:
            if f.flag == "inactive_eia":
                items.append(ActionItem(
                    priority="REVIEW",
                    category="Equipment Installment",
                    msisdn=f.msisdn,
                    description=f.action,
                    estimated_monthly_saving=f.estimated_monthly_saving,
                    estimated_annual_saving=f.estimated_annual_saving,
                ))

        # Add-on removal
        for f in addons:
            if f.estimated_monthly_saving > 0:
                items.append(ActionItem(
                    priority="REMOVE_ADDON",
                    category="Feature Charges",
                    msisdn=f.msisdn,
                    description=f.action,
                    estimated_monthly_saving=f.estimated_monthly_saving,
                    estimated_annual_saving=f.estimated_annual_saving,
                ))

        # Carrier inquiry items from billing flags
        for f in billing:
            if f.flag_type in ("credit_drop", "charge_volatility"):
                items.append(ActionItem(
                    priority="CARRIER_INQUIRY",
                    category="Billing Consistency",
                    msisdn="ACCOUNT",
                    description=f.action,
                    estimated_monthly_saving=max(f.delta_rands, 0),
                    estimated_annual_saving=max(f.delta_rands, 0) * 12,
                ))

        return items

    def _build_summary(
        self,
        bill_type:    str,
        month_labels: list[str],
        monthly_totals: list[float],
        lines:        list["BilledLine"],
        line_findings: list[LineLevelFinding],
        risk_flags:   list[RiskFlag],
    ) -> ExecutiveSummary:
        import numpy as np
        avg_spend = float(np.mean(monthly_totals)) if monthly_totals else 0.0

        disconnect  = sum(1 for f in line_findings if f.flag == "zero_use")
        downgrade   = sum(1 for f in line_findings if f.flag in ("low_use", "over_provisioned"))
        addon_rm    = sum(1 for f in line_findings if f.category == "addon")
        monthly_sav = sum(f.estimated_monthly_saving for f in line_findings)
        high_risk   = sum(1 for f in risk_flags if f.severity == "high")
        medium_risk = sum(1 for f in risk_flags if f.severity == "medium")

        return ExecutiveSummary(
            bill_type=bill_type,
            months_analyzed=len(month_labels),
            month_labels=month_labels,
            monthly_totals=monthly_totals,
            avg_monthly_spend=avg_spend,
            total_lines_analyzed=len(lines),
            disconnect_candidates=disconnect,
            downgrade_candidates=downgrade,
            addon_removal_candidates=addon_rm,
            estimated_monthly_savings=monthly_sav,
            estimated_annual_savings=monthly_sav * 12,
            high_risk_flags=high_risk,
            medium_risk_flags=medium_risk,
        )
