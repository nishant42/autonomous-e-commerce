"""A demand model built only from things that really happened.

The marketing model on the seeded panel is a complete piece of work, but its ad
spend is invented, because there is no ad account yet. This one is smaller and
entirely real: orders customers really placed, stock that was really on the
shelf, devices they really used, and public interest from Wikimedia's open
pageviews API.

It answers the question an architect will actually ask: does any of this work
on real data, or only on data you made up?
"""
from core import db
from adapters import interest

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.preprocessing import StandardScaler
    HAVE = True
except ImportError:                                            # pragma: no cover
    HAVE = False


def build_panel(conn, product_id):
    """One row per day for one product. Every column is observed, none invented."""
    product = db.one(conn, "SELECT * FROM product WHERE id=?", (product_id,))
    if not product:
        return None
    ids = [r["id"] for r in db.rows(conn, "SELECT id FROM variant WHERE product_id=?", (product_id,))]
    if not ids:
        return None
    marks = ",".join("?" for _ in ids)

    orders = {r["day"]: r["units"] for r in db.rows(conn, """
        SELECT substr(ts,1,10) AS day, SUM(units) AS units FROM sales_fact
        WHERE variant_id IN (%s) GROUP BY 1""" % marks, ids)}
    avail = {r["day"]: r["share"] for r in db.rows(conn, """
        SELECT day, AVG(share) AS share FROM (
            SELECT variant_id, substr(ts,1,10) AS day, SUM(buyable)*1.0/COUNT(*) AS share
            FROM inventory_snapshot WHERE variant_id IN (%s) GROUP BY variant_id, day)
        GROUP BY 1""" % marks, ids)}
    devices = {}
    for r in db.rows(conn, "SELECT day, device, share FROM device_mix"):
        devices.setdefault(r["day"], {})[r["device"]] = r["share"]
    views = interest.series_for(conn, product["name"])

    rows = []
    for day in sorted(avail):
        if day not in views:
            continue                      # no public signal for that day: skip, do not invent
        dmix = devices.get(day, {})
        dt = pd.Timestamp(day)
        rows.append({
            "day": dt, "orders": float(orders.get(day, 0)),
            "public_interest": float(views[day]),
            "stock_available": float(avail.get(day, 0)),
            "share_ios": float(dmix.get("ios", 0)), "share_android": float(dmix.get("android", 0)),
            "share_desktop": float(dmix.get("desktop", 0)),
            "dow": dt.dayofweek, "is_weekend": 1 if dt.dayofweek >= 5 else 0,
            "price": float(product["price"] or 0),
        })
    if len(rows) < 30:
        return None
    df = pd.DataFrame(rows).sort_values("day").reset_index(drop=True)
    # lags of the target are legitimate here: strictly yesterday, never today
    df["orders_yesterday"] = df["orders"].shift(1)
    df["orders_last_week"] = df["orders"].shift(7)
    df["interest_yesterday"] = df["public_interest"].shift(1)
    return df.dropna().reset_index(drop=True)


FEATURES = ["public_interest", "interest_yesterday", "stock_available", "share_ios",
            "share_android", "share_desktop", "dow", "is_weekend", "price",
            "orders_yesterday", "orders_last_week"]


def train(conn, product_id, test_days=14):
    if not HAVE:
        return {"error": "scikit-learn missing"}
    df = build_panel(conn, product_id)
    if df is None:
        return {"error": "not enough overlapping real history for this product"}
    feats = [f for f in FEATURES if df[f].std() > 1e-9]
    cut = df["day"].iloc[-test_days]
    train_df, test_df = df[df["day"] < cut], df[df["day"] >= cut]
    if len(train_df) < 20 or len(test_df) < 5:
        return {"error": "too few days to split honestly"}

    Xtr, ytr = train_df[feats].values, train_df["orders"].values
    Xte, yte = test_df[feats].values, test_df["orders"].values
    sc = StandardScaler().fit(Xtr)
    board = []
    baseline = np.full_like(yte, ytr.mean(), dtype=float)
    board.append({"family": "baseline_average", "r2": round(float(r2_score(yte, baseline)), 3),
                  "mae": round(float(mean_absolute_error(yte, baseline)), 3)})
    board.append({"family": "baseline_yesterday",
                  "r2": round(float(r2_score(yte, test_df["orders_yesterday"].values)), 3),
                  "mae": round(float(mean_absolute_error(yte, test_df["orders_yesterday"].values)), 3)})
    fitted = {}
    for name, model, scaled in (("ridge", Ridge(alpha=1.0), True),
                                ("random_forest", RandomForestRegressor(
                                    n_estimators=300, min_samples_leaf=4, random_state=0), False),
                                ("gradient_boosting", GradientBoostingRegressor(
                                    n_estimators=200, max_depth=2, learning_rate=0.05,
                                    random_state=0), False)):
        model.fit(sc.transform(Xtr) if scaled else Xtr, ytr)
        pred = model.predict(sc.transform(Xte) if scaled else Xte)
        board.append({"family": name, "r2": round(float(r2_score(yte, pred)), 3),
                      "mae": round(float(mean_absolute_error(yte, pred)), 3)})
        fitted[name] = (model, scaled)
    board.sort(key=lambda e: -e["r2"])

    importance = []
    best = board[0]["family"]
    if best in fitted and hasattr(fitted[best][0], "feature_importances_"):
        pairs = sorted(zip(feats, fitted[best][0].feature_importances_), key=lambda t: -t[1])
        importance = [{"feature": f, "weight": round(float(w), 3)} for f, w in pairs[:6]]
    elif best == "ridge":
        coefs = fitted["ridge"][0].coef_
        pairs = sorted(zip(feats, coefs), key=lambda t: -abs(t[1]))
        importance = [{"feature": f, "weight": round(float(w), 3)} for f, w in pairs[:6]]

    # How much of this is even predictable? For counts, the day-to-day variance
    # has an irreducible Poisson part equal to the mean. Whatever is left is the
    # only thing any model could ever explain. Saying so is more useful than
    # tuning features against noise.
    y = df["orders"].values
    mean_daily = float(np.mean(y))
    var_daily = float(np.var(y))
    weekly = df.set_index("day")["orders"].resample("7D").sum()
    signal_var = float(np.var(weekly.values / 7.0)) if len(weekly) > 2 else 0.0
    ceiling = max(0.0, min(1.0, signal_var / var_daily)) if var_daily > 0 else 0.0
    needed = round(max(1.0, 9.0 * mean_daily), 1)         # ~3x the rate for ~3x the signal ratio
    noise = {"orders_per_day": round(mean_daily, 2),
             "variance": round(var_daily, 2),
             "poisson_floor": round(mean_daily, 2),
             "best_r2_any_model_could_reach": round(ceiling, 3),
             "orders_per_day_needed_for_a_useful_model": needed}

    return {"product_id": product_id, "rows": len(df), "features": feats, "noise": noise,
            "train_days": len(train_df), "test_days": len(test_df),
            "leaderboard": board, "importance": importance,
            "beats_baseline": board[0]["r2"] > max(e["r2"] for e in board
                                                   if e["family"].startswith("baseline"))}


def train_all(conn, prefix="med_"):
    out = []
    for r in db.rows(conn, "SELECT id, name FROM product WHERE id LIKE ?", (prefix + "%",)):
        res = train(conn, r["id"])
        res["name"] = r["name"]
        out.append(res)
    return out
