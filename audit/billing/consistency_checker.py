"""
ConsistencyChecker — month-over-month billing anomaly detection.

Checks:
  1. Total spend variance (>10 % triggers a flag; >20 % is high severity)
  2. Line count changes between months
  3. Disappearing credits / promotional discounts
  4. Recurring charge volatility (individual charge codes that change)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_CREDIT_KW  = ["credit", "discount", "promo", "rebate", "refund", "adjustment",
               "waiver", "reversal"]
_UPGRADE_KW = ["upgrade", "device change", "handset change", "eia", "installment"]


@dataclass
class BillingFlag:
    severity:    str          # high | medium | low | info
    flag_type:   str          # spend_variance | line_count_change | credit_drop | charge_volatility
    title:       str
    description: str
    months:      list[str]
    delta_rands: float        # positive = spend increased / credits reduced
    action:      str
    data:        dict = field(default_factory=dict)


class ConsistencyChecker:
    """
    Parameters
    ----------
    dataframes   : list of DataFrames (one per month, oldest first)
    month_labels : human-readable month names
    """

    def check(
        self,
        dataframes: list[pd.DataFrame],
        month_labels: list[str],
    ) -> list[BillingFlag]:
        if len(dataframes) < 2:
            return []

        dfs   = [df.copy().rename(columns=lambda c: str(c).strip().lower()) for df in dataframes]
        flags: list[BillingFlag] = []

        flags.extend(self._check_spend_variance(dfs, month_labels))
        flags.extend(self._check_line_count(dfs, month_labels))
        flags.extend(self._check_credit_drop(dfs, month_labels))
        flags.extend(self._check_upgrade_spike(dfs, month_labels))

        return flags

    # ------------------------------------------------------------------
    # 1. Total spend variance
    # ------------------------------------------------------------------

    def _check_spend_variance(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[BillingFlag]:
        totals = [self._positive_total(df) for df in dfs]
        flags: list[BillingFlag] = []

        pct_changes = [
            (totals[i] - totals[i - 1]) / totals[i - 1] * 100
            for i in range(1, len(totals))
            if totals[i - 1] > 0
        ]
        if not pct_changes:
            return flags

        max_change = max(abs(c) for c in pct_changes)
        if max_change <= 10:
            return flags

        severity   = "high" if max_change > 20 else "medium"
        pair_strs  = [
            f"{labels[i-1]}→{labels[i]}: "
            f"{'+' if pct_changes[i-1]>0 else ''}{pct_changes[i-1]:.1f}%"
            for i in range(1, len(totals))
        ]
        delta = totals[-1] - totals[0]
        flags.append(BillingFlag(
            severity=severity,
            flag_type="spend_variance",
            title=f"Spend variance up to {max_change:.1f}% across months",
            description=(
                f"Monthly totals: {', '.join(f'R{t:,.2f}' for t in totals)}. "
                f"Changes: {'; '.join(pair_strs)}. "
                "Significant variance often signals expired promos, plan migrations, "
                "or device installment additions."
            ),
            months=labels,
            delta_rands=delta,
            action=(
                "Request an itemised billing change log from the carrier for the affected period. "
                "Cross-check against plan change orders and promo expiry dates."
            ),
            data={"totals": totals, "pct_changes": pct_changes},
        ))
        return flags

    # ------------------------------------------------------------------
    # 2. Line count changes
    # ------------------------------------------------------------------

    def _check_line_count(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[BillingFlag]:
        from audit.parser.line_extractor import _PHONE_RE
        flags: list[BillingFlag] = []

        counts = []
        for df in dfs:
            desc = self._desc_col(df)
            msisdns: set[str] = set()
            for text in desc:
                for m in _PHONE_RE.finditer(str(text)):
                    msisdns.add(m.group())
            counts.append(len(msisdns))

        for i in range(1, len(counts)):
            delta = counts[i] - counts[i - 1]
            if delta == 0:
                continue
            direction  = "increased" if delta > 0 else "decreased"
            severity   = "medium" if abs(delta) >= 2 else "info"
            flags.append(BillingFlag(
                severity=severity,
                flag_type="line_count_change",
                title=f"Line count {direction} by {abs(delta)} between {labels[i-1]} and {labels[i]}",
                description=(
                    f"Detected lines: {counts[i-1]} in {labels[i-1]}, "
                    f"{counts[i]} in {labels[i]}. "
                    + ("New lines may represent unauthorised additions. "
                       if delta > 0 else
                       "Removed lines may indicate unrecorded disconnects or extraction gaps.")
                ),
                months=[labels[i - 1], labels[i]],
                delta_rands=0.0,
                action=(
                    "Reconcile line count against the carrier's active-line report. "
                    "Confirm all additions were approved and all removals were intentional."
                ),
                data={"counts": counts, "delta": delta},
            ))
        return flags

    # ------------------------------------------------------------------
    # 3. Credit / discount drops
    # ------------------------------------------------------------------

    def _check_credit_drop(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[BillingFlag]:
        flags: list[BillingFlag] = []
        credit_totals: list[float] = []

        for df in dfs:
            mask    = self._kw_mask(df, _CREDIT_KW)
            amounts = self._amount_col(df[mask])
            credit_totals.append(float(amounts[amounts < 0].sum()))

        for i in range(1, len(credit_totals)):
            # Credits are negative; a less-negative value = fewer credits
            diff = credit_totals[i] - credit_totals[i - 1]
            if diff <= 50:
                continue
            severity = "high" if diff > 200 else "medium"
            flags.append(BillingFlag(
                severity=severity,
                flag_type="credit_drop",
                title=f"Credits reduced by R{diff:,.2f} between {labels[i-1]} and {labels[i]}",
                description=(
                    f"Net credits were R{abs(credit_totals[i-1]):,.2f} in {labels[i-1]} "
                    f"and R{abs(credit_totals[i]):,.2f} in {labels[i]}. "
                    "Promotional credits may have expired or a contractual discount may have been removed."
                ),
                months=[labels[i - 1], labels[i]],
                delta_rands=diff,
                action=(
                    "Contact the carrier to identify which credit expired or was removed. "
                    "Renegotiate if the reduction reflects an expired promo that can be renewed."
                ),
                data={"credit_totals": credit_totals},
            ))
        return flags

    # ------------------------------------------------------------------
    # 4. Upgrade / installment spikes
    # ------------------------------------------------------------------

    def _check_upgrade_spike(
        self, dfs: list[pd.DataFrame], labels: list[str]
    ) -> list[BillingFlag]:
        flags: list[BillingFlag] = []
        eia_totals: list[float] = []

        for df in dfs:
            mask   = self._kw_mask(df, _UPGRADE_KW)
            amounts = self._amount_col(df[mask])
            eia_totals.append(float(amounts[amounts > 0].sum()))

        for i in range(1, len(eia_totals)):
            delta = eia_totals[i] - eia_totals[i - 1]
            if delta < 200:
                continue
            flags.append(BillingFlag(
                severity="medium",
                flag_type="charge_volatility",
                title=f"Installment/upgrade charges up R{delta:,.2f} in {labels[i]}",
                description=(
                    f"Equipment/installment charges were R{eia_totals[i-1]:,.2f} in {labels[i-1]} "
                    f"and R{eia_totals[i]:,.2f} in {labels[i]}. "
                    "This suggests new device upgrades were added to the account."
                ),
                months=[labels[i - 1], labels[i]],
                delta_rands=delta,
                action=(
                    "Confirm upgrade authorisation with procurement. "
                    "Identify the specific lines and device models involved."
                ),
                data={"eia_totals": eia_totals},
            ))
        return flags

    # ------------------------------------------------------------------
    # Column helpers
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
        import re
        desc = self._desc_col(df)
        mask = pd.Series(False, index=df.index)
        for kw in kws:
            mask |= desc.str.contains(re.escape(kw), na=False)
        return mask

    def _positive_total(self, df: pd.DataFrame) -> float:
        amounts = self._amount_col(df)
        return float(amounts[amounts > 0].sum())
