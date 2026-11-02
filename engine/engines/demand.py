"""Censored-demand reconstruction.

The towel case in one function: units sold is what we were *able* to sell.
Demand is estimated only over the hours a variant was actually buyable, then
corrected for demand displaced from out-of-stock siblings, de-promoted to the
price we intend to charge, and cross-checked against signals of unmet demand.

Deterministic on purpose: the model never touches these numbers.
"""
import math
from statistics import NormalDist

from core import db

ELASTICITY = 1.3          # log-log own-price elasticity fallback (category prior)
SUBSTITUTION_CAPTURE = 0.40   # share of a sibling's lost demand that lands on an in-stock variant
BIS_CONVERSION = 0.55     # back-in-stock sign-up -> would have bought
OOS_VIEW_CONVERSION = 0.03


def _daily_panel(conn, variant_id, days):
    """One row per day: units sold, hours buyable, average discount."""
    sales = {r["day"]: r for r in db.rows(conn, """
        SELECT substr(ts,1,10) AS day, SUM(units) AS units,
               AVG(discount_pct) AS discount, SUM(units*unit_price) AS revenue,
               SUM(CASE WHEN refunded=1 THEN units ELSE 0 END) AS refunded
        FROM sales_fact WHERE variant_id=? GROUP BY 1""", (variant_id,))}
    # Availability is the SHARE of readings on that day that were buyable,
    # scaled to a day. Counting readings as hours silently breaks whenever the
    # sampling rate changes - one reading a day would look like one hour of
    # availability, and every rate of sale would be twenty-four times too high.
    avail = {}
    for r in db.rows(conn, """
            SELECT substr(ts,1,10) AS day, SUM(buyable) * 1.0 / COUNT(*) AS share,
                   COUNT(*) AS readings
            FROM inventory_snapshot WHERE variant_id=? GROUP BY 1""", (variant_id,)):
        avail[r["day"]] = (r["share"] or 0.0) * 24.0
    panel = []
    for day in sorted(avail)[-days:]:
        s = sales.get(day, {})
        panel.append({
            "day": day,
            "units": (s.get("units") or 0),
            "refunded": (s.get("refunded") or 0),
            "discount": (s.get("discount") or 0.0),
            "hours": min(24.0, float(avail.get(day, 0) or 0)),
        })
    return panel


def substitutes_for(conn, variant_id):
    """Which variants compete with this one for the same purchase.

    A learned map takes precedence: a sentence-embedding model reads the product
    text and decides what a shopper would accept instead. Without one we fall
    back to the hand-set group, which is usually just "same product, other
    colour" and misses cross-product substitution entirely.
    """
    learned = [r["b"] for r in db.rows(
        conn, "SELECT b FROM substitute_pair WHERE a=? ORDER BY score DESC", (variant_id,))]
    if learned:
        return learned, "learned from product text"
    me = db.one(conn, "SELECT substitution_group FROM variant WHERE id=?", (variant_id,))
    if not me or not me["substitution_group"]:
        return [], "none"
    rows = db.rows(conn, "SELECT id FROM variant WHERE substitution_group=? AND id<>?",
                   (me["substitution_group"], variant_id))
    return [r["id"] for r in rows], "same product group"


def _sibling_oos_days(conn, variant_id):
    """Days on which a substitutable sibling was unbuyable for most of the day."""
    siblings, _source = substitutes_for(conn, variant_id)
    if not siblings:
        return set()
    marks = ",".join("?" for _ in siblings)
    rows = db.rows(conn, """
        SELECT substr(ts,1,10) AS day, SUM(buyable) * 1.0 / COUNT(*) AS share
        FROM inventory_snapshot WHERE variant_id IN (%s) GROUP BY 1""" % marks, siblings)
    return {r["day"] for r in rows if (r["share"] or 0) < 0.5}


def _unmet_signal(conn, variant_id):
    rows = db.rows(conn, "SELECT kind, SUM(value) AS v FROM demand_signal WHERE variant_id=? GROUP BY 1",
                   (variant_id,))
    by = {r["kind"]: r["v"] or 0 for r in rows}
    lower = (by.get("back_in_stock", 0) * BIS_CONVERSION
             + by.get("oos_product_view", 0) * OOS_VIEW_CONVERSION)
    return round(lower, 1), by


def reconstruct(conn, variant_id, days=90, intended_discount=0.0):
    """Return the full demand picture for one variant, with every intermediate."""
    panel = _daily_panel(conn, variant_id, days)
    if not panel:
        return {"error": "no panel data"}

    sib_oos = _sibling_oos_days(conn, variant_id)
    buyable = [d for d in panel if d["hours"] > 0]
    available_days = sum(d["hours"] for d in buyable) / 24.0
    units = sum(d["units"] for d in panel)
    refunded = sum(d["refunded"] for d in panel)

    # Winsorise spike days so one viral day cannot become the forecast.
    daily = sorted(d["units"] for d in buyable)
    cap = daily[int(len(daily) * 0.95)] if len(daily) >= 20 else (max(daily) if daily else 0)
    cap = max(cap, 1)
    w_units = sum(min(d["units"], cap) for d in buyable)

    ros = (w_units / available_days) if available_days else 0.0

    # Substitution: how much faster did this variant sell while a sibling was gone?
    clean = [d for d in buyable if d["day"] not in sib_oos]
    dirty = [d for d in buyable if d["day"] in sib_oos]
    ros_clean = (sum(min(d["units"], cap) for d in clean) / (sum(d["hours"] for d in clean) / 24.0)) if clean and sum(d["hours"] for d in clean) else ros
    ros_dirty = (sum(min(d["units"], cap) for d in dirty) / (sum(d["hours"] for d in dirty) / 24.0)) if dirty and sum(d["hours"] for d in dirty) else 0.0
    dirty_share = (sum(d["hours"] for d in dirty) / 24.0 / available_days) if available_days else 0.0
    if ros_dirty > ros_clean > 0:
        displaced = (ros_dirty - ros_clean) / ros_dirty * dirty_share
    else:
        displaced = 0.0
    displaced = min(0.35, max(0.0, displaced))

    baseline_ros = ros * (1 - displaced)

    # De-promote: units moved at a discount are not demand at full price.
    avg_disc = (sum(d["discount"] * d["units"] for d in buyable) / w_units) if w_units else 0.0
    if avg_disc > intended_discount:
        ratio = (1 - intended_discount / 100.0) / max(0.01, (1 - avg_disc / 100.0))
        price_factor = ratio ** (-ELASTICITY)        # higher price -> lower demand
    else:
        price_factor = 1.0
    adj_ros = baseline_ros * price_factor

    return_rate = (refunded / units) if units else 0.0
    net_ros = adj_ros * (1 - return_rate)

    # Dispersion from the clean days, floored at Poisson.
    mean = (sum(min(d["units"], cap) for d in clean) / len(clean)) if clean else baseline_ros
    var = (sum((min(d["units"], cap) - mean) ** 2 for d in clean) / max(1, len(clean) - 1)) if len(clean) > 2 else mean
    dispersion = max(1.0, (var / mean) if mean > 0 else 1.0)

    lower_bound, signals = _unmet_signal(conn, variant_id)
    observed_demand = adj_ros * len(panel)
    censored_gap = observed_demand - units

    sibs, sib_source = substitutes_for(conn, variant_id)
    return {
        "variant_id": variant_id,
        "substitutes": sibs, "substitutes_source": sib_source,
        "period_days": len(panel),
        "units_shipped": units,
        "spike_capped_units": w_units,
        "raw_ros_per_available_day": (units / available_days) if available_days else 0.0,
        "correction_factors": {"substitution": 1 - displaced,
                               "price": price_factor, "returns": 1 - return_rate},
        "net_demand_period": round(net_ros * len(panel), 1),
        "available_days": round(available_days, 1),
        "ros_per_available_day": round(ros, 3),
        "spike_cap_applied": cap,
        "sibling_oos_days": len(sib_oos),
        "substitution_share": round(displaced, 3),
        "avg_discount_pct": round(avg_disc, 1),
        "price_factor": round(price_factor, 3),
        "return_rate": round(return_rate, 3),
        "baseline_ros": round(baseline_ros, 3),
        "adjusted_ros": round(adj_ros, 3),
        "net_ros": round(net_ros, 3),
        "dispersion": round(dispersion, 2),
        "reconstructed_demand_period": round(observed_demand, 1),
        "censored_gap": round(censored_gap, 1),
        "unmet_signal_lower_bound": lower_bound,
        "unmet_signals": signals,
        "signal_conflict": bool(lower_bound and censored_gap and lower_bound > 1.5 * censored_gap),
    }


def over_horizon(rec, horizon_days, service_level):
    """Mean, sd and the service-level quantile of demand over a protection interval."""
    mu = rec["net_ros"] * horizon_days
    sd = math.sqrt(max(mu, 0.0001) * rec["dispersion"])
    z = NormalDist().inv_cdf(min(0.999, max(0.001, service_level)))
    return {"mu": round(mu, 2), "sd": round(sd, 2), "z": round(z, 3),
            "quantile": round(mu + z * sd, 2),
            "p50": round(mu, 1), "p90": round(mu + 1.2816 * sd, 1)}
