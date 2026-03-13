"""
DiscountValidator — confirms corporate / enterprise discounts are present
and consistent across all uploaded billing months.

Limitation: without the signed contract we cannot verify the agreed
discount percentage.  We can only confirm presence, consistency, and
flag anomalies.  This is noted explicitly in every finding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

_DISCOUNT_KW  = ["discount", "corporate", "enterprise", "promo", "rebate",
                 "credit", "contract rate", "negotiated", "waiver"]
_TAX_KW       = ["vat", "tax", "levy", "surcharge", "regulatory",
                 "universal service", "e-rate", "rcm"]

# SA standard VAT rate
_SA_VAT_RATE = 15.0
_TAX_WARNING_THRESHOLD = 20.0   # flag if tax ratio exceeds this %


@dataclass
class DiscountFlag:
    severity:    str
    flag_type:   str   # missing_discount | reduced_discount | tax_anomaly | discount_ok
    title:       str
    description: str
    months:      list[str]
    detail:      str
    action:      str
    data:        dict = field(default_factory=dict)


class DiscountValidator:
    """
    Parameters
    ----------
    dataframes   : list of DataFrames (one per month)
    month_labels : human-readable labels
    """

    def validate(
        self,
        dataframes: list[pd.DataFrame],
        month_labels: list[str],
    ) -> list[DiscountFlag]:
        dfs   = [df.copy().rename(columns=lambda c: str(c).strip().lower()) for df in dataframes]
        flags: list[DiscountFlag] = []

        flags.extend(self._validate_discount_presence(dfs, month_labels))
        flags.extend(self._validate_discount_consistency(dfs, month_labels))
        flags.extend(self._validate_tax_ratios(dfs, month_labels))

        return flags

    # ------------------------------------------------------------------
    # 1. Discount presence
    # ------------------------------------------------------------------

    def _validate_discount_presence(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[DiscountFlag]:
        latest_df = dfs[-1]
        mask  = self._kw_mask(latest_df, _DISCOUNT_KW)
        rows  = latest_df[mask]

        if rows.empty:
            return [DiscountFlag(
                severity="medium",
                flag_type="missing_discount",
                title="No discount or credit lines found on latest bill",
                description=(
                    f"The most recent bill ({labels[-1]}) contains no rows matching "
                    "discount, corporate rate, or credit keywords."
                ),
                months=[labels[-1]],
                detail=(
                    "Note: without the signed contract we cannot confirm a discount "
                    "should be present.  This flag is a prompt to verify."
                ),
                action=(
                    "Request a discount confirmation letter from the carrier. "
                    "Cross-reference against the signed contract or pricing schedule. "
                    "If a corporate discount was negotiated, escalate to the carrier account team."
                ),
            )]

        amounts       = self._amount_col(rows)
        total_credits = float(amounts[amounts < 0].sum())
        positive_tot  = self._positive_total(latest_df)
        pct = abs(total_credits) / positive_tot * 100 if positive_tot else 0.0

        return [DiscountFlag(
            severity="info",
            flag_type="discount_ok",
            title=f"Discounts present: R{abs(total_credits):,.2f} ({pct:.1f}% of gross bill)",
            description=(
                f"Found {len(rows)} credit/discount row(s) on {labels[-1]} "
                f"totalling R{abs(total_credits):,.2f} ({pct:.1f}% of gross charges)."
            ),
            months=[labels[-1]],
            detail=(
                "LIMITATION: We cannot verify the discount matches the contracted "
                "rate without a copy of the signed agreement."
            ),
            action=(
                "Compare the effective discount percentage against the signed contract. "
                "Flag any month where the percentage drops more than 1 percentage point."
            ),
            data={"credit_rows": len(rows), "total_credits": total_credits, "pct": pct},
        )]

    # ------------------------------------------------------------------
    # 2. Discount consistency across months
    # ------------------------------------------------------------------

    def _validate_discount_consistency(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[DiscountFlag]:
        if len(dfs) < 2:
            return []

        credit_pcts: list[float] = []
        for df in dfs:
            mask     = self._kw_mask(df, _DISCOUNT_KW)
            credits  = self._amount_col(df[mask])
            net_cr   = float(credits[credits < 0].sum())
            pos_tot  = self._positive_total(df)
            credit_pcts.append(abs(net_cr) / pos_tot * 100 if pos_tot else 0.0)

        flags: list[DiscountFlag] = []
        for i in range(1, len(credit_pcts)):
            drop = credit_pcts[i - 1] - credit_pcts[i]
            if drop >= 1.0:
                flags.append(DiscountFlag(
                    severity="high" if drop >= 3.0 else "medium",
                    flag_type="reduced_discount",
                    title=(
                        f"Discount rate dropped {drop:.1f}pp between "
                        f"{labels[i-1]} and {labels[i]}"
                    ),
                    description=(
                        f"Effective discount rate: {credit_pcts[i-1]:.1f}% in {labels[i-1]}, "
                        f"{credit_pcts[i]:.1f}% in {labels[i]}."
                    ),
                    months=[labels[i - 1], labels[i]],
                    detail=(
                        "A drop of 1+ percentage points in a single month typically "
                        "indicates an expired promotional layer or a rate re-tier."
                    ),
                    action=(
                        "Contact the carrier to identify which discount component changed. "
                        "Request reinstatement if the reduction is due to an administrative error."
                    ),
                    data={"credit_pcts": credit_pcts},
                ))
        return flags

    # ------------------------------------------------------------------
    # 3. Tax ratio validation
    # ------------------------------------------------------------------

    def _validate_tax_ratios(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[DiscountFlag]:
        flags: list[DiscountFlag] = []
        for df, label in zip(dfs, labels):
            mask      = self._kw_mask(df, _TAX_KW)
            tax_rows  = df[mask]
            if tax_rows.empty:
                continue
            tax_total = float(self._amount_col(tax_rows).sum())
            pos_tot   = self._positive_total(df)
            if pos_tot == 0:
                continue
            ratio = tax_total / pos_tot * 100

            if ratio > _TAX_WARNING_THRESHOLD:
                flags.append(DiscountFlag(
                    severity="medium",
                    flag_type="tax_anomaly",
                    title=f"{label}: Tax / surcharge ratio {ratio:.1f}% exceeds {_TAX_WARNING_THRESHOLD:.0f}%",
                    description=(
                        f"Tax and surcharge charges of R{tax_total:,.2f} represent "
                        f"{ratio:.1f}% of gross spend in {label}. "
                        f"SA standard VAT is {_SA_VAT_RATE:.0f}%. "
                        "Ratios above 20% may indicate line type misclassification."
                    ),
                    months=[label],
                    detail=(
                        "LIMITATION: Statutory taxes cannot be eliminated — only "
                        "classification errors can be corrected."
                    ),
                    action=(
                        "Request an itemised tax breakdown for this month. "
                        "Verify line type classifications (business vs. consumer, "
                        "data-only vs. voice). Escalate confirmed misclassifications "
                        "to the carrier billing team."
                    ),
                    data={"tax_total": tax_total, "pos_tot": pos_tot, "ratio": ratio},
                ))
        return flags

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _desc_col(self, df: pd.DataFrame) -> pd.Series:
        for n in ("description", "desc", "service", "item"):
            if n in df.columns:
                return df[n].astype(str).str.lower()
        return pd.Series([""] * len(df), index=df.index)

    def _amount_col(self, df: pd.DataFrame) -> pd.Series:
        for n in ("amount", "charge", "total", "value"):
            if n in df.columns:
                return pd.to_numeric(df[n], errors="coerce").fillna(0.0)
        return pd.Series([0.0] * len(df), index=df.index)

    def _kw_mask(self, df: pd.DataFrame, kws: list[str]) -> pd.Series:
        desc = self._desc_col(df)
        mask = pd.Series(False, index=df.index)
        for kw in kws:
            mask |= desc.str.contains(re.escape(kw), na=False)
        return mask

    def _positive_total(self, df: pd.DataFrame) -> float:
        amounts = self._amount_col(df)
        return float(amounts[amounts > 0].sum())
