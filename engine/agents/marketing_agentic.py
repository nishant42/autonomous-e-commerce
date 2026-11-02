"""Model-led ad investigation, constrained by computed options and the gateway."""
from datetime import datetime, timezone

from core import bus, db, harness
from engines import allocator
from agents import tools

AGENT = "marketing_allocator"
TOOL_SPEC = [
    {"name": name, "args": args, "description": description}
    for name, args, description in [
        ("ad_metrics_panel", {"product_id": "the product"}, "Our measured spend, orders, clicks and frequency."),
        ("creative_history", {"cell_id": "the ad cell"}, "First-week CTR for fatigue comparison."),
        ("holdout_readout", {"product_id": "the product"}, "Descriptive orders in regions without ads."),
        ("stock_cover", {"product_id": "the product"}, "Days of stock per variant."),
        ("margin_table", {"product_id": "the product"}, "Contribution margin after costs and returns."),
        ("signal_health", {"product_id": "the product"}, "Platform counts against shop order counts."),
        ("experiment_budget", {"product_id": "the product"}, "Allocated and spent experiment budget."),
        ("band_options", {"cell_id": "the ad cell"}, "Required: computed budgets, permitted actions, and guards. Choose only a permitted action."),
    ]
]
TASK = """Investigate ad {cell}, product {product}. Decide why it is working or failing.
Call band_options before answering. You may read other tools in any order.
Only choose an action in permitted_actions. Budgets are computed, never yours to invent.
Do not infer creative fatigue or audience saturation without reading supporting evidence.
Return {{"answer": {{"action": "<permitted action>", "why": "<brief evidence-based reason>"}}}}.
"""


def hours_since_change(conn, cell_id):
    last = db.scalar(conn, "SELECT last_changed_at FROM cooldown WHERE lever=?",
                     ("budget:" + cell_id,), None)
    if not last:
        return 1e9
    then = datetime.fromisoformat(last.replace("Z", "+00:00"))
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - then).total_seconds() / 3600)


def options_for(conn, cell, target, policy, cover, health, experiment, model_cpa=None):
    """Shared by the agent and the explainer: guard constraints precede judgment."""
    hours = hours_since_change(conn, cell["cell_id"])
    cooldown = hours < policy["cooldown_hours_per_cell"]
    explained = allocator.explain_cell(conn, cell, target, policy, cover["hero_cover_days"],
                                       cooldown, model_cpa)
    daily = explained["daily_now"]
    delta = policy["max_change_pct"] / 100.0
    amounts = {"scale": round(daily * (1 + delta), 2), "hold": daily,
               "reduce": round(min(daily, max(target / 3, daily * (1 - delta))), 2),
               "pause": 0.0, "pause_acquisition": 0.0, "protect": daily,
               "request_creative": daily}
    action = explained["action"]
    spent_out = cell["spend"] >= policy["spend_exhaustion_multiple"] * target
    learning = cell["orders"] < policy["learning_conversions"] and not spent_out
    if action in ("protect", "pause_acquisition"):
        allowed = [action]
    elif cooldown or not allocator.exposure_met(cell, target, policy) or learning:
        allowed = ["hold"]
    elif action == "request_creative":
        allowed = ["hold", "request_creative"]
    else:
        allowed = ["hold", "reduce", "request_creative"]
        if action in ("scale", "pause"):
            allowed.append(action)
    frozen = not health["healthy"] or (experiment["allocated_eur"] <= experiment["spent_eur"])
    if frozen:
        allowed = [a for a in allowed if a != "scale"]
        if action == "scale":
            action = "hold"
            explained["reason"] = "scaling frozen: signal drift or experiment budget exhausted"
    explained.update({"action": action, "budget": amounts[action], "hours_since_change": hours,
                      "permitted_actions": allowed,
                      "budget_each_action_would_set": {a: amounts[a] for a in allowed},
                      "signal": health, "experiment": experiment,
                      "cost_per_order": round(cell["spend"] / cell["orders"], 2) if cell["orders"] else None,
                      "orders_last_7_days": cell["orders"], "spend_last_7_days": round(cell["spend"], 2)})
    return explained


@bus.subscribe("marketing.agentic")
def handle(conn, payload):
    cfg = harness.load_config(AGENT)
    policy = dict(harness.load_config("policy"), **cfg["policy"])
    product_id = payload.get("product_id", "p_towel")
    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "agentic"))
    for spec in TOOL_SPEC:
        if hasattr(tools, spec["name"]):
            h.register(spec["name"], getattr(tools, spec["name"]))
    cells = {c["cell_id"]: c for c in allocator.cell_stats(conn, product_id, 7) if not c["is_holdout"]}
    wanted = payload.get("cells") or list(cells)[:3]
    target = allocator.target_cpa(tools.margin_table(conn, product_id)["cm_per_unit"], policy["payback_factor"])
    model_cpas = allocator.model_view(conn, product_id, list(cells.values()), target)
    results = []
    for cell_id in wanted:
        if cell_id not in cells:
            continue
        cell = cells[cell_id]
        h.evidence = []
        h.new_decision(cell_id)
        cover, _ = h.read("stock_cover", product_id=product_id)
        health, _ = h.read("signal_health", product_id=product_id)
        experiment, _ = h.read("experiment_budget", product_id=product_id)

        def band_options(conn_, cell_id=cell_id):
            return options_for(conn_, cell, target, policy, cover, health, experiment,
                               model_cpas.get(cell_id, {}).get("expected_cpa"))

        h.register("band_options", band_options)
        out, events = h.investigate(TASK.format(cell=cell_id, product=product_id), TOOL_SPEC,
                                   {"product_id": [product_id], "cell_id": [cell_id]},
                                   required=["band_options"], max_steps=6)
        # Always record the authoritative calculation, including in fallback mode.
        computed, _ = h.read("band_options", cell_id=cell_id)
        daily = computed["daily_now"]
        decision = {"action": computed["action"], "budget": computed["budget"],
                    "why": computed["reason"], "source": "rules"}
        if out:
            answer = out["answer"]
            if answer.get("action") in computed["permitted_actions"]:
                action = answer["action"]
                decision = {"action": action, "budget": computed["budget_each_action_would_set"][action],
                            "why": answer["why"], "source": "agent"}
            else:
                h.step("verification", "model action rejected", "action outside guarded options")
        row = None
        period = payload.get("period", db.now()[:10])
        if decision["action"] in ("scale", "reduce") and decision["budget"] != daily:
            row = h.propose("propose_budget_change",
                            {"cell_id": cell_id, "from_eur": daily, "to_eur": decision["budget"]}, policy,
                            ctx={"sku_cover_days": cover["hero_cover_days"], "experiment_budget": experiment,
                                 "hours_since_change": computed["hours_since_change"],
                                 "portfolio_daily_total_eur": sum(c["spend"] / max(1, c["days"])
                                                                  for c in cells.values()) - daily + decision["budget"]},
                            rationale=decision["why"], period=period)
        elif decision["action"] in ("pause", "pause_acquisition"):
            pauses = db.scalar(conn, "SELECT COUNT(*) FROM ledger WHERE intent='propose_pause'"
                               " AND status='executed' AND substr(ts,1,10)=?"
                               " AND json_extract(payload,'$.cell_id') IN"
                               " (SELECT DISTINCT cell_id FROM ad_metrics WHERE product_id=?)",
                               (db.now()[:10], product_id))
            row = h.propose("propose_pause", {"cell_id": cell_id, "reason": decision["why"]}, policy,
                            ctx={"pauses_today": pauses}, rationale=decision["why"], period=period)
        elif decision["action"] == "request_creative":
            h.anomaly("creative_requested", "medium", "%s: %s" % (cell_id, decision["why"]))
        h.step("judgment", "decide " + cell_id, decision["why"],
               data={"decision": decision, "rules_would": computed["action"]}, fn=handle)
        results.append({"cell": cell_id, "decision": decision, "rules_would": computed["action"],
                        "options": computed["budget_each_action_would_set"], "target_cpa": target,
                        "cpa": computed["cost_per_order"],
                        "tool_calls": [e for e in events if e["kind"] == "tool_call"],
                        "ledger": dict(row) if row else None})
    h.finish("agentic marketing on %d cells" % len(results))
    handle.last = results
    return results


handle.last = []
