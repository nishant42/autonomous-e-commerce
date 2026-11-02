"""A reorder agent that genuinely plans its own investigation.

The difference from the pipeline version is who decides what to look at. There,
the order of the reads is written in the code. Here the model is given a goal,
a set of tools, and a budget of steps, and it chooses: it can notice a long
stock-out and go looking for unmet-demand signals, it can check whether a
sibling absorbed the demand, it can decide it has enough and stop.

What it still cannot do is invent a number. The quantity engine is one of its
tools, and the final order must be one of the quantities that tool returned.
The model chooses between options the maths produced; it never produces one.

That boundary is the whole design: autonomy over the reasoning, none over the
arithmetic.
"""
import json

from core import bus, db, gateway, harness, model
from engines import demand as demand_engine
from engines import quantity as quantity_engine
from agents import tools

AGENT = "reorder"

TOOL_SPEC = [
    {"name": "sales_panel", "args": {"variant_id": "the variant"},
     "description": "Reconstructed demand: rate of sale per day it was buyable, substitution "
                    "share, discount effect, return rate, demand hidden by stock-outs."},
    {"name": "availability_history", "args": {"variant_id": "the variant"},
     "description": "How many days it was buyable, when it first went out of stock, stock now."},
    {"name": "lost_demand_signals", "args": {"variant_id": "the variant"},
     "description": "What people did while it was unbuyable: back-in-stock sign-ups, views, searches."},
    {"name": "returns_by_variant", "args": {"variant_id": "the variant"},
     "description": "How much of what sold came back."},
    {"name": "economics", "args": {"variant_id": "the variant"},
     "description": "Price, unit cost, margin, holding and markdown costs."},
    {"name": "supplier_terms", "args": {"variant_id": "the variant"},
     "description": "Minimum order, case pack, unit cost, and the supplier's observed lead time."},
    {"name": "open_orders", "args": {"variant_id": "the variant"},
     "description": "Units already on their way, so nothing is ordered twice."},
    {"name": "cash_position", "args": {},
     "description": "Cash on hand and weeks of runway."},
    {"name": "compute_quantities", "args": {"variant_id": "the variant"},
     "description": "THE MATHS. Returns the order quantities the newsvendor engine supports: a "
                    "recommended quantity, a conservative one and a bold one, each with the cover "
                    "and capital it implies. Your final order must be one of these numbers."},
]

TASK = """You are deciding a purchase order for one product variant: {variant}.

Work out whether to order, and how much. Investigate in whatever order you
think is right - you do not have to call every tool.

Rules you cannot break:
- You must call compute_quantities before proposing an order.
- Your quantity must be exactly one of the numbers that tool returned. You may
  choose the conservative, recommended or bold option, but you may not invent a
  number or adjust one.
- If the evidence is contradictory or the money is large and the case is weak,
  escalate instead of ordering.

Answer with one JSON object:
  {{"answer": {{"action": "order" | "no_order" | "escalate",
              "quantity": <number, 0 if not ordering>,
              "option": "conservative" | "recommended" | "bold" | "none",
              "why": "<two sentences an owner would accept>"}}}}
"""


def _quantity_options(conn, variant_id, cfg):
    """The only quantities the agent may choose between."""
    rec = demand_engine.reconstruct(conn, variant_id, 90,
                                    cfg["policy"]["intended_discount_pct"])
    terms = tools.supplier_terms(conn, variant_id)
    econ = tools.economics(conn, variant_id)
    on_hand = db.scalar(conn, "SELECT on_hand FROM inventory_snapshot WHERE variant_id=?"
                              " ORDER BY ts DESC LIMIT 1", (variant_id,), 0) or 0
    on_order = tools.open_orders(conn, variant_id)["on_order"]
    base = quantity_engine.order(rec, terms, cfg["policy"], on_hand, on_order, econ)
    pack = max(1, terms["case_pack"])

    def rounded(units):
        return int(max(0, round(units / pack) * pack))

    # All three must be built from the SAME spread, or "bold" can come out
    # smaller than "recommended" and the options contradict each other. The
    # agent caught exactly that, refused to spend, and was right to.
    mu, sd = base["demand_mu"], base["demand_sd"]
    options = {
        "conservative": {"quantity": rounded(max(0, mu - on_hand - on_order)),
                         "covers": "median demand only, accepts stocking out half the time"},
        "recommended": {"quantity": base["qty"],
                        "covers": "%.0f%% service level, derived from this item's own margin"
                                  % (base["service_level"] * 100)},
        "bold": {"quantity": rounded(max(0, mu + 1.645 * sd - on_hand - on_order)),
                 "covers": "95% service level, for when running out is very expensive"},
    }
    # and if they still do not increase, say so rather than present nonsense
    order_check = [options["conservative"]["quantity"], options["recommended"]["quantity"],
                   options["bold"]["quantity"]]
    options["_consistent"] = order_check == sorted(order_check)
    for name, opt in options.items():
        if not isinstance(opt, dict):
            continue
        weekly = max(rec["net_ros"] * 7, 0.0001)
        opt["cover_after_weeks"] = round((on_hand + on_order + opt["quantity"]) / weekly, 1)
        opt["capital_eur"] = round(opt["quantity"] * terms["unit_cost"], 2)
    return {"options": options, "on_hand": on_hand, "on_order": on_order,
            "case_pack": pack, "engine": base, "terms": terms, "reconstruction": rec}


@bus.subscribe("reorder.agentic")
def handle(conn, payload):
    cfg = harness.load_config(payload.get("config", "reorder"))
    policy = dict(harness.load_config("policy"))
    policy.update(cfg["policy"])
    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "agentic"))
    for spec in TOOL_SPEC:
        if hasattr(tools, spec["name"]):
            h.register(spec["name"], getattr(tools, spec["name"]))

    results = []
    for variant_id in payload["variants"]:
        h.evidence = []
        h.new_decision(variant_id)
        computed = {"value": None}

        def compute_quantities(conn_, variant_id=variant_id):
            out = _quantity_options(conn_, variant_id, cfg)
            computed["value"] = out
            return {"options": {k: v for k, v in out["options"].items() if isinstance(v, dict)},
                    "options_increase_as_expected": out["options"].get("_consistent", True),
                    "on_hand": out["on_hand"],
                    "on_order": out["on_order"], "case_pack": out["case_pack"]}

        h.register("compute_quantities", compute_quantities)
        h.register("cash_position", lambda conn_, p=policy: tools.cash_position(conn_, p))

        out, events = h.investigate(TASK.format(variant=variant_id), TOOL_SPEC,
                                   {"variant_id": [variant_id]},
                                   required=["compute_quantities"], max_steps=8)

        # Whatever happened, the maths must exist before anything is proposed.
        if computed["value"] is None:
            h.read("compute_quantities", variant_id=variant_id)
        opts = {k: v for k, v in computed["value"]["options"].items() if isinstance(v, dict)}
        allowed = {name: o["quantity"] for name, o in opts.items()}

        decision = {"action": "order", "quantity": opts["recommended"]["quantity"],
                    "option": "recommended", "why": "", "source": "engine default"}
        if out:
            answer = out.get("answer")
            if isinstance(answer, str):
                try:
                    answer = json.loads(answer)
                except ValueError:
                    answer = None
            if isinstance(answer, dict):
                choice = answer.get("option")
                qty = answer.get("quantity")
                action = answer.get("action")
                if action in ("order", "no_order", "escalate") and (
                        action != "order" or (choice in allowed and qty == allowed[choice])):
                    decision = {"action": action,
                                "quantity": allowed.get(choice, 0) if action == "order" else 0,
                                "option": choice if action == "order" else "none",
                                "why": answer.get("why", ""), "source": "agent"}
                else:
                    decision["why"] = ("the agent proposed %s/%s, which is not one of the "
                                       "computed quantities, so the engine's recommendation stands"
                                       % (choice, qty))
                    decision["source"] = "engine default (agent answer rejected)"

        if not computed["value"]["options"].get("_consistent", True):
            decision = {"action": "escalate", "quantity": 0, "option": "none",
                        "why": "computed options contradict each other; human review required",
                        "source": "verification"}
        if decision["action"] == "order" and decision["quantity"] == 0:
            decision["action"] = "no_order"

        h.step("judgment", "agent decided: %s" % decision["action"],
               "%s units (%s) - %s" % (decision["quantity"], decision["option"],
                                       (decision["why"] or "")[:110]),
               data={"options": allowed, "chosen": decision, "tool_calls": len(out["trace"]) if out else 0},
               fn=handle)

        row = None
        if decision["action"] == "order" and decision["quantity"] > 0:
            rec = computed["value"]["reconstruction"]
            row = h.propose(
                "propose_reorder",
                {"variant_id": variant_id, "qty": int(decision["quantity"]),
                 "supplier_id": computed["value"]["terms"]["supplier_id"],
                 "need_by": payload.get("need_by", "2026-12-15")},
                policy,
                ctx={"cover_after_order_weeks": opts[decision["option"]]["cover_after_weeks"],
                     "demand_12w": rec["net_ros"] * 84,
                     "sales_12w": db.scalar(conn, "SELECT SUM(units) FROM sales_fact"
                                                  " WHERE variant_id=?", (variant_id,)) or 0,
                     "checker_lo": opts["conservative"]["quantity"],
                     "checker_hi": opts["bold"]["quantity"]},
                rationale=decision["why"] or "agent chose the %s option" % decision["option"],
                period=payload.get("period", "agentic"))
        elif decision["action"] == "escalate":
            h.anomaly("agent_escalated", "high", "%s: %s" % (variant_id, decision["why"][:150]))

        results.append({"variant_id": variant_id, "decision": decision, "options": opts,
                        "tool_calls": [e for e in events if e["kind"] == "tool_call"],
                        "ledger": dict(row) if row else None})

    h.finish("agentic reorder on %d variants" % len(results))
    handle.last = results
    return results


handle.last = []
