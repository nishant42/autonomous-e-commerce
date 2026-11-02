"""A verdict on a live product, using only evidence the shop really produced.

The funnel-based verdict needs session data, which a shop two days old does not
have. This one asks a narrower question with what actually exists: real orders,
real stock-outs, real prices and margins, and real customer sentiment classified
by a language model from review text people really wrote.

It will say "not enough evidence" rather than guess, which is the point: a
verdict reached on invented numbers is worse than no verdict.
"""
from core import db
from engines import demand

MIN_ORDERS = 8
MIN_DAYS = 21


def _trend(conn, variant_ids, recent=30):
    marks = ",".join("?" for _ in variant_ids)
    rows = db.rows(conn, """
        SELECT substr(ts,1,10) AS day, SUM(units) AS units FROM sales_fact
        WHERE variant_id IN (%s) GROUP BY 1 ORDER BY 1""" % marks, variant_ids)
    if len(rows) < recent * 2:
        return None
    last = sum(r["units"] for r in rows[-recent:])
    prev = sum(r["units"] for r in rows[-recent * 2:-recent])
    if not prev:
        return None
    return round((last - prev) / prev, 3)


def sentiment_for(conn, product_name):
    rows = db.rows(conn, "SELECT sentiment, COUNT(*) n FROM order_review"
                         " WHERE product=? AND sentiment IS NOT NULL GROUP BY 1", (product_name,))
    total = sum(r["n"] for r in rows)
    if not total:
        return {"classified": 0, "negative_share": None}
    neg = sum(r["n"] for r in rows if (r["sentiment"] or "").upper().startswith("NEG"))
    return {"classified": total, "negative_share": round(neg / total, 3), "negative": neg}


def judge(conn, product_id, policy=None):
    policy = policy or {}
    product = db.one(conn, "SELECT * FROM product WHERE id=?", (product_id,))
    if not product:
        return {"error": "no such product"}
    variants = db.rows(conn, "SELECT id, sku, colour, price, unit_cost FROM variant"
                             " WHERE product_id=?", (product_id,))
    if not variants:
        return {"error": "no variants"}
    ids = [v["id"] for v in variants]

    units = db.scalar(conn, "SELECT SUM(units) FROM sales_fact WHERE variant_id IN (%s)"
                            % ",".join("?" for _ in ids), ids) or 0
    days = db.scalar(conn, "SELECT COUNT(DISTINCT substr(ts,1,10)) FROM sales_fact"
                           " WHERE variant_id IN (%s)" % ",".join("?" for _ in ids), ids) or 0

    # availability: the share of variant-days customers could not buy
    # Only variants that actually sell can lose a sale. A size nobody buys being
    # out of stock costs nothing, and counting it would condemn every product.
    selling = [v["id"] for v in variants if db.scalar(
        conn, "SELECT COALESCE(SUM(units),0) FROM sales_fact WHERE variant_id=?", (v["id"],)) > 0]
    unbuyable_share = 0.0
    if selling:
        avail = db.one(conn, """
            SELECT SUM(CASE WHEN share < 0.5 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS lost_share
            FROM (SELECT variant_id, substr(ts,1,10) AS day,
                         SUM(buyable)*1.0/COUNT(*) AS share
                  FROM inventory_snapshot WHERE variant_id IN (%s)
                  GROUP BY variant_id, day)""" % ",".join("?" for _ in selling), selling)
        unbuyable_share = round(avail["lost_share"] or 0, 3)

    recs = [demand.reconstruct(conn, v["id"], 90) for v in variants]
    real_demand = round(sum(r.get("reconstructed_demand_period", 0) for r in recs), 1)
    sold_per_day = round(sum(r.get("net_ros", 0) for r in recs), 3)
    lost_units = round(max(0.0, real_demand - units), 1)

    price = max((v["price"] or 0) for v in variants)
    cost = max((v["unit_cost"] or 0) for v in variants)
    margin = round(price - cost - (product["ship_cost"] or 0) - price * (product["payment_fee_pct"] or 0), 2)
    margin_pct = round(margin / price, 3) if price else 0

    sent = sentiment_for(conn, product["name"])
    trend = _trend(conn, ids)

    evidence = {
        "units_sold": units, "days_with_sales": days,
        "real_demand_estimate": real_demand, "demand_lost_to_stockouts": lost_units,
        "share_of_days_unbuyable": unbuyable_share, "sells_per_day": sold_per_day,
        "price": price, "margin_per_unit": margin, "margin_pct": margin_pct,
        "contribution_per_day": round(sold_per_day * margin, 2),
        "sentiment": sent, "trend_30d": trend,
    }

    # --- the decision, from this evidence only ---------------------------
    if units < MIN_ORDERS or days < MIN_DAYS:
        return {"product_id": product_id, "name": product["name"], "verdict": "NOT_ENOUGH_EVIDENCE",
                "confidence": 0.0, "evidence": evidence,
                "because": "%d units over %d days of selling, below the gate of %d units and %d days"
                           % (units, days, MIN_ORDERS, MIN_DAYS),
                "actions": ["keep it listed and look again once it has sold %d units" % MIN_ORDERS]}

    neg = sent["negative_share"]
    reasons, actions = [], []

    if neg is not None and neg >= 0.5:
        reasons.append("%d%% of the %d classified reviews are negative" % (neg * 100, sent["classified"]))
        verdict, confidence = "KILL", 0.75
        actions = ["stop buying it, clear what is left",
                   "pull the review text and take the top complaint to the supplier",
                   "a product customers complain about cannot be scaled profitably"]
    elif lost_units >= max(3.0, 0.15 * units):
        # supply is only the problem when demand was actually turned away
        reasons.append("unbuyable on %d%% of the days its selling variants were listed, which "
                       "turned away about %s units against the %s it did sell"
                       % (unbuyable_share * 100, lost_units, units))
        verdict, confidence = "FIX_SUPPLY", 0.8
        actions = ["reorder before judging it: it is losing sales to empty shelves, not to the market",
                   "raise its service level so it stops running out"]
    elif margin_pct < 0.25:
        reasons.append("margin is %d%% of the price" % (margin_pct * 100))
        verdict, confidence = "REPRICE", 0.65
        actions = ["raise the price or renegotiate the cost; at this margin volume does not help"]
    elif trend is not None and trend <= -0.4:
        reasons.append("sales fell %d%% against the previous thirty days" % (abs(trend) * 100))
        verdict, confidence = "WATCH", 0.6
        actions = ["check whether the fall is seasonal before acting"]
    else:
        if unbuyable_share >= 0.2:
            reasons.append("out of stock on %d%% of days, but the demand it lost is small"
                           % (unbuyable_share * 100))
        reasons.append("sells %.2f a day at %d%% margin with no supply or sentiment problem"
                       % (sold_per_day, margin_pct * 100))
        verdict, confidence = "SCALE", 0.75
        actions = ["give it more stock cover and more attention"]

    if neg is None:
        reasons.append("no reviews classified yet, so customer opinion is not in this verdict")

    return {"product_id": product_id, "name": product["name"], "verdict": verdict,
            "confidence": confidence, "evidence": evidence,
            "because": "; ".join(reasons), "actions": actions}


def judge_all(conn, prefix="med_"):
    rows = db.rows(conn, "SELECT id FROM product WHERE id LIKE ?", (prefix + "%",))
    return [judge(conn, r["id"]) for r in rows]
