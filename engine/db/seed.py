"""Seed a reproducible 90-day history for four products.

The towel product is the real case from the brief: twenty white and twenty
black sold, but black was unbuyable after day 22. Everything the agents later
conclude is derived from these rows, not hard-coded anywhere.
"""
import json
import math
import random
from datetime import date, timedelta

from core import db

random.seed(42)
TODAY = date(2026, 10, 30)
DAYS = 90


def _days(n=DAYS):
    return [(TODAY - timedelta(days=n - 1 - i)) for i in range(n)]


def _snap(conn, variant_id, day, on_hand, buyable):
    conn.executemany(
        "INSERT OR REPLACE INTO inventory_snapshot (variant_id, ts, on_hand, buyable) VALUES (?,?,?,?)",
        [(variant_id, "%sT%02d:00:00" % (day.isoformat(), h), on_hand, 1 if buyable else 0) for h in range(24)],
    )


def _sale(conn, variant_id, day, units, price, discount, refunded=0, new=1):
    conn.execute(
        "INSERT INTO sales_fact (variant_id, ts, units, unit_price, discount_pct, is_new_customer, refunded, channel)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (variant_id, "%sT12:00:00" % day.isoformat(), units, price, discount, new, refunded, "online"),
    )


def seed_towels(conn):
    conn.execute("INSERT OR REPLACE INTO product VALUES ('p_towel','Halden Towel','towels.halden.test','2026-08-01',39.0,7.0,4.0,0.02)")
    conn.execute("INSERT OR REPLACE INTO variant VALUES ('v_white','p_towel','TOW-WHT','white',7.0,39.0,'B','towel_colour')")
    conn.execute("INSERT OR REPLACE INTO variant VALUES ('v_black','p_towel','TOW-BLK','black',7.0,39.0,'B','towel_colour')")

    days = _days()
    # --- white: in stock every day, slow, and propped up by discounting.
    # It sells FASTER in the window when black is unbuyable: that is the
    # substitution the naive report credits to white as its own success.
    white_days = ([3, 9, 14, 19]                                   # 4 units while black was in stock
                  + [24, 27, 31, 34, 38, 42, 46, 51, 55, 60, 64, 69, 73, 78, 82, 86])  # 16 after
    discounted = set(white_days[4:])                               # the post-stockout units moved on promo
    refund_days = {9, 38, 60, 82}                                  # 4 of 20 units came back
    on_hand = 44
    for i, day in enumerate(days):
        _snap(conn, "v_white", day, on_hand, on_hand > 0)
        if i in white_days:
            _sale(conn, "v_white", day, 1, 39.0,
                  30.0 if i in discounted else 0.0,
                  1 if i in refund_days else 0)
            on_hand -= 1
    # --- black: four times faster, and unbuyable from day 23 of 90 ---
    on_hand = 20
    skip = {5, 14}
    for i, day in enumerate(days):
        buyable = on_hand > 0
        _snap(conn, "v_black", day, max(on_hand, 0), buyable)
        if buyable and i < 22 and i not in skip:
            _sale(conn, "v_black", day, 1, 39.0, 0.0, 1 if i == 7 else 0)
            on_hand -= 1
    # --- grey bath sheet: the product's volume seller, always in stock.
    # Without it the store's own order count would not reconcile with what the
    # ad platforms report, and signal health would fire a false alarm.
    conn.execute("INSERT OR REPLACE INTO variant VALUES ('v_grey','p_towel','TOW-GRY','grey',9.0,45.0,'A',NULL)")
    conn.execute("INSERT OR REPLACE INTO supplier_terms VALUES ('sup_linen','v_grey',9.0,48,24,45.0,7.0)")
    on_hand = 1200
    for i, day in enumerate(days):
        if on_hand < 400:                      # a reorder arrived: grey is managed well
            on_hand += 1200
        _snap(conn, "v_grey", day, on_hand, True)
        units = 18 + (i % 5)
        _sale(conn, "v_grey", day, units, 45.0, 0.0, 1 if i % 30 == 0 else 0)
        on_hand -= units

    # --- what customers did while black was gone ---
    conn.executemany("INSERT OR REPLACE INTO demand_signal VALUES (?,?,?,?)", [
        ("v_black", TODAY.isoformat(), "back_in_stock", 41),
        ("v_black", TODAY.isoformat(), "oos_product_view", 390),
        ("v_black", TODAY.isoformat(), "site_search", 64),
    ])
    conn.executemany("INSERT OR REPLACE INTO supplier_terms VALUES (?,?,?,?,?,?,?)", [
        ("sup_linen", "v_white", 7.0, 24, 12, 45.0, 7.0),
        ("sup_linen", "v_black", 7.0, 24, 12, 45.0, 7.0),
    ])


OTHERS = [
    # id, name, price, cogs, funnel signature
    ("p_lamp", "Halden Lamp", 89.0, 22.0, "winner"),
    ("p_mug", "Halden Mug Set", 34.0, 8.0, "site_defect"),
    ("p_candle", "Halden Candle", 24.0, 6.0, "bad_product"),
]


def seed_others(conn):
    for pid, name, price, cogs, sig in OTHERS:
        conn.execute("INSERT OR REPLACE INTO product VALUES (?,?,?,?,?,?,?,?)",
                     (pid, name, pid[2:] + ".halden.test", "2026-09-15", price, cogs, 4.0, 0.02))
        vid = "v_" + pid[2:]
        conn.execute("INSERT OR REPLACE INTO variant VALUES (?,?,?,?,?,?,?,?)",
                     (vid, pid, pid[2:].upper() + "-STD", "default", cogs, price, "B", None))
        conn.execute("INSERT OR REPLACE INTO supplier_terms VALUES (?,?,?,?,?,?,?)",
                     ("sup_generic", vid, cogs, 50, 10, 30.0, 5.0))
        for i, day in enumerate(_days(30)):
            _snap(conn, vid, day, 120 - i, True)
            if sig == "winner" and i % 2 == 0:
                _sale(conn, vid, day, 2, price, 0.0)
            elif sig == "site_defect" and i % 4 == 0:
                _sale(conn, vid, day, 1, price, 0.0)
            elif sig == "bad_product" and i % 6 == 0:
                _sale(conn, vid, day, 1, price, 0.0, refunded=1 if i % 12 == 0 else 0)


# cell_id, platform, spend/day, orders/day, freq, ctr, holdout
# The order figures below are the *intent* of each cell; the actual daily orders
# are generated from the feature process in seed_marketing so that the panel the
# models learn from is internally consistent.
TOWEL_CELLS = [
    ("meta_prospect_morning", "meta", 140.0, 6.3, 1.8, 0.0190, 0),
    ("meta_prospect_fabric", "meta", 88.6, 1.5, 2.1, 0.0120, 0),
    ("meta_retarget", "meta", 44.3, 3.7, 3.2, 0.0260, 0),
    ("google_brand", "google", 20.0, 2.7, 1.1, 0.0810, 0),
    ("google_pmax", "google", 124.3, 3.0, 1.4, 0.0090, 0),
    ("tiktok_test", "tiktok", 40.0, 0.7, 1.3, 0.0070, 0),
    ("geo_holdout", "none", 0.0, 1.6, 0.0, 0.0, 1),
]

# sessions/day, pdp, atc, checkout, purchase, refund, CPA the ads actually paid.
# The funnel table and the ad table are generated from the same numbers, so the
# agents are never reconciling two inconsistent fictions.
FUNNEL_SIG = {
    "p_towel": (700, 0.62, 0.095, 0.68, 0.72, 0.04, 22.0),   # winner, but a variant is out of stock
    "p_lamp": (1150, 0.58, 0.110, 0.70, 0.74, 0.03, 45.0),   # winner on every rate
    "p_mug": (1080, 0.60, 0.105, 0.34, 0.80, 0.03, 20.0),    # site defect: cart -> checkout collapses
    "p_candle": (1200, 0.64, 0.028, 0.66, 0.70, 0.13, 30.0), # product defect: few add, many return
}


# The data-generating process behind the demo panel.
#
# Orders are produced from features with known coefficients plus noise, so the
# pipeline has something real to recover and we can check afterwards whether it
# found the true drivers. Three of these features are deliberately irrelevant
# (weekday noise, a tablet share, a vanity "impression quality" index) so that
# feature selection has something to throw away.
TRUE_COEF = {
    "log_spend": 0.62,          # diminishing returns, modelled in logs
    "ctr": 18.0,                # creative quality
    "search_index_category": 0.011,   # external demand: people searching for the thing
    "share_ios": 0.9,           # higher-intent, higher-AOV device mix
    "discount_pct": 0.012,
    "stock_cover_days": 0.0016,
    "creative_age_days": -0.018,      # fatigue
    "frequency": -0.11,
    "competitor_price_index": -0.7,
    "is_weekend": 0.08,
}
MARKETING_DAYS = 120


def _features_for(cell, plat, spend, freq, ctr, hold, i, day, rnd):
    """Thirty features per cell-day: spend, creative, device, intent, price,
    calendar, inventory and the lags. This is the panel the models see."""
    dow = day.weekday()
    search = 100 + 28 * math.sin(i / 11.0) + rnd.gauss(0, 7) + (18 if dow >= 5 else 0)
    share_ios = min(0.9, max(0.2, 0.52 + (0.12 if plat == "meta" else -0.05) + rnd.gauss(0, 0.04)))
    share_android = min(0.7, max(0.05, 0.9 - share_ios - 0.12 + rnd.gauss(0, 0.03)))
    share_tablet = max(0.0, min(0.2, 0.05 + rnd.gauss(0, 0.02)))
    jitter = 0.85 + rnd.random() * 0.3
    sp = round(spend * jitter, 2)
    ctr_today = max(0.001, ctr * (0.9 + rnd.random() * 0.25))
    imps = int(round(sp * 85)) if sp else 2000
    clicks = int(round(imps * ctr_today))
    return {
        # spend and delivery
        "spend": sp, "log_spend": math.log1p(sp), "impressions": imps, "clicks": clicks,
        "ctr": round(ctr_today, 5), "cpm": round((sp / imps * 1000) if imps else 0, 3),
        "cpc": round((sp / clicks) if clicks else 0, 3),
        "frequency": round(freq + i * 0.012 + rnd.gauss(0, 0.05), 3),
        # creative
        "creative_age_days": i % 45, "is_video": 1 if "morning" in cell or "tiktok" in cell else 0,
        "creative_concept": 1 if "fabric" in cell else (2 if "morning" in cell else 0),
        # device mix
        "share_ios": round(share_ios, 4), "share_android": round(share_android, 4),
        "share_desktop": round(max(0.0, 1 - share_ios - share_android - share_tablet), 4),
        "share_tablet": round(share_tablet, 4),
        # intent and external demand
        "search_index_category": round(search, 2),
        "search_index_brand": round(14 + 6 * math.sin(i / 19.0) + rnd.gauss(0, 2), 2),
        "site_search_count": int(max(0, 22 + 9 * math.sin(i / 7.0) + rnd.gauss(0, 4))),
        "aeo_citation_count": int(max(0, 3 + rnd.gauss(0, 1.4))),
        # price and offer
        "price": 39.0, "discount_pct": 30.0 if (i % 17) < 3 else 0.0,
        "competitor_price_index": round(1.0 + rnd.gauss(0, 0.05), 4),
        "free_shipping": 1 if (i % 23) < 4 else 0,
        # calendar
        "dow": dow, "is_weekend": 1 if dow >= 5 else 0,
        "is_payday_window": 1 if day.day <= 3 or day.day >= 27 else 0,
        "week_of_year": day.isocalendar()[1],
        # inventory and channel
        # mean-reverting: stock is drawn down and replenished, it does not slide
        # monotonically to zero, and a monotonic feature is a calendar in disguise
        "stock_cover_days": round(max(5.0, 60 + 25 * math.sin(i / 9.0) + rnd.gauss(0, 8)), 1),
        "is_holdout": hold, "platform_meta": 1 if plat == "meta" else 0,
        "platform_google": 1 if plat == "google" else 0,
        # a deliberately useless vanity metric, to be discarded by selection
        "impression_quality_index": round(rnd.uniform(60, 95), 2),
    }


def _orders_from(f, rnd):
    """Known process: a log-linear response with noise. Orders are a count.

    The intercept is set so that total paid orders reconcile with the store's
    own sales: if the ad platforms claim far more or far fewer orders than the
    shop recorded, the signal-health check fires - correctly - and nothing can
    be scaled until it is explained.
    """
    z = -2.05
    for key, coef in TRUE_COEF.items():
        z += coef * float(f.get(key, 0.0))
    lam = math.exp(min(6.0, z))
    # overdispersed counts
    return max(0, int(round(lam * (0.8 + rnd.random() * 0.45))))


def seed_marketing(conn):
    """Two passes, on purpose.

    Pass one writes the feature panel. Pass two reads those stored features back
    out and derives the orders from them. Generating the outcome from anything
    other than the rows a model will later see is how a synthetic panel ends up
    containing a relationship nobody can recover - and the model then looks
    broken when the data was.
    """
    rnd = random.Random(2026)
    days = _days(MARKETING_DAYS)

    # pass 1: the features
    for i, day in enumerate(days):
        for cell, plat, spend, orders, freq, ctr, hold in TOWEL_CELLS:
            f = _features_for(cell, plat, spend, freq, ctr, hold, i, day, rnd)
            conn.execute("INSERT OR REPLACE INTO ad_feature VALUES (?,?,?,?)",
                         (cell, day.isoformat(), "p_towel", db.dumps(f)))

    # pass 2: the outcome, read back from exactly those rows
    rnd2 = random.Random(7)
    prev = {}
    for i, day in enumerate(days):
        for cell, plat, spend, orders, freq, ctr, hold in TOWEL_CELLS:
            row = db.one(conn, "SELECT features FROM ad_feature WHERE cell_id=? AND day=?",
                         (cell, day.isoformat()))
            f = json.loads(row["features"])
            p = prev.get(cell, {})
            f["orders_lag1"] = p.get("orders", 0)
            f["orders_lag7"] = p.get("orders_lag7_src", 0)
            f["spend_lag1"] = p.get("spend", 0.0)
            f["cpa_roll7"] = p.get("cpa_roll7", 0.0)
            if hold:
                f["spend"], f["log_spend"], f["clicks"], f["impressions"] = 0.0, 0.0, 0, 0
                o = max(0, int(round(1.6 * (0.7 + rnd2.random() * 0.6))))
            else:
                o = _orders_from(f, rnd2)
            cpa = (f["spend"] / o) if o else 0.0
            prev[cell] = {"orders": o, "spend": f["spend"],
                          "cpa_roll7": round((p.get("cpa_roll7", cpa) * 6 + cpa) / 7.0, 3),
                          "orders_lag7_src": p.get("orders", 0)}
            conn.execute("UPDATE ad_feature SET features=? WHERE cell_id=? AND day=?",
                         (db.dumps(f), cell, day.isoformat()))
            conn.execute("INSERT OR REPLACE INTO ad_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (cell, day.isoformat(), plat, "p_towel", f["spend"], f["impressions"],
                          f["clicks"], o, max(0, o - 1), round(o * 41.0, 2), f["frequency"], hold))

    # the other products keep their simple, consistent panel
    for i, day in enumerate(_days(14)):
        for pid, (sess, pdp, atc, chk, pur, ref, cpa) in FUNNEL_SIG.items():
            if pid == "p_towel":
                continue
            jitter = 0.9 + random.random() * 0.2
            orders = max(0, int(round(sess * pdp * atc * chk * pur * jitter)))
            sp = round(orders * cpa, 2)
            imps = int(sp * 80)
            conn.execute("INSERT OR REPLACE INTO ad_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         ("%s_meta_main" % pid, day.isoformat(), "meta", pid, sp, imps,
                          int(imps * 0.013), orders, max(0, orders - 1), orders * 40.0, 1.6, 0))


def seed_funnel(conn):
    for day in _days(14):
        for pid, (sess, pdp, atc, chk, pur, ref, _cpa) in FUNNEL_SIG.items():
            j = 0.9 + random.random() * 0.2
            s = int(sess * j)
            p = int(s * pdp)
            a = int(p * atc)
            c = int(a * chk)
            o = int(round(c * pur))
            r = int(round(o * ref))
            conn.execute("INSERT OR REPLACE INTO funnel_daily VALUES (?,?,?,?,?,?,?,?)",
                         (pid, day.isoformat(), s, p, a, c, o, r))


def seed_fresh(conn):
    """A perishable line, for proving the same agent serves a different vertical.

    Sells fast, spoils in a week, and is bought almost daily. Nothing about the
    agent changes: only config/reorder_fresh.json.
    """
    conn.execute("INSERT OR REPLACE INTO product VALUES "
                 "('p_yoghurt','Daily Yoghurt 500g','grocery.halden.test','2026-06-01',1.40,0.75,0.05,0.02)")
    conn.execute("INSERT OR REPLACE INTO variant VALUES "
                 "('v_yoghurt','p_yoghurt','YOG-500','natural',0.75,1.40,'A',NULL)")
    conn.execute("INSERT OR REPLACE INTO supplier_terms VALUES "
                 "('sup_dairy','v_yoghurt',0.75,120,6,2.0,0.5)")
    on_hand = 160
    for i, day in enumerate(_days()):
        if on_hand < 70:                       # a delivery arrives most mornings
            on_hand += 120
        _snap(conn, "v_yoghurt", day, on_hand, True)
        units = 38 + (i % 7) * 2               # weekday rhythm
        _sale(conn, "v_yoghurt", day, units, 1.40, 0.0, 1 if i % 45 == 0 else 0)
        on_hand -= units


def seed_budgets(conn):
    for pid, spent in [("p_towel", 980.0), ("p_lamp", 760.0), ("p_mug", 820.0), ("p_candle", 1480.0)]:
        conn.execute("INSERT OR REPLACE INTO experiment_budget VALUES (?,?,?)", (pid, 1500.0, spent))


def run(conn):
    seed_towels(conn)
    seed_others(conn)
    seed_fresh(conn)
    seed_marketing(conn)
    seed_funnel(conn)
    seed_budgets(conn)
    counts = {t: db.scalar(conn, "SELECT COUNT(*) FROM " + t) for t in
              ["product", "variant", "inventory_snapshot", "sales_fact", "ad_metrics", "funnel_daily"]}
    return counts
