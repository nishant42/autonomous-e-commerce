"""Split a marketing budget across products.

The per-ad rules answer "is this ad working". This answers the question above
it: of everything we sell, which products deserve money this week, which must
not have any, and how much.

Four things decide it, and three of them are usually ignored:

  profit      what one order is actually worth after cost, shipping and fees
  supply      you cannot advertise what you cannot ship - spend is capped by
              the stock that exists, which is the mistake that turns a good
              campaign into a stockout and a refund queue
  evidence    an unproven product gets a fixed test budget, not a share of the
              pot, and never more than it needs to reach a verdict
  verdict     a product being killed gets nothing, whatever its numbers say
"""
from core import db
from engines import demand

MIN_COVER_DAYS = 14          # below this, more advertising sells stock we do not have
MAX_SHARE = 0.40             # no single product may own the budget
EXPLORE_SHARE = 0.10         # always kept back for the untested
MAX_MOVE = 0.35              # how far a product's budget may move in one cycle


def _ad_history(conn, product_id, days=14):
    row = db.one(conn, """
        SELECT SUM(spend) AS spend, SUM(orders) AS orders FROM ad_metrics
        WHERE product_id=? AND is_holdout=0
          AND day >= date((SELECT MAX(day) FROM ad_metrics), ?)""",
        (product_id, "-%d day" % days))
    spend = (row or {}).get("spend") or 0.0
    orders = (row or {}).get("orders") or 0
    return {"spend": round(spend, 2), "orders": orders,
            "cpa": round(spend / orders, 2) if orders else None,
            "daily_spend": round(spend / max(days, 1), 2)}


def _best_verdict(conn, product_id):
    """Funnel evidence where it exists, order evidence otherwise.

    A seeded product has sessions and a funnel; a product in the live shop has
    orders, stock and reviews. Each is judged on what it actually has.
    """
    from engines import funnel, live_verdict
    from agents import tools
    has_funnel = db.scalar(conn, "SELECT COUNT(*) FROM funnel_daily WHERE product_id=?",
                           (product_id,))
    if has_funnel:
        try:
            rates = funnel.rates(conn, product_id, 14)
            margin = tools.margin_table(conn, product_id)
            cfg = {"min_sessions": 1500, "min_spend_eur": 400}
            diag = funnel.diagnose(rates, round(margin["cm_per_unit"] * 1.2, 2),
                                   margin["cm_per_unit"], cfg)
            return {"verdict": diag["verdict"], "because": diag["diagnosis"],
                    "evidence": {"sentiment": {}}, "source": "funnel"}
        except Exception:                                      # noqa: BLE001
            pass
    out = live_verdict.judge(conn, product_id)
    out["source"] = "orders and reviews"
    return out


def _product_facts(conn, product_id):
    p = db.one(conn, "SELECT * FROM product WHERE id=?", (product_id,))
    variants = db.rows(conn, "SELECT id, price, unit_cost FROM variant WHERE product_id=?",
                       (product_id,))
    if not p or not variants:
        return None
    ids = [v["id"] for v in variants]
    recs = [demand.reconstruct(conn, v["id"], 90) for v in variants]
    sells_per_day = round(sum(r.get("net_ros", 0) for r in recs), 3)

    on_hand = 0
    for vid in ids:
        on_hand += db.scalar(conn, "SELECT on_hand FROM inventory_snapshot WHERE variant_id=?"
                                   " ORDER BY ts DESC LIMIT 1", (vid,), 0) or 0
    cover_days = round(on_hand / sells_per_day, 1) if sells_per_day > 0 else 999

    price = max(v["price"] or 0 for v in variants)
    cost = max(v["unit_cost"] or 0 for v in variants)
    margin = round(price - cost - (p["ship_cost"] or 0) - price * (p["payment_fee_pct"] or 0), 2)

    verdict = _best_verdict(conn, product_id)
    budget_row = db.one(conn, "SELECT * FROM experiment_budget WHERE product_id=?", (product_id,))
    return {"product_id": product_id, "name": p["name"], "margin": margin, "price": price,
            "sells_per_day": sells_per_day, "on_hand": on_hand, "cover_days": cover_days,
            "verdict": verdict.get("verdict"), "verdict_why": verdict.get("because"),
            "verdict_source": verdict.get("source"),
            "sentiment": (verdict.get("evidence") or {}).get("sentiment", {}),
            "ads": _ad_history(conn, product_id),
            "experiment_left": round((budget_row or {}).get("allocated_eur", 0)
                                     - (budget_row or {}).get("spent_eur", 0), 2)
                                if budget_row else None}


def split_channels(conn, product_id, amount, payback=1.2, days=7, window=14):
    """Split one product's budget across the channels that sell it.

    Scored on profit per euro from our own order data, not platform-reported
    revenue. A channel with no measured performance still gets a floor, because
    a channel you never fund is a channel you never learn about.
    """
    from engines import allocator
    from agents import tools
    if amount <= 0:
        return []
    cells = [c for c in allocator.cell_stats(conn, product_id, window) if not c["is_holdout"]]
    margin = tools.margin_table(conn, product_id)["cm_per_unit"]
    target = round(margin * payback, 2)

    if not cells:
        return [{"channel": "not started", "cell": None, "amount": round(amount, 2),
                 "cpa": None, "return_per_euro": None,
                 "why": "no advertising on this product yet: the whole budget is a first test, "
                        "and it is capped at what 25 orders would cost"}]

    by_channel = {}
    for c in cells:
        ch = by_channel.setdefault(c["platform"], {"spend": 0.0, "orders": 0, "cells": []})
        ch["spend"] += c["spend"]
        ch["orders"] += c["orders"]
        ch["cells"].append(c["cell_id"])

    scored = []
    for name, ch in by_channel.items():
        cpa = (ch["spend"] / ch["orders"]) if ch["orders"] else None
        rpe = (margin / cpa) if cpa else None
        scored.append({"channel": name, "cells": ch["cells"], "orders": ch["orders"],
                       "spend": round(ch["spend"], 2), "cpa": round(cpa, 2) if cpa else None,
                       "return_per_euro": round(rpe, 2) if rpe else None})

    # profit above break-even is what earns share; everything keeps a floor so
    # it stays measurable
    breakeven = 1.0 / payback
    weights = {}
    for row in scored:
        rpe = row["return_per_euro"]
        weights[row["channel"]] = max(0.0, (rpe - breakeven)) if rpe else 0.0
    total_w = sum(weights.values())
    floor = 0.08
    out = []
    for row in scored:
        if total_w > 0:
            share = floor + (1 - floor * len(scored)) * (weights[row["channel"]] / total_w)
        else:
            share = 1.0 / len(scored)
        share = max(share, floor)
        row["amount"] = round(amount * share, 2)
        rpe = row["return_per_euro"]
        if rpe is None:
            row["why"] = "no orders measured yet: funded at the floor so it can be judged"
        elif rpe >= breakeven:
            row["why"] = ("EUR %.2f back per euro at EUR %s a sale, above the EUR %.2f it must clear"
                          % (rpe, row["cpa"], breakeven))
        else:
            row["why"] = ("EUR %.2f back per euro, below the EUR %.2f break-even: held at the "
                          "floor rather than switched off, so we keep measuring it"
                          % (rpe, breakeven))
        out.append(row)
    scale = amount / max(sum(r["amount"] for r in out), 1e-9)
    for row in out:
        row["amount"] = round(row["amount"] * scale, 2)
    return sorted(out, key=lambda r: -r["amount"])


def allocate(conn, total_budget, product_ids=None, payback=1.2, days=7):
    """Return a per-product weekly budget with the reason for each line."""
    if product_ids is None:
        product_ids = [r["id"] for r in db.rows(conn, "SELECT id FROM product ORDER BY id")]
    facts = [f for f in (_product_facts(conn, pid) for pid in product_ids) if f]
    if not facts:
        return {"error": "no products"}

    known = [f["ads"]["cpa"] for f in facts if f["ads"]["cpa"]]
    fallback_cpa = round(sum(known) / len(known), 2) if known else None

    lines, fundable = [], []
    for f in facts:
        target_cpa = round(f["margin"] * payback, 2)
        cpa = f["ads"]["cpa"] or fallback_cpa
        cpa_source = "measured" if f["ads"]["cpa"] else ("portfolio average" if cpa else "unknown")

        # what supply allows: orders we could actually ship this week, times
        # what an order costs to buy
        servable = max(0.0, (f["on_hand"] - f["sells_per_day"] * days * 0.5))
        supply_cap = round(servable * (cpa or target_cpa), 2) if cpa or target_cpa else 0.0

        reason, allowed = None, True
        if f["verdict"] == "KILL":
            reason, allowed = "being killed: %s" % (f["verdict_why"] or "")[:70], False
        elif f["cover_days"] < MIN_COVER_DAYS:
            reason, allowed = ("only %.0f days of stock: advertising it now sells orders we "
                               "cannot ship" % f["cover_days"]), False
        elif f["margin"] <= 0:
            reason, allowed = "no margin to pay for an order", False
        elif f["experiment_left"] is not None and f["experiment_left"] <= 0 and \
                f["verdict"] in ("NOT_ENOUGH_EVIDENCE", "WATCH"):
            reason, allowed = "test budget spent without reaching a verdict", False

        line = {"product": f["name"], "product_id": f["product_id"], "verdict": f["verdict"],
                "verdict_source": f.get("verdict_source"),
                "margin": f["margin"], "price": f["price"], "target_cpa": target_cpa, "cpa": cpa,
                "cpa_source": cpa_source, "cover_days": f["cover_days"],
                "sells_per_day": f["sells_per_day"], "supply_cap": supply_cap,
                "current_daily": f["ads"]["daily_spend"], "allowed": allowed, "reason": reason,
                "sentiment": f["sentiment"]}
        lines.append(line)
        if allowed:
            fundable.append(line)

    pot = total_budget * (1 - EXPLORE_SHARE)
    # unproven products take a fixed test budget first: enough to reach a verdict,
    # never a share of the pot
    for line in fundable:
        breakeven = 1.0 / payback
        returns = (line["margin"] / line["cpa"]) if line["cpa"] else None
        never_advertised = line["cpa_source"] != "measured"
        if never_advertised and line["cpa"] and line["margin"] > 0:
            # It has never been advertised, so its cost per order is a guess from
            # other products. Condemning it on a guess is not evidence, it is
            # prejudice. Give it the smallest budget that could prove it either
            # way: 25 orders at the assumed rate.
            line["test_budget"] = round(min(25 * line["cpa"], pot * 0.15), 2)
            line["unproven"] = True
        elif line["verdict"] in ("NOT_ENOUGH_EVIDENCE", "CONTINUE_TEST") and line["cpa"] \
                and returns is not None and returns >= breakeven * 0.8:
            # close enough to break even to be worth proving; 25 orders is what
            # it takes to know
            line["test_budget"] = round(min(25 * line["cpa"], pot * 0.2), 2)
        else:
            line["test_budget"] = 0.0
    reserved = sum(line["test_budget"] for line in fundable)
    remaining = max(0.0, pot - reserved)

    # the rest by expected profit per euro, which is margin divided by what an
    # order costs to buy
    # only products with MEASURED performance compete for the main pot
    scored = [l for l in fundable
              if l["verdict"] not in ("NOT_ENOUGH_EVIDENCE",) and l["cpa"]
              and l["cpa_source"] == "measured"]
    weight_total = sum(max(0.0, (l["margin"] / l["cpa"]) - 1.0 / payback) for l in scored) or 1.0
    for line in fundable:
        share = 0.0
        if line in scored:
            w = max(0.0, (line["margin"] / line["cpa"]) - 1.0 / payback)
            share = w / weight_total
        want = line["test_budget"] + remaining * share
        # three ceilings, never a floor: a rule that forces money out of the door
        # is not a budget
        want = min(want, total_budget * MAX_SHARE)
        if line["supply_cap"]:
            want = min(want, line["supply_cap"])
        current_week = line["current_daily"] * days
        if current_week > 0:
            want = min(want, current_week * (1 + MAX_MOVE))   # ramp up slowly, cut freely
        line["want"] = round(want, 2)
        line["return_per_euro"] = round(line["margin"] / line["cpa"], 2) if line["cpa"] else None

    # the ceilings can only reduce, so the total may now be under the pot: share
    # what is left among the products that wanted more, and never exceed the pot
    total_want = sum(l["want"] for l in fundable)
    scale = (pot / total_want) if total_want > pot else 1.0
    for line in fundable:
        line["allocated"] = round(line["want"] * scale, 2)

    for line in lines:
        if not line["allowed"]:
            line["allocated"] = 0.0
            line["return_per_euro"] = None
        elif line.get("allocated", 0) <= 0.01 and not line["reason"]:
            breakeven = round(1.0 / payback, 2)
            if line["return_per_euro"] is not None and line["return_per_euro"] < breakeven:
                fix = ("raise the price to EUR %.2f, or get the cost per order under EUR %.2f"
                       % (line["price"] + (breakeven * line["cpa"] - line["margin"]),
                          line["margin"] / breakeven)) if line["cpa"] else "raise the price"
                line["reason"] = ("measured at EUR %.2f back per euro, below the EUR %.2f it must "
                                  "clear. Not a permanent no: %s, and it competes again"
                                  % (line["return_per_euro"], breakeven, fix))
            else:
                line["reason"] = "other products return more per euro this cycle"

    for line in lines:
        line["channels"] = split_channels(conn, line["product_id"], line.get("allocated", 0),
                                          payback, days)
    spent = sum(l["allocated"] for l in lines)
    return {"total_budget": round(total_budget, 2), "period_days": days,
            "allocated": round(spent, 2),
            "held_back": round(total_budget - spent, 2),
            "explore_reserve": round(total_budget * EXPLORE_SHARE, 2),
            "fallback_cpa": fallback_cpa,
            "lines": sorted(lines, key=lambda l: -l["allocated"])}
