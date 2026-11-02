"""Funnel decomposition and the product-versus-site discriminator.

The question the portfolio lives on: this product is not working - is that the
product, the site, the traffic, or the price? Each has a different signature,
and each has a different remedy, so guessing is expensive.
"""
from core import db

# Bands from comparable stores; configurable per category.
BENCHMARK = {
    "pdp_rate":      (0.35, 0.75),    # sessions -> product page
    "atc_rate":      (0.06, 0.14),    # pdp -> add to cart
    "checkout_rate": (0.55, 0.80),    # atc -> checkout started
    "purchase_rate": (0.55, 0.80),    # checkout -> order
    "refund_rate":   (0.00, 0.06),
    "ctr":           (0.008, 0.025),  # ad click-through
}


def rates(conn, product_id, window_days=14):
    f = db.one(conn, """
        SELECT SUM(sessions) s, SUM(pdp_views) p, SUM(add_to_cart) a,
               SUM(checkout_start) c, SUM(orders) o, SUM(refunds) r
        FROM funnel_daily WHERE product_id=? AND day >= date((SELECT MAX(day) FROM funnel_daily), ?)""",
        (product_id, "-%d day" % window_days))
    ad = db.one(conn, """
        SELECT SUM(clicks) clicks, SUM(impressions) imps, SUM(spend) spend, SUM(orders) orders
        FROM ad_metrics WHERE product_id=? AND is_holdout=0
          AND day >= date((SELECT MAX(day) FROM ad_metrics), ?)""", (product_id, "-%d day" % window_days))
    d = lambda a, b: (a / b) if (a and b) else 0.0        # noqa: E731
    return {
        "sessions": f["s"] or 0, "pdp_views": f["p"] or 0, "add_to_cart": f["a"] or 0,
        "checkout_start": f["c"] or 0, "orders": f["o"] or 0, "refunds": f["r"] or 0,
        "spend": ad["spend"] or 0.0, "clicks": ad["clicks"] or 0, "impressions": ad["imps"] or 0,
        "pdp_rate": round(d(f["p"], f["s"]), 4),
        "atc_rate": round(d(f["a"], f["p"]), 4),
        "checkout_rate": round(d(f["c"], f["a"]), 4),
        "purchase_rate": round(d(f["o"], f["c"]), 4),
        "refund_rate": round(d(f["r"], f["o"]), 4),
        "ctr": round(d(ad["clicks"], ad["imps"]), 4),
        "cpa": round((ad["spend"] / f["o"]), 2) if f["o"] else None,
    }


def _flag(value, key):
    lo, hi = BENCHMARK[key]
    if key == "refund_rate":
        return "high" if value > hi else "ok"
    if value < lo:
        return "low"
    if value > hi:
        return "high"
    return "ok"


def diagnose(r, target_cpa, cm1, policy):
    """Return diagnosis, verdict, confidence and ranked actions.

    The signature matters more than any single rate: the same symptom
    (few orders) has four different causes, and only one of them is 'bad product'.
    """
    flags = {k: _flag(r[k], k) for k in BENCHMARK}
    findings = []
    verdict, confidence = None, 0.5

    exposure_ok = (r["sessions"] >= policy["min_sessions"]
                   and r["spend"] >= policy["min_spend_eur"])
    if not exposure_ok:
        return {"flags": flags, "diagnosis": "insufficient exposure",
                "verdict": "CONTINUE_TEST", "confidence": 0.0,
                "actions": ["keep the test running: %d sessions and EUR %.0f spent is below the gate of %d / EUR %.0f"
                            % (r["sessions"], r["spend"], policy["min_sessions"], policy["min_spend_eur"])],
                "exposure_met": False}

    # --- site-side signatures: people want it, the shop is losing them ---
    if flags["atc_rate"] == "ok" and flags["checkout_rate"] == "low":
        findings.append(("SITE", "add-to-cart is healthy (%.1f%%) but only %.0f%% reach checkout"
                         % (r["atc_rate"] * 100, r["checkout_rate"] * 100),
                         ["show delivery cost and date on the product page",
                          "enable express wallets (Apple/Google Pay, Shop Pay)",
                          "move trust and returns copy above the cart summary"]))
    if flags["purchase_rate"] == "low":
        findings.append(("SITE", "%.0f%% of started checkouts complete" % (r["purchase_rate"] * 100),
                         ["check payment methods and 3DS failure rate",
                          "remove account-creation requirement",
                          "test shipping threshold at the cart level"]))
    if flags["pdp_rate"] == "low":
        findings.append(("SITE", "only %.0f%% of sessions reach a product page" % (r["pdp_rate"] * 100),
                         ["send ads to the product page, not the home page",
                          "cut hero carousel, one product one promise above the fold"]))

    # --- product/offer-side signatures: the shop works, the offer does not ---
    if flags["atc_rate"] == "low" and flags["pdp_rate"] in ("ok", "high"):
        findings.append(("PRODUCT", "people reach the product and do not want it at this price (%.1f%% add to cart)"
                         % (r["atc_rate"] * 100),
                         ["test price and bundle, not creative",
                          "re-shoot the two objections buyers raise in support tickets",
                          "if the rate does not move, this is a product verdict, not a site one"]))
    if flags["refund_rate"] == "high":
        findings.append(("PRODUCT", "refunds at %.0f%% point at the product itself, not the funnel"
                         % (r["refund_rate"] * 100),
                         ["pull the refund reasons and act on the top one",
                          "raise it with the supplier or change the size/colour mix",
                          "a product with this refund rate cannot be scaled profitably"]))

    # --- traffic-side ---
    if flags["ctr"] == "low":
        findings.append(("TRAFFIC", "ad click-through %.2f%% is below the band" % (r["ctr"] * 100),
                         ["new creative concepts before any budget change",
                          "check audience breadth and placement mix"]))

    # --- economics ---
    unit_econ_bad = r["cpa"] is not None and r["cpa"] > target_cpa * 1.3
    if unit_econ_bad and not findings:
        findings.append(("ECONOMICS", "funnel is within every band but CPA EUR %.0f exceeds target EUR %.0f"
                         % (r["cpa"], target_cpa),
                         ["raise price and re-test: the funnel can carry it",
                          "if price cannot move, this product does not clear its acquisition cost"]))

    owners = [f[0] for f in findings]
    if not findings:
        verdict, confidence = "SCALE", 0.85
        diagnosis = "no defect found: funnel inside every band and CPA within target"
    elif "SITE" in owners and "PRODUCT" not in owners:
        verdict, confidence = "FIX_SITE", 0.8
        diagnosis = "site-side loss: demand exists and the shop is leaking it"
    elif "PRODUCT" in owners and "SITE" not in owners:
        verdict, confidence = ("KILL" if (flags["refund_rate"] == "high" or unit_econ_bad) else "REPRICE"), 0.75
        diagnosis = "product-side: the offer is the problem, not the shop"
    elif owners == ["ECONOMICS"]:
        verdict, confidence = "REPRICE", 0.75
        diagnosis = "funnel is healthy and the economics are not: this is a price decision"
    elif "TRAFFIC" in owners and len(owners) == 1:
        verdict, confidence = "NEW_CREATIVE", 0.7
        diagnosis = "traffic-side: the product is not being judged yet because nobody is clicking"
    else:
        verdict, confidence = "FIX_SITE", 0.6
        diagnosis = "mixed signature: fix the site defect first, then re-judge the product"

    actions = []
    for _, _, acts in findings:
        actions.extend(acts)
    return {"flags": flags, "findings": [{"owner": o, "finding": f} for o, f, _ in findings],
            "diagnosis": diagnosis, "verdict": verdict, "confidence": confidence,
            "actions": actions, "exposure_met": True}
