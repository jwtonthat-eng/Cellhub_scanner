"""
AuditEngine — runs 8-category structured analysis over 1–3 months of
extracted telecom bill DataFrames and returns an AuditReport.

Minimum required columns: 'description' (str) and 'amount' (float).
Optional columns: 'quantity' (str/float), 'line_number' (str), 'date' (date).
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd

from core.audit_report import AuditFinding, AuditReport

# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

_INSURANCE_KW    = ["insurance", "protect", "device cover", "handset cover", "assurance", "warranty"]
_ROAMING_KW      = ["roam", "international", "global", "travel", "intl", "irl ", "overseas"]
_HOTSPOT_KW      = ["hotspot", "mobile hotspot", "wifi hotspot", "tethering", "mifi"]
_VOICEMAIL_KW    = ["voicemail", "voice mail"]
_PREMIUM_SUP_KW  = ["premium support", "tech support", "care plus", "priority support"]
_INSTALLMENT_KW  = ["installment", "instalment", "device payment", "handset payment",
                    "equipment", "eia", "device finance", "hardware"]
_TAX_KW          = ["vat", "tax", "levy", "surcharge", "regulatory", "universal service",
                    "e-rate", "erate", "rcm"]
_CREDIT_KW       = ["credit", "discount", "promo", "rebate", "refund", "adjustment",
                    "waiver", "reversal"]
_POOL_KW         = ["pool", "shared data", "group data", "bucket", "pool overage"]
_OVERAGE_KW      = ["overage", "over limit", "excess data", "exceeded", "out-of-bundle",
                    "oob", "out of bundle"]

_PHONE_RE = re.compile(r'\b(0[678]\d{8}|\+27\d{9})\b')


class AuditEngine:
    """
    Parameters
    ----------
    dataframes   : list of DataFrames, one per billing month (oldest first).
    month_labels : human-readable label for each month, e.g. ["Jan 2025", "Feb 2025"].
    bill_type    : optional string identifier from PatternManager.
    """

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

    def __init__(
        self,
        dataframes: list[pd.DataFrame],
        month_labels: list[str],
        bill_type: str = "",
    ) -> None:
        if not dataframes:
            raise ValueError("At least one DataFrame is required.")
        if len(dataframes) > 3:
            dataframes = dataframes[-3:]
            month_labels = month_labels[-3:]
        self.bill_type = bill_type
        self.month_labels = month_labels
        # Normalise column names to lowercase
        self.dfs = [df.copy().rename(columns=lambda c: str(c).strip().lower()) for df in dataframes]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> AuditReport:
        findings: list[AuditFinding] = []
        findings.extend(self._analyze_line_inventory())
        findings.extend(self._analyze_rate_plans())
        findings.extend(self._analyze_feature_charges())
        findings.extend(self._analyze_billing_consistency())
        findings.extend(self._analyze_discounts())
        findings.extend(self._analyze_equipment())
        findings.extend(self._analyze_taxes())
        findings.extend(self._analyze_pooling())

        monthly_totals = [self._total_positive(df) for df in self.dfs]
        avg = float(np.mean(monthly_totals)) if monthly_totals else 0.0

        report = AuditReport(
            bill_type=self.bill_type,
            months_analyzed=len(self.dfs),
            month_labels=self.month_labels,
            total_monthly_avg=avg,
            findings=findings,
        )
        report.executive_summary = self._build_executive_summary(report, monthly_totals)
        return report

    # ------------------------------------------------------------------
    # Column helpers — gracefully degrade when columns are absent
    # ------------------------------------------------------------------

    def _amount_col(self, df: pd.DataFrame) -> pd.Series:
        for name in ("amount", "charge", "total", "value", "cost"):
            if name in df.columns:
                return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
        return pd.Series([0.0] * len(df), index=df.index)

    def _desc_col(self, df: pd.DataFrame) -> pd.Series:
        for name in ("description", "desc", "service", "item", "detail"):
            if name in df.columns:
                return df[name].astype(str).str.lower()
        return pd.Series([""] * len(df), index=df.index)

    def _qty_str_col(self, df: pd.DataFrame) -> Optional[pd.Series]:
        for name in ("quantity", "usage", "data_usage", "qty", "volume"):
            if name in df.columns:
                return df[name].astype(str)
        return None

    def _total_positive(self, df: pd.DataFrame) -> float:
        amounts = self._amount_col(df)
        return float(amounts[amounts > 0].sum())

    def _kw_mask(self, df: pd.DataFrame, keywords: list[str]) -> pd.Series:
        desc = self._desc_col(df)
        mask = pd.Series(False, index=df.index)
        for kw in keywords:
            mask |= desc.str.contains(re.escape(kw), na=False)
        return mask

    def _extract_lines(self, df: pd.DataFrame) -> list[str]:
        """Extract South African phone numbers from description column."""
        # First look for a dedicated line_number / msisdn column
        for col in ("line_number", "msisdn", "phone", "number", "line"):
            if col in df.columns:
                nums = df[col].dropna().astype(str).str.strip()
                nums = nums[nums.str.match(r'0[678]\d{8}')]
                if not nums.empty:
                    return sorted(nums.unique().tolist())
        # Fall back to regex over description
        desc = self._desc_col(df)
        numbers: set[str] = set()
        for text in desc:
            for m in _PHONE_RE.finditer(text):
                numbers.add(m.group())
        return sorted(numbers)

    # ------------------------------------------------------------------
    # 1. Line Inventory
    # ------------------------------------------------------------------

    def _analyze_line_inventory(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        all_sets = [set(self._extract_lines(df)) for df in self.dfs]
        if len(all_sets) < 2 or all(len(s) == 0 for s in all_sets):
            return findings

        all_lines  = set().union(*all_sets)
        latest     = all_sets[-1]
        prior      = set().union(*all_sets[:-1])
        disappeared = sorted(prior - latest)
        appeared    = sorted(latest - prior)

        if disappeared:
            findings.append(AuditFinding(
                category="line_inventory",
                severity="medium",
                title=f"{len(disappeared)} line(s) absent from latest bill",
                description=(
                    f"Line(s) seen in earlier months but missing from "
                    f"{self.month_labels[-1]}: {', '.join(disappeared[:8])}. "
                    "May indicate disconnect, number change, or extraction gap."
                ),
                affected_lines=disappeared,
                action=(
                    "Validate on carrier account portal. Confirm intentional disconnect "
                    "or check for line migration / number change."
                ),
                data={"disappeared_lines": disappeared},
            ))

        if appeared:
            findings.append(AuditFinding(
                category="line_inventory",
                severity="info",
                title=f"{len(appeared)} new line(s) on latest bill",
                description=(
                    f"New line(s) detected in {self.month_labels[-1]}: "
                    f"{', '.join(appeared[:8])}. Verify these are authorised additions."
                ),
                affected_lines=appeared,
                action="Confirm new lines are approved by HR / procurement.",
                data={"new_lines": appeared},
            ))

        return findings

    # ------------------------------------------------------------------
    # 2. Rate Plan Optimisation
    # ------------------------------------------------------------------

    def _analyze_rate_plans(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        for i, df in enumerate(self.dfs):
            qty_str = self._qty_str_col(df)
            if qty_str is None:
                continue
            # Extract numeric GB / MB values from quantity strings
            gb = qty_str.str.extract(r'([\d.]+)\s*(?:gb|gigabyte)', expand=False).astype(float)
            mb = qty_str.str.extract(r'([\d.]+)\s*(?:mb|megabyte)', expand=False).astype(float) / 1024
            usage_gb = gb.fillna(mb)
            low_mask = (usage_gb < 3.0) & usage_gb.notna()
            if low_mask.sum() == 0:
                continue
            premium_mask = self._kw_mask(df, ["premium", "unlimited", "pro", "max"])
            premium_rows = df[premium_mask]
            if premium_rows.empty:
                continue
            avg_charge = float(self._amount_col(premium_rows).mean())
            low_count  = int(low_mask.sum())
            monthly_saving = avg_charge * low_count * 0.30
            lines = self._extract_lines(df[low_mask])
            findings.append(AuditFinding(
                category="rate_plan",
                severity="medium",
                title=f"{self.month_labels[i]}: {low_count} low-data line(s) on premium plans",
                description=(
                    f"{low_count} line(s) averaged under 3 GB but appear to be on premium/unlimited plans. "
                    "Downgrading to a standard or capped plan could reduce spend."
                ),
                estimated_monthly_savings=monthly_saving,
                estimated_annual_savings=monthly_saving * 12,
                affected_lines=lines,
                action=(
                    "Pull 3-month usage per line. Identify candidates under 3 GB/month. "
                    "Propose downgrade to standard unlimited or capped data plan (allow 20% buffer)."
                ),
                data={"low_usage_lines": low_count, "avg_premium_charge": avg_charge},
            ))
        return findings

    # ------------------------------------------------------------------
    # 3. Feature & Add-On Charges
    # ------------------------------------------------------------------

    def _analyze_feature_charges(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        feature_groups = [
            ("Insurance / Device Protection", _INSURANCE_KW,   "medium"),
            ("International Roaming",         _ROAMING_KW,     "high"),
            ("Mobile Hotspot Add-On",         _HOTSPOT_KW,     "low"),
            ("Voicemail Enhancements",        _VOICEMAIL_KW,   "low"),
            ("Premium Support Services",      _PREMIUM_SUP_KW, "low"),
        ]
        df = self.dfs[-1]
        for label, keywords, severity in feature_groups:
            mask  = self._kw_mask(df, keywords)
            rows  = df[mask]
            if rows.empty:
                continue
            total = float(self._amount_col(rows).sum())
            if total <= 0:
                continue
            lines = self._extract_lines(rows)
            findings.append(AuditFinding(
                category="feature_charges",
                severity=severity,
                title=f"{label}: R{total:.2f}/month across {len(rows)} charge(s)",
                description=(
                    f"Found {len(rows)} charge(s) related to {label.lower()}, "
                    f"totalling R{total:.2f}. Validate whether each is actively used."
                ),
                estimated_monthly_savings=total,
                estimated_annual_savings=total * 12,
                affected_lines=lines,
                action=(
                    f"Request carrier usage report for {label.lower()}. "
                    "Remove from lines where the feature shows no usage in the past 3 months."
                ),
                data={"row_count": len(rows), "total_charge": total},
            ))
        return findings

    # ------------------------------------------------------------------
    # 4. Billing Consistency
    # ------------------------------------------------------------------

    def _analyze_billing_consistency(self) -> list[AuditFinding]:
        if len(self.dfs) < 2:
            return []
        findings: list[AuditFinding] = []
        totals = [self._total_positive(df) for df in self.dfs]

        pct_changes = [
            (totals[i] - totals[i - 1]) / totals[i - 1] * 100
            for i in range(1, len(totals))
            if totals[i - 1] > 0
        ]
        if not pct_changes:
            return findings

        max_change = max(abs(c) for c in pct_changes)
        if max_change > 10:
            severity = "high" if max_change > 20 else "medium"
            pairs = [
                f"{self.month_labels[i-1]}→{self.month_labels[i]}: "
                f"{'+' if pct_changes[i-1] > 0 else ''}{pct_changes[i-1]:.1f}%"
                for i in range(1, len(totals))
            ]
            findings.append(AuditFinding(
                category="billing_consistency",
                severity=severity,
                title=f"Spend variance up to {max_change:.1f}% detected across months",
                description=(
                    f"Monthly totals: {', '.join(f'R{t:,.2f}' for t in totals)}. "
                    f"Month-on-month changes: {'; '.join(pairs)}. "
                    "Significant variance may indicate expired promotions, plan migrations, or billing errors."
                ),
                action=(
                    "Request itemised billing change log from carrier for the affected months. "
                    "Specifically check for expired promo credits, plan-tier changes, and device EIAs added or removed."
                ),
                data={"totals": totals, "pct_changes": pct_changes, "labels": self.month_labels},
            ))

        # Check for disappearing credits
        credit_totals: list[float] = []
        for df in self.dfs:
            mask    = self._kw_mask(df, _CREDIT_KW)
            amounts = self._amount_col(df[mask])
            credit_totals.append(float(amounts[amounts < 0].sum()))

        if len(credit_totals) >= 2:
            first, last = credit_totals[0], credit_totals[-1]
            # Credits are negative; last > first means fewer credits
            diff = last - first
            if diff > 50:
                findings.append(AuditFinding(
                    category="billing_consistency",
                    severity="high",
                    title=f"Credits / discounts reduced by R{diff:.2f}/month",
                    description=(
                        f"Credits were R{abs(first):,.2f} in {self.month_labels[0]} and "
                        f"R{abs(last):,.2f} in {self.month_labels[-1]}. "
                        "Promotional or contractual credits may have expired or been removed."
                    ),
                    estimated_monthly_savings=diff,
                    estimated_annual_savings=diff * 12,
                    action=(
                        "Contact carrier to confirm credit expiry. "
                        "Renegotiate or reinstate contractual discounts if applicable."
                    ),
                    data={"credit_totals": credit_totals},
                ))
        return findings

    # ------------------------------------------------------------------
    # 5. Discount & Credit Visibility
    # ------------------------------------------------------------------

    def _analyze_discounts(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        df   = self.dfs[-1]
        mask = self._kw_mask(df, _CREDIT_KW)
        rows = df[mask]

        if rows.empty:
            findings.append(AuditFinding(
                category="discounts",
                severity="medium",
                title="No discount or credit lines detected on latest bill",
                description=(
                    "No corporate discounts, promotional credits, or rebates were found. "
                    "This may indicate the contracted discount is not being applied."
                ),
                action=(
                    "Request a discount confirmation letter from the carrier. "
                    "Cross-reference against the signed contract or tender pricing schedule."
                ),
            ))
        else:
            amounts      = self._amount_col(rows)
            total_credit = float(amounts[amounts < 0].sum())
            pct = abs(total_credit) / self._total_positive(df) * 100 if self._total_positive(df) else 0
            findings.append(AuditFinding(
                category="discounts",
                severity="info",
                title=f"Discounts / credits present: R{abs(total_credit):,.2f} ({pct:.1f}% of bill)",
                description=(
                    f"Found {len(rows)} credit/discount row(s) totalling R{abs(total_credit):,.2f} "
                    f"({pct:.1f}% of gross charges). "
                    "Verify consistency across all months and confirm against contracted rates."
                ),
                action=(
                    "Compare discount percentage against signed contract. "
                    "Flag any month where the percentage drops more than 1 percentage point."
                ),
                data={"credit_rows": len(rows), "total_credit": total_credit, "pct": pct},
            ))
        return findings

    # ------------------------------------------------------------------
    # 6. Equipment Installment Charges
    # ------------------------------------------------------------------

    def _analyze_equipment(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        df   = self.dfs[-1]
        mask = self._kw_mask(df, _INSTALLMENT_KW)
        rows = df[mask]
        if rows.empty:
            return findings
        total = float(self._amount_col(rows).sum())
        lines = self._extract_lines(rows)

        # Flag lines with installments but low/zero usage
        qty_str = self._qty_str_col(df)
        low_use_lines: list[str] = []
        if qty_str is not None:
            gb = qty_str.str.extract(r'([\d.]+)\s*(?:gb|gigabyte)', expand=False).astype(float)
            for ln in lines:
                # Find rows mentioning this line
                ln_mask = self._desc_col(df).str.contains(re.escape(ln), na=False)
                usage = gb[ln_mask].dropna()
                if not usage.empty and usage.mean() < 0.5:
                    low_use_lines.append(ln)

        severity = "high" if low_use_lines else "medium"
        title    = (
            f"Equipment installments: R{total:,.2f}/month"
            + (f" — {len(low_use_lines)} low-use line(s) flagged" if low_use_lines else "")
        )
        findings.append(AuditFinding(
            category="equipment",
            severity=severity,
            title=title,
            description=(
                f"Found {len(rows)} device installment charge(s) totalling R{total:,.2f}. "
                + (
                    f"Lines {', '.join(low_use_lines[:5])} have near-zero data usage "
                    "while still carrying device payment charges. "
                    if low_use_lines else ""
                )
                + "Installments on inactive lines represent misallocated spend."
            ),
            affected_lines=lines,
            action=(
                "Cross-reference installment lines against usage data. "
                "For lines with <0.5 GB usage, validate whether the device is still in use. "
                "Consider suspending or terminating zero-use lines carrying active EIAs."
            ),
            data={"installment_rows": len(rows), "total": total, "low_use_lines": low_use_lines},
        ))
        return findings

    # ------------------------------------------------------------------
    # 7. Taxes & Surcharges
    # ------------------------------------------------------------------

    def _analyze_taxes(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        df          = self.dfs[-1]
        mask        = self._kw_mask(df, _TAX_KW)
        tax_rows    = df[mask]
        if tax_rows.empty:
            return findings

        tax_total     = float(self._amount_col(tax_rows).sum())
        service_total = self._total_positive(df)
        if service_total == 0:
            return findings

        tax_ratio = tax_total / service_total * 100

        # SA standard VAT is 15 %; anything above 20 % warrants review
        if tax_ratio > 20:
            findings.append(AuditFinding(
                category="taxes",
                severity="medium",
                title=f"High tax / surcharge ratio: {tax_ratio:.1f}% of gross bill",
                description=(
                    f"Tax and surcharge charges total R{tax_total:,.2f} "
                    f"({tax_ratio:.1f}% of R{service_total:,.2f}). "
                    "South African standard VAT is 15%. Ratios above 20% may indicate "
                    "incorrect line-type classification increasing the tax base."
                ),
                action=(
                    "Request itemised tax breakdown. "
                    "Verify line type classifications (business vs. consumer, data-only vs. voice). "
                    "Escalate misclassifications to carrier billing team."
                ),
                data={"tax_total": tax_total, "service_total": service_total, "ratio": tax_ratio},
            ))
        else:
            findings.append(AuditFinding(
                category="taxes",
                severity="info",
                title=f"Tax / surcharge ratio: {tax_ratio:.1f}% — within normal range",
                description=(
                    f"Tax charges of R{tax_total:,.2f} represent {tax_ratio:.1f}% of gross spend. "
                    "No anomalies detected."
                ),
                data={"tax_total": tax_total, "service_total": service_total, "ratio": tax_ratio},
            ))
        return findings

    # ------------------------------------------------------------------
    # 8. Pooling & Shared Plan Performance
    # ------------------------------------------------------------------

    def _analyze_pooling(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        df   = self.dfs[-1]
        mask = self._kw_mask(df, _POOL_KW)
        if not mask.any():
            return findings

        overage_mask = self._kw_mask(df, _OVERAGE_KW)
        overage_rows = df[overage_mask]

        if not overage_rows.empty:
            overage_total = float(self._amount_col(overage_rows).sum())
            findings.append(AuditFinding(
                category="pooling",
                severity="high",
                title=f"Pool overage charges detected: R{overage_total:,.2f}",
                description=(
                    f"Found {len(overage_rows)} overage row(s) totalling R{overage_total:,.2f}. "
                    "Recurring overages indicate the pool is undersized relative to actual usage."
                ),
                estimated_monthly_savings=overage_total,
                estimated_annual_savings=overage_total * 12,
                action=(
                    "Identify top 3 data consumers in the pool. "
                    "Evaluate whether a larger pool tier is cheaper than recurring overage charges. "
                    "Consider moving heavy users to individual unlimited plans."
                ),
                data={"overage_rows": len(overage_rows), "overage_total": overage_total},
            ))
        else:
            pool_rows  = df[mask]
            pool_total = float(self._amount_col(pool_rows).sum())
            findings.append(AuditFinding(
                category="pooling",
                severity="info",
                title="Shared pool present — no overages detected",
                description=(
                    f"Pool charges of R{pool_total:,.2f} found with no overage indicators. "
                    "Verify the pool is not significantly over-provisioned."
                ),
                action=(
                    "Monitor pool utilisation monthly for 3 months. "
                    "If utilisation is consistently below 70%, consider reducing pool tier to lower base cost."
                ),
                data={"pool_total": pool_total},
            ))
        return findings

    # ------------------------------------------------------------------
    # Executive Summary
    # ------------------------------------------------------------------

    def _build_executive_summary(self, report: AuditReport, monthly_totals: list[float]) -> dict:
        high   = len([f for f in report.findings if f.severity == "high"])
        medium = len([f for f in report.findings if f.severity == "medium"])
        return {
            "months_analyzed":          len(self.dfs),
            "month_labels":             self.month_labels,
            "monthly_totals":           monthly_totals,
            "avg_monthly_spend":        report.total_monthly_avg,
            "total_findings":           len(report.findings),
            "high_priority_findings":   high,
            "medium_priority_findings": medium,
            "estimated_monthly_savings": report.total_estimated_monthly_savings,
            "estimated_annual_savings":  report.total_estimated_annual_savings,
        }
