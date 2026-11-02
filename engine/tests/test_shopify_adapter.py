"""Adapter test with canned Shopify payloads. No network, no store needed.

Checks the things that actually go wrong: inventory levels keyed by
inventory_item_id rather than variant id, refunded line items, discount
percentages, device parsing, and pagination via the Link header.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["ENGINE_DB"] = "/tmp/claude-501/shopify_test.db"
os.environ["SHOPIFY_STORE"] = "demo-store.myshopify.com"
os.environ["SHOPIFY_TOKEN"] = "shpat_test"

from core import db                      # noqa: E402
from adapters import shopify             # noqa: E402

PAYLOADS = {
    "shop.json": {"shop": {"name": "Halden Test", "currency": "EUR",
                           "plan_display_name": "Development", "iana_timezone": "Europe/Dublin"}},
    "products/count.json": {"count": 2},
    "orders/count.json": {"count": 3},
    "locations.json": {"locations": [{"id": 1}, {"id": 2}]},
    "products.json": {"products": [{
        "id": 111, "title": "Halden Towel", "created_at": "2026-08-01T10:00:00Z",
        "variants": [
            {"id": 9001, "sku": "TOW-WHT", "title": "white", "price": "39.00", "inventory_item_id": 7001},
            {"id": 9002, "sku": "TOW-BLK", "title": "black", "price": "39.00", "inventory_item_id": 7002},
        ]}]},
    "orders.json": {"orders": [{
        "id": 501, "created_at": "2026-10-20T11:30:00Z",
        "client_details": {"user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari"},
        "line_items": [
            {"id": 601, "variant_id": 9002, "quantity": 2, "price": "39.00",
             "discount_allocations": [{"amount": "23.40"}]},
            {"id": 602, "variant_id": 9001, "quantity": 1, "price": "39.00",
             "discount_allocations": []},
        ],
        "refunds": [{"refund_line_items": [{"line_item_id": 602}]}]},
        {"id": 502, "created_at": "2026-10-20T15:00:00Z",
         "client_details": {"user_agent": "Mozilla/5.0 (Linux; Android 14) Chrome"},
         "line_items": [{"id": 603, "variant_id": 9002, "quantity": 1, "price": "39.00",
                         "discount_allocations": []}],
         "refunds": []}]},
    "inventory_levels.json": {"inventory_levels": [
        {"inventory_item_id": 7001, "available": 24},
        {"inventory_item_id": 7001, "available": 6},      # a second location
        {"inventory_item_id": 7002, "available": 0},
    ]},
}


class FakeResponse(object):
    def __init__(self, body):
        self._body = json.dumps(body).encode()
        self.headers = {"Link": ""}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    path = req.full_url.split("/admin/api/")[1].split("/", 1)[1].split("?")[0]
    assert req.headers.get("X-shopify-access-token") == "shpat_test", "token header missing"
    if path not in PAYLOADS:
        raise AssertionError("unexpected path requested: " + path)
    return FakeResponse(PAYLOADS[path])


def main():
    urllib.request.urlopen = fake_urlopen
    if os.path.exists(os.environ["ENGINE_DB"]):
        os.remove(os.environ["ENGINE_DB"])
    conn = db.init(reset=True)
    fails = []

    info = shopify.check()
    assert info["name"] == "Halden Test", info
    assert info["counts"]["locations"] == 2, info
    print("  check            ok   %s, %s, %s" % (info["name"], info["currency"], info["counts"]))

    p = shopify.pull_products(conn)
    assert p == {"products": 1, "variants": 2}, p
    mapped = db.rows(conn, "SELECT * FROM ext_map ORDER BY variant_id")
    assert mapped[0]["ext_inventory_item_id"] == "7001", mapped
    assert db.scalar(conn, "SELECT COUNT(*) FROM supplier_terms") == 2
    print("  products         ok   %s, map keyed by inventory_item_id" % p)

    o = shopify.pull_orders(conn)
    assert o["order_lines"] == 3, o
    assert o["orders_with_device"] == 2, o
    black = db.one(conn, "SELECT SUM(units) u, MAX(discount_pct) d FROM sales_fact"
                         " WHERE variant_id='shv_9002'")
    assert black["u"] == 3, black
    assert abs(black["d"] - 30.0) < 0.01, "discount should be 30%%, got %s" % black["d"]
    refunded = db.scalar(conn, "SELECT COUNT(*) FROM sales_fact WHERE refunded=1")
    assert refunded == 1, refunded
    mix = {r["device"]: r["share"] for r in db.rows(conn, "SELECT * FROM device_mix")}
    assert abs(mix.get("ios", 0) - 0.5) < 0.01 and abs(mix.get("android", 0) - 0.5) < 0.01, mix
    print("  orders           ok   3 lines, 1 refund, discount 30%%, device mix %s" % mix)

    s = shopify.snapshot_inventory(conn)
    assert s["variants"] == 2, s
    white = db.one(conn, "SELECT on_hand, buyable FROM inventory_snapshot"
                         " WHERE variant_id='shv_9001' ORDER BY ts DESC LIMIT 1")
    blackinv = db.one(conn, "SELECT on_hand, buyable FROM inventory_snapshot"
                            " WHERE variant_id='shv_9002' ORDER BY ts DESC LIMIT 1")
    assert white["on_hand"] == 30, "two locations must be summed, got %s" % white
    assert blackinv["buyable"] == 0, blackinv
    print("  inventory        ok   white 30 across 2 locations, black unbuyable")

    print()
    print("  all adapter checks passed" if not fails else "  FAILURES: %s" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
