# -*- coding: utf-8 -*-
"""Economic evaluator with explicit capex/operating separation."""

from __future__ import annotations

from typing import Any

from production_model import ASSUMPTIONS, baseline_result


class EconomicEvaluator:
    """Compute incremental economics without hiding capex double counting.

    ``production_model`` subtracts a monthly capex amortization from
    contribution and also divides the full capex by ``monthly_gain`` for its
    reported payback. Those two operations are not the same cash-flow basis.
    This evaluator exposes both numbers and labels the difference.
    """

    def __init__(self, amortize_months: int | None = None, annual_opex_cny: float = 0.0):
        self.amortize_months = int(amortize_months or ASSUMPTIONS.get("capex_amortize_months", 36))
        self.annual_opex_cny = float(annual_opex_cny)

    def evaluate(self, production_result: dict[str, Any], *, scenario: str = "base") -> dict[str, Any]:
        metrics = production_result.get("metrics", production_result)
        contribution = float(metrics.get("contribution", 0.0))
        capex_wan = float(metrics.get("capex_wan", 0.0))
        monthly_gain_reported = contribution - float(baseline_result()["contribution"])
        capex_monthly = capex_wan * 10000.0 / self.amortize_months if capex_wan else 0.0
        operating_gain = monthly_gain_reported + capex_monthly
        factor = {"conservative": 0.7, "base": 1.0, "optimistic": 1.3}.get(scenario, 1.0)
        operating_gain *= factor
        annual_net = operating_gain * 12.0 - self.annual_opex_cny
        payback = (capex_wan * 10000.0 / annual_net * 12.0) if annual_net > 0 and capex_wan > 0 else None
        reported_payback = metrics.get("payback_months")
        return {
            "scenario": scenario,
            "capex_wan": capex_wan,
            "monthly_gain_after_amortization": monthly_gain_reported,
            "capex_monthly_amortization": capex_monthly,
            "monthly_operating_gain_before_capex": operating_gain,
            "annual_net_benefit": annual_net,
            "payback_months_cash_basis": payback,
            "payback_months_reported_by_production_model": reported_payback,
            "double_counting_warning": (
                "production_model subtracts capex amortization in contribution and also "
                "uses monthly_gain for payback; cash-basis payback is reported separately"
            ),
            "annual_opex_cny": self.annual_opex_cny,
            "available": annual_net > 0,
        }

