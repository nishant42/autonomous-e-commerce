"""Reorder agent.

Trigger: schedule, a stockout-risk event, or a published verdict.
Decides: how much of each variant to buy, from whom, by when.
Never computes a quantity itself: the demand and quantity engines do that, and
every figure in the rationale must trace to an evidence row.
"""
from core import bus, db, harness, gateway
from engines import quantity
from engines import demand as demand_engine
from agents import tools

AGENT = "reorder"
TOOLS = ["sales_panel", "availability_history", "lost_demand_signals", "returns_by_variant",
         "supplier_terms", "open_orders", "cash_position", "economics"]

RATIONALE = ("{colour}: {units_per_available_day} units per available day over "
             "{days_it_was_buyable} buyable days ({days_it_was_unbuyable} days unbuyable), "
             "{back_in_stock_signups} back-in-stock sign-ups, substitution-corrected demand "
             "{real_demand_units} units per {period_days} days, service level "
             "{service_level_fraction}, order {order_quantity_units} units giving "
             "{cover_after_arrival_WEEKS} weeks of cover for {capital_EUR} EUR.")


def _checker(conn, intent, payload, ctx):
    """Independent re-derivation for T2 proposals (maker-checker).

    The checker does not re-run the maker's arithmetic, which would only
    reproduce its mistakes. It brackets the decision: a defensible order lies
    between covering median demand and covering the 90th percentile, with a
    tolerance either side. Anything outside that bracket goes to a human.
    """
    lo, hi = ctx.get("checker_lo"), ctx.get("checker_hi")
    if lo is None or hi is None:
        return False, "no independent derivation available"
    q = payload["qty"]
    if hi == 0:
        return q == 0, "independent derivation says no order is needed"
    ok = lo * 0.8 <= q <= hi * 1.2
    return ok, "independent bracket P50 %d to P90 %d, proposed %d" % (lo, hi, q)


@bus.subscribe("reorder.due")
def handle(conn, payload):
    # Which configuration this run uses is part of the trigger, so one deployment
    # serves several verticals: linen on the durable config, a fresh aisle on
    # reorder_fresh, sunglasses on a seasonal one. The code below is identical.
    cfg = harness.load_config(payload.get("config", AGENT))
    gpolicy = harness.load_config("policy")
    policy = dict(gpolicy)
    policy.update(cfg["policy"])
    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "schedule"))
    h.config_name = payload.get("config", AGENT)
    for name in TOOLS:
        h.register(name, getattr(tools, name))

    proposals = []
    for variant_id in payload["variants"]:
        h.evidence = []                              # evidence per decision
        h.new_decision(variant_id)
        rec, _ = h.read("sales_panel", variant_id=variant_id,
                        intended_discount=cfg["policy"]["intended_discount_pct"])
        avail, _ = h.read("availability_history", variant_id=variant_id)
        signals, _ = h.read("lost_demand_signals", variant_id=variant_id)
        terms, _ = h.read("supplier_terms", variant_id=variant_id)
        econ, _ = h.read("economics", variant_id=variant_id)
        oo, _ = h.read("open_orders", variant_id=variant_id)
        h.read("cash_position", policy=policy)

        # stage 5: things that must be true before any quantity is considered
        failures = h.verify([
            ("history", rec["period_days"] >= cfg["policy"]["min_history_days"],
             "only %d days of history" % rec["period_days"]),
            ("snapshot_freshness", avail["freshness_ok"], "inventory snapshot stale or missing"),
        ])
        if failures:
            h.anomaly("reorder_blocked", "medium", "%s: %s" % (variant_id, failures))
            proposals.append({"variant_id": variant_id, "blocked": failures})
            continue

        h.step("rule", "sanity checks before any quantity",
               "history %s days (need %s), snapshot fresh: %s"
               % (rec["period_days"], cfg["policy"]["min_history_days"], avail["freshness_ok"]),
               data={"failures": failures})
        if rec["signal_conflict"]:
            h.anomaly("demand_signal_conflict", "high",
                      "%s: model says %.0f censored units, unmet signals imply at least %.0f"
                      % (variant_id, rec["censored_gap"], rec["unmet_signal_lower_bound"]))

        h.step("engine", "reconstruct demand",
               "%s units shipped over %s buyable days -> %s units of real demand"
               % (rec["units_shipped"], rec["available_days"], rec["reconstructed_demand_period"]),
               data={"rate_of_sale": rec["ros_per_available_day"],
                     "substitution_removed": rec["substitution_share"],
                     "price_factor": rec["price_factor"], "return_rate": rec["return_rate"]},
               fn=demand_engine.reconstruct)

        # When the model's reconstruction and the unmet-demand signals disagree
        # by a wide margin, somebody has to decide which to believe. That is a
        # judgment about evidence quality, not arithmetic.
        trust = None
        if rec["signal_conflict"]:
            trust = h.judge(
                "Demand reconstruction and the unmet-demand signals disagree for %s. "
                "Which should the order be based on?" % variant_id,
                ["reconstruction", "signals", "escalate_to_human"],
                {"variant": variant_id,
                 "reconstructed_hidden_demand": rec["censored_gap"],
                 "signals_imply_at_least": rec["unmet_signal_lower_bound"],
                 "back_in_stock_signups": signals.get("back_in_stock"),
                 "views_while_unbuyable": signals.get("oos_product_view"),
                 "days_unbuyable": avail["unbuyable_days"]},
                default="reconstruction",
                tool_names=["lost_demand_signals", "availability_history", "sales_panel"])
            if trust["choice"] == "escalate_to_human":
                h.anomaly("demand_evidence_disputed", "high",
                          "%s: %s" % (variant_id, trust["why"][:160]))

        decision = quantity.order(rec, terms, cfg["policy"], avail["on_hand_now"], oo["on_order"], econ)
        h.step("engine", "newsvendor quantity",
               "service level %.0f%% from margin %.2f against leftover cost %.2f -> order %s units"
               % (decision["service_level"] * 100, decision["Cu"], decision["Co"], decision["qty"]),
               data={"order_up_to": decision["order_up_to"], "on_hand": decision["on_hand"],
                     "case_pack": decision["case_pack"],
                     "cover_after_weeks": decision["cover_after_weeks"]},
               fn=quantity.order)

        # the checker's independent bracket: cover P50 demand at the low end,
        # cover P90 demand at the high end, both net of stock already available
        pack = terms["case_pack"]
        def _bracket(level):
            raw = max(0, level - avail["on_hand_now"] - oo["on_order"])
            return int(((raw + pack - 1) // pack) * pack)
        # both ends use the same total variability as the maker (demand plus
        # lead-time), so the bracket tests the decision and not the arithmetic
        checker_lo = _bracket(decision["demand_mu"])
        checker_hi = _bracket(decision["demand_mu"] + 1.2816 * decision["demand_sd"])

        colour = db.scalar(conn, "SELECT colour FROM variant WHERE id=?", (variant_id,), variant_id)
        # Every key carries its unit. The model is told not to invent numbers,
        # but nothing stopped it calling weeks "days" until the key said so.
        facts = {
            "colour": colour,
            "units_per_available_day": rec["ros_per_available_day"],
            "days_it_was_buyable": rec["available_days"],
            "days_it_was_unbuyable": avail["unbuyable_days"],
            "back_in_stock_signups": int(signals.get("back_in_stock", 0) or 0),
            "real_demand_units": rec["reconstructed_demand_period"],
            "period_days": rec["period_days"],
            "service_level_fraction": decision["service_level"],
            "order_quantity_units": decision["qty"],
            "cover_after_arrival_WEEKS": decision["cover_after_weeks"],
            "capital_EUR": decision["capital_eur"],
        }
        rationale = h.rationale(facts, RATIONALE)
        uncited = h.uncited_numbers(rationale, extra=[facts, decision])
        if uncited:
            rationale = RATIONALE.format(**facts)        # fall back rather than publish untraceable numbers

        sales_12w = db.scalar(conn, """
            SELECT SUM(units) FROM sales_fact WHERE variant_id=?
              AND ts >= datetime('now','-84 day')""", (variant_id,))
        demand_12w = rec["net_ros"] * 84          # the number the sanity band is checked against
        row = h.propose(
            "propose_reorder",
            {"variant_id": variant_id, "qty": decision["qty"], "supplier_id": terms["supplier_id"],
             "need_by": payload.get("need_by", "2026-12-15")},
            policy,
            ctx={"cover_after_order_weeks": decision["cover_after_weeks"],
                 "sales_12w": sales_12w or 0, "demand_12w": demand_12w,
                 "checker_lo": checker_lo, "checker_hi": checker_hi},
            rationale=rationale, period=payload.get("period", "2026-W44"), checker=_checker,
        )
        proposals.append({"variant_id": variant_id, "decision": decision, "ledger": dict(row),
                          "rationale": rationale, "reconstruction": rec})

    h.finish("proposed %d" % len(proposals))
    bus.emit(conn, "reorder.cycle.complete", {"count": len(proposals)})
    handle.last = proposals                             # for the CLI report
    return proposals


handle.last = []
