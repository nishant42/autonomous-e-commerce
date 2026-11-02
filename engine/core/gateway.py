"""The Action Gateway: the only place a side effect can happen.

Every write an agent wants is a typed proposal that passes, in order:
  1. schema validation      (is this even a well-formed action?)
  2. ownership              (is this agent allowed to express this intent?)
  3. deterministic guards   (cash, cover, caps, cooldowns, exposure)
  4. tier assignment        (auto / maker-checker / human, by money and reversibility)
  5. idempotent execution   (same business decision twice = one effect)
  6. ledger + outbox event  (audit trail and downstream notification)

The agent cannot choose its own tier, cannot skip a guard, and cannot call a
third-party API directly: credentials live here.
"""
import hashlib
import json
from datetime import datetime, timezone

from core import db, bus

# ---- intent registry: schema, ownership, how a value in euros is derived ----

INTENTS = {
    "propose_reorder": {
        "owner": "reorder",
        "fields": {"variant_id": str, "qty": int, "need_by": str, "supplier_id": str},
        "value": lambda conn, p: p["qty"] * db.scalar(
            conn, "SELECT unit_cost FROM supplier_terms WHERE supplier_id=? AND variant_id=?",
            (p["supplier_id"], p["variant_id"]), 0.0),
        "guards": ["qty_sanity_band", "cover_cap", "cash_runway"],   # cheapest and most specific first
        "reversible": True,
    },
    "propose_budget_change": {
        "owner": "marketing_allocator",
        "fields": {"cell_id": str, "from_eur": float, "to_eur": float},
        "value": lambda conn, p: abs(p["to_eur"] - p["from_eur"]),
        "guards": ["max_change_pct", "cooldown", "portfolio_daily_cap", "stock_cover", "experiment_budget"],
        "reversible": True,
    },
    "propose_pause": {
        "owner": "marketing_allocator",
        "fields": {"cell_id": str, "reason": str},
        "value": lambda conn, p: 0.0,
        "guards": ["max_pauses_per_day"],
        "reversible": True,
    },
    "propose_negatives": {
        "owner": "marketing_allocator",
        "fields": {"campaign": str, "terms": list},
        "value": lambda conn, p: 0.0,
        "guards": [],
        "reversible": True,
    },
    "publish_verdict": {
        "owner": "product_verdict",
        "fields": {"product_id": str, "verdict": str, "confidence": float},
        "value": lambda conn, p: 0.0,
        "guards": ["verdict_needs_exposure"],
        "reversible": True,
        # A kill stops spend and clears stock: outward-facing and expensive to undo.
        "force_human": lambda p: p["verdict"] == "KILL",
    },
    "raise_anomaly": {
        "owner": "*",
        "fields": {"kind": str, "severity": str, "note": str},
        "value": lambda conn, p: 0.0,
        "guards": [],
        "reversible": True,
    },
}

# Always human, whatever the amount (rule R9).
ALWAYS_HUMAN = {"change_supplier_bank_details", "release_domain", "customer_email_blast", "new_ad_platform"}


class Rejected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------- guards ----

def _guard_cover_cap(conn, policy, p, ctx):
    if p.get("qty", 1) == 0:
        return                      # "do not order" cannot breach a cover cap
    cover_weeks = ctx.get("cover_after_order_weeks")
    cap = policy["cover_cap_weeks"]
    if cover_weeks is not None and cover_weeks > cap:
        raise Rejected("cover after order %.1fw exceeds cap %sw" % (cover_weeks, cap))


def _guard_cash_runway(conn, policy, p, ctx):
    value = ctx["value_eur"]
    cash = policy["cash_on_hand_eur"]
    weekly_burn = policy["weekly_burn_eur"]
    runway_after = (cash - value) / weekly_burn if weekly_burn else 99
    if runway_after < policy["cash_runway_floor_weeks"]:
        raise Rejected("cash runway after order %.1fw below floor %sw"
                       % (runway_after, policy["cash_runway_floor_weeks"]))


def _guard_qty_sanity(conn, policy, p, ctx):
    """Sanity band against RECONSTRUCTED demand, not units shipped.

    Checking an order against units shipped is the towel trap in guard form: it
    would block the correct order for a variant that was out of stock. Shipped
    units are still recorded so the gap is visible in the audit trail.
    """
    if p.get("qty", 0) == 0:
        return
    lo, hi = policy["qty_band_vs_12w_sales"]
    base = ctx.get("demand_12w") or 0
    shipped = ctx.get("sales_12w") or 0
    if base and not (lo * base <= p["qty"] <= hi * base):
        raise Rejected("qty %d outside sanity band %.1f-%.1f x 12w reconstructed demand (%.0f)"
                       % (p["qty"], lo, hi, base))
    if base and shipped and base > 2 * shipped:
        ctx["note"] = ("12w reconstructed demand %.0f vs %d units shipped: censored by stockouts"
                       % (base, shipped))


def _guard_max_change_pct(conn, policy, p, ctx):
    frm, to = p["from_eur"], p["to_eur"]
    if frm > 0:
        pct = abs(to - frm) / frm * 100
        if pct > policy["max_change_pct_per_cell_per_day"] + 0.05:   # 0.05pp for rounding, not a breach
            raise Rejected("budget change %.0f%% exceeds cap %s%%" % (pct, policy["max_change_pct_per_cell_per_day"]))


def _guard_cooldown(conn, policy, p, ctx):
    lever = "budget:" + p["cell_id"]
    last = db.scalar(conn, "SELECT last_changed_at FROM cooldown WHERE lever=?", (lever,), None)
    if last:
        then = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        hours = max(0, (datetime.now(timezone.utc) - then).total_seconds() / 3600)
    else:
        hours = float("inf")
    if hours < policy["cooldown_hours_per_cell"]:
        raise Rejected("cell in cooldown (%sh remaining)"
                       % int(policy["cooldown_hours_per_cell"] - hours))


def _guard_portfolio_cap(conn, policy, p, ctx):
    if ctx.get("portfolio_daily_total_eur", 0) > policy["portfolio_daily_cap_eur"]:
        raise Rejected("portfolio daily spend %.0f over cap %s"
                       % (ctx["portfolio_daily_total_eur"], policy["portfolio_daily_cap_eur"]))


def _guard_stock_cover(conn, policy, p, ctx):
    cover_days = ctx.get("sku_cover_days")
    if cover_days is not None and cover_days < policy["min_cover_days_for_acquisition"] and p["to_eur"] > p["from_eur"]:
        raise Rejected("cannot raise acquisition spend: SKU cover %.0fd below %sd"
                       % (cover_days, policy["min_cover_days_for_acquisition"]))


def _guard_experiment_budget(conn, policy, p, ctx):
    row = ctx.get("experiment_budget")
    if row and row["spent_eur"] >= row["allocated_eur"] and p["to_eur"] > p["from_eur"]:
        raise Rejected("experiment budget for product exhausted (%.0f of %.0f spent)"
                       % (row["spent_eur"], row["allocated_eur"]))


def _guard_max_pauses(conn, policy, p, ctx):
    if ctx.get("pauses_today", 0) >= policy["max_pauses_per_product_per_day"]:
        raise Rejected("pause limit for product reached today")


def _guard_verdict_exposure(conn, policy, p, ctx):
    if not ctx.get("exposure_met", True):
        raise Rejected("minimum exposure not met: verdict is 'not yet known', not a decision")


GUARDS = {
    "cover_cap": _guard_cover_cap,
    "cash_runway": _guard_cash_runway,
    "qty_sanity_band": _guard_qty_sanity,
    "max_change_pct": _guard_max_change_pct,
    "cooldown": _guard_cooldown,
    "portfolio_daily_cap": _guard_portfolio_cap,
    "stock_cover": _guard_stock_cover,
    "experiment_budget": _guard_experiment_budget,
    "max_pauses_per_day": _guard_max_pauses,
    "verdict_needs_exposure": _guard_verdict_exposure,
}


# ------------------------------------------------------------- execution ----

def idempotency_key(agent, intent, payload, period):
    """Same business decision in the same period hashes to the same key."""
    basis = {"propose_reorder": ("variant_id", "supplier_id"),
             "propose_budget_change": ("cell_id",),
             "propose_pause": ("cell_id",),
             "publish_verdict": ("product_id",),
             "propose_negatives": ("campaign",),
             "raise_anomaly": ("kind",)}.get(intent, tuple(sorted(payload)))
    keys = {k: payload.get(k) for k in basis}
    raw = db.dumps([agent, intent, keys, period])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _tier(policy, value, spec, payload):
    if spec.get("force_human") and spec["force_human"](payload):
        return "T3_human"
    if value >= policy["autonomy"]["human_signal_above_eur"]:
        return "T3_human"
    if value >= policy["autonomy"]["auto_execute_below_eur"]:
        return "T2_checker"
    return "T1_auto"


def propose(conn, agent, intent, payload, policy, ctx=None, rationale="", evidence=None, period="", checker=None):
    """Commit the ledger, cooldown and outbox together, including nested callers."""
    conn.execute("SAVEPOINT gateway_proposal")
    try:
        result = _propose(conn, agent, intent, payload, policy, ctx, rationale, evidence, period, checker)
        conn.execute("RELEASE SAVEPOINT gateway_proposal")
        return result
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT gateway_proposal")
        conn.execute("RELEASE SAVEPOINT gateway_proposal")
        raise


def _propose(conn, agent, intent, payload, policy, ctx=None, rationale="", evidence=None, period="", checker=None):
    """The single entry point for every side effect. Returns the ledger row."""
    ctx = dict(ctx or {})
    evidence = evidence or []
    spec = INTENTS.get(intent)
    if spec is None:
        return _record(conn, agent, intent, payload, 0, "-", "rejected", "unknown intent", rationale, evidence, period)

    # 1. schema
    for field, typ in spec["fields"].items():
        if field not in payload:
            return _record(conn, agent, intent, payload, 0, "-", "rejected",
                           "missing field %s" % field, rationale, evidence, period)
        if typ is float and isinstance(payload[field], int):
            payload[field] = float(payload[field])
        if not isinstance(payload[field], typ):
            return _record(conn, agent, intent, payload, 0, "-", "rejected",
                           "field %s must be %s" % (field, typ.__name__), rationale, evidence, period)

    # 2. ownership (R2)
    if spec["owner"] not in ("*", agent):
        return _record(conn, agent, intent, payload, 0, "-", "rejected",
                       "intent owned by %s, not %s" % (spec["owner"], agent), rationale, evidence, period)

    # 3. verification: every number in the rationale must be cited (R3)
    if rationale and not evidence:
        return _record(conn, agent, intent, payload, 0, "-", "rejected",
                       "rationale carries no evidence ids", rationale, evidence, period)

    value = float(spec["value"](conn, payload) or 0.0)
    ctx["value_eur"] = value

    # 4. deterministic guards
    for name in spec["guards"]:
        try:
            GUARDS[name](conn, policy, payload, ctx)
        except Rejected as rej:
            return _record(conn, agent, intent, payload, value, "-", "rejected",
                           rej.reason, rationale, evidence, period)

    tier = _tier(policy, value, spec, payload)

    # 5. idempotency
    key = idempotency_key(agent, intent, payload, period)
    existing = db.one(conn, "SELECT * FROM ledger WHERE idempotency_key=?", (key,))
    if existing:
        return existing

    status = {"T1_auto": "executed", "T2_checker": "pending_checker", "T3_human": "pending_human"}[tier]
    reason = {"T1_auto": "within autonomy envelope",
              "T2_checker": "maker-checker required",
              "T3_human": "human signal required"}[tier]

    if status == "pending_checker" and checker is not None:
        agreed, note = checker(conn, intent, payload, ctx)
        status = "executed" if agreed else "pending_human"
        reason = "checker agreed: " + note if agreed else "checker disagreed: " + note

    row = _record(conn, agent, intent, payload, value, tier, status, reason, rationale, evidence, period, key)

    # 6. downstream event, in the same transaction as the ledger row
    if status == "executed":
        bus.emit(conn, intent.replace("propose_", "") + ".executed",
                 {"ledger_id": row["id"], "payload": payload}, payload.get("variant_id") or payload.get("cell_id"))
        if intent == "propose_budget_change":
            conn.execute("INSERT OR REPLACE INTO cooldown (lever, last_changed_at) VALUES (?,?)",
                         ("budget:" + payload["cell_id"], db.now()))
    return row


def _record(conn, agent, intent, payload, value, tier, status, reason, rationale, evidence, period, key=None):
    key = key or idempotency_key(agent, intent, payload, period + ":" + status + reason[:12])
    conn.execute(
        "INSERT OR IGNORE INTO ledger (ts, agent, intent, payload, value_eur, tier, status, reason, rationale,"
        " evidence, idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (db.now(), agent, intent, db.dumps(payload), value, tier, status, reason, rationale,
         db.dumps(evidence), key),
    )
    return db.one(conn, "SELECT * FROM ledger WHERE idempotency_key=?", (key,))


def reverse(conn, ledger_id, note="manual reversal"):
    """R11: every autonomous decision is reversible by a reverse entry, never a delete."""
    orig = db.one(conn, "SELECT * FROM ledger WHERE id=?", (ledger_id,))
    if not orig or orig["status"] != "executed":
        raise Rejected("only executed entries can be reversed")
    conn.execute(
        "INSERT INTO ledger (ts, agent, intent, payload, value_eur, tier, status, reason, idempotency_key)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (db.now(), "human", "reverse:" + orig["intent"], orig["payload"], -orig["value_eur"],
         "T1_auto", "executed", note, "rev_%s" % ledger_id),
    )
    conn.execute("UPDATE ledger SET reversed_by=(SELECT MAX(id) FROM ledger) WHERE id=?", (ledger_id,))
