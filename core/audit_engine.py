"""
AuditEngine — top-level orchestrator for the telecom bill audit.

Delegates to five specialist submodules:

  audit/parser/         → LineExtractor   (BilledLine per MSISDN)
  audit/analysis/       → UsageAnalyzer   (zero/low/over-provisioned/near-limit flags)
                        → AddOnAuditor    (per-line feature charge catalog)
  audit/billing/        → ConsistencyChecker (spend variance, credit drops, upgrades)
                        → DiscountValidator  (discount presence, tax ratios)
  audit/report/         → ReportBuilder   (AuditOutput with scope limitations)

The AuditEngine also maintains the legacy CATEGORY_LABELS dict so existing
UI code that references it continues to work unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from audit.report.report_builder import AuditOutput

# Legacy category labels — kept for UI compatibility
CATEGORY_LABELS: dict[str, str] = {
    "line_inventory":       "1. Active Line Inventory",
    "rate_plan":            "2. Rate Plan Optimisation",
    "feature_charges":      "3. Feature & Add-On Charges",
    "billing_consistency":  "4. Billing Consistency",
    "discounts":            "5. Contracted Discount Visibility",
    "equipment":            "6. Equipment Installment Charges",
    "taxes":                "7. Taxes & Surcharges",
    "pooling":              "8. Pooling & Shared Plan Performance",
}


class AuditEngine:
    """
    Parameters
    ----------
    dataframes   : 1–3 DataFrames (oldest first), one per billing month.
    month_labels : human-readable label per month, e.g. ["Jan 2025", "Feb 2025"].
    bill_type    : optional string identifier from PatternManager.
    """

    # Expose for UI code that does AuditEngine.CATEGORY_LABELS
    CATEGORY_LABELS = CATEGORY_LABELS

    def __init__(
        self,
        dataframes:   list[pd.DataFrame],
        month_labels: list[str],
        bill_type:    str = "",
    ) -> None:
        if not dataframes:
            raise ValueError("At least one DataFrame is required.")
        if len(dataframes) > 3:
            dataframes   = dataframes[-3:]
            month_labels = month_labels[-3:]
        self.bill_type    = bill_type
        self.month_labels = month_labels
        self.dfs          = dataframes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> "AuditOutput":
        from audit.parser.line_extractor import LineExtractor
        from audit.analysis.usage_analyzer import UsageAnalyzer
        from audit.analysis.addon_auditor import AddOnAuditor
        from audit.billing.consistency_checker import ConsistencyChecker
        from audit.billing.discount_validator import DiscountValidator
        from audit.report.report_builder import ReportBuilder

        # 1 — Parse: build per-MSISDN model
        extractor   = LineExtractor()
        billed_lines = extractor.extract(self.dfs, self.month_labels)

        # 2 — Analysis: usage patterns and add-ons
        usage_findings = UsageAnalyzer().analyze(billed_lines)
        addon_findings = AddOnAuditor().audit(billed_lines)

        # 3 — Billing: consistency and discount validation
        billing_flags  = ConsistencyChecker().check(self.dfs, self.month_labels)
        discount_flags = DiscountValidator().validate(self.dfs, self.month_labels)

        # 4 — Report: assemble AuditOutput
        monthly_totals = [self._positive_total(df) for df in self.dfs]
        output = ReportBuilder().build(
            bill_type=self.bill_type,
            month_labels=self.month_labels,
            monthly_totals=monthly_totals,
            billed_lines=billed_lines,
            usage_findings=usage_findings,
            addon_findings=addon_findings,
            billing_flags=billing_flags,
            discount_flags=discount_flags,
        )
        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _positive_total(self, df: pd.DataFrame) -> float:
        df_n = df.rename(columns=lambda c: str(c).strip().lower())
        for col in ("amount", "charge", "total", "value"):
            if col in df_n.columns:
                amounts = pd.to_numeric(df_n[col], errors="coerce").fillna(0.0)
                return float(amounts[amounts > 0].sum())
        return 0.0
