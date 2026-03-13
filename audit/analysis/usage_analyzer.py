"""
UsageAnalyzer — per-line usage pattern analysis.

Flags:
  zero_use         : avg < 0.1 GB — disconnect candidate
  low_use          : avg 0.1–1.0 GB — downgrade or suspend candidate
  over_provisioned : avg < 50 % of capped plan, or < 5 GB on unlimited
  near_limit       : avg ≥ 80 % of capped plan — do NOT recommend downgrade
  inactive_eia     : near-zero usage but carrying device installment charges

Buffer logic: if a line is near_limit it is never flagged as over_provisioned,
regardless of absolute usage.  A 20 % buffer is applied so we don't recommend
a downgrade that would immediately trigger overages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audit.parser.line_extractor import BilledLine

# Estimated saving percentages by recommendation type
_SAVING_PCT = {
    "zero_use":         1.00,   # full charge recoverable by disconnect
    "low_use":          0.60,   # downgrade saves ~60 % of plan cost
    "over_provisioned": 0.30,   # downgrade saves ~30 %
    "inactive_eia":     1.00,   # full installment recoverable by suspend/terminate
}


@dataclass
class UsageFinding:
    msisdn:            str
    line_type:         str
    flag:              str          # zero_use | low_use | over_provisioned | near_limit | inactive_eia
    avg_usage_gb:      float
    plan_name:         str
    plan_cap_gb:       float | None
    avg_monthly_charge: float
    estimated_monthly_saving: float
    estimated_annual_saving:  float
    trend:             str          # increasing | decreasing | stable | insufficient_data
    detail:            str
    action:            str


class UsageAnalyzer:
    """
    Parameters
    ----------
    lines : list of BilledLine objects from LineExtractor
    """

    def analyze(self, lines: list["BilledLine"]) -> list[UsageFinding]:
        findings: list[UsageFinding] = []
        for line in lines:
            findings.extend(self._analyze_line(line))
        return findings

    def _analyze_line(self, line: "BilledLine") -> list[UsageFinding]:
        results: list[UsageFinding] = []

        # --- zero use -------------------------------------------------------
        if line.is_zero_use and not all(line.suspended):
            saving = line.avg_charge * _SAVING_PCT["zero_use"]
            results.append(UsageFinding(
                msisdn=line.msisdn,
                line_type=line.line_type,
                flag="zero_use",
                avg_usage_gb=line.avg_usage_gb,
                plan_name=line.plan_name,
                plan_cap_gb=line.plan_cap_gb,
                avg_monthly_charge=line.avg_charge,
                estimated_monthly_saving=saving,
                estimated_annual_saving=saving * 12,
                trend=line.usage_trend(),
                detail=(
                    f"Average usage {line.avg_usage_gb:.2f} GB — effectively zero. "
                    "This line is a disconnect candidate."
                ),
                action=(
                    "Validate with the user — confirm the device is not in use. "
                    "If confirmed inactive, submit a disconnect order to the carrier."
                ),
            ))
            return results  # no point adding more flags for a zero-use line

        # --- near limit (buffer — do not flag for downgrade) -----------------
        if line.is_near_limit:
            cap_str = f"{line.plan_cap_gb:.0f} GB" if line.plan_cap_gb else "plan limit"
            results.append(UsageFinding(
                msisdn=line.msisdn,
                line_type=line.line_type,
                flag="near_limit",
                avg_usage_gb=line.avg_usage_gb,
                plan_name=line.plan_name,
                plan_cap_gb=line.plan_cap_gb,
                avg_monthly_charge=line.avg_charge,
                estimated_monthly_saving=0.0,
                estimated_annual_saving=0.0,
                trend=line.usage_trend(),
                detail=(
                    f"Average usage {line.avg_usage_gb:.1f} GB is ≥ 80 % of "
                    f"the {cap_str} cap. No downgrade recommended — overage risk."
                ),
                action="Monitor monthly. Ensure plan tier is adequate as usage trends increase.",
            ))
            return results

        # --- low use --------------------------------------------------------
        if line.is_low_use:
            saving = line.avg_charge * _SAVING_PCT["low_use"]
            results.append(UsageFinding(
                msisdn=line.msisdn,
                line_type=line.line_type,
                flag="low_use",
                avg_usage_gb=line.avg_usage_gb,
                plan_name=line.plan_name,
                plan_cap_gb=line.plan_cap_gb,
                avg_monthly_charge=line.avg_charge,
                estimated_monthly_saving=saving,
                estimated_annual_saving=saving * 12,
                trend=line.usage_trend(),
                detail=(
                    f"Average usage {line.avg_usage_gb:.2f} GB — low but non-zero. "
                    "Downgrade or suspension may be appropriate."
                ),
                action=(
                    "Confirm with end-user whether they need the current plan. "
                    "If confirmed low-need, downgrade to a lower data tier or a voice-only plan."
                ),
            ))

        # --- over-provisioned -----------------------------------------------
        elif line.is_over_provisioned:
            cap_desc = (
                f"{line.plan_cap_gb:.0f} GB cap" if line.plan_cap_gb
                else "unlimited plan"
            )
            saving = line.avg_charge * _SAVING_PCT["over_provisioned"]
            results.append(UsageFinding(
                msisdn=line.msisdn,
                line_type=line.line_type,
                flag="over_provisioned",
                avg_usage_gb=line.avg_usage_gb,
                plan_name=line.plan_name,
                plan_cap_gb=line.plan_cap_gb,
                avg_monthly_charge=line.avg_charge,
                estimated_monthly_saving=saving,
                estimated_annual_saving=saving * 12,
                trend=line.usage_trend(),
                detail=(
                    f"Average usage {line.avg_usage_gb:.1f} GB on a {cap_desc}. "
                    "A lower-tier plan would cover this usage with buffer to spare."
                ),
                action=(
                    "Identify the next plan tier that comfortably covers this user's "
                    "average usage plus a 20 % buffer for occasional spikes."
                ),
            ))

        # --- inactive device installment ------------------------------------
        if line.carries_inactive_eia:
            eia_saving = sum(line.installment)
            results.append(UsageFinding(
                msisdn=line.msisdn,
                line_type=line.line_type,
                flag="inactive_eia",
                avg_usage_gb=line.avg_usage_gb,
                plan_name=line.plan_name,
                plan_cap_gb=line.plan_cap_gb,
                avg_monthly_charge=line.avg_charge,
                estimated_monthly_saving=eia_saving / max(len(line.installment), 1),
                estimated_annual_saving=eia_saving,
                trend=line.usage_trend(),
                detail=(
                    f"Device installment charges of "
                    f"R{sum(line.installment):,.2f} total detected on a near-zero-use line. "
                    "Device may be lost, unused, or reassigned without a contract update."
                ),
                action=(
                    "Locate the physical device. If unused, terminate the line and "
                    "confirm whether the EIA payoff is feasible. "
                    "If device is reallocated, update the line owner on the account."
                ),
            ))

        return results
