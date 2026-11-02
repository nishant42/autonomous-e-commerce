"""Read-only interview view: the same engines, with explicit data provenance."""
import json
import math

from core import bus, db, harness, model
from agents import tools, marketing_agentic
from engines import allocator, budget, demand, quantity, verdict_evidence


def variant(conn, variant_id, config):
    cfg = harness.load_config(config)
    rec = demand.reconstruct(conn, variant_id, 90, cfg["policy"]["intended_discount_pct"])
    if rec.get("error"):
        return None
    terms = tools.supplier_terms(conn, variant_id)
    if not terms:
        return None
    econ = tools.economics(conn, variant_id)
    on_hand = db.scalar(conn, "SELECT on_hand FROM inventory_snapshot WHERE variant_id=? ORDER BY ts DESC LIMIT 1",
                        (variant_id,))
    on_order = tools.open_orders(conn, variant_id)["on_order"]
    label = db.one(conn, "SELECT v.colour,v.sku,p.name product FROM variant v JOIN product p ON p.id=v.product_id WHERE v.id=?", (variant_id,))
    return {"name": label["colour"], "label": "%s · %s" % (label["product"], label["colour"] or label["sku"]),
            "reconstruction": rec, "terms": terms, "economics": econ, "policy": cfg["policy"],
            "config": config, "on_order": on_order,
            "decision": quantity.order(rec, terms, cfg["policy"], on_hand, on_order, econ),
            "before_order": quantity.order(rec, terms, cfg["policy"], 0, 0, econ)}


def quantity_preview(conn, data):
    cu, co = float(data["cu"]), float(data["co"])
    if not all(math.isfinite(v) and 0 < v <= 10000 for v in (cu, co)):
        raise ValueError("costs must be finite positive values up to 10000")
    v = variant(conn, "v_black", "reorder")
    if not v:
        raise ValueError("no towel history")
    econ = dict(v["economics"], cm_per_unit=cu, lost_customer_value=0,
                holding_cost_per_unit_month=0, expected_markdown_per_unit=co)
    mode = data.get("inventory", "live")
    if mode not in ("live", "before"):
        raise ValueError("inventory must be live or before")
    on_hand = v["decision"]["on_hand"] if mode == "live" else 0
    on_order = v["on_order"] if mode == "live" else 0
    return quantity.order(v["reconstruction"], v["terms"], v["policy"], on_hand, on_order, econ)


def snapshot(conn, include_live=False):
    out = {"generated_at": db.now(), "variants": {},
           "provenance": {"towels": "Seeded 90-day case study", "advertising": "Simulated ad measurements",
                          "shop": "Imported local Medusa demo orders and reviews"}}
    for vid, cfg in (("v_black", "reorder"), ("v_white", "reorder"), ("v_yoghurt", "reorder_fresh")):
        result = variant(conn, vid, cfg)
        if result:
            out["variants"][vid] = result
    if include_live:
        for row in db.rows(conn, "SELECT v.id FROM variant v WHERE id LIKE 'medv_%' ORDER BY"
                                " (SELECT COALESCE(SUM(units),0) FROM sales_fact WHERE variant_id=v.id) DESC LIMIT 8"):
            result = variant(conn, row["id"], "reorder")
            if result:
                out["variants"][row["id"]] = result
    out["model"] = db.one(conn, "SELECT id, family, out_sample, features, diagnostics, promotion_reason,"
                          " n_train,n_test,trained_at FROM model_registry"
                          " WHERE promoted=1 AND target='orders_7d' ORDER BY id DESC LIMIT 1")
    if out["model"]:
        for k, fallback in (("features", []), ("out_sample", {}), ("diagnostics", {})):
            out["model"][k] = json.loads(out["model"][k] or json.dumps(fallback))
    out["forecast_benchmark"] = db.one(conn, "SELECT family, promoted, out_sample, promotion_reason FROM model_registry"
                                        " WHERE target='demand_horizon' ORDER BY id DESC LIMIT 1")
    cfg = harness.load_config("marketing_allocator")
    policy = dict(harness.load_config("policy"), **cfg["policy"])
    product_id = "p_towel"
    margin = tools.margin_table(conn, product_id)
    target = allocator.target_cpa(margin["cm_per_unit"], policy["payback_factor"])
    cover, health = tools.stock_cover(conn, product_id), tools.signal_health(conn, product_id)
    experiment = tools.experiment_budget(conn, product_id)
    cells = allocator.cell_stats(conn, product_id, 7)
    predicted = allocator.model_view(conn, product_id, cells, target)
    out["marketing"] = {"policy": policy, "target_cpa": target, "margin": margin,
                        "holdout": tools.holdout_readout(conn, product_id), "health": health,
                        "cells": [dict(c, explanation=marketing_agentic.options_for(
                            conn, c, target, policy, cover, health, experiment,
                            predicted.get(c["cell_id"], {}).get("expected_cpa"))) for c in cells]}
    vp = harness.load_config("product_verdict")["policy"]
    out["verdicts"] = [verdict_evidence.build(conn, p["id"], vp)
                       for p in db.rows(conn, "SELECT id FROM product ORDER BY id")]
    out["policy"] = harness.load_config("policy")
    out["provider"] = {k: v for k, v in model.status().items() if k in ("provider", "label", "unreachable")}
    out["queue"] = bus.depth(conn)
    out["bus"] = {"max_attempts": bus.MAX_ATTEMPTS, "lease_seconds": bus.LOCK_TIMEOUT_SECONDS}
    out["runs"] = db.rows(conn, "SELECT agent, started_at, mode, steps,tokens,outcome FROM agent_run ORDER BY started_at DESC LIMIT 12")
    out["reviews"] = {"classified": db.scalar(conn, "SELECT COUNT(*) FROM order_review WHERE sentiment IS NOT NULL"),
                      "total": db.scalar(conn, "SELECT COUNT(*) FROM order_review")}
    out["substitution_pairs"] = db.scalar(conn, "SELECT COUNT(*) FROM substitute_pair")
    out["budget"] = budget.allocate(conn, 3000)
    return out
