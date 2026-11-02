"""Read tools exposed to agents.

Each one is a plain function: the harness records its arguments and its result
as evidence, so every number an agent cites can be traced back to the query
that produced it. Agents can only call the tools listed in their config.
"""
from core import db
from engines import demand, allocator, funnel


# ---- demand and inventory -------------------------------------------------

def sales_panel(conn, variant_id, days=90, intended_discount=0.0):
    return demand.reconstruct(conn, variant_id, days, intended_discount)


def availability_history(conn, variant_id, days=90):
    rows = db.rows(conn, """
        SELECT substr(ts,1,10) AS day, SUM(buyable) AS buyable_hours, MAX(on_hand) AS on_hand
        FROM inventory_snapshot WHERE variant_id=? GROUP BY 1 ORDER BY 1 DESC LIMIT ?""",
        (variant_id, days))
    unbuyable = [r["day"] for r in rows if (r["buyable_hours"] or 0) < 12]
    return {"days": len(rows), "unbuyable_days": len(unbuyable),
            "first_unbuyable": min(unbuyable) if unbuyable else None,
            "on_hand_now": rows[0]["on_hand"] if rows else 0,
            "freshness_ok": len(rows) > 0}


def lost_demand_signals(conn, variant_id, days=90):
    rows = db.rows(conn, "SELECT kind, SUM(value) AS value FROM demand_signal WHERE variant_id=? GROUP BY 1",
                   (variant_id,))
    return {r["kind"]: r["value"] for r in rows}


def returns_by_variant(conn, variant_id, days=90):
    sold = db.scalar(conn, "SELECT SUM(units) FROM sales_fact WHERE variant_id=?", (variant_id,))
    ref = db.scalar(conn, "SELECT SUM(units) FROM sales_fact WHERE variant_id=? AND refunded=1", (variant_id,))
    return {"units_sold": sold, "units_refunded": ref, "rate": round((ref / sold) if sold else 0, 3)}


def supplier_terms(conn, variant_id):
    return db.one(conn, "SELECT * FROM supplier_terms WHERE variant_id=? ORDER BY unit_cost LIMIT 1", (variant_id,))


def open_orders(conn, variant_id):
    qty = db.scalar(conn, """
        SELECT SUM(json_extract(payload,'$.qty')) FROM ledger
        WHERE intent='propose_reorder' AND status='executed'
          AND json_extract(payload,'$.variant_id')=?""", (variant_id,))
    return {"on_order": int(qty or 0)}


def cash_position(conn, policy):
    return {"cash_on_hand_eur": policy["cash_on_hand_eur"],
            "weekly_burn_eur": policy["weekly_burn_eur"],
            "runway_weeks": round(policy["cash_on_hand_eur"] / policy["weekly_burn_eur"], 1)}


def economics(conn, variant_id):
    """Contribution margin per unit, computed, never typed in by anyone."""
    row = db.one(conn, """
        SELECT v.price, v.unit_cost, p.ship_cost, p.payment_fee_pct, p.id AS product_id
        FROM variant v JOIN product p ON p.id=v.product_id WHERE v.id=?""", (variant_id,))
    ret = returns_by_variant(conn, variant_id)
    cm = row["price"] - row["unit_cost"] - row["ship_cost"] - row["price"] * row["payment_fee_pct"]
    cm_net = cm * (1 - ret["rate"]) - row["unit_cost"] * ret["rate"] * 0.3   # restock loss on returns
    return {"product_id": row["product_id"], "price": row["price"], "unit_cost": row["unit_cost"],
            "cm_per_unit": round(cm_net, 2), "cm_gross": round(cm, 2),
            "return_rate": ret["rate"],
            "holding_cost_per_unit_month": round(row["unit_cost"] * 0.02, 3),
            "expected_markdown_per_unit": round(row["price"] * 0.08, 2),
            "expected_sellthrough_days": 120, "lost_customer_value": 0.0}


def stock_cover(conn, product_id):
    """Cover in days per variant, and for the product's hero (most-stocked) variant."""
    out = {}
    for v in db.rows(conn, "SELECT id, colour FROM variant WHERE product_id=?", (product_id,)):
        rec = demand.reconstruct(conn, v["id"], 90)
        on_hand = db.scalar(conn, """
            SELECT on_hand FROM inventory_snapshot WHERE variant_id=? ORDER BY ts DESC LIMIT 1""", (v["id"],))
        ros = rec.get("net_ros") or 0.0
        out[v["id"]] = {"colour": v["colour"], "on_hand": on_hand,
                        "net_ros": ros, "cover_days": round(on_hand / ros, 1) if ros else 999}
    hero = max(out.values(), key=lambda r: r["cover_days"]) if out else {"cover_days": 999}
    worst = min(out.values(), key=lambda r: r["cover_days"]) if out else {"cover_days": 999}
    return {"variants": out, "hero_cover_days": hero["cover_days"], "worst_cover_days": worst["cover_days"]}


# ---- marketing ------------------------------------------------------------

def ad_metrics_panel(conn, product_id, window_days=7):
    return {"cells": allocator.cell_stats(conn, product_id, window_days)}


def orders_panel(conn, product_id, window_days=7):
    row = db.one(conn, """
        SELECT SUM(s.units) AS units, SUM(CASE WHEN s.is_new_customer=1 THEN s.units ELSE 0 END) AS new_units,
               SUM(s.units*s.unit_price*(1-s.discount_pct/100.0)) AS revenue
        FROM sales_fact s JOIN variant v ON v.id=s.variant_id
        WHERE v.product_id=? AND substr(s.ts,1,10) >= date((SELECT MAX(day) FROM ad_metrics), ?)""",
        (product_id, "-%d day" % window_days))
    return {k: (v or 0) for k, v in row.items()}


def margin_table(conn, product_id):
    """Product-level contribution margin, weighted by what actually sold.

    Not the first variant's margin: a target CPA built on one colour's return
    rate would be wrong for the product the ads are selling.
    """
    rows = db.rows(conn, """
        SELECT v.id, SUM(s.units) AS units FROM variant v
        LEFT JOIN sales_fact s ON s.variant_id=v.id
        WHERE v.product_id=? GROUP BY v.id""", (product_id,))
    parts = []
    total = 0.0
    for r in rows:
        units = r["units"] or 0
        if not units:
            continue
        econ = economics(conn, r["id"])
        parts.append((units, econ))
        total += units
    if not parts:
        if not rows:
            raise ValueError("no variants for product %s: is the database seeded?" % product_id)
        return economics(conn, rows[0]["id"])
    blended = sum(u * e["cm_per_unit"] for u, e in parts) / total
    ret = sum(u * e["return_rate"] for u, e in parts) / total
    base = dict(parts[0][1])
    base.update({"cm_per_unit": round(blended, 2), "return_rate": round(ret, 3),
                 "units_basis": int(total), "variants_in_basis": len(parts)})
    return base


def creative_history(conn, cell_id):
    return {"cell_id": cell_id, "ctr_first_week": round(allocator.ctr_baseline(conn, cell_id), 5)}


def holdout_readout(conn, product_id, window_days=7):
    return allocator.holdout_lift(conn, product_id, window_days)


def experiment_budget(conn, product_id):
    return db.one(conn, "SELECT * FROM experiment_budget WHERE product_id=?", (product_id,)) or \
        {"product_id": product_id, "allocated_eur": 0.0, "spent_eur": 0.0}


def signal_health(conn, product_id):
    day = db.scalar(conn, "SELECT MAX(day) FROM ad_metrics", (), None)
    return allocator.signal_health(conn, product_id, day)


# ---- verdict --------------------------------------------------------------

def funnel_rates(conn, product_id, window_days=14):
    return funnel.rates(conn, product_id, window_days)


def portfolio_memory(conn, product_id=None):
    """What previous verdicts taught us. Priors for the next launch."""
    rows = db.rows(conn, """
        SELECT json_extract(payload,'$.product_id') AS product_id,
               json_extract(payload,'$.verdict') AS verdict, reason, ts
        FROM ledger WHERE intent='publish_verdict' ORDER BY id DESC LIMIT 20""")
    return {"past_verdicts": rows}
