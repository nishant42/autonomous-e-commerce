"""Model-led product diagnosis with evidence, exposure and supply constraints."""
import math

from core import bus, db, harness
from engines import verdict_evidence
from agents import tools

AGENT = "product_verdict"
VERDICTS = verdict_evidence.VERDICTS
TOOL_SPEC = [
    {"name": name, "args": args, "description": description}
    for name, args, description in [
        ("funnel_rates", {"product_id": "the product"}, "Measured funnel stages, when available."),
        ("evidence_pack", {"product_id": "the product"}, "Required: shop evidence, funnel diagnosis, permitted verdicts and computed fixes."),
        ("returns_by_variant", {"variant_id": "a variant"}, "Refunded units and return rate."),
        ("stock_cover", {"product_id": "the product"}, "Stock cover per variant."),
        ("margin_table", {"product_id": "the product"}, "Contribution after costs and returns."),
        ("portfolio_memory", {}, "Past verdicts and their recorded rationale."),
    ]
]
TASK = """Judge product {product}. Investigate in your own order; call evidence_pack at least once.
Decide whether the product, shop, price, or traffic needs attention.
Only choose from permitted_verdicts. Insufficient exposure means CONTINUE_TEST.
Supply-limited weak sales cannot justify KILL. A KILL recommendation always waits for a person.
Choose first_fix from the computed actions, or 'none'; do not invent remedies or numeric claims.
Return {{"answer": {{"verdict": "<permitted verdict>", "confidence": <0 to 1>,
"why": "<brief evidence-based reason>", "first_fix": "<computed action or none>"}}}}.
"""


@bus.subscribe("verdict.agentic")
def handle(conn, payload):
    cfg = harness.load_config(AGENT)
    policy = dict(harness.load_config("policy"), **cfg["policy"])
    h = harness.Harness(conn, AGENT, cfg, trigger=payload.get("trigger", "agentic"))
    for spec in TOOL_SPEC:
        if hasattr(tools, spec["name"]):
            h.register(spec["name"], getattr(tools, spec["name"]))
    rows = []
    for product_id in payload["products"]:
        h.evidence = []
        h.new_decision(product_id)
        variants = [r["id"] for r in db.rows(conn, "SELECT id FROM variant WHERE product_id=?", (product_id,))]

        def evidence_pack(conn_, product_id=product_id):
            return verdict_evidence.build(conn_, product_id, policy)

        h.register("evidence_pack", evidence_pack)
        out, events = h.investigate(TASK.format(product=product_id), TOOL_SPEC,
                                   {"product_id": [product_id], "variant_id": variants},
                                   required=["evidence_pack"], max_steps=7)
        packed, _ = h.read("evidence_pack", product_id=product_id)
        actions = packed["actions"]
        decision = {"verdict": packed["engine_verdict"], "confidence": packed["confidence"],
                    "why": packed["engine_reason"], "first_fix": actions[0] if actions else "none",
                    "source": "engine default"}
        if out:
            answer = out["answer"]
            confidence = answer.get("confidence")
            if (answer.get("verdict") in packed["permitted_verdicts"]
                    and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                    and math.isfinite(confidence) and 0 <= confidence <= 1
                    and answer.get("first_fix", "none") in actions + ["none"]):
                decision = {"verdict": answer["verdict"], "confidence": float(confidence),
                            "why": answer["why"], "first_fix": answer.get("first_fix", "none"),
                            "source": "agent"}
            else:
                h.step("verification", "model verdict rejected", "invalid confidence, fix, or guarded verdict")
        # CONTINUE_TEST is a recorded finding; it does not authorize spending.
        row = h.propose("publish_verdict",
                        {"product_id": product_id, "verdict": decision["verdict"],
                         "confidence": float(decision["confidence"])}, policy,
                        ctx={"exposure_met": packed["exposure_met"] or decision["verdict"] == "CONTINUE_TEST"},
                        rationale=decision["why"], period=payload.get("period", db.now()[:10]))
        h.step("judgment", "verdict on " + product_id, decision["why"], data=decision, fn=handle)
        rows.append({"product_id": product_id, "decision": decision,
                     "engine_verdict": packed["engine_verdict"], "evidence": packed["evidence"],
                     "tool_calls": [e for e in events if e["kind"] == "tool_call"], "ledger": dict(row)})
    h.finish("agentic verdicts on %d products" % len(rows))
    handle.last = rows
    return rows


handle.last = []
