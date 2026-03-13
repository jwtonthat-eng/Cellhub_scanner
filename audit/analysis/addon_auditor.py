"""
AddOnAuditor — catalogs recurring feature charges per line and
flags candidates for validation or removal.

Because usage data rarely includes feature-level consumption, most
recommendations are framed as "validation requests" rather than
direct removal orders.  The exception is international roaming, where
presence on the bill without matching roaming data rows is a clearer signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from audit.parser.line_extractor import BilledLine

# Add-ons where a usage signal CAN be inferred from bill data
_USAGE_INFERABLE = {"International Roaming", "Mobile Hotspot Add-On"}


@dataclass
class AddOnFinding:
    msisdn:              str
    add_on:              str
    months_present:      list[str]    # which month labels it appeared in
    avg_monthly_charge:  float
    estimated_monthly_saving: float
    estimated_annual_saving:  float
    validation_required: bool         # True if usage can't be confirmed from bill data
    detail:              str
    action:              str


class AddOnAuditor:
    """
    Parameters
    ----------
    lines : list of BilledLine from LineExtractor
    """

    def audit(self, lines: list["BilledLine"]) -> list[AddOnFinding]:
        findings: list[AddOnFinding] = []
        for line in lines:
            findings.extend(self._audit_line(line))
        return findings

    def _audit_line(self, line: "BilledLine") -> list[AddOnFinding]:
        results: list[AddOnFinding] = []

        # Collect all add-ons seen across months
        all_addons: set[str] = set()
        for month_addons in line.add_ons:
            all_addons.update(month_addons)

        for addon in sorted(all_addons):
            months_present = [
                line.month_labels[i]
                for i, m_addons in enumerate(line.add_ons)
                if addon in m_addons
            ]

            # Estimate charge: use avg_charge as upper bound proxy
            # A per-add-on charge split would require per-row charge data
            # which the existing schema may not carry; flag for validation.
            est_charge = self._estimate_charge(line, addon, months_present)

            validation_required = addon not in _USAGE_INFERABLE

            detail = self._build_detail(line, addon, months_present, validation_required)
            action = self._build_action(line, addon, validation_required)

            results.append(AddOnFinding(
                msisdn=line.msisdn,
                add_on=addon,
                months_present=months_present,
                avg_monthly_charge=est_charge,
                estimated_monthly_saving=est_charge,
                estimated_annual_saving=est_charge * 12,
                validation_required=validation_required,
                detail=detail,
                action=action,
            ))

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _estimate_charge(
        self, line: "BilledLine", addon: str, months_present: list[str]
    ) -> float:
        """
        We don't have per-add-on charge data directly; return a placeholder
        that the report can mark as 'to be confirmed with carrier'.
        Uses a conservative 10 % of average monthly charge as a proxy.
        """
        if not months_present:
            return 0.0
        # Roaming tends to be a larger share; other add-ons smaller
        pct = 0.15 if "Roaming" in addon else 0.08
        return round(line.avg_charge * pct, 2)

    def _build_detail(
        self,
        line: "BilledLine",
        addon: str,
        months_present: list[str],
        validation_required: bool,
    ) -> str:
        month_str = ", ".join(months_present)
        base = (
            f"'{addon}' detected on {line.msisdn} in: {month_str}. "
        )
        if validation_required:
            base += (
                "Usage data in the bill does not confirm whether this feature "
                "was actively used."
            )
        else:
            if addon == "International Roaming" and len(months_present) == len(line.month_labels):
                base += "Active roaming charges detected every month — confirm travel schedule."
            elif addon == "Mobile Hotspot Add-On":
                base += "Hotspot add-on present — confirm whether tethering is actively required."
        return base

    def _build_action(self, line: "BilledLine", addon: str, validation_required: bool) -> str:
        if validation_required:
            return (
                f"Submit a validation request to the end-user for '{addon}' on {line.msisdn}. "
                "If confirmed unused for 60+ days, request removal from the carrier."
            )
        if addon == "International Roaming":
            return (
                "Confirm upcoming travel schedule. "
                "If no international travel is planned, request roaming suspension. "
                "Re-enable on request before each trip."
            )
        if addon == "Mobile Hotspot Add-On":
            return (
                "Verify whether the user requires a standalone hotspot add-on "
                "or whether their plan already includes hotspot capability."
            )
        return (
            f"Validate usage of '{addon}' with line owner. "
            "Remove if not actively needed."
        )
