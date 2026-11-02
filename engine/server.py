#!/usr/bin/env python3
"""Operator console: HTTP API plus the single-page UI.

Standard library only. One thread per request, one SQLite connection per
request, a shared in-memory event log that the UI polls so a run can be
watched as it happens.

  python3 server.py            -> http://127.0.0.1:8787
  python3 server.py 9000       -> another port
"""
import json
import math
import os
import sqlite3
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import env as _env  # noqa: E402
_env.load()
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import db, bus, gateway, harness, model
from db import seed as seeder
from agents import reorder, marketing, verdict, analyst, executor       # noqa: F401 registers handlers

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
PRODUCTS = ["p_towel", "p_lamp", "p_mug", "p_candle"]
TOWELS = ["v_black", "v_white", "v_grey"]

LOG = []                 # [{"seq","ts","channel","level","text","data"}]
LOCK = threading.Lock()
RESULTS = {"reorder": [], "marketing": {}, "weekly": {}, "verdict": [], "asks": {},
           "model": None, "bench": None, "classify": None}
BUSY = {"running": False, "what": None}


def log(channel, text, level="info", data=None):
    with LOCK:
        LOG.append({"seq": len(LOG) + 1, "ts": time.strftime("%H:%M:%S"), "channel": channel,
                    "level": level, "text": text, "data": data})
        if len(LOG) > 4000:
            del LOG[:1000]


# ----------------------------------------------------------------- cycles ----

def ensure_db():
    """Seed when there is no data, not merely when there is no file.

    A database that exists but is empty - a half-finished run, a file created
    by another process - would otherwise start a console with nothing in it and
    fail on the first agent.
    """
    conn = db.init(reset=False)
    if db.scalar(conn, "SELECT COUNT(*) FROM product") == 0:
        log("system", "empty database: seeding 90 days of history")
        counts = seeder.run(conn)
        log("system", "seeded " + json.dumps(counts))
    return conn


def run_cycle(what):
    """Run one or all agent cycles, narrating each step into the event log."""
    if BUSY["running"]:
        return {"error": "a cycle is already running"}
    BUSY.update({"running": True, "what": what})
    conn = db.connect()
    try:
        prov = model.status()
        anomaly_watermark = db.scalar(conn, "SELECT MAX(id) FROM anomaly", (), 0) or 0
        log("system", "cycle '%s' starting - model: %s" % (what, prov["label"]), data=prov)
        if what in ("all", "reorder"):
            # the seeded towel case, plus whatever the connected shop is actually selling
            live = [r["id"] for r in db.rows(conn, """
                SELECT v.id FROM variant v
                WHERE v.id LIKE 'medv_%' OR v.id LIKE 'shv_%'
                ORDER BY (SELECT COALESCE(SUM(units), 0) FROM sales_fact WHERE variant_id = v.id) DESC
                LIMIT 4""")]
            if live:
                log("system", "reorder will also run on %d variants from the live shop" % len(live))
            bus.publish(conn, "reorder.due",
                        {"variants": TOWELS + live, "trigger": "console",
                         "period": time.strftime("%Y-W%W-%d%H")}, "v_black")
        if what in ("all", "marketing"):
            bus.publish(conn, "marketing.daily", {"product_id": "p_towel",
                                                  "period": time.strftime("%Y-%m-%d")}, "p_towel")
            bus.publish(conn, "marketing.weekly", {"product_id": "p_towel"}, "p_towel")
        if what in ("all", "verdict"):
            bus.publish(conn, "verdict.weekly", {"products": PRODUCTS,
                                                 "period": time.strftime("%Y-W%W")}, "portfolio")

        reclaimed = bus.reclaim_expired(conn)
        if reclaimed:
            log("bus", "reclaimed %s job(s) abandoned by a previous worker" % reclaimed, "warn")
        depth = bus.depth(conn)
        log("bus", "queued: %s ready" % depth["ready"], data=depth)

        # drain the queue one job at a time so the UI can follow it
        guard = 0
        while guard < 500:
            guard += 1
            before = bus.depth(conn)
            claimable = db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='ready'"
                                        " AND run_after<=?", (db.now(),))
            if not claimable:
                if before["ready"]:
                    log("bus", "%s job(s) are waiting on a retry timer; they will run on the next "
                               "cycle" % before["ready"], "warn")
                break
            done, dead = bus.run_worker(conn, worker_id="console", max_jobs=1, verbose=False)
            after = bus.depth(conn)
            log("bus", "job handled - %s ready, %s done, %s dead"
                % (after["ready"], after["done"], after["dead"]), data=after)
            # progress is measured on the queue itself, not on a return value
            if after["done"] + after["dead"] == before["done"] + before["dead"]:
                # a job failed and went back on the queue with a backoff; keep
                # going with whatever else is ready rather than stopping here
                still = db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='ready'"
                                        " AND run_after<=?", (db.now(),))
                if not still:
                    log("bus", "%s job(s) left, all waiting on retry timers" % after["ready"], "warn")
                    break

        if what in ("all", "reorder") and reorder.handle.last:
            RESULTS["reorder"] = reorder.handle.last
            for p in reorder.handle.last:
                if p.get("blocked"):
                    log("reorder", "%s blocked: %s" % (p["variant_id"], p["blocked"]), "warn")
                    continue
                d, lg = p["decision"], p["ledger"]
                log("reorder", "%s -> order %s units (%s weeks cover, EUR %s) | %s / %s"
                    % (p["variant_id"], d["qty"], d["cover_after_weeks"], d["capital_eur"],
                       lg["tier"], lg["status"]),
                    "ok" if lg["status"] == "executed" else "warn",
                    {"ledger_id": lg["id"], "reason": lg["reason"]})
        if what in ("all", "marketing") and marketing.handle.last:
            RESULTS["marketing"] = marketing.handle.last
            RESULTS["weekly"] = marketing.weekly.last
            for c in marketing.handle.last["cells"]:
                log("marketing", "%s -> %s (%s)" % (c["cell"], c["action"], c["reason"]),
                    "ok" if c["action"] in ("scale", "protect") else
                    ("warn" if c["action"].startswith("pause") else "info"))
        if what in ("all", "verdict") and verdict.handle.last:
            RESULTS["verdict"] = verdict.handle.last
            for v in verdict.handle.last:
                log("verdict", "%s -> %s (%.0f%% confidence) | %s"
                    % (v["product_id"], v["diagnosis"]["verdict"], v["diagnosis"]["confidence"] * 100,
                       v["ledger"]["status"]),
                    "bad" if v["diagnosis"]["verdict"] == "KILL" else "ok")

        for a in db.rows(conn, "SELECT * FROM anomaly WHERE resolved=0 AND id>? ORDER BY id",
                         (anomaly_watermark,)):
            log("anomaly", "[%s] %s: %s" % (a["severity"], a["kind"], a["note"]), "warn")
        log("system", "cycle '%s' complete" % what)
        return {"ok": True}
    except Exception as exc:                                        # noqa: BLE001
        log("system", "cycle failed: %r" % exc, "bad")
        traceback.print_exc()
        return {"error": repr(exc)}
    finally:
        BUSY.update({"running": False, "what": None})
        conn.close()


def run_model(target="orders_7d"):
    """Train the marketing models and record the whole workflow for the console."""
    if BUSY["running"]:
        return {"error": "a cycle is already running"}
    BUSY.update({"running": True, "what": "model"})
    conn = db.connect()
    try:
        from engines import ml, allocator
        from agents import tools
        if not ml.available():
            log("model", "scikit-learn is not installed; the allocator stays on its bands", "warn")
            return {"error": "sklearn missing"}
        margin = tools.margin_table(conn, "p_towel")
        target_cpa = allocator.target_cpa(margin["cm_per_unit"], 1.2)
        log("model", "training on the feature panel, target %s" % target)
        out = ml.run_pipeline(conn, target_cpa=target_cpa, target=target,
                              verbose_sink=lambda m: log("model", m))
        if out.get("error"):
            log("model", out["error"], "warn")
            return out
        best = out["leaderboard"][0]
        log("model", "best out of sample: %s on the %s panel, %s target, R2 %.3f, AUC %s"
            % (best["family"], best["panel"], best["transform"], best["out_sample"]["r2"],
               best.get("auc")), "ok")
        log("model", "promotion: %s - %s" % ("promoted" if out["promoted"] else "held back",
                                             out["reason"]),
            "ok" if out["promoted"] else "warn")
        RESULTS["model"] = out
        return out
    except Exception as exc:                                    # noqa: BLE001
        log("model", "training failed: %r" % exc, "bad")
        traceback.print_exc()
        return {"error": repr(exc)}
    finally:
        BUSY.update({"running": False, "what": None})
        conn.close()


def run_classify():
    """Label the real review text with a language model."""
    BUSY.update({"running": True, "what": "classify-reviews"})
    conn = db.connect()
    try:
        from engines import foundation
        log("model", "reading the review text customers left, with distilbert")
        out = foundation.classify_reviews(conn)
        RESULTS["classify"] = out
        if out.get("error"):
            log("model", out["error"], "bad")
        else:
            log("model", "classified %s reviews, %s negative"
                % (out.get("classified"), out.get("negative")), "ok")
    finally:
        BUSY.update({"running": False, "what": None})
        conn.close()


def run_forecast_bench():
    """Chronos against the statistics, scored on held-out demand."""
    BUSY.update({"running": True, "what": "forecast-bench"})
    conn = db.connect()
    try:
        from engines import foundation
        if not foundation.available():
            log("model", "Chronos is not installed (.venv-ml missing)", "warn")
            RESULTS["bench"] = {"error": "not installed"}
            return
        variants = [r["id"] for r in db.rows(conn, """
            SELECT v.id FROM variant v
            ORDER BY (SELECT COALESCE(SUM(units),0) FROM sales_fact WHERE variant_id=v.id) DESC
            LIMIT 8""")]
        log("model", "holding out 14 days and asking Chronos and the statistics to predict it")
        out = foundation.benchmark(conn, variants, horizon=14, say=lambda m: log("model", m))
        RESULTS["bench"] = out
        if out.get("error"):
            log("model", out["error"], "bad")
            return
        log("model", "%s wins by %.0f%%; Chronos %s"
            % (out["winner"], abs(out["margin_pct"]),
               "promoted" if out["winner"] == "chronos" else "not promoted"),
            "ok" if out["winner"] == "chronos" else "warn")
    except Exception as exc:                                    # noqa: BLE001
        log("model", "benchmark failed: %r" % exc, "bad")
        RESULTS["bench"] = {"error": repr(exc)[:200]}
    finally:
        BUSY.update({"running": False, "what": None})
        conn.close()


def run_ask(ticket, question):
    conn = db.connect()
    RESULTS["asks"][ticket] = {"status": "running", "question": question, "events": [],
                               "answer": None, "trace": [], "totals": {}}
    log("agent", "question: " + question)

    def on_event(kind, payload):
        entry = {"kind": kind, "payload": payload, "ts": time.strftime("%H:%M:%S")}
        RESULTS["asks"][ticket]["events"].append(entry)
        if kind == "tool_call":
            log("agent", "tool %s(%s) -> evidence %s"
                % (payload["tool"], json.dumps(payload.get("args") or {}), payload.get("evidence_id")),
                "ok" if payload.get("ok") else "bad", payload.get("result"))
        elif kind == "thinking":
            log("agent", "step %s" % payload["step"])
        elif kind == "tool_denied":
            log("agent", "tool refused: " + payload["reason"], "warn")
        elif kind == "answer":
            log("agent", "answer ready")

    try:
        out = analyst.ask(conn, question, max_steps=7, on_event=on_event)
        RESULTS["asks"][ticket].update({"status": "done", "answer": out["answer"],
                                        "trace": out["trace"], "totals": out.get("totals", {}),
                                        "uncited": out.get("uncited", []),
                                        "provider": out.get("provider", {})})
        if out.get("uncited"):
            log("agent", "figures with no evidence behind them: %s" % ", ".join(out["uncited"]), "warn")
    except Exception as exc:                                        # noqa: BLE001
        msg = str(exc) or repr(exc)
        RESULTS["asks"][ticket].update(
            {"status": "error",
             "answer": "The model could not be reached, so there is no answer to give.\n\n" + msg +
                       "\n\nThe engines are unaffected: every decision in the ledger was produced "
                       "deterministically and is still correct."})
        log("agent", "ask failed: " + msg[:200], "bad")
    finally:
        conn.close()


# ------------------------------------------------------------------ state ----

def _source_of(module_name, qualname):
    """The actual source of the function that produced a step.

    Showing the code beside the number is the difference between claiming a
    decision was computed and demonstrating it.
    """
    import importlib
    import inspect
    if not module_name or module_name.startswith(("os", "sys", "builtins")):
        return {"error": "not a project module"}
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:                                    # noqa: BLE001
        return {"error": "cannot import %s: %r" % (module_name, exc)}
    target = mod
    for part in (qualname or "").split("."):
        if not part:
            continue
        target = getattr(target, part, None)
        if target is None:
            return {"error": "%s not found in %s" % (qualname, module_name)}
    try:
        src = inspect.getsource(target)
        line = inspect.getsourcelines(target)[1]
    except (OSError, TypeError) as exc:
        return {"error": "no source available: %r" % exc}
    path = getattr(inspect.getmodule(target), "__file__", "") or ""
    if len(src) > 7000:
        src = src[:7000] + "\n    # ... truncated"
    return {"module": module_name, "name": qualname, "line": line,
            "file": os.path.relpath(path, os.path.dirname(os.path.abspath(__file__))),
            "source": src}


def _band(cpa, target, policy):
    """The same bands the allocator uses, named for a human."""
    if not cpa or not target:
        return "unknown"
    pct = cpa / target * 100
    if pct <= 80:
        return "scale"
    if pct <= 100:
        return "hold"
    if pct <= policy["pause_above_target_multiple"] * 100:
        return "reduce"
    return "pause"


def _norm_ledger(row):
    """Ledger rows embedded in agent results carry JSON as text; the UI wants objects."""
    if not isinstance(row, dict):
        return row
    out = dict(row)
    for key in ("payload", "evidence"):
        val = out.get(key)
        if isinstance(val, str):
            try:
                out[key] = json.loads(val or ("[]" if key == "evidence" else "{}"))
            except ValueError:
                out[key] = [] if key == "evidence" else {}
    return out


def _norm_results():
    reorder_out = []
    for item in RESULTS["reorder"]:
        row = dict(item)
        if "ledger" in row:
            row["ledger"] = _norm_ledger(row["ledger"])
        reorder_out.append(row)
    verdict_out = []
    for item in RESULTS["verdict"]:
        row = dict(item)
        if "ledger" in row:
            row["ledger"] = _norm_ledger(row["ledger"])
        verdict_out.append(row)
    mkt = dict(RESULTS["marketing"]) if RESULTS["marketing"] else {}
    if mkt.get("cells"):
        mkt["cells"] = [dict(c, ledger=_norm_ledger(c["ledger"]) if c.get("ledger") else None)
                        for c in mkt["cells"]]
    return reorder_out, mkt, verdict_out


def _plain_headline(agent, trace, names=None):
    """One sentence a non-technical person can repeat back.

    Built from the stored trace rather than from memory, so the page says the
    same thing whichever process ran the agents.
    """
    if not trace:
        return "has not run yet"

    names = names or {}
    nice = lambda v: names.get(v, v)                           # noqa: E731

    if agent == "reorder":
        variant, why, orders, declined = None, {}, [], []
        for st in trace:
            args = (st.get("data") or {}).get("args") or {}
            if args.get("variant_id"):
                variant = args["variant_id"]
            if st["kind"] == "engine" and st["title"] == "reconstruct demand" and variant:
                why[variant] = st
            if st["kind"] == "gateway" and st["title"] == "propose_reorder":
                payload = (st.get("data") or {}).get("payload") or {}
                item = {"variant": payload.get("variant_id"), "qty": payload.get("qty", 0),
                        "why": why.get(payload.get("variant_id"), {})}
                (orders if item["qty"] else declined).append(item)
        if not orders and not declined:
            return "ran, but proposed nothing"
        if not orders:
            return ("looked at %d products and bought none: either they have enough stock or "
                    "an order is already on its way" % len(declined))
        def hidden(item):
            d = (item["why"].get("data") or {})
            return d.get("substitution_removed", 0) + (0 if "unbuyable" not in
                                                       (item["why"].get("detail") or "") else 1)
        top = max(orders, key=lambda i: i["qty"])
        for item in orders:
            detail = item["why"].get("detail") or ""
            if "buyable days ->" in detail:
                shipped, rest = detail.split(" units shipped over ", 1)
                days = rest.split(" buyable days")[0]
                try:
                    if float(days) < 60:
                        top = item
                        break
                except ValueError:
                    pass
        line = "ordered %s units of %s" % (top["qty"], nice(top["variant"]))
        if top["why"].get("detail"):
            line += " — " + top["why"]["detail"]
        if declined:
            line += "; bought none of %s" % ", ".join(nice(d["variant"]) for d in declined[:2])
        return line

    if agent == "marketing_allocator":
        decisions = [st for st in trace if st["kind"] == "rule" and st["title"].startswith("decide ")]
        if not decisions:
            return "reviewed the ads and changed nothing"
        scaled = [d for d in decisions if (d.get("data") or {}).get("action") == "scale"]
        paused = [d for d in decisions if str((d.get("data") or {}).get("action", "")).startswith("pause")]
        waiting = [d for d in decisions if "not yet known" in (d.get("detail") or "")]
        bits = []
        if scaled:
            bits.append("gave more money to %d ad%s beating the target"
                        % (len(scaled), "" if len(scaled) == 1 else "s"))
        if paused:
            p = paused[0]
            bits.append("switched off %s — %s" % (p["title"].replace("decide ", "").replace("_", " "),
                                                  (p.get("detail") or "")[:70]))
        if waiting:
            bits.append("left %d alone for want of traffic to judge them" % len(waiting))
        return "; ".join(bits) or "reviewed %d ads and held them all" % len(decisions)

    if agent == "product_verdict":
        plain = {"SCALE": "working, give them more", "KILL": "stop selling",
                 "FIX_SITE": "the shop is losing buyers, not the product",
                 "REPRICE": "the price is wrong", "CONTINUE_TEST": "not enough evidence yet",
                 "NEW_CREATIVE": "nobody is clicking, so it has not been judged yet"}
        by = {}
        for st in trace:
            if st["kind"] == "gateway" and st["title"] == "publish_verdict":
                payload = (st.get("data") or {}).get("payload") or {}
                by.setdefault(payload.get("verdict"), []).append(
                    str(payload.get("product_id", "")).replace("p_", ""))
        if not by:
            return "judged nothing this cycle"
        return "; ".join("%s: %s" % (", ".join(v), plain.get(k, k)) for k, v in by.items())

    return ""


def build_boxes():
    """The live state of each layer, in the words a person would use."""
    conn = db.connect()
    try:
        from adapters import medusa as med, shopify as shp
        shop = None
        for name, mod, prefix in (("Medusa", med, "medv_"), ("Shopify", shp, "shv_")):
            variants = db.scalar(conn, "SELECT COUNT(*) FROM ext_map WHERE source=?", (name.lower(),))
            if not variants:
                continue
            oos = db.scalar(conn, """
                SELECT COUNT(*) FROM (SELECT variant_id, MAX(ts) t FROM inventory_snapshot
                WHERE variant_id LIKE ? GROUP BY variant_id) x
                JOIN inventory_snapshot s ON s.variant_id=x.variant_id AND s.ts=x.t
                WHERE s.buyable=0""", (prefix + "%",))
            shop = {"name": name, "connected": True, "variants": variants,
                    "out_of_stock": oos,
                    "orders": db.scalar(conn, "SELECT COUNT(*) FROM sales_fact WHERE channel=?",
                                        (name.lower(),)),
                    "last_sync": db.scalar(conn, "SELECT MAX(ts) FROM inventory_snapshot"
                                                 " WHERE variant_id LIKE ?", (prefix + "%",), None)}
            break
        if shop is None:
            shop = {"name": "none connected", "connected": False,
                    "variants": db.scalar(conn, "SELECT COUNT(*) FROM variant"),
                    "out_of_stock": 0, "orders": 0, "last_sync": None}

        runs = {}
        for r in db.rows(conn, "SELECT * FROM agent_run WHERE trace IS NOT NULL"
                               " ORDER BY started_at DESC LIMIT 20"):
            trace = json.loads(r["trace"] or "[]")
            prev = runs.get(r["agent"])
            if prev and len(prev["trace"]) >= len(trace):
                continue
            kinds = {}
            for st in trace:
                kinds[st["kind"]] = kinds.get(st["kind"], 0) + 1
            runs[r["agent"]] = {"trace": trace, "kinds": kinds, "mode": r["mode"],
                                "started_at": r["started_at"], "run_id": r["id"],
                                "judgments": [st for st in trace if st["kind"] == "judgment"]}

        names = {}
        for row in db.rows(conn, "SELECT v.id, v.sku, v.colour, p.name FROM variant v"
                                 " JOIN product p ON p.id=v.product_id"):
            label = row["sku"] or row["id"]
            if row["id"].startswith("v_"):
                label = "the %s %s" % (row["colour"], row["name"].split()[-1].lower())
            names[row["id"]] = label

        agents = []
        for key, title, job, engine in (
                ("marketing_allocator", "Marketing agent", "decides where the ad money goes",
                 "trained model + rules"),
                ("reorder", "Reorder agent", "decides what to buy and how much",
                 "demand reconstruction + newsvendor maths"),
                ("product_verdict", "Verdict agent", "decides keep, fix, or kill",
                 "funnel decomposition + rules")):
            r = runs.get(key) or {}
            agents.append({
                "key": key, "title": title, "job": job, "engine": engine,
                "headline": _plain_headline(key, r.get("trace"), names),
                "steps": len(r.get("trace") or []), "kinds": r.get("kinds") or {},
                "judgments": len(r.get("judgments") or []),
                "judgment_detail": [{"q": j["title"], "a": j["detail"],
                                     "source": (j.get("data") or {}).get("source")}
                                    for j in (r.get("judgments") or [])],
                "mode": r.get("mode"), "last_run": r.get("started_at")})

        tiers = {}
        for row in db.rows(conn, "SELECT tier, status, COUNT(*) n FROM ledger GROUP BY tier, status"):
            tiers.setdefault(row["status"], 0)
            tiers[row["status"]] += row["n"]

        mdl = db.one(conn, "SELECT family, out_sample, trained_at FROM model_registry"
                           " WHERE promoted=1 ORDER BY id DESC LIMIT 1")
        if mdl:
            mdl["out_sample"] = json.loads(mdl["out_sample"] or "{}")

        return {
            "shop": shop,
            "memory": {
                "snapshots": db.scalar(conn, "SELECT COUNT(*) FROM inventory_snapshot"),
                "sales": db.scalar(conn, "SELECT COUNT(*) FROM sales_fact"),
                "ad_days": db.scalar(conn, "SELECT COUNT(*) FROM ad_feature"),
                "evidence": db.scalar(conn, "SELECT COUNT(*) FROM evidence")},
            "bus": bus.depth(conn),
            "agents": agents,
            "model": mdl,
            "gate": {"executed": tiers.get("executed", 0),
                     "waiting": tiers.get("pending_human", 0) + tiers.get("pending_checker", 0),
                     "refused": tiers.get("rejected", 0),
                     "capital": round(db.scalar(conn, "SELECT SUM(value_eur) FROM ledger"
                                                      " WHERE intent='propose_reorder'"
                                                      " AND status='executed'") or 0, 2)},
            "ledger": {"entries": db.scalar(conn, "SELECT COUNT(*) FROM ledger"),
                       "anomalies": db.scalar(conn, "SELECT COUNT(*) FROM anomaly")},
            "bench": RESULTS["bench"],
            "substitutes": db.scalar(conn, "SELECT COUNT(*) FROM substitute_pair"
                                           " WHERE source='embedding'") // 2,
            "busy": BUSY,
            "provider": model.status(),
        }
    finally:
        conn.close()


def build_state():
    conn = db.connect()
    try:
        prov = model.status()
        ledger = db.rows(conn, "SELECT * FROM ledger ORDER BY id DESC LIMIT 60")
        for r in ledger:
            r["payload"] = json.loads(r["payload"] or "{}")
            r["evidence"] = json.loads(r["evidence"] or "[]")
        pending = [r for r in ledger if r["status"] in ("pending_human", "pending_checker")]
        committed = db.scalar(conn, "SELECT SUM(value_eur) FROM ledger WHERE intent='propose_reorder'"
                                    " AND status='executed'") or 0
        runs = db.rows(conn, "SELECT * FROM agent_run ORDER BY started_at DESC LIMIT 12")
        from engines.funnel import BENCHMARK
        norm_reorder, norm_marketing, norm_verdict = _norm_results()
        return {
            "provider": prov,
            "benchmark": BENCHMARK,
            "busy": BUSY,
            "queue": bus.depth(conn),
            "evidence_count": db.scalar(conn, "SELECT COUNT(*) FROM evidence"),
            "anomalies": db.rows(conn, "SELECT * FROM anomaly ORDER BY id DESC LIMIT 12"),
            "ledger": ledger,
            "pending": pending,
            "runs": runs,
            "cost_total": round(db.scalar(conn, "SELECT SUM(cost_eur) FROM agent_run") or 0.0, 4),
            "capital_committed": round(committed, 2),
            "model": RESULTS["model"],
            "model_registry": db.rows(conn, "SELECT id, trained_at, target, family, promoted,"
                                            " promotion_reason, in_sample, out_sample, n_train,"
                                            " n_test FROM model_registry ORDER BY id DESC LIMIT 12"),
            "reorder": norm_reorder,
            "marketing": norm_marketing,
            "weekly": RESULTS["weekly"],
            "verdict": norm_verdict,
            "products": db.rows(conn, "SELECT * FROM product"),
        }
    finally:
        conn.close()


# ----------------------------------------------------------------- server ----

class Handler(BaseHTTPRequestHandler):
    server_version = "HaldenConsole/1.0"

    def log_message(self, fmt, *args):      # quieter console
        pass

    # -- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
        ext = os.path.splitext(path)[1]
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("content-type", types.get(ext, "application/octet-stream"))
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def resilient(self, fn):
        """Survive the database being rebuilt underneath a running console.

        `run.py demo` drops and reseeds, and a console open in another window
        would otherwise 500 on every request until it was restarted.
        """
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            log("system", "database was rebuilt underneath the console: re-initialising", "warn")
            ensure_db()
            return fn()

    def body_json(self):
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except ValueError:
            return {}

    # -- routes
    def do_GET(self):
        path = self.path.split("?")[0]
        query = {}
        if "?" in self.path:
            for part in self.path.split("?", 1)[1].split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    query[k] = v

        if path in ("/explain", "/explain.html"):
            return self.send_file(os.path.join(UI, "explain.html"))
        if path in ("/", "/demo", "/demo.html"):
            if self.headers.get("Host", "").split(":", 1)[0] == "127.0.0.1":
                self.send_response(302)
                self.send_header("Location", "http://localhost:%s%s" % (self.server.server_port, self.path))
                self.end_headers()
                return
            return self.send_file(os.path.join(UI, "demo.html"))
        if path in ("/map", "/live", "/live.html"):
            return self.send_file(os.path.join(UI, "live.html"))
        if path in ("/boxes", "/boxes.html"):
            return self.send_file(os.path.join(UI, "boxes.html"))
        if path in ("/flow", "/flow.html"):
            return self.send_file(os.path.join(UI, "flow.html"))
        if path in ("/console", "/index.html"):
            return self.send_file(os.path.join(UI, "index.html"))
        if path.startswith("/ui/"):
            safe = os.path.normpath(path[4:]).lstrip("/")
            return self.send_file(os.path.join(UI, safe))
        if path == "/api/catalogue-text":
            conn = db.connect()
            try:
                rows = db.rows(conn, """
                    SELECT v.id, v.sku, v.colour, p.name AS product, p.id AS product_id
                    FROM variant v JOIN product p ON p.id = v.product_id
                    ORDER BY v.id""")
                for r in rows:
                    r["text"] = ("%s %s" % (r["product"], r["colour"] or "")).strip()
                return self.send_json({"variants": rows})
            finally:
                conn.close()

        if path == "/api/demo-data":
            conn = db.connect()
            try:
                from engines import explanation
                out = explanation.snapshot(conn, include_live=True)
                out["shop_counts"] = {
                    "products": db.scalar(conn, "SELECT COUNT(*) FROM product WHERE id LIKE 'med_%'"),
                    "variants": db.scalar(conn, "SELECT COUNT(*) FROM ext_map WHERE source='medusa'"),
                    "order_lines": db.scalar(conn, "SELECT COUNT(*) FROM sales_fact WHERE variant_id LIKE 'medv_%'"),
                    "units": db.scalar(conn, "SELECT SUM(units) FROM sales_fact WHERE variant_id LIKE 'medv_%'")}
                out["traces"] = []
                seen = set()
                for row in db.rows(conn, "SELECT agent,started_at,mode,trace FROM agent_run WHERE trace IS NOT NULL"
                                         " AND trace<>'[]' ORDER BY started_at DESC,rowid DESC LIMIT 30"):
                    if row["agent"] in seen:
                        continue
                    seen.add(row["agent"])
                    row["trace"] = json.loads(row["trace"] or "[]")
                    out["traces"].append(row)
                return self.send_json(out)
            finally:
                conn.close()

        if path == "/api/explain":
            conn = db.connect()
            try:
                from engines import explanation
                return self.send_json(explanation.snapshot(conn))
            finally:
                conn.close()

        if path == "/api/budget":
            conn = db.connect()
            try:
                from engines import budget as bg
                amount = float(query.get("amount", 3000))
                if not math.isfinite(amount) or not 0 < amount <= 1000000:
                    raise ValueError("budget must be between 0 and 1000000")
                return self.send_json(bg.allocate(conn, amount))
            except (TypeError, ValueError) as exc:
                return self.send_json({"error": str(exc)}, 400)
            finally:
                conn.close()

        if path == "/api/live-verdict":
            conn = db.connect()
            try:
                from engines import live_verdict
                return self.send_json({"verdicts": live_verdict.judge_all(conn)})
            finally:
                conn.close()

        if path == "/api/reviews":
            conn = db.connect()
            try:
                rows = db.rows(conn, "SELECT product, text, day FROM order_review"
                                     " ORDER BY day DESC LIMIT 120")
                return self.send_json({"reviews": rows, "count": len(rows)})
            finally:
                conn.close()

        if path == "/api/boxes":
            return self.send_json(self.resilient(build_boxes))

        if path == "/api/shops":
            # which storefront is feeding the engine, and what else it could be
            from adapters import medusa as med, shopify as shp
            conn = db.connect()
            try:
                out = []
                for name, mod, prefix, label in (
                        ("medusa", med, "medv_", "Medusa (open source, self-hosted)"),
                        ("shopify", shp, "shv_", "Shopify (hosted)")):
                    variants = db.scalar(
                        conn, "SELECT COUNT(*) FROM ext_map WHERE source=?", (name,))
                    snaps = db.scalar(
                        conn, "SELECT COUNT(*) FROM inventory_snapshot WHERE variant_id LIKE ?",
                        (prefix + "%",))
                    out.append({"name": name, "label": label,
                                "configured": mod.configured(), "variants": variants,
                                "snapshots": snaps,
                                "adapter": "adapters/%s.py" % name,
                                "lines": sum(1 for _ in open(os.path.join(
                                    os.path.dirname(os.path.abspath(__file__)),
                                    "adapters", name + ".py")))})
                seeded = db.scalar(conn, "SELECT COUNT(*) FROM variant WHERE id LIKE 'v_%'")
                return self.send_json({"shops": out, "seeded_variants": seeded})
            finally:
                conn.close()

        if path == "/api/flow":
            conn = db.connect()
            try:
                runs = db.rows(conn, "SELECT id, agent, started_at, trigger, mode, outcome, trace"
                                     " FROM agent_run WHERE trace IS NOT NULL AND trace<>'[]'"
                                     " ORDER BY started_at DESC LIMIT 12")
                best = {}
                for r in runs:          # the fullest recent run per agent, not just the newest
                    r["trace"] = json.loads(r["trace"] or "[]")
                    prev = best.get(r["agent"])
                    if prev is None or len(r["trace"]) > len(prev["trace"]):
                        best[r["agent"]] = r
                out = list(best.values())
                out.sort(key=lambda r: ["reorder", "marketing_allocator", "product_verdict",
                                        "analyst"].index(r["agent"])
                         if r["agent"] in ("reorder", "marketing_allocator", "product_verdict",
                                           "analyst") else 9)
                return self.send_json({"runs": out})
            finally:
                conn.close()

        if path == "/api/code":
            module = query.get("module", "")
            name = urllib.parse.unquote(query.get("name", ""))
            return self.send_json(_source_of(module, name))

        if path == "/api/state":
            return self.send_json(self.resilient(build_state))
        if path == "/api/provider":
            return self.send_json(model.status())
        if path == "/api/log":
            after = int(query.get("after", 0))
            with LOCK:
                rows = [e for e in LOG if e["seq"] > after]
            return self.send_json({"events": rows, "busy": BUSY})
        if path.startswith("/api/evidence/"):
            eid = path.rsplit("/", 1)[-1]
            conn = db.connect()
            try:
                row = db.one(conn, "SELECT * FROM evidence WHERE id=?", (eid,))
            finally:
                conn.close()
            if not row:
                return self.send_json({"error": "no such evidence"}, 404)
            row["args"] = json.loads(row["args"] or "{}")
            row["result"] = json.loads(row["result"] or "null")
            return self.send_json(row)
        if path.startswith("/api/ask/"):
            ticket = path.rsplit("/", 1)[-1]
            return self.send_json(RESULTS["asks"].get(ticket, {"status": "unknown"}))
        return self.send_json({"error": "no such route"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        data = self.body_json()

        if path == "/api/demo-sync":
            conn = db.connect()
            try:
                from adapters import medusa
                if not medusa.configured():
                    return self.send_json({"error": "Medusa adapter is not configured"}, 400)
                before = db.scalar(conn, "SELECT COUNT(*) FROM sales_fact WHERE variant_id LIKE 'medv_%'")
                imported = medusa.sync(conn)
                after = db.scalar(conn, "SELECT COUNT(*) FROM sales_fact WHERE variant_id LIKE 'medv_%'")
                return self.send_json({"new_order_lines": after - before, "orders": after, "imported": imported})
            except Exception as exc:
                return self.send_json({"error": "Shop sync failed: %s" % str(exc)[:160]}, 502)
            finally:
                conn.close()

        if path == "/api/explain-quantity":
            conn = db.connect()
            try:
                from engines import explanation
                return self.send_json(explanation.quantity_preview(conn, data))
            except (KeyError, TypeError, ValueError) as exc:
                return self.send_json({"error": str(exc)}, 400)
            finally:
                conn.close()

        if path == "/api/run":
            what = data.get("what", "all")
            if BUSY["running"]:
                return self.send_json({"error": "already running"}, 409)
            threading.Thread(target=run_cycle, args=(what,), daemon=True).start()
            return self.send_json({"started": what})

        if path == "/api/explain":
            # the full rule ladder for one ad cell, as the agent evaluated it
            conn = db.connect()
            try:
                from engines import allocator
                from agents import tools
                product_id = data.get("product_id", "p_towel")
                cell_id = data.get("cell_id")
                cfg = harness.load_config("marketing_allocator")
                policy = dict(harness.load_config("policy"))
                policy.update(cfg["policy"])
                cells = allocator.cell_stats(conn, product_id, 7)
                cell = next((c for c in cells if c["cell_id"] == cell_id), None)
                if not cell:
                    return self.send_json({"error": "no such cell"}, 404)
                margin = tools.margin_table(conn, product_id)
                target = allocator.target_cpa(margin["cm_per_unit"], cfg["policy"]["payback_factor"])
                cover = tools.stock_cover(conn, product_id)
                mv = allocator.model_view(conn, product_id, [cell], target).get(cell_id, {})
                out = allocator.explain_cell(conn, cell, target, policy,
                                             cover["hero_cover_days"], False,
                                             mv.get("expected_cpa"))
                out["cell"] = cell
                return self.send_json(out)
            finally:
                conn.close()

        if path == "/api/whatif":
            conn = db.connect()
            try:
                from engines import ml, allocator
                from agents import tools
                if not ml.available():
                    return self.send_json({"error": "scikit-learn not installed"}, 400)
                cell_id = data.get("cell_id")
                row = db.one(conn, "SELECT features FROM ad_feature WHERE cell_id=?"
                                   " ORDER BY day DESC LIMIT 1", (cell_id,))
                if not row:
                    return self.send_json({"error": "no features for that cell"}, 404)
                feats = json.loads(row["features"])
                base = {k + "_7d": v for k, v in feats.items() if isinstance(v, (int, float))}
                base.update(feats)
                out = ml.what_if(conn, base, data.get("overrides") or {})
                if out.get("error"):
                    return self.send_json(out, 400)
                # what the prediction means for the decision
                margin = tools.margin_table(conn, data.get("product_id", "p_towel"))
                cfg = harness.load_config("marketing_allocator")
                target = allocator.target_cpa(margin["cm_per_unit"], cfg["policy"]["payback_factor"])
                spend_7d = float(data.get("weekly_spend") or (feats.get("spend", 0) * 7))
                for key, label in (("before", "cpa_before"), ("after", "cpa_after")):
                    orders = max(0.01, out[key])
                    out[label] = round(spend_7d / orders, 2)
                out["target_cpa"] = target
                out["action_before"] = _band(out["cpa_before"], target, cfg["policy"])
                out["action_after"] = _band(out["cpa_after"], target, cfg["policy"])
                out["weekly_spend"] = round(spend_7d, 2)
                return self.send_json(out)
            finally:
                conn.close()

        if path == "/api/classify-reviews":
            if BUSY["running"]:
                return self.send_json({"error": "already running"}, 409)
            threading.Thread(target=run_classify, daemon=True).start()
            return self.send_json({"started": "classify"})

        if path == "/api/forecast-bench":
            if BUSY["running"]:
                return self.send_json({"error": "already running"}, 409)
            threading.Thread(target=run_forecast_bench, daemon=True).start()
            return self.send_json({"started": "forecast-bench"})

        if path == "/api/model":
            if BUSY["running"]:
                return self.send_json({"error": "already running"}, 409)
            threading.Thread(target=run_model, daemon=True).start()
            return self.send_json({"started": "model"})

        if path == "/api/ask":
            question = (data.get("question") or "").strip()
            if not question:
                return self.send_json({"error": "empty question"}, 400)
            ticket = "ask_%d" % int(time.time() * 1000)
            threading.Thread(target=run_ask, args=(ticket, question), daemon=True).start()
            return self.send_json({"ticket": ticket})

        if path == "/api/substitutes":
            # pairs learned in the browser by a sentence-embedding model
            pairs = data.get("pairs") or []
            conn = db.connect()
            try:
                conn.execute("DELETE FROM substitute_pair WHERE source='embedding'")
                for p2 in pairs:
                    a, b, score = p2.get("a"), p2.get("b"), float(p2.get("score") or 0)
                    if not a or not b or a == b:
                        continue
                    for x, y in ((a, b), (b, a)):
                        conn.execute("INSERT OR REPLACE INTO substitute_pair VALUES (?,?,?,?,?)",
                                     (x, y, score, "embedding", db.now()))
                log("model", "substitution map learned from product text: %d pairs" % len(pairs), "ok")
                return self.send_json({"stored": len(pairs)})
            finally:
                conn.close()

        if path == "/api/approve":
            ledger_id = int(data.get("id"))
            decision = data.get("decision")
            conn = db.connect()
            try:
                row = db.one(conn, "SELECT * FROM ledger WHERE id=?", (ledger_id,))
                if not row:
                    return self.send_json({"error": "no such entry"}, 404)
                if decision == "approve":
                    conn.execute("UPDATE ledger SET status='executed', reason=? WHERE id=?",
                                 ("approved by operator in console", ledger_id))
                    bus.emit(conn, row["intent"].replace("propose_", "") + ".executed",
                             {"ledger_id": ledger_id, "payload": json.loads(row["payload"])})
                    bus.relay(conn)
                    log("approval", "#%s %s approved by operator" % (ledger_id, row["intent"]), "ok")
                else:
                    conn.execute("UPDATE ledger SET status='rejected', reason=? WHERE id=?",
                                 ("rejected by operator in console", ledger_id))
                    log("approval", "#%s %s rejected by operator" % (ledger_id, row["intent"]), "warn")
                return self.send_json({"ok": True})
            finally:
                conn.close()

        if path == "/api/reverse":
            conn = db.connect()
            try:
                gateway.reverse(conn, int(data.get("id")), "reversed by operator in console")
                log("approval", "#%s reversed (reverse entry written, nothing deleted)"
                    % data.get("id"), "warn")
                return self.send_json({"ok": True})
            except gateway.Rejected as rej:
                return self.send_json({"error": rej.reason}, 400)
            finally:
                conn.close()

        if path == "/api/reset":
            conn = db.init(reset=True)
            counts = seeder.run(conn)
            conn.close()
            with LOCK:
                del LOG[:]
            for k in ("reorder", "verdict"):
                RESULTS[k] = []
            RESULTS["marketing"], RESULTS["weekly"] = {}, {}
            log("system", "database reset and reseeded: " + json.dumps(counts))
            return self.send_json({"ok": True, "counts": counts})

        return self.send_json({"error": "no such route"}, 404)


def main(port=None):
    """port comes from the caller (run.py ui [port]) or from argv when run directly."""
    if port is None:
        args = [a for a in sys.argv[1:] if a.isdigit()]
        port = int(args[0]) if args else 8787
    conn = ensure_db()
    conn.close()
    prov = model.status()
    log("system", "console ready - model: %s" % prov["label"], data=prov)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        if getattr(exc, "errno", None) not in (48, 98):
            raise
        print("Port %d is already in use - most likely a console you started earlier.\n" % port)
        print("  Stop it:      pkill -f 'run.py ui'")
        print("  Or use another port:  python3 run.py ui %d" % (port + 1))
        for alt in range(port + 1, port + 12):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", alt), Handler)
                port = alt
                print("\n  Started on %d instead." % alt)
                break
            except OSError:
                continue
        else:
            return
    print("Halden control room on http://127.0.0.1:%d" % port)
    print("model provider: %s (%s)" % (prov["label"], prov["detail"]))
    print("Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
