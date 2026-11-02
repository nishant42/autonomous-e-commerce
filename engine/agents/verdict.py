"""Product verdict agent: keep, fix, reprice, or kill - and product or site.

This is the agent that decides where the other two spend money. In a portfolio
of ten launches, the cost of a wrong 'keep' is three months of spend and a
reorder on a dead product; the cost of a wrong 'kill' is losing one of the two
winners that pay for everything. So the verdict separates a product failure
from a site failure before it recommends anything irreversible.
"""
from core import bus, db, harness
from engines import funnel, allocator
from agents import tools

AGENT = "product_verdict"
TOOLS = ["funnel_rates", "ad_metrics_panel", "margin_table", "stock_cover", "experiment_budget",
         "returns_by_variant", "portfolio_memory"]

KILL_RUNBOOK = [
    "stop all acquisition spend on the product (marketing agent, same cycle)",
    "cancel open purchase orders not yet shipped",
    "mark down remaining stock on a 3-step curve to clear within 60 days",
    "keep the storefront live until stock clears, then archive and release the domain (human signal)",
    "write the finding to portfolio memory as a prior for the next launch",
]


@bus.subscribe("verdict.weekly")
def handle(conn, payload):
    cfg = harness.load_config(AGENT)
    gpolicy = harness.load_config("policy")
    policy = dict(gpolicy)
    policy.update(cfg["policy"])
    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "weekly"))
    for name in TOOLS:
        h.register(name, getattr(tools, name))

    out = []
    for product_id in payload["products"]:
        h.evidence = []
        h.new_decision(product_id)
        rates, _ = h.read("funnel_rates", product_id=product_id, window_days=cfg["policy"]["window_days"])
        margin, _ = h.read("margin_table", product_id=product_id)
        cover, _ = h.read("stock_cover", product_id=product_id)
        budget, _ = h.read("experiment_budget", product_id=product_id)
        h.read("portfolio_memory", product_id=product_id)

        target = allocator.target_cpa(margin["cm_per_unit"], cfg["policy"]["payback_factor"])
        diag = funnel.diagnose(rates, target, margin["cm_per_unit"], cfg["policy"])

        h.step("engine", "decompose the funnel for %s" % product_id,
               "page %.0f%%, add to cart %.0f%%, checkout %.0f%%, purchase %.0f%%, refunds %.0f%%"
               % (rates["pdp_rate"] * 100, rates["atc_rate"] * 100, rates["checkout_rate"] * 100,
                  rates["purchase_rate"] * 100, rates["refund_rate"] * 100),
               data={"flags": diag["flags"], "cpa": rates["cpa"], "target_cpa": target},
               fn=funnel.rates)
        h.step("rule", "which stage is at fault", diag["diagnosis"],
               data={"verdict": diag["verdict"], "confidence": diag["confidence"],
                     "findings": diag["findings"]}, fn=funnel.diagnose)

        # Supply constraint is not a product verdict. A product starved of stock
        # is being judged on sales it was never allowed to make.
        supply_blocked = cover["worst_cover_days"] < 7
        if supply_blocked and diag["verdict"] in ("SCALE", "REPRICE", "KILL"):
            diag["actions"].insert(0, "reorder the out-of-stock variant first: %.0f days cover on the "
                                      "weakest variant means part of demand is unservable"
                                      % cover["worst_cover_days"])
            if diag["verdict"] == "KILL":
                diag["verdict"], diag["confidence"] = "CONTINUE_TEST", 0.4
                diag["diagnosis"] += " (kill withheld: the product has been out of stock)"

        budget_left = budget["allocated_eur"] - budget["spent_eur"]
        if diag["verdict"] == "CONTINUE_TEST" and budget_left <= 0:
            diag["verdict"] = "KILL"
            diag["diagnosis"] += "; experiment budget exhausted with no verdict reached"
            diag["confidence"] = 0.7

        # Which fix to try first is a judgment: the funnel says where the loss is,
        # not which remedy is cheapest to test. The options come from the engine.
        if diag["actions"] and diag["verdict"] in ("FIX_SITE", "REPRICE", "NEW_CREATIVE"):
            pick = h.judge(
                "Which single fix should %s try first?" % product_id,
                diag["actions"][:4],
                {"product": product_id, "diagnosis": diag["diagnosis"],
                 "stage_rates_percent": {k: round(rates[k] * 100, 1) for k in
                                         ("pdp_rate", "atc_rate", "checkout_rate",
                                          "purchase_rate", "refund_rate")},
                 "cost_per_order": rates["cpa"], "target_cost_per_order": target,
                 "experiment_budget_left": round(budget_left, 2)},
                default=diag["actions"][0],
                tool_names=["funnel_rates", "returns_by_variant", "portfolio_memory"])
            if pick["choice"] in diag["actions"]:
                diag["actions"].remove(pick["choice"])
                diag["actions"].insert(0, pick["choice"])
            diag["first_fix_reason"] = pick["why"]

        facts = {"product": product_id, "verdict": diag["verdict"], "diagnosis": diag["diagnosis"],
                 "atc": round(rates["atc_rate"] * 100, 1), "checkout": round(rates["checkout_rate"] * 100, 1),
                 "refund": round(rates["refund_rate"] * 100, 1),
                 "cpa": rates["cpa"] or 0, "target": target,
                 "sessions": rates["sessions"], "spend": round(rates["spend"], 2),
                 "budget_left": round(budget_left, 2)}
        rationale = h.rationale(
            facts,
            "{product}: {verdict} - {diagnosis}. Add-to-cart {atc}%, cart-to-checkout {checkout}%, "
            "refunds {refund}%, CPA {cpa} EUR against target {target} EUR on {sessions} sessions and "
            "{spend} EUR spent; {budget_left} EUR of experiment budget left.")

        row = h.propose("publish_verdict",
                        {"product_id": product_id, "verdict": diag["verdict"],
                         "confidence": float(diag["confidence"])},
                        policy,
                        ctx={"exposure_met": diag["exposure_met"]},
                        rationale=rationale, period=payload.get("period", "2026-W44"))

        if supply_blocked:
            h.step("rule", "supply check before any verdict",
                   "weakest variant has %.0f days of cover, so part of demand is unservable"
                   % cover["worst_cover_days"], data=cover)
        if diag["verdict"] == "KILL":
            h.anomaly("kill_recommended", "high", "%s: %s" % (product_id, diag["diagnosis"]))

        out.append({"product_id": product_id, "rates": rates, "target_cpa": target,
                    "diagnosis": diag, "ledger": dict(row), "rationale": rationale,
                    "budget_left": round(budget_left, 2),
                    "runbook": KILL_RUNBOOK if diag["verdict"] == "KILL" else []})

    h.finish("published %d verdicts" % len(out))
    bus.emit(conn, "verdict.published", {"count": len(out)})
    handle.last = out
    return out


handle.last = []
