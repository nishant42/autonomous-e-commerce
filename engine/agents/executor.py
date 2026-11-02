"""The last mile: making an approved decision change the real shop.

Everything upstream decides. This subscribes to what the gateway actually
approved and carries it out. It is deliberately the only component that writes
to the shop, it only ever reacts to a ledger entry, and it writes what it did
back into the ledger so the loop is closed and auditable.

  reorder executed        -> stock arrives in the shop
  verdict KILL approved   -> the product comes off sale
"""
import json

from core import bus, db


def _note(conn, ledger_id, text):
    conn.execute("UPDATE ledger SET reason = reason || ' | ' || ? WHERE id=?", (text, ledger_id))


@bus.subscribe("reorder.executed")
def on_reorder(conn, payload):
    """A purchase order was approved. In this demo the supplier ships at once,
    so the stock appears; in production this fires on the 3PL receipt instead."""
    from adapters import medusa
    if not medusa.configured():
        return
    body = payload.get("payload") or {}
    qty = int(body.get("qty") or 0)
    variant = body.get("variant_id")
    if qty <= 0 or not variant:
        return
    try:
        out = medusa.receive_stock(conn, variant, qty)
    except Exception as exc:                                    # noqa: BLE001
        conn.execute("INSERT INTO anomaly (ts, agent, kind, severity, note) VALUES (?,?,?,?,?)",
                     (db.now(), "executor", "shop_write_failed", "high",
                      "stock for %s: %r" % (variant, exc)))
        return
    if out.get("skipped"):
        return
    _note(conn, payload.get("ledger_id"),
          "shop updated: %s stock %s -> %s" % (variant, out["was"], out["now"]))
    conn.execute("INSERT INTO anomaly (ts, agent, kind, severity, note) VALUES (?,?,?,?,?)",
                 (db.now(), "executor", "stock_received", "info",
                  "%s units of %s arrived; the shop now holds %s" % (out["received"], variant, out["now"])))


@bus.subscribe("publish_verdict.executed")
def on_verdict(conn, payload):
    """A verdict was approved. A KILL takes the product off sale; anything else
    makes sure it is on sale."""
    from adapters import medusa
    if not medusa.configured():
        return
    body = payload.get("payload") or {}
    product, verdict = body.get("product_id"), body.get("verdict")
    if not product:
        return
    want = "draft" if verdict == "KILL" else "published"
    try:
        out = medusa.set_product_status(conn, product, want)
    except Exception as exc:                                    # noqa: BLE001
        conn.execute("INSERT INTO anomaly (ts, agent, kind, severity, note) VALUES (?,?,?,?,?)",
                     (db.now(), "executor", "shop_write_failed", "high",
                      "status for %s: %r" % (product, exc)))
        return
    if out.get("skipped"):
        return
    _note(conn, payload.get("ledger_id"), "shop updated: product set to %s" % out["status"])
    if want == "draft":
        conn.execute("INSERT INTO anomaly (ts, agent, kind, severity, note) VALUES (?,?,?,?,?)",
                     (db.now(), "executor", "product_withdrawn", "high",
                      "%s has been taken off sale in the shop" % product))
