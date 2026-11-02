"""Marketing allocation: deterministic daily bands, weekly Thompson sampling.

Decisions are made on contribution margin from our own order data, never on
platform-reported revenue, and never on a cell that has not yet earned the
right to be judged (minimum exposure).
"""
import random

from core import db

random.seed(7)   # reproducible demo; remove in production


def target_cpa(cm1, payback_factor):
    return round(cm1 * payback_factor, 2)


def cell_stats(conn, product_id, window_days=7):
    """Our copy of ad metrics, joined to our own order truth."""
    return db.rows(conn, """
        SELECT cell_id, platform, is_holdout,
               SUM(spend) AS spend, SUM(orders) AS orders, SUM(new_customers) AS new_customers,
               SUM(revenue) AS revenue, AVG(frequency) AS frequency,
               SUM(clicks) AS clicks, SUM(impressions) AS impressions,
               COUNT(*) AS days
        FROM ad_metrics WHERE product_id=? AND day >= date((SELECT MAX(day) FROM ad_metrics), ?)
        GROUP BY cell_id, platform, is_holdout ORDER BY spend DESC""",
        (product_id, "-%d day" % window_days))


def ctr_baseline(conn, cell_id):
    """A cell's own first-week click-through rate, for fatigue detection."""
    row = db.one(conn, """
        SELECT SUM(clicks)*1.0/NULLIF(SUM(impressions),0) AS ctr FROM (
          SELECT clicks, impressions FROM ad_metrics WHERE cell_id=? ORDER BY day LIMIT 7)""", (cell_id,))
    return (row or {}).get("ctr") or 0.0


def exposure_met(stats, target, policy):
    """A cell has earned a verdict when either enough conversions have happened
    to measure it, or enough money has been spent that the absence of them is
    itself the evidence. Both still require a minimum number of days."""
    enough_conversions = stats["orders"] >= policy["min_conversions"]
    enough_spend = stats["spend"] >= policy["spend_exhaustion_multiple"] * target
    return (enough_conversions or enough_spend) and stats["days"] >= policy["min_days"]


def model_view(conn, product_id, cells, target):
    """Expected CPA per cell from the promoted model, if there is one.

    The model never decides. It supplies an expectation that the deterministic
    bands then judge, and it is ignored entirely when no model is promoted or
    when the prediction disagrees with the observation by more than a factor of
    two - at which point the observation wins and an anomaly is raised.
    """
    try:
        from engines import ml
    except Exception:                                          # noqa: BLE001
        return {}
    if not ml.available():
        return {}
    bundle = ml.load_promoted(conn)
    if not bundle:
        return {}
    import json as _json
    out = {}
    for c in cells:
        row = db.one(conn, """
            SELECT features FROM ad_feature WHERE cell_id=? ORDER BY day DESC LIMIT 1""",
            (c["cell_id"],))
        if not row:
            continue
        feats = _json.loads(row["features"])
        # the promoted model is fitted on trailing means; approximate them with
        # the cell's own last seven days, which is what the panel holds
        trailing = {k + "_7d": v for k, v in feats.items() if isinstance(v, (int, float))}
        trailing.update(feats)
        pred = ml.predict_orders(conn, [trailing])
        if not pred:
            continue
        expected_orders_week = max(0.01, pred[0])
        weekly_spend = (c["spend"] / max(1, c["days"])) * 7
        out[c["cell_id"]] = {
            "expected_orders_7d": round(expected_orders_week, 2),
            "expected_cpa": round(weekly_spend / expected_orders_week, 2),
            "observed_cpa": round(c["spend"] / c["orders"], 2) if c["orders"] else None,
            "model": bundle["registry"]["family"],
        }
    return out


def reconcile(model_cpa, observed_cpa, tolerance=2.0):
    """Which number the agent acts on, and why."""
    if model_cpa is None:
        return observed_cpa, "no model promoted: observation only"
    if observed_cpa is None:
        return model_cpa, "no conversions yet: model expectation used"
    ratio = max(model_cpa, 0.01) / max(observed_cpa, 0.01)
    if ratio > tolerance or ratio < 1 / tolerance:
        return observed_cpa, ("model expected EUR %.0f against observed EUR %.0f: more than a "
                              "factor of two apart, so the observation wins and the gap is logged"
                              % (model_cpa, observed_cpa))
    blended = 0.5 * model_cpa + 0.5 * observed_cpa
    return blended, ("blended model EUR %.0f with observed EUR %.0f" % (model_cpa, observed_cpa))


def explain_cell(conn, stats, target, policy, cover_days, in_cooldown, model_cpa=None):
    """Every check, in the order it is made, with the value it was made on.

    decide_cell returns only the rule that fired. This returns the whole ladder,
    so a person can see what was tested, what passed, and where it stopped.
    """
    steps = []
    daily = round(stats["spend"] / max(1, stats["days"]), 2)
    observed_cpa = (stats["spend"] / stats["orders"]) if stats["orders"] else None
    cpa, cpa_note = reconcile(model_cpa, observed_cpa)
    ctr = (stats["clicks"] / stats["impressions"]) if stats["impressions"] else 0.0
    base = ctr_baseline(conn, stats["cell_id"])
    spent_out = stats["spend"] >= policy["spend_exhaustion_multiple"] * target

    def step(name, detail, outcome, stops=False):
        steps.append({"check": name, "detail": detail, "outcome": outcome, "decided": stops})
        return stops

    action, budget, reason = decide_cell(conn, stats, target, policy, cover_days,
                                         in_cooldown, model_cpa)

    step("Is this the measurement holdout?",
         "holdout = %s" % bool(stats["is_holdout"]),
         "protected, never funded or paused" if stats["is_holdout"] else "no, continue",
         bool(stats["is_holdout"]))
    step("Can supply serve more demand?",
         "hero variant cover %.0f days, floor %d" % (cover_days or 0, policy["min_cover_days_for_acquisition"]),
         "below floor, acquisition off" if (cover_days is not None and cover_days < policy["min_cover_days_for_acquisition"]) else "yes",
         cover_days is not None and cover_days < policy["min_cover_days_for_acquisition"])
    step("Has it earned a verdict?",
         "%d orders (need %d) or EUR %.0f spent (need %.0f), over %d days (need %d)"
         % (stats["orders"], policy["min_conversions"], stats["spend"],
            policy["spend_exhaustion_multiple"] * target, stats["days"], policy["min_days"]),
         "yes" if exposure_met(stats, target, policy) else "not yet known, no action",
         not exposure_met(stats, target, policy))
    step("Still in the platform's learning phase?",
         "%d conversions (threshold %d), spend exhausted = %s"
         % (stats["orders"], policy["learning_conversions"], spent_out),
         "yes, edits would restart learning" if (stats["orders"] < policy["learning_conversions"] and not spent_out) else "no",
         stats["orders"] < policy["learning_conversions"] and not spent_out)
    step("Changed recently?", "cooldown %dh" % policy["cooldown_hours_per_cell"],
         "in cooldown" if in_cooldown else "no", in_cooldown)
    fatigued = (stats["frequency"] or 0) > policy["fatigue_frequency"] and base and ctr < base * (1 - policy["fatigue_ctr_drop"])
    step("Is the creative worn out?",
         "frequency %.1f (limit %.1f), CTR %.2f%% against its own baseline %.2f%%"
         % (stats["frequency"] or 0, policy["fatigue_frequency"], ctr * 100, base * 100),
         "fatigued, ask for new creative" if fatigued else "no", fatigued)
    step("What does the model expect?",
         "model CPA %s, observed CPA %s" % (
             ("EUR %.0f" % model_cpa) if model_cpa else "no model promoted",
             ("EUR %.0f" % observed_cpa) if observed_cpa else "no conversions"),
         cpa_note)
    if cpa:
        pct = cpa / target * 100
        band = ("at or under 80% of target: scale" if pct <= 80 else
                "80-100%: hold" if pct <= 100 else
                "100-%d%%: trim" % (policy["pause_above_target_multiple"] * 100) if pct <= policy["pause_above_target_multiple"] * 100 else
                "over %d%%: pause" % (policy["pause_above_target_multiple"] * 100))
        step("Cost per order against target",
             "EUR %.0f against target EUR %.0f = %.0f%%" % (cpa, target, pct), band, True)

    return {"action": action, "budget": budget, "reason": reason, "steps": steps,
            "daily_now": daily, "target_cpa": target, "cpa_used": cpa,
            "observed_cpa": observed_cpa, "model_cpa": model_cpa}


def decide_cell(conn, stats, target, policy, cover_days, in_cooldown, model_cpa=None):
    """Return (action, new_budget_eur, reason) for one cell. Deterministic."""
    daily = round(stats["spend"] / max(1, stats["days"]), 2)   # the proposal is built from this exact figure
    observed_cpa = (stats["spend"] / stats["orders"]) if stats["orders"] else None
    cpa, cpa_note = reconcile(model_cpa, observed_cpa)
    ncac = (stats["spend"] / stats["new_customers"]) if stats["new_customers"] else None
    ctr = (stats["clicks"] / stats["impressions"]) if stats["impressions"] else 0.0
    base = ctr_baseline(conn, stats["cell_id"])
    fatigued = (stats["frequency"] or 0) > policy["fatigue_frequency"] and base and ctr < base * (1 - policy["fatigue_ctr_drop"])

    if stats["is_holdout"]:
        return "protect", daily, "geo holdout: never funded, never paused - it is the measurement baseline"
    if cover_days is not None and cover_days < policy["min_cover_days_for_acquisition"]:
        return "pause_acquisition", 0.0, "SKU cover %.0f days below %d: marketing may not sell what supply cannot serve" % (cover_days, policy["min_cover_days_for_acquisition"])
    if not exposure_met(stats, target, policy):
        return "hold", daily, "minimum exposure not met (%d orders, EUR %.0f spent, %d days): not yet known" % (stats["orders"], stats["spend"], stats["days"])
    spent_out = stats["spend"] >= policy["spend_exhaustion_multiple"] * target
    if stats["orders"] < policy["learning_conversions"] and not spent_out:
        return "hold", daily, "still in learning (%d of %d conversions): edits restart learning" % (stats["orders"], policy["learning_conversions"])
    if in_cooldown:
        return "hold", daily, "cell changed within the last %dh" % policy["cooldown_hours_per_cell"]
    if fatigued:
        return "request_creative", daily, "creative fatigue: frequency %.1f, CTR %.2f%% vs %.2f%% baseline" % (stats["frequency"], ctr * 100, base * 100)
    if cpa is None:
        return "hold", daily, "no conversions yet"
    if cpa <= target * 0.8:
        return "scale", round(daily * (1 + policy["max_change_pct"] / 100.0), 2), "CPA EUR %.0f is %.0f%% of target EUR %.0f (%s)" % (cpa, cpa / target * 100, target, cpa_note)
    if cpa <= target:
        return "hold", daily, "CPA EUR %.0f inside target EUR %.0f but without headroom (%s)" % (cpa, target, cpa_note)
    if cpa <= target * policy["pause_above_target_multiple"]:
        floor = target / 3.0
        return "reduce", round(max(floor, daily * (1 - policy["max_change_pct"] / 100.0)), 2), "CPA EUR %.0f is %.0f%% of target: trim rather than pause, so the cell stays measurable (%s)" % (cpa, cpa / target * 100, cpa_note)
    return "pause", 0.0, "CPA EUR %.0f is %.0f%% of target with exposure met (%s)" % (cpa, cpa / target * 100, cpa_note)


def holdout_lift(conn, product_id, window_days=7):
    """Orders in holdout regions are orders we did not pay for."""
    rows = cell_stats(conn, product_id, window_days)
    paid = sum(r["orders"] for r in rows if not r["is_holdout"])
    held = sum(r["orders"] for r in rows if r["is_holdout"])
    if not paid:
        return {"paid_orders": paid, "holdout_orders": held, "organic_share": None}
    share = held / (paid + held)
    return {"paid_orders": paid, "holdout_orders": held,
            "organic_share": round(share, 3),
            "incrementality_factor": round(1 - share, 3)}


def thompson(arms, policy):
    """Sample a channel allocation from the posterior of profit per euro.

    arms: {name: {"wins": profitable orders, "losses": unprofitable orders, "share": current}}
    """
    samples = {}
    for name, a in arms.items():
        samples[name] = random.betavariate(1 + a["wins"], 1 + a["losses"])
    total = sum(samples.values()) or 1.0
    raw = {k: v / total for k, v in samples.items()}

    # exploration floor, then per-arm caps, then renormalise
    k = len(raw)
    floor_pool = policy["exploration_floor"]
    out = {name: floor_pool / k + (1 - floor_pool) * share for name, share in raw.items()}
    for name in out:
        out[name] = min(policy["max_share_per_arm"], max(policy["min_share_per_arm"], out[name]))
    total = sum(out.values())
    out = {k2: v / total for k2, v in out.items()}

    # cap weekly movement per arm against the current share
    capped = {}
    for name, share in out.items():
        cur = arms[name].get("share", share)
        lo, hi = cur * (1 - policy["max_weekly_change_per_arm"]), cur * (1 + policy["max_weekly_change_per_arm"])
        capped[name] = min(hi, max(lo, share)) if cur else share
    total = sum(capped.values())
    return {k3: round(v / total, 4) for k3, v in capped.items()}


def signal_health(conn, product_id, day, window_days=7):
    """Platform-reported orders vs our own order count. Drift freezes scaling.

    Compared over a week: a single day is too noisy to act on, and the failure
    we are catching (a broken pixel) persists.
    """
    platform = db.scalar(conn, """
        SELECT SUM(orders) FROM ad_metrics WHERE product_id=? AND is_holdout=0
          AND day >= date(?, ?)""", (product_id, day, "-%d day" % window_days))
    ours = db.scalar(conn, """
        SELECT SUM(s.units) FROM sales_fact s JOIN variant v ON v.id=s.variant_id
        WHERE v.product_id=? AND substr(s.ts,1,10) >= date(?, ?)""",
        (product_id, day, "-%d day" % window_days))
    if not ours:
        return {"platform": platform, "ours": ours, "drift_pct": None, "healthy": True}
    drift = abs(platform - ours) / ours * 100
    return {"platform": platform, "ours": ours, "drift_pct": round(drift, 1), "healthy": drift <= 25}
