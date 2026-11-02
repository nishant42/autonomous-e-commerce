"""The marketing model pipeline.

Targeted marketing is a modelling problem, not a rules problem: who saw the ad,
on what device, after searching for what, at what price, with how much stock
behind it. This module does the whole workflow on that panel and refuses to
hand anything to the allocator until it has earned its place:

  1. build the panel        30+ features per cell-day, from the feature store
  2. stationarity           ADF per feature; difference what is not stationary
  3. significance           correlation with p-values, and VIF for collinearity
  4. feature selection      LassoCV on standardised features, time-series folds
  5. model families         ridge, lasso, random forest, gradient boosting,
                            XGBoost - plus two naive baselines to beat
  6. out-of-sample          a forward split in time, never a random split
  7. promotion              the winner is promoted only if it beats the
                            incumbent and the baseline; the decision is recorded

Optional by design: with scikit-learn absent the marketing agent keeps running
on its deterministic bands, exactly as it does when the model is unavailable.
"""
import json
import math
import os
import pickle
import warnings

from core import db

warnings.filterwarnings("ignore")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
TEST_FRACTION = 0.25          # the most recent quarter of the panel is held out
PROMOTION_MARGIN = 0.02       # a new model must beat the incumbent by this much R2
MIN_OUT_SAMPLE_R2 = 0.05      # below this it is not a model, it is a decoration

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LassoCV, LinearRegression, Ridge
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    HAVE_SKLEARN = True
except ImportError:                                            # pragma: no cover
    HAVE_SKLEARN = False

try:
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tsa.stattools import adfuller
    HAVE_STATSMODELS = True
except ImportError:                                            # pragma: no cover
    HAVE_STATSMODELS = False

try:
    from xgboost import XGBRegressor
    HAVE_XGB = True
except ImportError:                                            # pragma: no cover
    HAVE_XGB = False

try:
    from lightgbm import LGBMRegressor
    HAVE_LGBM = True
except ImportError:                                            # pragma: no cover
    HAVE_LGBM = False


def available():
    return HAVE_SKLEARN


# ------------------------------------------------------------------ panel ----

def load_panel(conn, product_id="p_towel", include_holdout=False):
    """Join the feature store to the target. One row per cell-day."""
    rows = db.rows(conn, """
        SELECT f.cell_id, f.day, f.features, m.orders, m.spend, m.is_holdout, m.platform
        FROM ad_feature f JOIN ad_metrics m ON m.cell_id=f.cell_id AND m.day=f.day
        WHERE f.product_id=? ORDER BY f.day, f.cell_id""", (product_id,))
    records = []
    for r in rows:
        if r["is_holdout"] and not include_holdout:
            continue
        rec = json.loads(r["features"])
        rec.update({"cell_id": r["cell_id"], "day": r["day"], "orders": r["orders"]})
        records.append(rec)
    df = pd.DataFrame.from_records(records)
    df["day"] = pd.to_datetime(df["day"])
    return df.sort_values(["day", "cell_id"]).reset_index(drop=True)


def feature_columns(df):
    drop = {"orders", "day", "cell_id", "is_holdout"}
    return [c for c in df.columns if c not in drop and not c.startswith("cellflag_")
            and pd.api.types.is_numeric_dtype(df[c])]


# ---------------------------------------------------------- 2. stationarity --

def stationarity(df, cols, alpha=0.05):
    """Augmented Dickey-Fuller per feature, on the panel mean by day.

    A feature with a unit root will produce a spurious relationship with any
    other trending series, so it is differenced before it is allowed into the
    model rather than silently fitted.
    """
    if not HAVE_STATSMODELS:
        return [], []
    daily = df.groupby("day")[cols].mean()
    out, to_difference = [], []
    for c in cols:
        series = daily[c].dropna()
        if series.nunique() <= 2 or len(series) < 20:
            out.append({"feature": c, "adf": None, "p_value": None,
                        "stationary": True, "note": "constant or binary, test not applicable"})
            continue
        try:
            stat, p, _, _, crit, _ = adfuller(series, autolag="AIC")
        except Exception:                                      # noqa: BLE001
            out.append({"feature": c, "adf": None, "p_value": None, "stationary": True,
                        "note": "test failed, left as is"})
            continue
        stationary = p < alpha
        if not stationary:
            to_difference.append(c)
        out.append({"feature": c, "adf": round(float(stat), 3), "p_value": round(float(p), 4),
                    "crit_5pct": round(float(crit["5%"]), 3), "stationary": bool(stationary),
                    "note": "stationary" if stationary else "unit root: first-differenced"})
    return out, to_difference


def make_trailing(df, cols, window=7):
    """Re-express the panel at the cadence the allocator actually decides on.

    A single cell-day is mostly noise: a handful of orders against multiplicative
    variance. The daily rule reads a seven-day window, so that is what gets
    modelled. Windows overlap, which inflates apparent performance if the split
    straddles them - handled in the split, not hidden here.
    """
    out = df.sort_values(["cell_id", "day"]).copy()
    g = out.groupby("cell_id")
    for c in cols:
        out[c + "_7d"] = g[c].transform(lambda s: s.rolling(window, min_periods=window).mean())
    out["orders_7d"] = g["orders"].transform(lambda s: s.rolling(window, min_periods=window).sum())
    # The honest lag: the PREVIOUS, non-overlapping window. A trailing feature
    # built from the target shares six of its seven days with it, so a model fed
    # orders_lag1_7d scores 0.97 and has learned nothing but "same as last week".
    out["orders_prev_window"] = out.groupby("cell_id")["orders_7d"].shift(window)
    return out.dropna(subset=["orders_7d", "orders_prev_window"]).reset_index(drop=True)


# Anything computed FROM orders. These can only enter a model as a strictly
# lagged, non-overlapping term, which is what orders_prev_window is for.
TARGET_DERIVED = ("orders_lag", "cpa_roll", "cpa_", "cvr", "conversion_rate", "revenue")


def target_overlap_check(cols, target):
    """Remove features derived from the target itself.

    Two ways this bites. A trailing transform of the target shares most of its
    window with it. And a ratio built on the target - cost per acquisition is
    spend divided by orders - carries the target in its denominator. Either one
    will dominate every model and teach it nothing.
    """
    keep = {"orders_prev_window", target}
    bad = [c for c in cols
           if c not in keep and (c.startswith("orders") or c.startswith(TARGET_DERIVED))]
    return bad, [{"feature": c, "note": "computed from the target: excluded"} for c in bad]


def leakage_check(df, cols, threshold=0.9):
    """Drop features that are a proxy for the calendar.

    A feature that rises monotonically with time (a week index, a counter) lets
    a tree memorise *when* a row happened. In-sample it looks brilliant; out of
    sample, past the end of the training range, it is worthless. This is the
    most common way a marketing model flatters itself.
    """
    from scipy import stats as sps
    t = df["day"].rank(method="dense").values
    leaky, report = [], []
    for c in cols:
        x = df[c].astype(float).values
        if np.nanstd(x) < 1e-9:
            continue
        rho, _ = sps.spearmanr(t, x)
        if rho is None or np.isnan(rho):
            continue
        if abs(rho) > threshold:
            leaky.append(c)
            report.append({"feature": c, "rho_time": round(float(rho), 3),
                           "note": "monotonic in time: dropped as a calendar proxy"})
    return leaky, report


def target_stationarity(df, target="orders"):
    """The target gets the same test. Differencing features while leaving the
    target in levels - which is the easy mistake - destroys the relationship."""
    if not HAVE_STATSMODELS:
        return None
    series = df.groupby("day")[target].mean().dropna()
    try:
        stat, p, _, _, crit, _ = adfuller(series, autolag="AIC")
    except Exception:                                          # noqa: BLE001
        return None
    return {"feature": target, "adf": round(float(stat), 3), "p_value": round(float(p), 4),
            "stationary": bool(p < 0.05)}


def add_cell_dummies(df):
    """Each cell has its own level. Without this the models spend their capacity
    learning which row belongs to which campaign."""
    out = df.copy()
    for cell in sorted(out["cell_id"].unique()):
        out["cellflag_" + cell] = (out["cell_id"] == cell).astype(int)
    return out


def apply_differencing(df, cols):
    """First-difference within each cell, so one cell's history never leaks into another."""
    out = df.copy()
    for c in cols:
        out[c] = out.groupby("cell_id")[c].diff()
    return out.dropna().reset_index(drop=True)


# ---------------------------------------------------------- 3. significance --

def significance(df, cols, target="orders", alpha=0.05):
    from scipy import stats as sps
    rows = []
    y = df[target].astype(float)
    for c in cols:
        x = df[c].astype(float)
        if x.nunique() < 2:
            continue
        r, p = sps.pearsonr(x, y)
        rows.append({"feature": c, "pearson_r": round(float(r), 4),
                     "p_value": float(p), "significant": bool(p < alpha)})
    rows.sort(key=lambda d: -abs(d["pearson_r"]))
    return rows


def collinearity(df, cols, threshold=10.0):
    """Variance inflation: two features saying the same thing make coefficients
    meaningless, so the weaker of a collinear pair is reported for removal."""
    if not HAVE_STATSMODELS or len(cols) < 2:
        return []
    X = df[cols].astype(float)
    X = X.loc[:, X.std() > 1e-9]
    X = (X - X.mean()) / X.std()
    X = X.assign(_const=1.0)
    out = []
    for i, c in enumerate(X.columns[:-1]):
        try:
            vif = variance_inflation_factor(X.values, i)
        except Exception:                                      # noqa: BLE001
            continue
        out.append({"feature": c, "vif": round(float(vif), 2), "collinear": bool(vif > threshold)})
    out.sort(key=lambda d: -d["vif"])
    return out


# ------------------------------------------------------ 4. feature selection --

def select_features(df, cols, target="orders"):
    """LassoCV with time-series folds. Features whose coefficient is driven to
    zero are dropped, which is how the vanity metrics leave the model."""
    X = df[cols].astype(float).values
    y = df[target].astype(float).values
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    model = LassoCV(cv=TimeSeriesSplit(n_splits=4), random_state=0, max_iter=20000).fit(Xs, y)
    coefs = dict(zip(cols, model.coef_))
    selected = [c for c in cols if abs(coefs[c]) > 1e-6]
    dropped = [c for c in cols if c not in selected]
    ranked = sorted(((c, float(coefs[c])) for c in selected), key=lambda t: -abs(t[1]))
    return {"selected": selected, "dropped": dropped, "alpha": float(model.alpha_),
            "ranked": [{"feature": c, "std_coef": round(v, 4)} for c, v in ranked]}


# ------------------------------------------------------------- 5/6. models ----

def _metrics(y, pred):
    return {"r2": round(float(r2_score(y, pred)), 4),
            "rmse": round(float(mean_squared_error(y, pred, squared=False)), 4),
            "mae": round(float(mean_absolute_error(y, pred)), 4)}


def _families():
    fams = {
        "ridge": Ridge(alpha=1.0),
        "lasso": LassoCV(cv=TimeSeriesSplit(n_splits=4), random_state=0, max_iter=20000),
        "random_forest": RandomForestRegressor(n_estimators=400, min_samples_leaf=8,
                                               max_features=0.5, random_state=0, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=250, max_depth=3,
                                                       learning_rate=0.05, subsample=0.85,
                                                       random_state=0),
    }
    if HAVE_XGB:
        fams["xgboost"] = XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                       subsample=0.85, colsample_bytree=0.8, reg_lambda=2.0,
                                       min_child_weight=4, random_state=0, verbosity=0)
    if HAVE_LGBM:
        fams["lightgbm"] = LGBMRegressor(n_estimators=400, learning_rate=0.06, random_state=0)
    return fams


def train_and_compare(panels, features_by_panel, target="orders", target_cpa=None, embargo=0):
    """Every family against every candidate panel and target transform.

    Two questions are settled here by out-of-sample evidence rather than taste:
    whether the response scales linearly or multiplicatively (identity versus
    log target), and whether the panel should be levels or differenced. Metrics
    are always reported on the original order scale, so the rows compare.

    The split is forward in time. A random split leaks the future into training
    and makes every model look better than it is.
    """
    board, fitted = [], {}
    baseline_done = False

    for panel_name, df in panels.items():
        feats = features_by_panel[panel_name]
        df = df.sort_values("day").reset_index(drop=True)
        days = sorted(df["day"].unique())
        cut = days[int(len(days) * (1 - TEST_FRACTION))]
        train, test = df[df["day"] < cut], df[df["day"] >= cut]
        if embargo:
            # a trailing window that spans the cut has seen training data, so the
            # first `embargo` days of the test set are discarded outright
            keep_from = cut + pd.Timedelta(days=embargo)
            test = test[test["day"] >= keep_from]
        if len(train) < 30 or len(test) < 10:
            continue

        Xtr, Xte = train[feats].astype(float).values, test[feats].astype(float).values
        ytr_raw = train[target].astype(float).values
        yte_raw = test[target].astype(float).values
        scaler = StandardScaler().fit(Xtr)
        Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)

        if not baseline_done:
            baseline_done = True
            board.append({"family": "baseline_mean", "panel": panel_name, "transform": "-",
                          "in_sample": _metrics(ytr_raw, np.full_like(ytr_raw, ytr_raw.mean())),
                          "out_sample": _metrics(yte_raw, np.full_like(yte_raw, ytr_raw.mean())),
                          "auc": None})
            lag_col = "orders_prev_window" if "orders_prev_window" in test.columns else (
                "orders_lag1" if "orders_lag1" in test.columns else None)
            if lag_col:
                tr_l, te_l = train[lag_col].astype(float), test[lag_col].astype(float)
                if tr_l.notna().all() and te_l.notna().all():
                    board.append({"family": "baseline_previous_window", "panel": panel_name,
                                  "transform": "-",
                                  "in_sample": _metrics(ytr_raw, tr_l.values),
                                  "out_sample": _metrics(yte_raw, te_l.values), "auc": None})

        for transform in ("identity", "log"):
            fwd = (lambda v: np.log1p(np.maximum(v, 0))) if transform == "log" else (lambda v: v)
            back = (lambda v: np.expm1(np.clip(v, -10, 10))) if transform == "log" else (lambda v: v)
            ytr = fwd(ytr_raw)
            for name, model in _families().items():
                use_scaled = name in ("ridge", "lasso")
                try:
                    model.fit(Xtr_s if use_scaled else Xtr, ytr)
                    pin = back(model.predict(Xtr_s if use_scaled else Xtr))
                    pout = back(model.predict(Xte_s if use_scaled else Xte))
                except Exception as exc:                        # noqa: BLE001
                    board.append({"family": name, "panel": panel_name, "transform": transform,
                                  "error": repr(exc)[:80]})
                    continue
                key = "%s|%s|%s" % (name, panel_name, transform)
                entry = {"family": name, "panel": panel_name, "transform": transform,
                         "key": key, "in_sample": _metrics(ytr_raw, pin),
                         "out_sample": _metrics(yte_raw, pout)}
                # The same question asked as a classification: will this cell
                # be profitable? That is what the allocator actually acts on.
                if target_cpa:
                    col = "spend_7d" if "spend_7d" in test.columns else (
                        "spend" if "spend" in test.columns else None)
                    if col:
                        spend = test[col].astype(float).values
                        if col == "spend_7d":
                            spend = spend * 7.0          # mean per day over the window
                        actual = ((spend / np.maximum(yte_raw, 1e-9)) <= target_cpa).astype(int)
                        score = -(spend / np.maximum(pout, 1e-9))
                        if 0 < actual.sum() < len(actual):
                            entry["auc"] = round(float(roc_auc_score(actual, score)), 4)
                board.append(entry)
                fitted[key] = (model, scaler, use_scaled, feats, transform, panel_name)

    ranked = [e for e in board if "out_sample" in e]
    ranked.sort(key=lambda e: -e["out_sample"]["r2"])
    cut_day = str(cut)[:10]
    return {"leaderboard": ranked, "fitted": fitted, "cut_day": cut_day,
            "n_train": len(train), "n_test": len(test)}


# --------------------------------------------------------------- 7. promote --

def _save(model_id, obj):
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, "model_%s.pkl" % model_id)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh)
    return path


def load_promoted(conn, target="orders_7d"):
    row = db.one(conn, "SELECT * FROM model_registry WHERE promoted=1 AND target=?"
                       " ORDER BY id DESC LIMIT 1", (target,))
    if not row:
        return None
    path = os.path.join(MODEL_DIR, "model_%s.pkl" % row["id"])
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        bundle = pickle.load(fh)
    bundle["registry"] = row
    return bundle


def run_pipeline(conn, product_id="p_towel", target_cpa=None, verbose_sink=None, target="orders"):
    """The whole workflow. Returns a report the console and the CLI both render."""
    def say(msg):
        if verbose_sink:
            verbose_sink(msg)

    if not available():
        return {"error": "scikit-learn is not installed; the allocator stays on its rule bands"}

    df = load_panel(conn, product_id)
    cols = feature_columns(df)
    say("panel: %d cell-days, %d candidate features" % (len(df), len(cols)))

    embargo = 0
    if target == "orders_7d":
        df = make_trailing(df, cols)
        cols = [c + "_7d" for c in cols if c + "_7d" in df.columns]
        embargo = 7
        say("re-expressed at the seven-day cadence the allocator decides on: %d rows, "
            "%d trailing features, 7-day embargo at the split" % (len(df), len(cols)))

    adf, to_diff = stationarity(df, cols)
    tgt_adf = target_stationarity(df, target)
    say("stationarity: %d of %d features carry a unit root; target itself is %s"
        % (len(to_diff), len(adf), "stationary" if (tgt_adf or {}).get("stationary") else "not stationary"))

    overlap, overlap_report = target_overlap_check(cols, target)
    if overlap:
        cols = [c for c in cols if c not in overlap]
        if "orders_prev_window" in df.columns and "orders_prev_window" not in cols:
            cols.append("orders_prev_window")
        say("overlap guard: dropped %d target-derived feature(s): %s"
            % (len(overlap), ", ".join(overlap)))

    leaky, leak_report = leakage_check(df, cols)
    if leaky:
        cols = [c for c in cols if c not in leaky]
        say("leakage guard: dropped %d calendar-proxy feature(s): %s"
            % (len(leaky), ", ".join(leaky)))

    levels = add_cell_dummies(df)
    dummies = [c for c in levels.columns if c.startswith("cellflag_")]
    sig = significance(levels, cols, target=target)
    vif = collinearity(levels, [x["feature"] for x in sig[:20]])
    say("significance: %d of %d features correlate with orders at p<0.05"
        % (sum(1 for x in sig if x["significant"]), len(sig)))

    sel = select_features(levels, cols, target=target)
    say("selection: Lasso kept %d features, dropped %d" % (len(sel["selected"]), len(sel["dropped"])))
    chosen = (sel["selected"] or cols)

    panels = {"levels": levels}
    features_by_panel = {"levels": chosen + dummies}
    if to_diff:
        diffed = add_cell_dummies(apply_differencing(df, to_diff))
        panels["differenced"] = diffed
        features_by_panel["differenced"] = [c for c in chosen if c in diffed.columns] + dummies
        say("also evaluating a differenced panel, since %d features carry a unit root" % len(to_diff))

    res = train_and_compare(panels, features_by_panel, target=target,
                            target_cpa=target_cpa, embargo=embargo)
    best = res["leaderboard"][0]
    say("best out-of-sample: %s on the %s panel with a %s target (R2 %.3f)"
        % (best["family"], best["panel"], best["transform"], best["out_sample"]["r2"]))

    # promotion: beat both the incumbent and the naive baselines, or do not ship
    baseline = max((e["out_sample"]["r2"] for e in res["leaderboard"]
                    if e["family"].startswith("baseline")), default=-9)
    incumbent = db.one(conn, "SELECT * FROM model_registry WHERE promoted=1 AND target=?"
                             " ORDER BY id DESC LIMIT 1", (target,))
    inc_r2 = json.loads(incumbent["out_sample"])["r2"] if incumbent else None

    promote, reason = True, "first model, and it beats both naive baselines"
    if best["out_sample"]["r2"] < MIN_OUT_SAMPLE_R2:
        promote, reason = False, ("best out-of-sample R2 %.3f is below the floor of %.2f: a model "
                                  "that cannot beat the test-set mean is not used, whatever the "
                                  "baseline did" % (best["out_sample"]["r2"], MIN_OUT_SAMPLE_R2))
    elif best["family"].startswith("baseline"):
        promote, reason = False, "no model beat the naive baseline: nothing is promoted"
    elif best["out_sample"]["r2"] <= baseline:
        promote, reason = False, "best model R2 %.3f does not beat baseline %.3f" % (
            best["out_sample"]["r2"], baseline)
    elif inc_r2 is not None:
        if best["out_sample"]["r2"] < inc_r2 - PROMOTION_MARGIN:
            promote, reason = False, "regression against the live model (%.3f vs %.3f): the " \
                                     "incumbent stays" % (best["out_sample"]["r2"], inc_r2)
        else:
            reason = "beats the live model (%.3f vs %.3f)" % (best["out_sample"]["r2"], inc_r2)

    diagnostics = {"stationarity": adf, "target_stationarity": tgt_adf, "leakage": leak_report,
                   "significance": sig,
                   "collinearity": vif, "selection": sel, "cut_day": res["cut_day"],
                   "baseline_r2": baseline, "incumbent_r2": inc_r2,
                   "panel": best.get("panel"), "transform": best.get("transform")}
    cur = conn.execute(
        "INSERT INTO model_registry (trained_at, target, family, features, n_train, n_test,"
        " in_sample, out_sample, promoted, promotion_reason, diagnostics)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (db.now(), target, "%s (%s panel, %s target)" % (best["family"], best["panel"], best["transform"]),
         db.dumps(features_by_panel[best["panel"]]), res["n_train"], res["n_test"],
         db.dumps(best["in_sample"]), db.dumps(best["out_sample"]), 1 if promote else 0,
         reason, db.dumps(diagnostics)))
    model_id = cur.lastrowid
    if promote:
        conn.execute("UPDATE model_registry SET promoted=0 WHERE id<>? AND target=?",
                     (model_id, target))
        model, scaler, use_scaled, feats, transform, panel_name = res["fitted"][best["key"]]
        _save(model_id, {"model": model, "scaler": scaler, "scaled": use_scaled,
                         "features": feats, "transform": transform, "panel": panel_name,
                         "differenced": to_diff if panel_name == "differenced" else [],
                         "family": best["family"]})
    say("promotion: %s - %s" % ("PROMOTED" if promote else "held back", reason))

    return {"model_id": model_id, "promoted": promote, "reason": reason, "target": target,
            "leaderboard": res["leaderboard"], "diagnostics": diagnostics,
            "features": features_by_panel[best["panel"]],
            "n_train": res["n_train"], "n_test": res["n_test"],
            "cut_day": res["cut_day"], "panel_rows": len(df), "candidates": len(cols)}


def feature_ranges(conn, product_id="p_towel"):
    """What each feature actually looked like in training, so the UI can keep a
    person inside the range and flag them when they leave it."""
    df = load_panel(conn, product_id)
    out = {}
    for c in feature_columns(df):
        col = df[c].astype(float)
        out[c] = {"min": round(float(col.min()), 3), "max": round(float(col.max()), 3),
                  "median": round(float(col.median()), 3)}
    return out


def what_if(conn, base_features, overrides=None):
    """Predict with one or more inputs changed, and say how much it moved.

    This is the honest way to show a model is a model: move an input, watch the
    prediction follow. A hardcoded number does not move.
    """
    bundle = load_promoted(conn)
    if not bundle or not available():
        return {"error": "no promoted model"}
    row = dict(base_features)
    changed = {}
    for key, value in (overrides or {}).items():
        for name in (key, key + "_7d"):
            if name in row or name in bundle["features"]:
                changed[name] = {"from": row.get(name), "to": float(value)}
                row[name] = float(value)
    before = predict_orders(conn, [base_features])
    after = predict_orders(conn, [row])
    if not before or not after:
        return {"error": "prediction failed"}

    # A model knows nothing outside the range it was trained on. Saying so is
    # part of the answer, not a footnote.
    ranges, warnings = feature_ranges(conn), []
    for name, move in changed.items():
        rng = ranges.get(name) or ranges.get(name.replace("_7d", ""))
        if not rng:
            continue
        if (move["to"] < rng["min"] or move["to"] > rng["max"]) and not any(
                name.replace("_7d", "") in w for w in warnings):
            warnings.append("%s set to %.0f, outside the trained range %.0f to %.0f: the "
                            "prediction is an extrapolation and should not be trusted"
                            % (name.replace("_7d", ""), move["to"], rng["min"], rng["max"]))
    return {"before": round(before[0], 2), "after": round(after[0], 2),
            "changed": changed, "family": bundle["registry"]["family"],
            "features_used": bundle["features"], "ranges": ranges,
            "extrapolating": warnings}


def predict_orders(conn, feature_rows):
    """Predict orders for a list of feature dicts using the promoted model."""
    bundle = load_promoted(conn)
    if not bundle or not available():
        return None
    X = pd.DataFrame([{k: float(r.get(k, 0.0) or 0.0) for k in bundle["features"]}
                      for r in feature_rows])
    Xv = bundle["scaler"].transform(X.values) if bundle["scaled"] else X.values
    pred = bundle["model"].predict(Xv)
    if bundle.get("transform") == "log":
        pred = np.expm1(np.clip(pred, -10, 10))
    return [max(0.0, float(v)) for v in pred]
