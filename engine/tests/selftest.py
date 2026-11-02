"""One command to prove the whole thing works before a demo.

Seeds a throwaway database, trains the models, runs all three agents through
the bus and the gateway, and asserts the invariants that matter. Prints PASS or
FAIL per check and exits non-zero on any failure.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["ENGINE_DB"] = "/tmp/claude-501/selftest.db"

from core import db, bus, model                       # noqa: E402
from db import seed as seeder                         # noqa: E402
from agents import reorder, marketing, verdict        # noqa: E402  (registers handlers)
from agents import tools                              # noqa: E402
from engines import ml, allocator                     # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("  %-46s %s  %s" % (name, "PASS" if condition else "FAIL", detail))
    return bool(condition)


def main():
    t0 = time.time()
    if os.path.exists(os.environ["ENGINE_DB"]):
        os.remove(os.environ["ENGINE_DB"])
    print("\nSELF TEST\n" + "=" * 78)

    conn = db.init(reset=True)
    counts = seeder.run(conn)
    check("seed: products, variants, feature panel",
          counts["product"] >= 5 and db.scalar(conn, "SELECT COUNT(*) FROM ad_feature") > 500,
          str(counts["product"]) + " products")

    # --- the model pipeline ---
    if ml.available():
        margin = tools.margin_table(conn, "p_towel")
        target = allocator.target_cpa(margin["cm_per_unit"], 1.2)
        out = ml.run_pipeline(conn, target_cpa=target, target="orders_7d")
        best = out["leaderboard"][0]
        check("model: beats the previous-window baseline",
              best["out_sample"]["r2"] > max(
                  (e["out_sample"]["r2"] for e in out["leaderboard"]
                   if e["family"].startswith("baseline")), default=-9),
              "R2 out %.3f" % best["out_sample"]["r2"])
        check("model: leakage guards fired",
              any("target" in d.get("note", "") or "calendar" in d.get("note", "")
                  for d in out["diagnostics"]["leakage"]),
              "%d features removed" % len(out["diagnostics"]["leakage"]))
        check("model: promoted and loadable", out["promoted"] and ml.load_promoted(conn) is not None)
    else:
        print("  (scikit-learn absent: model checks skipped, engines unaffected)")

    # --- the agents, through the bus ---
    bus.publish(conn, "reorder.due", {"variants": ["v_black", "v_white", "v_grey"],
                                      "period": "test"}, "v_black")
    bus.publish(conn, "marketing.daily", {"product_id": "p_towel", "period": "test"}, "p_towel")
    bus.publish(conn, "verdict.weekly", {"products": ["p_towel", "p_lamp", "p_mug", "p_candle"],
                                         "period": "test"}, "portfolio")
    done, dead = bus.run_worker(conn, max_jobs=80, verbose=False)
    depth = bus.depth(conn)
    check("bus: queue drains with no dead letters", depth["ready"] == 0 and dead == 0,
          "%d done, %d dead" % (depth["done"], dead))

    # --- the towel case ---
    byv = {p["variant_id"]: p for p in reorder.handle.last if not p.get("blocked")}
    black, white = byv.get("v_black", {}), byv.get("v_white", {})
    check("towels: black demand reconstructed above shipped units",
          black and black["reconstruction"]["reconstructed_demand_period"] > 60,
          "%.1f units vs 20 shipped" % black["reconstruction"]["reconstructed_demand_period"])
    check("towels: substitution removed from white",
          white and white["reconstruction"]["substitution_share"] > 0.05,
          "%.0f%% of white's sales" % (white["reconstruction"]["substitution_share"] * 100))
    check("towels: orders black, declines white",
          black.get("decision", {}).get("qty", 0) > 0 and white.get("decision", {}).get("qty", 1) == 0,
          "black %s, white %s" % (black.get("decision", {}).get("qty"),
                                  white.get("decision", {}).get("qty")))

    # --- the gateway ---
    tiers = {r["tier"] for r in db.rows(conn, "SELECT DISTINCT tier FROM ledger")}
    check("gateway: more than one tier exercised", len(tiers - {None, "-"}) >= 2, ", ".join(sorted(t for t in tiers if t)))
    kill = db.one(conn, "SELECT * FROM ledger WHERE intent='publish_verdict'"
                        " AND payload LIKE '%KILL%'")
    check("gateway: a kill is never autonomous", kill and kill["status"] == "pending_human",
          kill["status"] if kill else "no kill produced")
    uncited = db.scalar(conn, "SELECT COUNT(*) FROM ledger WHERE rationale IS NOT NULL"
                              " AND rationale<>'' AND (evidence IS NULL OR evidence='[]')")
    check("gateway: no rationale without evidence", uncited == 0, "%d offenders" % uncited)

    # --- idempotency ---
    before = db.scalar(conn, "SELECT COUNT(*) FROM ledger WHERE intent='propose_reorder'")
    bus.publish(conn, "reorder.due", {"variants": ["v_black"], "period": "test"}, "v_black")
    bus.run_worker(conn, max_jobs=20, verbose=False)
    after = db.scalar(conn, "SELECT COUNT(*) FROM ledger WHERE intent='propose_reorder'")
    check("idempotency: a repeated trigger makes no second order", before == after,
          "%d then %d" % (before, after))

    # --- marketing and verdict shape ---
    cells = marketing.handle.last.get("cells", [])
    check("marketing: every cell has a rule and an action",
          cells and all(c["action"] and c["reason"] for c in cells), "%d cells" % len(cells))
    verdicts = {v["product_id"]: v["diagnosis"]["verdict"] for v in verdict.handle.last}
    check("verdict: the site defect is not called a bad product",
          verdicts.get("p_mug") == "FIX_SITE", "p_mug -> %s" % verdicts.get("p_mug"))
    check("verdict: the bad product is killed",
          verdicts.get("p_candle") == "KILL", "p_candle -> %s" % verdicts.get("p_candle"))

    # --- model provider ---
    st = model.status()
    print("\n  model provider: %s (%s)" % (st["label"], st["detail"]))
    if st["provider"] != "rules_only":
        try:
            text, meta = model.complete("Reply with exactly: ok")
            check("model provider responds", "ok" in text.lower(), text.strip()[:40])
        except Exception as exc:                               # noqa: BLE001
            check("model provider responds", False, str(exc)[:90])

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 78)
    print("  %d checks, %d failed, %.1fs" % (len(RESULTS), len(failed), time.time() - t0))
    if failed:
        print("  FAILED: " + ", ".join(failed))
    return 1 if failed else 0


def _unused():
    pass


if __name__ == "__main__":
    sys.exit(main())
