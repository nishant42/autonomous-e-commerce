"""The operator's agent: answers questions about the business, read-only.

This is a real tool-using loop. The model decides which reads it needs, the
harness executes them against the database and records each result as
evidence, and the answer is then checked: any figure that does not trace back
to a tool result in this conversation is reported as uncited.

It has no write tools at all, so there is nothing it can do to the business.
"""
from core import db, harness, model
from agents import tools

AGENT = "analyst"

TOOL_SPEC = [
    {"name": "sales_panel",
     "description": "Reconstructed demand for one variant: rate of sale per available day, "
                    "substitution share, discount effect, return rate, demand hidden by stockouts.",
     "args": {"variant_id": "e.g. v_black, v_white, v_grey", "days": "optional, default 90"}},
    {"name": "availability_history",
     "description": "How many days a variant was actually buyable, and when it first went unbuyable.",
     "args": {"variant_id": "variant id"}},
    {"name": "lost_demand_signals",
     "description": "Back-in-stock sign-ups, product views while out of stock, site searches.",
     "args": {"variant_id": "variant id"}},
    {"name": "returns_by_variant",
     "description": "Units sold, units refunded and the return rate for a variant.",
     "args": {"variant_id": "variant id"}},
    {"name": "economics",
     "description": "Price, unit cost and contribution margin per unit for a variant.",
     "args": {"variant_id": "variant id"}},
    {"name": "stock_cover",
     "description": "Days of cover per variant for a product, plus hero and worst variant.",
     "args": {"product_id": "e.g. p_towel, p_lamp, p_mug, p_candle"}},
    {"name": "ad_metrics_panel",
     "description": "Per-cell spend, orders, clicks and frequency for a product over a window.",
     "args": {"product_id": "product id", "window_days": "optional, default 7"}},
    {"name": "funnel_rates",
     "description": "Stage rates for a product: sessions to product page, add to cart, checkout, "
                    "purchase, refunds, ad CTR and CPA.",
     "args": {"product_id": "product id"}},
    {"name": "holdout_readout",
     "description": "Paid versus geo-holdout orders, and the resulting incrementality factor.",
     "args": {"product_id": "product id"}},
    {"name": "margin_table",
     "description": "Product-level contribution margin, weighted by units sold.",
     "args": {"product_id": "product id"}},
    {"name": "experiment_budget",
     "description": "How much of a product's experiment budget is spent.",
     "args": {"product_id": "product id"}},
    {"name": "catalogue",
     "description": "Every product and variant with its id, so other tools can be called correctly.",
     "args": {}},
    {"name": "decisions",
     "description": "The ledger: what the agents proposed, the tier, the status and the reason.",
     "args": {"limit": "optional, default 25"}},
]

SYSTEM_CONTEXT = """Context you can rely on:
- Four products are live: p_towel (white/black/grey towels), p_lamp, p_mug, p_candle.
- Three agents run: reorder, marketing_allocator, product_verdict. Their decisions are in the ledger.
- Units shipped is not demand. A variant that was out of stock records no sales, and demand must be
  reconstructed from the hours it was actually buyable. sales_panel does that for you.
- Start with the catalogue or decisions tool if you are unsure which ids exist.
"""


def catalogue(conn):
    return {"products": db.rows(conn, "SELECT id, name, price, cogs FROM product"),
            "variants": db.rows(conn, "SELECT id, product_id, sku, colour FROM variant")}


def decisions(conn, limit=25):
    return db.rows(conn, """
        SELECT id, agent, intent, payload, value_eur, tier, status, reason, rationale
        FROM ledger ORDER BY id DESC LIMIT ?""", (int(limit),))


EXTRA = {"catalogue": catalogue, "decisions": decisions}


def ask(conn, question, max_steps=6, on_event=None):
    """Answer an operator's question with tool access. Returns the full trace."""
    cfg = {"reads": [t["name"] for t in TOOL_SPEC],
           "model": {"plan": None, "max_steps": max_steps * 3, "token_budget_month": 0}}
    h = harness.Harness(conn, AGENT, cfg, trigger="operator question")
    for spec in TOOL_SPEC:
        name = spec["name"]
        h.register(name, EXTRA.get(name) or getattr(tools, name))

    if not model.available():
        h.finish("no model provider")
        return {"answer": "No model provider is available, so there is nothing to narrate. "
                          "The engines still decide: see the ledger for what the agents did.",
                "trace": [], "totals": {}, "mode": "rules_only",
                "uncited": [], "provider": model.status()}

    def executor(name, args):
        clean = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        result, eid = h.read(name, **clean)
        return result, eid

    out = model.agent_loop(
        task=SYSTEM_CONTEXT + "\nThe operator asks:\n" + question,
        tools_spec=TOOL_SPEC, executor=executor, max_steps=max_steps, on_event=on_event)

    uncited = h.uncited_numbers(out["answer"])
    h.conn.execute("UPDATE agent_run SET tokens=?, cost_eur=? WHERE id=?",
                   (out["totals"].get("tokens_in", 0) + out["totals"].get("tokens_out", 0),
                    round(out["totals"].get("cost_eur", 0.0), 5), h.run_id))
    h.finish("answered with %d tool calls" % len(out["trace"]))
    out.update({"mode": "model", "uncited": uncited, "provider": model.status(),
                "run_id": h.run_id})
    return out
