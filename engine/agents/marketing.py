"""Marketing allocation agent.

Daily: judge each cell against its target CPA, within guard rails, and only
once the cell has earned the right to be judged.
Weekly: resample the channel split from the posterior of profit per euro.
"""
from core import bus, harness
from engines import allocator
from agents import tools

AGENT = "marketing_allocator"
TOOLS = ["ad_metrics_panel", "orders_panel", "margin_table", "stock_cover", "creative_history",
         "holdout_readout", "experiment_budget", "signal_health"]


@bus.subscribe("marketing.daily")
def handle(conn, payload):
    cfg = harness.load_config(AGENT)
    gpolicy = harness.load_config("policy")
    policy = dict(gpolicy)
    policy.update(cfg["policy"])
    product_id = payload["product_id"]

    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "daily"))
    for name in TOOLS:
        h.register(name, getattr(tools, name))

    health, _ = h.read("signal_health", product_id=product_id)
    margin, _ = h.read("margin_table", product_id=product_id)
    cover, _ = h.read("stock_cover", product_id=product_id)
    hold, _ = h.read("holdout_readout", product_id=product_id)
    budget, _ = h.read("experiment_budget", product_id=product_id)
    panel, _ = h.read("ad_metrics_panel", product_id=product_id, window_days=7)

    target = allocator.target_cpa(margin["cm_per_unit"], cfg["policy"]["payback_factor"])
    frozen = not health["healthy"]
    if frozen:
        h.anomaly("signal_drift", "high",
                  "platform reports %s orders vs %s in our own data (%.0f%% drift): scaling frozen"
                  % (health["platform"], health["ours"], health["drift_pct"]))

    # A variant being out of stock is a supply problem, not a reason to stop
    # advertising the ones that are in stock: use the hero's cover.
    hero_cover = cover["hero_cover_days"]
    if cover["worst_cover_days"] < policy["min_cover_days_for_acquisition"]:
        h.anomaly("variant_out_of_stock", "medium",
                  "worst variant cover %.0f days; unmet demand is being lost while ads run"
                  % cover["worst_cover_days"])

    model_cpas = allocator.model_view(conn, product_id, panel["cells"], target)
    if model_cpas:
        h.anomaly("model_in_use", "info",
                  "a promoted model is supplying expected CPA for %d cell(s); the bands still "
                  "decide and the observation wins any disagreement over 2x" % len(model_cpas))

    h.step("rule", "target cost per order",
           "contribution margin %.2f x payback %.1f = target EUR %.2f"
           % (margin["cm_per_unit"], cfg["policy"]["payback_factor"], target),
           data={"cm_per_unit": margin["cm_per_unit"]}, fn=allocator.target_cpa)
    h.step("rule", "signal health",
           "platform reports %s orders against %s in our own data, drift %s%%"
           % (health["platform"], health["ours"], health["drift_pct"]),
           data=health, fn=allocator.signal_health)
    if model_cpas:
        first = list(model_cpas.values())[0]
        h.step("model", "promoted model supplies expected cost per order",
               "%s predicts %s orders next week for the first cell, implying EUR %s"
               % (first.get("model"), first.get("expected_orders_7d"), first.get("expected_cpa")),
               data=model_cpas, fn=allocator.model_view)

    results = []
    incrementality = hold.get("incrementality_factor") or 1.0
    for cell in panel["cells"]:
        daily_now = round(cell["spend"] / max(1, cell["days"]), 2)
        mv = model_cpas.get(cell["cell_id"], {})
        action, new_budget, reason = allocator.decide_cell(
            conn, cell, target, policy, hero_cover, in_cooldown=False,
            model_cpa=mv.get("expected_cpa"))

        # The bands leave one case genuinely ambiguous: a cell inside target but
        # without headroom. Trimming it, holding it, or replacing the creative are
        # all defensible, and the right answer depends on context a rule cannot
        # hold. That judgment goes to the model, fenced to these three options.
        if action == "hold" and cell["orders"] and allocator.exposure_met(cell, target, policy):
            cpa = cell["spend"] / cell["orders"]
            if target * 0.8 < cpa <= target:
                verdict = h.judge(
                    "Cell %s is profitable but has no headroom. What should we do?" % cell["cell_id"],
                    ["hold", "reduce", "request_creative"],
                    {"cell": cell["cell_id"], "platform": cell["platform"],
                     "cost_per_order": round(cpa, 2), "target_cost_per_order": target,
                     "orders_last_7_days": cell["orders"],
                     "spend_last_7_days": round(cell["spend"], 2),
                     "times_each_person_saw_it": round(cell["frequency"] or 0, 2),
                     "model_expected_cost_per_order": mv.get("expected_cpa"),
                     "share_of_orders_that_are_organic": hold.get("organic_share"),
                     "experiment_budget_left": round(budget["allocated_eur"] - budget["spent_eur"], 2)},
                    default="hold",
                    tool_names=["creative_history", "ad_metrics_panel", "holdout_readout"])
                if verdict["choice"] != "hold":
                    action = verdict["choice"]
                    reason = "%s (judgment: %s)" % (reason, verdict["why"][:110])
                    if action == "reduce":
                        new_budget = round(daily_now * (1 - policy["max_change_pct"] / 100.0), 2)
        daily_now = round(cell["spend"] / max(1, cell["days"]), 2)

        # Discount reported performance by the holdout before acting on it.
        adj_cpa = (cell["spend"] / (cell["orders"] * incrementality)) if cell["orders"] else None
        if frozen and action == "scale":
            action, new_budget, reason = "hold", daily_now, "scaling frozen: " + reason

        row = None
        if action in ("scale", "reduce"):
            facts = {"cell": cell["cell_id"], "cpa": round(cell["spend"] / cell["orders"], 2),
                     "target": target, "orders": cell["orders"], "spend": round(cell["spend"], 2),
                     "from_eur": round(daily_now, 2), "to_eur": round(new_budget, 2),
                     "incremental_cpa": round(adj_cpa, 2) if adj_cpa else 0}
            rationale = h.rationale(
                facts,
                "{cell}: CPA {cpa} EUR against target {target} EUR on {orders} orders and {spend} EUR spent; "
                "holdout-adjusted CPA {incremental_cpa} EUR; daily budget {from_eur} -> {to_eur} EUR.")
            row = h.propose("propose_budget_change",
                            {"cell_id": cell["cell_id"], "from_eur": round(daily_now, 2),
                             "to_eur": round(new_budget, 2)},
                            policy,
                            ctx={"sku_cover_days": hero_cover, "experiment_budget": budget,
                                 "portfolio_daily_total_eur": sum(c["spend"] / max(1, c["days"])
                                                                  for c in panel["cells"]),
                                 "hours_since_change": 999},
                            rationale=rationale, period=payload.get("period", "2026-10-30"))
        elif action in ("pause", "pause_acquisition"):
            row = h.propose("propose_pause", {"cell_id": cell["cell_id"], "reason": reason}, policy,
                            ctx={"pauses_today": sum(1 for r in results if r["action"].startswith("pause"))},
                            rationale=reason, period=payload.get("period", "2026-10-30"))

        h.step("rule", "decide %s" % cell["cell_id"], reason,
               data={"action": action, "from_eur": round(daily_now, 2),
                     "to_eur": round(new_budget, 2), "orders": cell["orders"],
                     "spend": round(cell["spend"], 2)}, fn=allocator.decide_cell)
        results.append({"cell": cell["cell_id"], "platform": cell["platform"],
                        "model": mv or None,
                        "spend": round(cell["spend"], 2), "orders": cell["orders"],
                        "cpa": round(cell["spend"] / cell["orders"], 2) if cell["orders"] else None,
                        "action": action, "from_eur": round(daily_now, 2), "to_eur": round(new_budget, 2),
                        "reason": reason, "ledger": dict(row) if row else None})

    h.finish("decided %d cells" % len(results))
    handle.last = {"product_id": product_id, "target_cpa": target, "signal": health,
                   "holdout": hold, "budget": budget, "cover": cover, "cells": results}
    return handle.last


@bus.subscribe("marketing.weekly")
def weekly(conn, payload):
    """Channel-level reallocation: Thompson sampling, capped and floored."""
    cfg = harness.load_config(AGENT)
    product_id = payload["product_id"]
    h = harness.Harness(conn, AGENT, cfg, trigger="weekly")
    for name in TOOLS:
        h.register(name, getattr(tools, name))
    panel, _ = h.read("ad_metrics_panel", product_id=product_id, window_days=14)
    margin, _ = h.read("margin_table", product_id=product_id)
    target = allocator.target_cpa(margin["cm_per_unit"], cfg["policy"]["payback_factor"])

    total_spend = sum(c["spend"] for c in panel["cells"] if not c["is_holdout"]) or 1.0
    arms = {}
    for c in panel["cells"]:
        if c["is_holdout"]:
            continue
        cpa = (c["spend"] / c["orders"]) if c["orders"] else target * 3
        profitable = c["orders"] if cpa <= target else 0
        arms[c["cell_id"]] = {"wins": profitable, "losses": max(0, c["orders"] - profitable) + 1,
                              "share": c["spend"] / total_spend}
    shares = allocator.thompson(arms, cfg["policy"]["weekly"])
    h.finish("reallocated %d arms" % len(shares))
    weekly.last = {"product_id": product_id, "target_cpa": target,
                   "before": {k: round(v["share"], 4) for k, v in arms.items()}, "after": shares}
    return weekly.last


handle.last = {}
weekly.last = {}
