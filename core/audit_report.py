"""
Audit data classes — shared between AuditEngine and the UI layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AuditFinding:
    category: str          # matches AuditEngine.CATEGORY_LABELS key
    severity: str          # "high" | "medium" | "low" | "info"
    title: str
    description: str
    estimated_monthly_savings: float = 0.0
    estimated_annual_savings: float = 0.0
    affected_lines: list[str] = field(default_factory=list)
    action: str = ""
    data: dict = field(default_factory=dict)

    @property
    def severity_color(self) -> tuple[str, str]:
        """Return (light_hex, dark_hex) for the severity level."""
        return {
            "high":   ("#dc2626", "#ef4444"),
            "medium": ("#ea580c", "#f97316"),
            "low":    ("#ca8a04", "#eab308"),
            "info":   ("#2563eb", "#60a5fa"),
        }.get(self.severity, ("#6b7280", "#9ca3af"))


@dataclass
class AuditReport:
    bill_type: str
    months_analyzed: int
    month_labels: list[str]
    total_monthly_avg: float
    findings: list[AuditFinding]
    executive_summary: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def high_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "high"]

    @property
    def medium_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "medium"]

    @property
    def total_estimated_monthly_savings(self) -> float:
        return sum(f.estimated_monthly_savings for f in self.findings)

    @property
    def total_estimated_annual_savings(self) -> float:
        return self.total_estimated_monthly_savings * 12

    @property
    def findings_by_category(self) -> dict[str, list[AuditFinding]]:
        result: dict[str, list[AuditFinding]] = {}
        for f in self.findings:
            result.setdefault(f.category, []).append(f)
        return result

    @property
    def action_plan(self) -> list[dict]:
        """Ordered list of actions, high-severity first."""
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        sorted_findings = sorted(self.findings, key=lambda f: order.get(f.severity, 4))
        return [
            {
                "priority": f.severity.upper(),
                "category": f.category,
                "action": f.action,
                "estimated_monthly_saving": f.estimated_monthly_savings,
                "affected_lines": ", ".join(f.affected_lines[:5]),
            }
            for f in sorted_findings
            if f.action
        ]

    @property
    def risk_flags(self) -> list[AuditFinding]:
        return [
            f for f in self.findings
            if f.severity in ("high", "medium")
            and f.category in ("billing_consistency", "discounts", "taxes")
        ]
