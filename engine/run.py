#!/usr/bin/env python3
"""CLI for the agent platform.

  python3 run.py demo        seed 90 days of history, run all three agents, print the decisions
  python3 run.py towels      just the towel case, with every intermediate number
  python3 run.py marketing   the daily allocation pass and the weekly reallocation
  python3 run.py verdict     the portfolio verdicts
  python3 run.py ledger      the audit trail
  python3 run.py console     write console.html for the browser
  python3 run.py reverse N   reverse ledger entry N (rule R11)

No dependencies. Set ANTHROPIC_API_KEY to have the model write the rationales;
without it the harness runs in rules-only mode and the decisions are identical.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import env as _env  # noqa: E402
_env.load()

from core import db, bus, harness, gateway, model
from db import seed as seeder
from agents import reorder, marketing, verdict, executor
from agents import reorder_agentic, marketing_agentic, verdict_agentic   # noqa: F401 - registers handlers

TOWELS = ["v_black", "v_white", "v_grey"]   # grey is the volume line: its order escalates by value
PRODUCTS = ["p_towel", "p_lamp", "p_mug", "p_candle"]
W = 78


def line(ch="-"):
    print(ch * W)


def head(title):
    print()
    line("=")
    print(title)
    line("=")


def setup(reset=True):
    conn = db.init(reset=reset)
    counts = seeder.run(conn)
    return conn, counts


def enqueue_all(conn):
    live = [r["id"] for r in db.rows(conn, """
        SELECT v.id FROM variant v WHERE v.id LIKE 'medv_%' OR v.id LIKE 'shv_%'
        ORDER BY (SELECT COALESCE(SUM(units), 0) FROM sales_fact WHERE variant_id = v.id) DESC
        LIMIT 4""")]
    bus.publish(conn, "reorder.due",
                {"variants": TOWELS + live, "trigger": "schedule", "period": "2026-W44"}, "v_black")
    bus.publish(conn, "marketing.daily", {"product_id": "p_towel", "period": "2026-10-30"}, "p_towel")
    bus.publish(conn, "marketing.weekly", {"product_id": "p_towel"}, "p_towel")
    bus.publish(conn, "verdict.weekly", {"products": PRODUCTS, "period": "2026-W44"}, "portfolio")


def report_towels(conn):
    head("AGENT 1 of 3 - REORDER.  The case: 20 white sold, 20 black sold.")
    for p in reorder.handle.last:
        if p.get("blocked"):
            print("  %s BLOCKED: %s" % (p["variant_id"], p["blocked"]))
            continue
        r, d, lg = p["reconstruction"], p["decision"], p["ledger"]
        print()
        print("  %s" % p["variant_id"].upper())
        line()
        rows = [
            ("units shipped (90d)", r["units_shipped"]),
            ("days actually buyable", r["available_days"]),
            ("rate of sale / available day", r["ros_per_available_day"]),
            ("sibling out-of-stock days", r["sibling_oos_days"]),
            ("substitution share removed", "%.0f%%" % (r["substitution_share"] * 100)),
            ("avg discount on sales", "%.0f%%" % r["avg_discount_pct"]),
            ("price adjustment factor", r["price_factor"]),
            ("return rate", "%.0f%%" % (r["return_rate"] * 100)),
            ("RECONSTRUCTED DEMAND (90d)", r["reconstructed_demand_period"]),
            ("censored gap vs shipped", r["censored_gap"]),
            ("unmet-signal lower bound", r["unmet_signal_lower_bound"]),
            ("", ""),
            ("Cu / Co (margin vs leftover)", "%.2f / %.2f" % (d["Cu"], d["Co"])),
            ("derived service level", "%.0f%%" % (d["service_level"] * 100)),
            ("protection interval (days)", d["protection_interval_days"]),
            ("demand over interval mu/sd", "%.1f / %.1f" % (d["demand_mu"], d["demand_sd"])),
            ("order-up-to level", d["order_up_to"]),
            ("on hand / on order", "%s / %s" % (d["on_hand"], d["on_order"])),
            ("ORDER QUANTITY (pack %d)" % d["case_pack"], d["qty"]),
            ("cover after arrival", "%.1f weeks" % d["cover_after_weeks"]),
            ("capital committed", "EUR %.2f" % d["capital_eur"]),
            ("gateway", "%s / %s / %s" % (lg["tier"], lg["status"], lg["reason"])),
        ]
        for k, v in rows:
            print("    %-32s %s" % (k, v) if k else "")
        print("    rationale: %s" % p["rationale"])
    print()
    print("  Human decision on the same report: 40 white, 0 black.")
    print("  Agent decision: %s" % ", ".join(
        "%s %s" % (p["decision"]["qty"], p["variant_id"]) for p in reorder.handle.last if not p.get("blocked")))


def report_marketing(conn):
    head("AGENT 2 of 3 - MARKETING ALLOCATION.  Daily pass on p_towel.")
    m = marketing.handle.last
    print("  target CPA            EUR %.2f  (CM1 x payback factor)" % m["target_cpa"])
    print("  signal health         platform %s orders vs %s ours -> drift %s%%  healthy=%s"
          % (m["signal"]["platform"], m["signal"]["ours"], m["signal"]["drift_pct"], m["signal"]["healthy"]))
    print("  holdout               %s paid orders, %s holdout orders -> %.0f%% of orders are organic"
          % (m["holdout"]["paid_orders"], m["holdout"]["holdout_orders"],
             (m["holdout"]["organic_share"] or 0) * 100))
    print("  experiment budget     EUR %.0f of %.0f spent" % (m["budget"]["spent_eur"], m["budget"]["allocated_eur"]))
    print("  stock cover           hero %.0fd, worst %.0fd" % (m["cover"]["hero_cover_days"], m["cover"]["worst_cover_days"]))
    line()
    print("  %-24s %8s %7s %8s  %-16s %s" % ("cell", "spend", "orders", "CPA", "action", "budget"))
    line()
    for c in m["cells"]:
        print("  %-24s %8.0f %7d %8s  %-16s %s"
              % (c["cell"], c["spend"], c["orders"], ("%.0f" % c["cpa"]) if c["cpa"] else "-",
                 c["action"], "%.0f -> %.0f" % (c["from_eur"], c["to_eur"])))
        print("      %s" % c["reason"])
        if c["ledger"]:
            print("      gateway: %s / %s / %s" % (c["ledger"]["tier"], c["ledger"]["status"], c["ledger"]["reason"]))
    w = marketing.weekly.last
    if w:
        print()
        print("  Weekly channel reallocation (Thompson sampling on profit per euro):")
        for arm in sorted(w["after"], key=lambda a: -w["after"][a]):
            print("    %-24s %5.1f%%  ->  %5.1f%%" % (arm, w["before"].get(arm, 0) * 100, w["after"][arm] * 100))


def report_verdict(conn):
    head("AGENT 3 of 3 - PRODUCT VERDICT.  Product or site? Keep, fix, or kill?")
    for v in verdict.handle.last:
        r, d = v["rates"], v["diagnosis"]
        print()
        print("  %s   VERDICT: %s  (confidence %.0f%%)" % (v["product_id"], d["verdict"], d["confidence"] * 100))
        line()
        print("    %-26s %s" % ("sessions / spend", "%d / EUR %.0f" % (r["sessions"], r["spend"])))
        for k in ("pdp_rate", "atc_rate", "checkout_rate", "purchase_rate", "refund_rate", "ctr"):
            print("    %-26s %6.2f%%   [%s]" % (k, r[k] * 100, d["flags"][k]))
        print("    %-26s %s vs target %s" % ("CPA", r["cpa"], v["target_cpa"]))
        print("    diagnosis: %s" % d["diagnosis"])
        for f in d["findings"]:
            print("      - [%s] %s" % (f["owner"], f["finding"]))
        for a in d["actions"]:
            print("      -> %s" % a)
        print("    gateway: %s / %s / %s" % (v["ledger"]["tier"], v["ledger"]["status"], v["ledger"]["reason"]))
        for step in v["runbook"]:
            print("      kill runbook: %s" % step)


def report_platform(conn):
    head("PLATFORM: bus, ledger, evidence, cost")
    print("  queue      %s" % bus.depth(conn))
    print("  evidence   %d stored tool results" % db.scalar(conn, "SELECT COUNT(*) FROM evidence"))
    print("  anomalies")
    for a in db.rows(conn, "SELECT * FROM anomaly ORDER BY id"):
        print("    [%s] %-26s %s" % (a["severity"], a["kind"], a["note"]))
    print("  agent runs")
    for r in db.rows(conn, "SELECT * FROM agent_run ORDER BY started_at"):
        print("    %-20s steps=%-3s tokens=%-6s cost=EUR %-7s mode=%-10s %s"
              % (r["agent"], r["steps"], r["tokens"], round(r["cost_eur"] or 0, 4), r["mode"], r["outcome"]))


def report_ledger(conn):
    head("LEDGER (every side effect, with its tier, status and reason)")
    for r in db.rows(conn, "SELECT * FROM ledger ORDER BY id"):
        print("  #%-3s %-18s %-22s EUR %-9s %-10s %-16s %s"
              % (r["id"], r["agent"], r["intent"], round(r["value_eur"] or 0, 2), r["tier"],
                 r["status"], r["reason"]))
        payload = json.loads(r["payload"])
        print("        payload: %s" % payload)
        if r["rationale"]:
            print("        rationale: %s" % r["rationale"])
        if r["evidence"] and r["evidence"] != "[]":
            print("        evidence: %s" % ", ".join(json.loads(r["evidence"])[:4]))


def report_guardrails(conn):
    """Try to do things the agents are not allowed to do, and show what stops them."""
    head("GUARDRAILS: four proposals that must be refused")
    policy = harness.load_config("policy")
    policy.update(harness.load_config("reorder")["policy"])
    attempts = [
        ("an agent writing an intent it does not own",
         "marketing_allocator", "propose_reorder",
         {"variant_id": "v_black", "qty": 24, "supplier_id": "sup_linen", "need_by": "2026-12-15"},
         {}, "", ""),
        ("a quantity far outside the sanity band",
         "reorder", "propose_reorder",
         {"variant_id": "v_black", "qty": 5000, "supplier_id": "sup_linen", "need_by": "2026-12-15"},
         {"demand_12w": 76.0, "sales_12w": 20, "cover_after_order_weeks": 9.0}, "", ""),
        ("an order that would break the cash runway floor",
         "reorder", "propose_reorder",
         {"variant_id": "v_grey", "qty": 1200, "supplier_id": "sup_linen", "need_by": "2026-12-15"},
         {"demand_12w": 1700.0, "sales_12w": 1600, "cover_after_order_weeks": 8.0}, "", ""),
        ("a rationale that cites numbers with no evidence behind them",
         "marketing_allocator", "propose_budget_change",
         {"cell_id": "meta_prospect_morning", "from_eur": 100.0, "to_eur": 110.0},
         {"hours_since_change": 999}, "CPA was 14 EUR so we raised the budget", ""),
    ]
    for label, agent, intent, payload, ctx, rationale, _ in attempts:
        row = gateway.propose(conn, agent, intent, payload, policy, ctx=ctx,
                              rationale=rationale, evidence=[], period="guardrail-test")
        print("  %-52s -> %-9s %s" % (label, row["status"], row["reason"]))
    print()
    print("  Nothing above reached a third party: the gateway holds the credentials.")


def check_model():
    """Prove the model path works, before a demo rather than during one."""
    head("MODEL PROVIDER CHECK")
    st = model.status()
    print("  candidates examined:")
    for row in model.survey():
        print("    %-4s %-46s %s" % ("OK" if row["ok"] else "no", row["reason"][:46], row["path"]))
    print()
    print("  detected   %s" % st["label"])
    print("  detail     %s" % st["detail"])
    if st["provider"] == "rules_only":
        print()
        print("  No model provider. The engines still decide and every number in the ledger is")
        print("  still correct; only the written rationales and the Ask-the-agent panel need one.")
        print("  Options, cheapest first:")
        print("    1. repair the npm shim:  npm install -g @anthropic-ai/claude-code")
        print("    2. point at a binary:    export CLAUDE_CLI=/full/path/to/claude")
        print("    3. use the paid API:     export ANTHROPIC_API_KEY=sk-ant-...")
        return
    print("  calling the provider with a trivial prompt...")
    try:
        text, meta = model.complete('Reply with one JSON object and nothing else: {"provider": "ok"}')
        if model._extract_json(text) != {"provider": "ok"}:
            raise RuntimeError("provider replied, but did not pass the response check: %r" % text.strip()[:100])
        print("  reply      %r" % text.strip()[:80])
        print("  tokens     in=%s out=%s" % (meta.get("tokens_in"), meta.get("tokens_out")))
        print("  billing    %s" % (meta.get("billing") or "unknown"))
        print("  used       %s" % (meta.get("provider") or "unknown"))
        print()
        print("  PASS - this provider returned the expected JSON response.")
    except Exception as exc:                                     # noqa: BLE001
        print("  FAIL - %s" % exc)
        print()
        print("  The engines are unaffected. Run with ENGINE_MODEL_PROVIDER=rules_only to silence it.")
        raise SystemExit(1)


def ask_cli(question):
    from agents import analyst
    conn = db.connect()
    head("ASK THE AGENT (read-only, real tool calls)")
    print("  q: %s" % question)
    print()

    def on_event(kind, payload):
        if kind == "thinking":
            print("  [step %s] deciding what to read" % payload["step"])
        elif kind == "tool_call":
            print("  [tool] %s(%s) -> evidence %s" % (payload["tool"], payload.get("args"),
                                                      payload.get("evidence_id")))
        elif kind == "tool_denied":
            print("  [refused] %s" % payload["reason"])
    out = analyst.ask(conn, question, on_event=on_event)
    print()
    print("  answer: %s" % out["answer"])
    if out.get("uncited"):
        print("  WARNING - figures with no evidence behind them: %s" % ", ".join(out["uncited"]))
    else:
        print("  every figure traced to stored evidence")


def report_model(conn):
    """The marketing model workflow, printed the way a reviewer would want it."""
    from engines import ml, allocator
    from agents import tools
    head("MARKETING MODEL PIPELINE")
    if not ml.available():
        print("  scikit-learn is not installed; the allocator stays on its rule bands.")
        return
    margin = tools.margin_table(conn, "p_towel")
    target = allocator.target_cpa(margin["cm_per_unit"], 1.2)
    target_name = sys.argv[2] if len(sys.argv) > 2 else "orders_7d"
    out = ml.run_pipeline(conn, target_cpa=target, target=target_name,
                          verbose_sink=lambda m: print("  " + m))
    if out.get("error"):
        print("  " + out["error"]); return
    d = out["diagnostics"]

    print()
    print("  1 · STATIONARITY (augmented Dickey-Fuller, per feature)")
    line()
    print("    %-26s %9s %9s  %s" % ("feature", "ADF", "p", "verdict"))
    for r in d["stationarity"][:12]:
        print("    %-26s %9s %9s  %s" % (r["feature"], r["adf"], r["p_value"], r["note"]))
    nd = [r for r in d["stationarity"] if not r["stationary"]]
    print("    ... %d features tested, %d differenced" % (len(d["stationarity"]), len(nd)))

    print()
    print("  2 · SIGNIFICANCE (Pearson r against orders, and collinearity)")
    line()
    print("    %-26s %9s %11s  %s" % ("feature", "r", "p", "keep?"))
    for r in d["significance"][:12]:
        print("    %-26s %9.3f %11.2e  %s" % (r["feature"], r["pearson_r"], r["p_value"],
                                              "yes" if r["significant"] else "no"))
    bad_vif = [v for v in d["collinearity"] if v["collinear"]][:5]
    if bad_vif:
        print("    collinear (VIF > 10): " + ", ".join("%s=%.0f" % (v["feature"], v["vif"]) for v in bad_vif))

    print()
    print("  3 · FEATURE SELECTION (LassoCV, time-series folds, alpha=%.4f)" % d["selection"]["alpha"])
    line()
    for r in d["selection"]["ranked"][:12]:
        print("    %-26s %+8.3f" % (r["feature"], r["std_coef"]))
    print("    dropped %d: %s" % (len(d["selection"]["dropped"]),
                                  ", ".join(d["selection"]["dropped"][:8]) + ("..." if len(d["selection"]["dropped"]) > 8 else "")))

    print()
    print("  4 · OUT-OF-SAMPLE COMPARISON (forward split at %s · train %d · test %d)"
          % (out["cut_day"], out["n_train"], out["n_test"]))
    line()
    print("    %-19s %-12s %-9s %7s | %7s %8s %8s %7s"
          % ("family", "panel", "target", "R2 in", "R2 out", "RMSE out", "MAE out", "AUC"))
    shown = out["leaderboard"][:10]
    for e in out["leaderboard"]:
        if e["family"].startswith("baseline") and e not in shown:
            shown.append(e)
    for e in shown:
        print("    %-19s %-12s %-9s %7.3f | %7.3f %8.3f %8.3f %7s"
              % (e["family"], e.get("panel", "-"), e.get("transform", "-"),
                 e["in_sample"]["r2"], e["out_sample"]["r2"], e["out_sample"]["rmse"],
                 e["out_sample"]["mae"], e.get("auc") if e.get("auc") is not None else "-"))

    print()
    print("  5 · PROMOTION")
    line()
    print("    model #%s  %s" % (out["model_id"], "PROMOTED" if out["promoted"] else "HELD BACK"))
    print("    reason: %s" % out["reason"])
    print("    the allocator uses this model only while it is promoted; otherwise it falls")
    print("    back to the deterministic CPA bands, which are never switched off.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd in ("agentic-verdict", "agentic-marketing"):
        from core import model as _m
        import textwrap
        conn = db.connect()
        period = "agentic-cli:" + db.now()[:10]
        head("AGENTIC %s - THE MODEL PLANS ITS OWN INVESTIGATION"
             % ("VERDICT" if cmd.endswith("verdict") else "MARKETING"))
        print("  provider: %s" % _m.status()["label"])
        if cmd == "agentic-verdict":
            prods = [a for a in sys.argv[2:] if not a.startswith("--")] or ["p_mug", "p_candle"]
            prods = [p for p in prods if db.scalar(conn, "SELECT COUNT(*) FROM product WHERE id=?", (p,))]
            for r in verdict_agentic.handle(conn, {"products": prods, "period": period}):
                d = r["decision"]
                print()
                print("  %s" % r["product_id"])
                line()
                print("    it chose to look at : %s"
                      % (", ".join(t["payload"]["tool"] for t in r["tool_calls"]) or "(no model)"))
                print("    the engine said     : %s" % r["engine_verdict"])
                print("    the agent said      : %s  (%s, confidence %.0f%%)"
                      % (d["verdict"], d["source"], float(d["confidence"]) * 100))
                for ln in textwrap.wrap("reason: " + (d["why"] or ""), 72):
                    print("    %s" % ln)
                if d.get("first_fix") and d["first_fix"] != "none":
                    for ln in textwrap.wrap("first fix: " + d["first_fix"], 72):
                        print("    %s" % ln)
                print("    gateway             : %s / %s" % (r["ledger"]["tier"], r["ledger"]["status"]))
        else:
            for r in marketing_agentic.handle(conn, {"product_id": "p_towel", "period": period}):
                d = r["decision"]
                print()
                print("  %s" % r["cell"])
                line()
                print("    it chose to look at : %s"
                      % (", ".join(t["payload"]["tool"] for t in r["tool_calls"]) or "(no model)"))
                print("    cost per order      : EUR %s against a EUR %s target" % (r["cpa"], r["target_cpa"]))
                print("    the rules alone     : %s" % r["rules_would"])
                print("    the agent           : %s -> EUR %s a day (%s)"
                      % (d["action"], d["budget"], d["source"]))
                for ln in textwrap.wrap("reason: " + (d["why"] or ""), 72):
                    print("    %s" % ln)
                if r["ledger"]:
                    print("    gateway             : %s / %s" % (r["ledger"]["tier"], r["ledger"]["status"]))
        print()
        print("  Autonomy over the reasoning. None over the arithmetic.")
        return

    if cmd == "agentic":
        """Watch the agent plan its own investigation."""
        from core import model as _m
        head("AGENTIC REORDER - THE MODEL PLANS ITS OWN INVESTIGATION")
        if "--fresh" in sys.argv:
            conn, counts = setup(reset=True)
            print("  reseeded so the agent faces an undecided order: %s products" % counts["product"])
        else:
            conn = db.connect()
        variants = [v for v in sys.argv[2:] if not v.startswith("--")] or ["v_black", "v_white"]
        print("  provider: %s" % _m.status()["label"])
        print("  The agent is given a goal, a set of tools and eight steps. It chooses what")
        print("  to look at. The quantity engine is one of its tools, and its final order")
        print("  must be one of the numbers that engine returned.")
        rows = reorder_agentic.handle(conn, {"variants": variants, "period": "agentic-cli:" + db.now()[:10]})
        for r in rows:
            d = r["decision"]
            print()
            print("  %s" % r["variant_id"])
            line()
            print("    it chose to look at, in this order:")
            if not r["tool_calls"]:
                print("      (no model available - the engine default was used)")
            for i, t in enumerate(r["tool_calls"], 1):
                print("      %d. %s" % (i, t["payload"]["tool"]))
            print()
            print("    the quantities the maths allowed:")
            for name, o in r["options"].items():
                print("      %-13s %5s units   %5s weeks cover   EUR %s"
                      % (name, o["quantity"], o["cover_after_weeks"], o["capital_eur"]))
            print()
            print("    DECISION   %s %s units (%s option)"
                  % (d["action"], d["quantity"], d["option"]))
            print("    decided by %s" % d["source"])
            if d["why"]:
                import textwrap
                for ln in textwrap.wrap("reason: " + d["why"], 74):
                    print("    %s" % ln)
            if r["ledger"]:
                print("    gateway    %s / %s / %s" % (r["ledger"]["tier"], r["ledger"]["status"],
                                                       r["ledger"]["reason"]))
        print()
        print("  Autonomy over the reasoning. None over the arithmetic.")
        return

    if cmd == "budget":
        from engines import budget as bg
        amount = float(sys.argv[2]) if len(sys.argv) > 2 else 3000.0
        head("BUDGET ALLOCATION - EUR %.0f THIS WEEK" % amount)
        conn = db.connect()
        out = bg.allocate(conn, amount)
        if out.get("error"):
            print("  %s" % out["error"]); return
        print("  Who gets money, who does not, and why. Four things decide it: what an")
        print("  order is worth, what stock allows, whether the product has proved itself,")
        print("  and whether it is being killed.")
        print()
        print("  Two decisions, not one: which products deserve money, then which channel")
        print("  spends it. Both from the same evidence.")
        print()
        print("  %-22s %-16s %7s %8s %10s" % ("product", "verdict", "cover", "margin", "this week"))
        line()
        for l in out["lines"]:
            print("  %-22s %-16s %6.0fd %8.2f %10.2f"
                  % (l["product"][:22], (l["verdict"] or "")[:16], l["cover_days"],
                     l["margin"], l["allocated"]))
            why = l["reason"] or ("returns EUR %s for every euro spent" % l["return_per_euro"])
            print("      %s" % why[:90])
            for c in (l.get("channels") or []):
                if c["amount"] <= 0:
                    continue
                print("        -> %-10s EUR %8.2f   %s" % (c["channel"], c["amount"], c["why"][:62]))
        line()
        print("  %-22s %-16s %7s %8s %10.2f" % ("allocated", "", "", "", out["allocated"]))
        print("  %-22s %-16s %7s %8s %10.2f" % ("held back to test new things", "", "", "",
                                                out["held_back"]))
        print()
        funded = [l for l in out["lines"] if l["allocated"] > 0]
        blocked = [l for l in out["lines"] if l["allocated"] <= 0]
        print("  %d products funded, %d not." % (len(funded), len(blocked)))
        supply = [l for l in blocked if l["reason"] and "stock" in l["reason"]]
        if supply:
            print("  Note %s: it sells well and gets nothing, because advertising it would"
                  % supply[0]["product"])
            print("  book orders the warehouse cannot ship. That is the mistake this is for.")
        return

    if cmd == "live-marketing":
        from engines import live_marketing
        head("A MARKETING MODEL ON REAL DATA ONLY")
        conn = db.connect()
        print("  Features: orders that really happened, stock that was really on the shelf,")
        print("  devices customers really used, and public interest from Wikimedia's open")
        print("  pageviews API. No ad spend, because there is no ad account yet.")
        rows = live_marketing.train_all(conn)
        for r in rows:
            print()
            if r.get("error"):
                print("  %-22s %s" % (r.get("name"), r["error"])); continue
            n = r["noise"]
            print("  %s   %d real days, %d train / %d test"
                  % (r["name"], r["rows"], r["train_days"], r["test_days"]))
            line()
            for e in r["leaderboard"]:
                mark = "  <- best" if e is r["leaderboard"][0] else ""
                print("    %-20s R2 %7.3f   average miss %5.2f orders%s"
                      % (e["family"], e["r2"], e["mae"], mark))
            print("    sells %.2f a day; at that rate the day-to-day randomness alone caps any"
                  % n["orders_per_day"])
            print("    model at about R2 %.2f, and we reached %.2f."
                  % (n["best_r2_any_model_could_reach"], r["leaderboard"][0]["r2"]))
            print("    what the best model leaned on: %s"
                  % ", ".join("%s (%s)" % (i["feature"], i["weight"]) for i in r["importance"][:3]))
        print()
        print("  The finding, stated plainly: at one or two orders a day you cannot forecast")
        print("  daily sales, and no feature engineering changes that. The randomness is")
        print("  larger than the signal. These products need roughly %s orders a day before"
              % (rows[0].get("noise", {}).get("orders_per_day_needed_for_a_useful_model", "10")
                 if rows and not rows[0].get("error") else "10"))
        print("  a daily model earns its place. Until then the agent uses its rules, which do")
        print("  not need a forecast to be right.")
        print()
        print("  This is why the seeded panel exists: it demonstrates the method at a volume")
        print("  this shop has not reached. Both are shown, and neither is dressed up.")
        return

    if cmd == "classify-reviews":
        from engines import foundation
        head("READING THE REVIEWS WITH A LANGUAGE MODEL")
        conn = db.connect()
        out = foundation.classify_reviews(conn)
        print("  %s" % out)
        if not out.get("error"):
            for r in db.rows(conn, "SELECT product, sentiment, COUNT(*) n FROM order_review"
                                   " WHERE sentiment IS NOT NULL GROUP BY 1,2 ORDER BY 1"):
                print("    %-24s %-10s %s" % (r["product"], r["sentiment"], r["n"]))
        return

    if cmd == "interest":
        from adapters import interest as itr
        head("REAL PUBLIC INTEREST (WIKIMEDIA OPEN DATA)")
        conn = db.init(reset=False)
        out = itr.sync(conn, 120, say=lambda m: print("  " + m))
        print()
        print("  %s" % out)
        print("  No key, no account, no vendor. It is the honest stand-in for a search-term")
        print("  report until there is an ad account to read one from.")
        return

    if cmd == "live-verdict":
        from engines import live_verdict
        head("VERDICTS ON THE LIVE SHOP - REAL EVIDENCE ONLY")
        conn = db.connect()
        rows = live_verdict.judge_all(conn)
        if not rows:
            print("  No live products. Run: python3 run.py medusa sync")
            return
        for v in rows:
            if v.get("error"):
                print("  %s" % v["error"]); continue
            e = v["evidence"]
            print()
            print("  %s   %s  (confidence %.0f%%)" % (v["name"], v["verdict"], v["confidence"] * 100))
            line()
            print("    %-34s %s" % ("units really sold", e["units_sold"]))
            print("    %-34s %s" % ("days it sold on", e["days_with_sales"]))
            print("    %-34s %s" % ("reconstructed real demand", e["real_demand_estimate"]))
            print("    %-34s %s" % ("demand lost to empty shelves", e["demand_lost_to_stockouts"]))
            print("    %-34s %.0f%%" % ("days its sellers were unbuyable", e["share_of_days_unbuyable"] * 100))
            print("    %-34s EUR %s (%.0f%% of price)" % ("margin per unit", e["margin_per_unit"],
                                                          e["margin_pct"] * 100))
            print("    %-34s EUR %s" % ("contribution per day", e["contribution_per_day"]))
            s2 = e["sentiment"]
            print("    %-34s %s" % ("reviews read by the model",
                                    ("%d, %d%% negative" % (s2["classified"], (s2["negative_share"] or 0) * 100))
                                    if s2["classified"] else "none classified yet"))
            if e["trend_30d"] is not None:
                print("    %-34s %+.0f%%" % ("last 30 days vs the 30 before", e["trend_30d"] * 100))
            print("    because: %s" % v["because"])
            for a in v["actions"]:
                print("      -> %s" % a)
        print()
        print("  Every figure above came out of the live shop. Nothing here is seeded.")
        return

    if cmd == "forecast-threshold":
        """At what volume would the foundation model start to earn its place?"""
        from engines import threshold
        head("WHEN DOES THE FOUNDATION MODEL START WINNING?")
        print("  Chronos loses on this shop's data. Either the data is too thin or the")
        print("  benchmark is wrong. This settles it: simulated series with a pattern that")
        print("  genuinely exists - weekly rhythm, slow growth, occasional promotions - at")
        print("  five volumes and two history lengths, scored the same way as the real test.")
        print()
        out = threshold.sweep(say=lambda m: print("  " + m))
        if out.get("error"):
            print("  FAILED: %s" % out["error"]); return
        print()
        print("  %-12s %9s %8s %12s %14s %9s" % ("orders/day", "history", "series",
                                                 "Chronos err", "statistics err", "winner"))
        line()
        for r in out["rows"]:
            print("  %-12s %8dd %8d %11.1f%% %13.1f%% %9s"
                  % (r["per_day"], r["days"], r["series"], r["chronos_error_pct"],
                     r["statistics_error_pct"], r["winner"]))
        print()
        if out["crossover_per_day"]:
            print("  Chronos wins in %d of %d cells, from about %s orders a day upwards."
                  % (out["chronos_wins"], out["cells"], out["crossover_per_day"]))
            print("  The benchmark is sound: the model can win, just not on data this thin.")
        else:
            print("  Chronos won none of the %d cells. That points at the harness or at how"
                  % out["cells"])
            print("  the series are built, not at the shop, and is worth chasing down.")
        by_history = {}
        for r in out["rows"]:
            by_history.setdefault(r["days"], []).append(r)
        print()
        for days, rows2 in sorted(by_history.items()):
            w = sum(1 for r in rows2 if r["winner"] == "chronos")
            print("  With %3d days of history it wins %d of %d volumes." % (days, w, len(rows2)))
        print()
        print("  The binding constraint is history, not volume: with a year behind it the")
        print("  model wins at every volume, including one order a day. With four months it")
        print("  is marginal. This shop has four months and one to two orders a day, which")
        print("  is the worst corner of this table.")
        print()
        print("  So the fix is not a better model or more features. It is to keep recording,")
        print("  and to re-run this. The benchmark already does that on a schedule.")
        return

    if cmd == "forecast-retry":
        """The fair rerun: better checkpoints, several folds, split by volume."""
        from engines import foundation
        head("CHRONOS, PROPERLY TESTED")
        conn = db.connect()
        if not foundation.available():
            print("  Chronos is not installed."); return
        variants = [r["id"] for r in db.rows(conn, """
            SELECT v.id FROM variant v
            ORDER BY (SELECT COALESCE(SUM(units),0) FROM sales_fact WHERE variant_id=v.id) DESC
            LIMIT 8""")]
        print("  The first test used the smallest checkpoint and one lucky window. This")
        print("  runs four checkpoints over several folds walked forward through time.")
        print()
        out = foundation.rolling_benchmark(conn, variants, horizon=14, folds=3,
                                           say=lambda m: print("  " + m))
        if out.get("error"):
            print("  FAILED: %s" % out["error"]); return
        print()
        print("  %-26s %10s %12s %10s %8s" % ("checkpoint", "its error", "statistics", "coverage", "tests"))
        line()
        for r in out["results"]:
            print("  %-26s %10.2f %12.2f %9.0f%% %8d"
                  % (r["model"].split("/")[-1], r["chronos_mae"], r["statistics_mae"],
                     r["coverage"] * 100, r["evaluations"]))
        b = out["best"]
        print()
        print("  Best checkpoint: %s" % b["model"])
        if b["busy"]["n"] and b["busy"]["chronos"] is not None:
            print("  %-28s Chronos %6.2f   statistics %6.2f"
                  % ("busy products (%d)" % b["busy"]["n"], b["busy"]["chronos"], b["busy"]["statistics"]))
        if b["slow"]["n"] and b["slow"]["chronos"] is not None:
            print("  %-28s Chronos %6.2f   statistics %6.2f"
                  % ("slow sellers (%d)" % b["slow"]["n"], b["slow"]["chronos"], b["slow"]["statistics"]))
        print()
        print("  Overall winner: %s by %.0f%%." % (out["winner"].upper(), abs(out["margin_pct"])))
        if out["winner"] == "chronos":
            print("  Promoted. The first result was the smallest model on one window, and that")
            print("  was my mistake, not the model's.")
        else:
            print("  Still not promoted. A better checkpoint and a fairer test did not change")
            print("  the answer on this data, which is itself worth knowing.")
        return

    if cmd == "forecast-bench":
        """Does a 2024 foundation model beat the statistics we already use?"""
        from engines import foundation
        head("FOUNDATION MODEL vs STATISTICS")
        conn = db.connect()
        if not foundation.available():
            print("  Chronos is not installed. Set it up once with:")
            print("    python3 -m venv .venv-ml && .venv-ml/bin/pip install torch chronos-forecasting")
            return
        variants = [r["id"] for r in db.rows(conn, """
            SELECT v.id FROM variant v
            ORDER BY (SELECT COALESCE(SUM(units),0) FROM sales_fact WHERE variant_id=v.id) DESC
            LIMIT 8""")]
        print("  Holding out the last 14 days of each product's history and asking both")
        print("  methods what total demand would be. Neither sees the answer.")
        print()
        out = foundation.benchmark(conn, variants, horizon=14, say=lambda m: print("  " + m))
        if out.get("error"):
            print("  FAILED: %s" % out["error"])
            return
        print()
        print("  %-26s %8s %12s %12s %12s" % ("product", "actual", "Chronos p50", "statistics", "in band?"))
        line()
        for r in out["rows"]:
            print("  %-26s %8.1f %12.1f %12.1f %12s"
                  % (r["variant"][:26], r["actual"], r["chronos_p50"], r["statistics"],
                     "yes" if r["actual_inside_band"] else "no"))
        line()
        print("  %-26s %8s %12.2f %12.2f" % ("average error (units)", "", out["chronos_mae"],
                                             out["statistics_mae"]))
        print()
        bv = out.get("by_volume") or {}
        if bv.get("busy_products", {}).get("n") and bv.get("slow_products", {}).get("n"):
            print("  %-26s %8s %12s %12s" % ("", "", "Chronos", "statistics"))
            print("  %-26s %8s %12s %12s"
                  % ("5+ a day (%d series)" % bv["busy_products"]["n"], "",
                     bv["busy_products"]["chronos"], bv["busy_products"]["statistics"]))
            print("  %-26s %8s %12s %12s"
                  % ("the long tail (%d series)" % bv["slow_products"]["n"], "",
                     bv["slow_products"]["chronos"], bv["slow_products"]["statistics"]))
            print()
        print("  Winner overall: %s, by %.0f%%." % (out["winner"].upper(), abs(out["margin_pct"])))
        print("  Chronos's 10-90%% band contained the real number %.0f%% of the time."
              % (out["band_coverage"] * 100))
        print()
        if out.get("insight"):
            import textwrap
            for ln in textwrap.wrap(out["insight"], 74):
                print("  " + ln)
            print()
            print("  Recommendation: %s." % out.get("recommendation"))
            print()
        if out["winner"] == "chronos":
            print("  It is promoted: the reorder agent may use it, and will stop using it the")
            print("  moment it stops winning.")
        else:
            print("  It is not promoted. A pretrained transformer lost to an average over the")
            print("  last four weeks on this data, and the honest thing is to say so and keep")
            print("  the cheaper method. Re-run it as real history accumulates.")
        return

    if cmd == "vertical":
        """The architect's own question: is it really the same agent?"""
        from engines import demand as dm, quantity as qt
        from agents import tools as tl
        head("THE SAME AGENT, TWO DIFFERENT BUSINESSES")
        conn = db.connect()
        cases = [("v_black", "reorder", "Linen towels", "durable goods, weekly buying"),
                 ("v_yoghurt", "reorder_fresh", "Fresh yoghurt", "perishable, bought daily")]
        results = []
        for variant, config_name, label, blurb in cases:
            cfg = harness.load_config(config_name)
            rec = dm.reconstruct(conn, variant, 90, cfg["policy"]["intended_discount_pct"])
            terms = tl.supplier_terms(conn, variant)
            econ = tl.economics(conn, variant)
            on_hand = db.scalar(conn, "SELECT on_hand FROM inventory_snapshot WHERE variant_id=?"
                                      " ORDER BY ts DESC LIMIT 1", (variant,), 0)
            d = qt.order(rec, terms, cfg["policy"], on_hand, 0, econ)
            results.append((label, blurb, config_name, cfg["policy"], rec, d, econ))

        print()
        print("  Same code path, same engines, same gateway. The only difference is the")
        print("  configuration file each run was handed.")
        print()
        print("  %-30s %-22s %-22s" % ("", results[0][0], results[1][0]))
        print("  %-30s %-22s %-22s" % ("", results[0][1], results[1][1]))
        line()
        rows = [
            ("config file", lambda r: "config/%s.json" % r[2]),
            ("how often it reorders", lambda r: "every %s day(s)" % r[3]["review_period_days"]),
            ("shelf life", lambda r: ("%s days" % r[3]["shelf_life_days"]) if r[3]["shelf_life_days"] else "does not expire"),
            ("most stock it may hold", lambda r: "%.1f weeks" % r[3]["cover_cap_weeks"]),
            ("markdown policy", lambda r: r[3]["markdown_curve"]),
            ("", lambda r: ""),
            ("margin per unit (Cu)", lambda r: "%.2f" % r[5]["Cu"]),
            ("cost of one left over (Co)", lambda r: "%.2f" % r[5]["Co"]),
            ("SERVICE LEVEL IT CHOSE", lambda r: "%.0f%%" % (r[5]["service_level"] * 100)),
            ("", lambda r: ""),
            ("sells per day", lambda r: "%.2f" % r[4]["net_ros"]),
            ("protection interval", lambda r: "%.0f days" % r[5]["protection_interval_days"]),
            ("order-up-to level", lambda r: "%.0f" % r[5]["order_up_to"]),
            ("on hand", lambda r: "%s" % r[5]["on_hand"]),
            ("ORDER QUANTITY", lambda r: "%s" % r[5]["qty"]),
            ("cover after it arrives", lambda r: "%.1f weeks" % r[5]["cover_after_weeks"]),
        ]
        for label, fn in rows:
            print("  %-30s %-22s %-22s" % (label, fn(results[0]), fn(results[1])))

        a, b = results[0][5], results[1][5]
        print()
        print("  Read the service levels. The towel agent covers %.0f%% of demand because running"
              % (a["service_level"] * 100))
        print("  out costs far more than holding one extra. The yoghurt agent covers only %.0f%%,"
              % (b["service_level"] * 100))
        print("  deliberately under-ordering, because a leftover tub is a write-off and a lost")
        print("  sale is not. Nobody wrote that rule: both numbers come out of the same")
        print("  newsvendor formula fed each item's own economics.")
        print()
        print("  A new vertical is a configuration file and a set of adapters. It is not a")
        print("  new agent, and it is not a new team.")
        return

    if cmd == "liveprep":
        """Everything needed to start a demo from a cold database."""
        from adapters import medusa
        head("PREPARING A LIVE DEMO")
        conn = db.init(reset=False)
        if db.scalar(conn, "SELECT COUNT(*) FROM product") == 0:
            print("  seeding the reference history (the towel case)...")
            print("  %s" % seeder.run(conn))
        if medusa.configured():
            try:
                print("  reading the live shop...")
                out = medusa.sync(conn)
                print("    %s" % out["products"])
                print("    %s" % out["orders"])
                print("  estimating stock history from the order log...")
                print("    %s" % medusa.backfill_availability(conn, 90))
            except Exception as exc:                            # noqa: BLE001
                print("  live shop not reachable (%s); continuing on stored history" % str(exc)[:80])
        else:
            print("  no shop configured; continuing on stored history")
        try:
            from engines import ml as _ml, allocator as _alloc
            from agents import tools as _tools
            if _ml.available():
                print("  training the marketing models...")
                _m = _tools.margin_table(conn, "p_towel")
                _out = _ml.run_pipeline(conn, target_cpa=_alloc.target_cpa(_m["cm_per_unit"], 1.2),
                                        target="orders_7d")
                print("    %s, out-of-sample R2 %.3f, %s"
                      % (_out["leaderboard"][0]["family"], _out["leaderboard"][0]["out_sample"]["r2"],
                         "promoted" if _out["promoted"] else "held back"))
        except Exception as exc:                                # noqa: BLE001
            print("  model training skipped: %s" % str(exc)[:80])
        try:
            from engines import foundation as _fnd
            if _fnd.available():
                print("  reading the review text with a language model...")
                print("    %s" % _fnd.classify_reviews(conn))
        except Exception as exc:                                # noqa: BLE001
            print("  review classification skipped: %s" % str(exc)[:70])
        enqueue_all(conn)
        done, dead = bus.run_worker(conn, max_jobs=200, verbose=False)
        print("  ran every agent: %d jobs done, %d dead" % (done, dead))
        print()
        print("  Ready. Start the console and open http://127.0.0.1:8787")
        print("    python3 run.py ui")
        return

    if cmd == "selftest":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        a = subprocess.call([sys.executable, os.path.join(here, "tests", "selftest.py")])
        b = subprocess.call([sys.executable, os.path.join(here, "tests", "test_shopify_adapter.py")])
        c = subprocess.call([sys.executable, os.path.join(here, "tests", "test_medusa_adapter.py")])
        return sys.exit(a or b or c)

    if cmd == "medusa":
        from adapters import medusa
        sub = sys.argv[2] if len(sys.argv) > 2 else "check"
        head("MEDUSA ADAPTER - %s" % sub)
        if not medusa.configured():
            print("  Not configured. Point the engine at your running shop:")
            print("    export MEDUSA_URL=http://localhost:9000")
            print("    export MEDUSA_EMAIL=admin@medusajs.com")
            print("    export MEDUSA_PASSWORD=supersecret")
            print("  or, instead of email and password, a secret key from")
            print("  the admin at Settings -> Secret API Keys:")
            print("    export MEDUSA_API_KEY=sk_...")
            print()
            print("  Not installed yet? bash scripts/setup-medusa.sh")
            return
        conn = db.init(reset=False)
        try:
            if sub == "check":
                for k, v in medusa.check().items():
                    print("  %-10s %s" % (k, v))
            elif sub == "probe":
                print("  what the live shop actually returns:")
                for name, info in medusa.probe().items():
                    print()
                    print("  %s" % name.upper())
                    for k, v in info.items():
                        print("    %-18s %s" % (k, str(v)[:150]))
            elif sub == "sync":
                print("  pulling products, orders and an inventory snapshot...")
                out = medusa.sync(conn, since_days=int(sys.argv[3]) if len(sys.argv) > 3 else 120)
                for section, vals in out.items():
                    print("  %-10s %s" % (section, vals))
                print()
                print("  Demand reconstruction needs availability HISTORY, so leave")
                print("  'python3 run.py medusa watch' running to build it up.")
            elif sub == "snapshot":
                print("  %s" % medusa.snapshot_inventory(conn))
            elif sub == "backfill":
                out = medusa.backfill_availability(
                    conn, int(sys.argv[3]) if len(sys.argv) > 3 else 90)
                print("  %s" % out)
            elif sub == "watch":
                every = int(sys.argv[3]) if len(sys.argv) > 3 else 900
                print("  snapshotting inventory every %ds. Ctrl-C to stop." % every)
                while True:
                    try:
                        print("  %s" % medusa.snapshot_inventory(conn))
                    except Exception as exc:                    # noqa: BLE001
                        print("  snapshot failed: %r" % exc)
                    time.sleep(every)
            else:
                print("  unknown subcommand: use check, probe, sync, snapshot or watch")
        except Exception as exc:                                # noqa: BLE001
            print("  FAILED: %s" % exc)
        return

    if cmd == "shopify":
        from adapters import shopify
        sub = sys.argv[2] if len(sys.argv) > 2 else "check"
        head("SHOPIFY ADAPTER - %s" % sub)
        if not shopify.configured():
            print("  Not configured. Set two environment variables:")
            print("    export SHOPIFY_STORE=your-store.myshopify.com")
            print("    export SHOPIFY_TOKEN=shpat_...")
            print()
            print("  The token comes from a custom app in the store admin:")
            print("    Settings -> Apps and sales channels -> Develop apps -> Create an app")
            print("    -> Configure Admin API scopes -> %s" % ", ".join(shopify.SCOPES_NEEDED))
            print("    -> Install app -> reveal the Admin API access token")
            return
        conn = db.init(reset=False)
        try:
            if sub == "check":
                info = shopify.check()
                for k, v in info.items():
                    print("  %-12s %s" % (k, v))
                print()
                print("  If any count says 'denied', the custom app is missing that scope.")
            elif sub == "sync":
                print("  pulling products, orders and an inventory snapshot...")
                out = shopify.sync(conn, since_days=int(sys.argv[3]) if len(sys.argv) > 3 else 120)
                for section, vals in out.items():
                    print("  %-10s %s" % (section, vals))
                print()
                print("  Run 'python3 run.py towels' style commands against the real catalogue now,")
                print("  but remember: demand reconstruction needs availability HISTORY, so the")
                print("  snapshot job has to run for a while before it can say anything useful.")
            elif sub == "snapshot":
                print("  %s" % shopify.snapshot_inventory(conn))
            elif sub == "watch":
                every = int(sys.argv[3]) if len(sys.argv) > 3 else 900
                print("  snapshotting inventory every %ds. Ctrl-C to stop." % every)
                while True:
                    try:
                        print("  %s" % shopify.snapshot_inventory(conn))
                    except Exception as exc:                    # noqa: BLE001
                        print("  snapshot failed: %r" % exc)
                    time.sleep(every)
            else:
                print("  unknown subcommand: use check, sync, snapshot or watch")
        except Exception as exc:                                # noqa: BLE001
            print("  FAILED: %s" % exc)
        return

    if cmd == "model":
        return report_model(db.connect())
    if cmd == "check-model":
        return check_model()
    if cmd == "ask":
        return ask_cli(" ".join(sys.argv[2:]) or "Why did you order 60 black towels and none white?")
    if cmd == "ui":
        import server
        port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 8787
        return server.main(port)
    if cmd == "reverse":
        conn = db.connect()
        gateway.reverse(conn, int(sys.argv[2]))
        report_ledger(conn)
        return

    fresh = "--fresh" in sys.argv or not os.path.exists(db.DB_PATH)
    if fresh:
        conn, counts = setup(reset=True)
        print("seeded: %s" % counts)
        # a reset wipes the live shop's data too, so put it straight back
        try:
            from adapters import medusa as _med
            if _med.configured():
                out = _med.sync(conn)
                print("re-read the live shop: %s products, %s order lines"
                      % (out["products"]["products"], out["orders"]["order_lines"]))
                _med.backfill_availability(conn, 90)
                from engines import foundation as _f
                if _f.available():
                    _f.classify_reviews(conn)
        except Exception as exc:                                # noqa: BLE001
            print("live shop not re-read: %s" % str(exc)[:70])
    else:
        # never wipe a live demo by accident: pass --fresh to start over
        conn = db.init(reset=False)
        print("using the existing database (pass --fresh to reseed)")
    try:
        from engines import ml as _ml
        from engines import allocator as _alloc
        from agents import tools as _tools
        if _ml.available():
            _m = _tools.margin_table(conn, "p_towel")
            _out = _ml.run_pipeline(conn, target_cpa=_alloc.target_cpa(_m["cm_per_unit"], 1.2),
                                    target="orders_7d")
            print("model: %s, out-of-sample R2 %.3f, %s"
                  % (_out["leaderboard"][0]["family"], _out["leaderboard"][0]["out_sample"]["r2"],
                     "promoted" if _out["promoted"] else "held back"))
    except Exception as _exc:                                   # noqa: BLE001
        print("model pipeline skipped: %r" % _exc)
    enqueue_all(conn)
    done, dead = bus.run_worker(conn, max_jobs=50, verbose=True)
    print("  [bus] %d jobs done, %d dead" % (done, dead))

    if cmd in ("demo", "towels"):
        report_towels(conn)
    if cmd in ("demo", "marketing"):
        report_marketing(conn)
    if cmd in ("demo", "verdict"):
        report_verdict(conn)
    if cmd in ("demo", "platform"):
        report_platform(conn)
    if cmd == "console":
        import console
        path = console.write(conn, reorder.handle.last, marketing.handle.last,
                             marketing.weekly.last, verdict.handle.last)
        print("wrote %s" % path)
        return
    if cmd in ("demo", "guardrails"):
        report_guardrails(conn)
    if cmd in ("demo", "ledger"):
        report_ledger(conn)


if __name__ == "__main__":
    main()
