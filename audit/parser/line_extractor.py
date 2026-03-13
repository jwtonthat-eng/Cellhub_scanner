"""
LineExtractor — builds a per-MSISDN data model from 1–3 months of
extracted bill DataFrames.

BilledLine is the core unit for all downstream analysis.  Each instance
represents one phone number across all uploaded billing months.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Regex / keyword tables
# ---------------------------------------------------------------------------

_PHONE_RE    = re.compile(r'\b(0[678]\d{8}|\+27\d{9})\b')
_PLAN_CAP_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:gb|gigabyte)', re.IGNORECASE)
_GB_RE       = re.compile(r'([\d.]+)\s*(?:gb|gigabyte)', re.IGNORECASE)
_MB_RE       = re.compile(r'([\d.]+)\s*(?:mb|megabyte)', re.IGNORECASE)

_LINE_TYPE_KW: dict[str, list[str]] = {
    "tablet":     ["tablet", "ipad", "data-only", "data only"],
    "hotspot":    ["hotspot", "mifi", "router", "jetpack", "mobile wifi", "wifi egg"],
    "wearable":   ["watch", "wearable", "galaxy watch", "apple watch", "gear"],
    "smartphone": ["voice", "call", "sms", "mobile", "smartphone", "handset"],
}

_INSTALLMENT_KW = ["installment", "instalment", "eia", "device payment",
                   "handset payment", "device finance", "equipment"]
_ADDON_KW = {
    "Insurance":              ["insurance", "protect", "device cover", "assurance"],
    "International Roaming":  ["roam", "international", "intl", "overseas", "global"],
    "Mobile Hotspot Add-On":  ["hotspot", "tethering", "mifi"],
    "Voicemail":              ["voicemail", "voice mail"],
    "Premium Support":        ["premium support", "care plus", "tech support"],
}
_SUSPENDED_KW = ["suspend", "inactive", "disconnected", "barred"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BilledLine:
    """
    Per-MSISDN record aggregated across all uploaded billing months.
    All list fields are ordered oldest → newest (matching month_labels).
    """
    msisdn:          str
    line_type:       str           # smartphone | tablet | hotspot | wearable | unknown
    plan_name:       str
    plan_cap_gb:     Optional[float]   # None = unlimited; float = capped in GB
    month_labels:    list[str]

    # Per-month metrics
    usage_gb:        list[float]       # extracted from quantity column
    charges:         list[float]       # sum of all charge rows for this MSISDN
    installment:     list[float]       # device EIA charges per month
    add_ons:         list[list[str]]   # add-on labels active each month
    suspended:       list[bool]        # True if line appeared suspended that month

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def avg_usage_gb(self) -> float:
        valid = [u for u in self.usage_gb if u >= 0]
        return float(np.mean(valid)) if valid else 0.0

    @property
    def avg_charge(self) -> float:
        valid = [c for c in self.charges if c > 0]
        return float(np.mean(valid)) if valid else 0.0

    @property
    def total_installment(self) -> float:
        return sum(self.installment)

    @property
    def current_add_ons(self) -> list[str]:
        """Add-ons seen on the most recent month."""
        return self.add_ons[-1] if self.add_ons else []

    @property
    def is_zero_use(self) -> bool:
        return self.avg_usage_gb < 0.1

    @property
    def is_low_use(self) -> bool:
        return 0.1 <= self.avg_usage_gb < 1.0

    @property
    def is_near_limit(self) -> bool:
        """Usage >= 80 % of plan cap — do NOT recommend downgrade."""
        if self.plan_cap_gb is None:
            return False
        return self.avg_usage_gb >= self.plan_cap_gb * 0.80

    @property
    def is_over_provisioned(self) -> bool:
        """
        On an unlimited plan but consistently low usage, or on a capped
        plan but using less than half the allowance.
        """
        if self.is_near_limit:
            return False
        if self.plan_cap_gb is None:
            # Unlimited — flag if avg < 5 GB
            return self.avg_usage_gb < 5.0
        return self.avg_usage_gb < self.plan_cap_gb * 0.50

    @property
    def carries_inactive_eia(self) -> bool:
        """Has device payments but near-zero usage."""
        return self.total_installment > 0 and self.is_zero_use

    def usage_trend(self) -> str:
        """'increasing' | 'decreasing' | 'stable' | 'insufficient_data'"""
        if len(self.usage_gb) < 2:
            return "insufficient_data"
        delta = self.usage_gb[-1] - self.usage_gb[0]
        if abs(delta) < 0.5:
            return "stable"
        return "increasing" if delta > 0 else "decreasing"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class LineExtractor:
    """
    Accepts a list of DataFrames (one per billing month) and builds a
    ``BilledLine`` object for every distinct MSISDN found.

    Account-level charges without a detectable MSISDN are grouped under
    the synthetic key ``"ACCOUNT"`` and excluded from per-line analysis.
    """

    def extract(
        self,
        dataframes: list[pd.DataFrame],
        month_labels: list[str],
    ) -> list[BilledLine]:
        # Normalise column names
        dfs = [df.copy().rename(columns=lambda c: str(c).strip().lower()) for df in dataframes]

        # Discover every MSISDN across all months
        all_msisdns: set[str] = set()
        for df in dfs:
            all_msisdns.update(self._msisdns_in_df(df))
        all_msisdns.discard("ACCOUNT")

        if not all_msisdns:
            return []

        lines: list[BilledLine] = []
        for msisdn in sorted(all_msisdns):
            per_month = [self._month_data(df, msisdn) for df in dfs]
            line = self._build_line(msisdn, per_month, month_labels, dfs)
            lines.append(line)

        return lines

    # ------------------------------------------------------------------
    # Per-month slice
    # ------------------------------------------------------------------

    def _msisdns_in_df(self, df: pd.DataFrame) -> set[str]:
        desc_col = self._desc_col(df)
        found: set[str] = set()
        for text in desc_col:
            for m in _PHONE_RE.finditer(str(text)):
                found.add(m.group())
        # Also check dedicated number columns
        for col in ("line_number", "msisdn", "phone", "number"):
            if col in df.columns:
                vals = df[col].dropna().astype(str).str.strip()
                found.update(vals[vals.str.match(r'0[678]\d{8}')].tolist())
        return found

    def _month_data(self, df: pd.DataFrame, msisdn: str) -> dict:
        """Extract all rows belonging to ``msisdn`` for one month."""
        mask = self._rows_for_msisdn(df, msisdn)
        rows = df[mask]
        amounts = self._amount_col(df)

        usage_gb    = self._sum_usage_gb(df[mask])
        charge      = float(amounts[mask & (amounts > 0)].sum())
        installment = float(amounts[mask & self._kw_mask(df, _INSTALLMENT_KW) & (amounts > 0)].sum())
        add_ons     = self._detect_addons(df[mask])
        suspended   = bool(self._kw_mask(df, _SUSPENDED_KW)[mask].any())
        plan_name   = self._infer_plan_name(df[mask])

        return {
            "usage_gb":    usage_gb,
            "charge":      charge,
            "installment": installment,
            "add_ons":     add_ons,
            "suspended":   suspended,
            "plan_name":   plan_name,
        }

    # ------------------------------------------------------------------
    # Build BilledLine
    # ------------------------------------------------------------------

    def _build_line(
        self,
        msisdn: str,
        per_month: list[dict],
        month_labels: list[str],
        dfs: list[pd.DataFrame],
    ) -> BilledLine:
        plan_name = next((m["plan_name"] for m in per_month if m["plan_name"]), "Unknown Plan")
        plan_cap  = self._infer_plan_cap(plan_name)
        line_type = self._infer_line_type(msisdn, dfs)

        return BilledLine(
            msisdn=msisdn,
            line_type=line_type,
            plan_name=plan_name,
            plan_cap_gb=plan_cap,
            month_labels=month_labels,
            usage_gb=    [m["usage_gb"]    for m in per_month],
            charges=     [m["charge"]      for m in per_month],
            installment= [m["installment"] for m in per_month],
            add_ons=     [m["add_ons"]     for m in per_month],
            suspended=   [m["suspended"]   for m in per_month],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _desc_col(self, df: pd.DataFrame) -> pd.Series:
        for n in ("description", "desc", "service", "item", "detail"):
            if n in df.columns:
                return df[n].astype(str).str.lower()
        return pd.Series([""] * len(df), index=df.index)

    def _amount_col(self, df: pd.DataFrame) -> pd.Series:
        for n in ("amount", "charge", "total", "value", "cost"):
            if n in df.columns:
                return pd.to_numeric(df[n], errors="coerce").fillna(0.0)
        return pd.Series([0.0] * len(df), index=df.index)

    def _qty_col(self, df: pd.DataFrame) -> pd.Series:
        for n in ("quantity", "usage", "data_usage", "qty", "volume"):
            if n in df.columns:
                return df[n].astype(str)
        return pd.Series([""] * len(df), index=df.index)

    def _rows_for_msisdn(self, df: pd.DataFrame, msisdn: str) -> pd.Series:
        """Boolean mask: rows that mention this MSISDN."""
        desc = self._desc_col(df)
        mask = desc.str.contains(re.escape(msisdn), na=False)
        for col in ("line_number", "msisdn", "phone", "number"):
            if col in df.columns:
                mask |= df[col].astype(str).str.strip() == msisdn
        return mask

    def _kw_mask(self, df: pd.DataFrame, keywords: list[str]) -> pd.Series:
        desc = self._desc_col(df)
        mask = pd.Series(False, index=df.index)
        for kw in keywords:
            mask |= desc.str.contains(re.escape(kw), na=False)
        return mask

    def _sum_usage_gb(self, rows: pd.DataFrame) -> float:
        if rows.empty:
            return 0.0
        qty = self._qty_col(rows)
        total = 0.0
        for val in qty:
            m_gb = _GB_RE.search(val)
            m_mb = _MB_RE.search(val)
            if m_gb:
                total += float(m_gb.group(1))
            elif m_mb:
                total += float(m_mb.group(1)) / 1024
        return total

    def _detect_addons(self, rows: pd.DataFrame) -> list[str]:
        if rows.empty:
            return []
        desc = self._desc_col(rows)
        found: list[str] = []
        for label, keywords in _ADDON_KW.items():
            if any(desc.str.contains(re.escape(kw), na=False).any() for kw in keywords):
                found.append(label)
        return found

    def _infer_plan_name(self, rows: pd.DataFrame) -> str:
        if rows.empty:
            return ""
        desc = self._desc_col(rows)
        plan_kw = ["plan", "unlimited", "bundle", "package", "capped", "gb plan", "gig plan"]
        for text in desc:
            if any(kw in text for kw in plan_kw):
                return text[:60].strip().title()
        return ""

    def _infer_plan_cap(self, plan_name: str) -> Optional[float]:
        """Extract numeric GB cap from plan name; None = unlimited."""
        lower = plan_name.lower()
        if "unlimited" in lower or "uncapped" in lower:
            return None
        m = _PLAN_CAP_RE.search(plan_name)
        if m:
            return float(m.group(1))
        return None

    def _infer_line_type(self, msisdn: str, dfs: list[pd.DataFrame]) -> str:
        combined_desc = " ".join(
            " ".join(self._desc_col(df)[self._rows_for_msisdn(df, msisdn)].tolist())
            for df in dfs
        ).lower()
        for line_type, keywords in _LINE_TYPE_KW.items():
            if any(kw in combined_desc for kw in keywords):
                return line_type
        return "unknown"
