"""Combine shop evidence with funnel diagnosis when that measurement exists."""
from core import db
from engines import allocator, funnel, live_verdict
from agents import tools

VERDICTS = ["SCALE", "FIX_SITE", "REPRICE", "NEW_CREATIVE", "CONTINUE_TEST", "KILL"]


def build(conn, product_id, policy):
    shop = live_verdict.judge(conn, product_id)
    if shop.get("error"):
        raise ValueError(shop["error"])
    evidence = shop["evidence"]
    source = "orders, inventory and classified reviews"
    raw = shop["verdict"]
    verdict = raw if raw in VERDICTS else "CONTINUE_TEST"
    reason, actions, confidence = shop["because"], shop["actions"], shop["confidence"]
    exposure = raw != "NOT_ENOUGH_EVIDENCE"
    rates, diag = None, None
    if db.scalar(conn, "SELECT COUNT(*) FROM funnel_daily WHERE product_id=?", (product_id,)):
        rates = funnel.rates(conn, product_id, policy["window_days"])
        margin = tools.margin_table(conn, product_id)["cm_per_unit"]
        diag = funnel.diagnose(rates, allocator.target_cpa(margin, policy["payback_factor"]), margin, policy)
        # Classified customer complaints are direct product evidence; otherwise
        # use the measured funnel to separate shop, traffic, offer and price.
        if raw != "KILL":
            verdict, confidence = diag["verdict"], diag["confidence"]
            reason, actions, exposure = diag["diagnosis"], diag["actions"], diag["exposure_met"]
            source = "funnel and shop evidence"
    supply_limited = evidence["demand_lost_to_stockouts"] >= max(3, 0.15 * evidence["units_sold"])
    neg = evidence["sentiment"].get("negative_share")
    direct_complaints = neg is not None and neg >= 0.5
    if supply_limited and not direct_complaints and verdict == "KILL":
        verdict, confidence = "CONTINUE_TEST", 0.4
        reason = "supply constraint must be fixed before judging the product"
        actions = ["restore stock and measure demand again"]
    allowed = list(VERDICTS)
    if not exposure:
        allowed = ["CONTINUE_TEST"]
        verdict = "CONTINUE_TEST"
    elif supply_limited and not direct_complaints:
        allowed.remove("KILL")
    return {"product_id": product_id, "name": shop["name"], "source": source,
            "raw_shop_verdict": raw, "engine_verdict": verdict, "engine_reason": reason,
            "confidence": confidence, "actions": actions, "evidence": evidence,
            "funnel": rates, "diagnosis": diag, "exposure_met": exposure,
            "supply_limited": supply_limited, "permitted_verdicts": allowed}
