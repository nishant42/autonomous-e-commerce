"""Quantity engine: newsvendor service level, order-up-to, and the constraints.

Called by the reorder agent. The service level is derived from the economics of
the item rather than set as a blanket policy, which is what makes the same code
correct for sunglasses and for yoghurt.
"""
import math

from engines import demand as demand_engine


def service_level(cm_per_unit, holding_cost, markdown_cost, shelf_life_days=None,
                  expected_sellthrough_days=120, unit_cost=0.0, lost_customer_value=0.0):
    """Critical ratio: Cu / (Cu + Co)."""
    cu = cm_per_unit + lost_customer_value
    co = holding_cost * (expected_sellthrough_days / 30.0) + markdown_cost
    if shelf_life_days:                    # perishable: leftovers are written off
        co = unit_cost + holding_cost * (shelf_life_days / 30.0)
    cr = cu / (cu + co) if (cu + co) > 0 else 0.5
    return max(0.05, min(0.995, cr)), round(cu, 2), round(co, 2)


def protection_interval(lead_time_mean, lead_time_sd, review_period_days):
    return lead_time_mean + review_period_days, lead_time_sd


def order(rec, terms, policy, on_hand, on_order, economics):
    """Return the full order decision with every intermediate value exposed."""
    sl, cu, co = service_level(
        cm_per_unit=economics["cm_per_unit"],
        holding_cost=economics["holding_cost_per_unit_month"],
        markdown_cost=economics["expected_markdown_per_unit"],
        shelf_life_days=policy.get("shelf_life_days"),
        expected_sellthrough_days=economics.get("expected_sellthrough_days", 120),
        unit_cost=terms["unit_cost"],
        lost_customer_value=economics.get("lost_customer_value", 0.0),
    )
    pi_days, lt_sd = protection_interval(
        terms["lead_time_mean_days"], terms["lead_time_sd_days"], policy["review_period_days"])

    q = demand_engine.over_horizon(rec, pi_days, sl)
    # Lead-time variability adds its own term: sd_total^2 = LT*var_d + d^2*var_LT
    sd_total = math.sqrt(q["sd"] ** 2 + (rec["net_ros"] ** 2) * (lt_sd ** 2))
    order_up_to = q["mu"] + q["z"] * sd_total

    raw = max(0.0, order_up_to - on_hand - on_order)
    pack = max(1, terms["case_pack"])
    qty = int(math.ceil(raw / pack) * pack)
    if qty and qty < terms["moq"]:
        qty = int(math.ceil(terms["moq"] / pack) * pack)

    weekly = max(rec["net_ros"] * 7, 0.0001)
    cover_after = (on_hand + on_order + qty) / weekly
    capped = False
    if cover_after > policy["cover_cap_weeks"]:
        allowed = max(0.0, policy["cover_cap_weeks"] * weekly - on_hand - on_order)
        qty = int(math.floor(allowed / pack) * pack)
        capped = True
        cover_after = (on_hand + on_order + qty) / weekly

    if policy.get("shelf_life_days"):
        # Never order more than can be sold inside the shelf life.
        sellable = rec["net_ros"] * policy["shelf_life_days"]
        qty = min(qty, int(math.floor(sellable / pack) * pack))

    return {
        "service_level": round(sl, 3), "Cu": cu, "Co": co,
        "protection_interval_days": round(pi_days, 1),
        "demand_mu": q["mu"], "demand_sd": round(sd_total, 2), "z": q["z"],
        "p50": q["p50"], "p90": q["p90"],
        "order_up_to": round(order_up_to, 1),
        "on_hand": on_hand, "on_order": on_order,
        "raw_qty": round(raw, 1), "case_pack": pack, "moq": terms["moq"],
        "qty": qty, "cover_after_weeks": round(cover_after, 1),
        "cover_cap_applied": capped,
        "capital_eur": round(qty * terms["unit_cost"], 2),
    }
