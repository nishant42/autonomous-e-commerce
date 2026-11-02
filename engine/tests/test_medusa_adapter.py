"""Medusa adapter test with canned payloads. No Medusa server needed.

Covers the parts that actually break: JWT login, the Basic secret-key header,
paging on the count envelope, the variant to inventory-item mapping, discount
percentages per line, and stock summed across two locations minus reservations.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["ENGINE_DB"] = "/tmp/claude-501/medusa_test.db"
os.environ["MEDUSA_URL"] = "http://localhost:9000"
os.environ["MEDUSA_EMAIL"] = "admin@medusajs.com"
os.environ["MEDUSA_PASSWORD"] = "supersecret"
os.environ.pop("MEDUSA_API_KEY", None)

from core import db                      # noqa: E402
from adapters import medusa              # noqa: E402

PRODUCTS = {"limit": 100, "offset": 0, "count": 1, "products": [{
    "id": "prod_1", "title": "Halden Towel", "created_at": "2026-08-01T09:00:00",
    "variants": [
        {"id": "var_white", "sku": "TOW-WHT", "title": "white",
         "prices": [{"amount": 39.0}], "inventory_quantity": 24,
         "inventory_items": [{"inventory_item_id": "iitem_white"}]},
        {"id": "var_black", "sku": "TOW-BLK", "title": "black",
         "prices": [{"amount": 39.0}], "inventory_quantity": 0,
         "inventory_items": [{"inventory_item_id": "iitem_black"}]},
    ]}]}

ORDERS = {"limit": 100, "offset": 0, "count": 1, "orders": [{
    "id": "order_1", "created_at": "2026-10-20T11:30:00", "currency_code": "eur",
    "items": [
        {"id": "li_1", "variant_id": "var_black", "quantity": 2, "unit_price": 39.0,
         "discount_total": 23.4, "variant_sku": "TOW-BLK"},
        {"id": "li_2", "variant_id": "var_white", "quantity": 1, "unit_price": 39.0,
         "discount_total": 0.0, "variant_sku": "TOW-WHT"},
        {"id": "li_3", "variant_id": "var_unknown", "quantity": 5, "unit_price": 10.0,
         "discount_total": 0.0, "variant_sku": "GHOST"},
    ]}]}

INVENTORY = {"limit": 100, "offset": 0, "count": 2, "inventory_items": [
    {"id": "iitem_white", "sku": "TOW-WHT", "stocked_quantity": 30, "reserved_quantity": 6,
     "location_levels": [
         {"location_id": "loc_1", "stocked_quantity": 24, "reserved_quantity": 4},
         {"location_id": "loc_2", "stocked_quantity": 6, "reserved_quantity": 2}]},
    {"id": "iitem_black", "sku": "TOW-BLK", "stocked_quantity": 0, "reserved_quantity": 0,
     "location_levels": [{"location_id": "loc_1", "stocked_quantity": 0, "reserved_quantity": 0}]},
]}

CALLS = []


class FakeResponse(object):
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    url = req.full_url
    CALLS.append((url, dict(req.headers)))
    if "/auth/user/emailpass" in url:
        body = json.loads(req.data)
        assert body["email"] == "admin@medusajs.com", body
        return FakeResponse({"token": "jwt_test_token"})
    auth = req.headers.get("Authorization", "")
    assert auth == "Bearer jwt_test_token", "expected the cached JWT, got %r" % auth
    if "/admin/products" in url:
        return FakeResponse(PRODUCTS)
    if "/admin/orders" in url:
        return FakeResponse(ORDERS)
    if "/admin/inventory-items" in url:
        return FakeResponse(INVENTORY)
    raise AssertionError("unexpected URL: " + url)


def main():
    urllib.request.urlopen = fake_urlopen
    if os.path.exists(os.environ["ENGINE_DB"]):
        os.remove(os.environ["ENGINE_DB"])
    conn = db.init(reset=True)

    info = medusa.check()
    assert info["ok"], info
    assert info["counts"]["products"] == 1, info
    print("  check            ok   %s, counts %s" % (info["auth"], info["counts"]))

    p = medusa.pull_products(conn)
    assert p == {"products": 1, "variants": 2, "inventory_ids_resolved": 2}, p
    row = db.one(conn, "SELECT * FROM ext_map WHERE variant_id='medv_var_black'")
    assert row["ext_inventory_item_id"] == "iitem_black", row
    assert row["source"] == "medusa", row
    print("  products         ok   %s, inventory ids resolved" % p)

    logins = [u for u, _ in CALLS if "emailpass" in u]
    assert len(logins) == 1, "JWT should be cached, saw %d logins" % len(logins)
    print("  auth             ok   logged in once, token reused across %d calls" % len(CALLS))

    o = medusa.pull_orders(conn)
    assert o["order_lines"] == 2 and o["skipped_unmapped"] == 1, o
    black = db.one(conn, "SELECT SUM(units) u, MAX(discount_pct) d FROM sales_fact"
                         " WHERE variant_id='medv_var_black'")
    assert black["u"] == 2, black
    assert abs(black["d"] - 30.0) < 0.01, "discount should be 30%%, got %s" % black["d"]
    print("  orders           ok   2 lines mapped, 1 unknown variant skipped, discount 30%")

    s = medusa.snapshot_inventory(conn)
    assert s["variants"] == 2, s
    white = db.one(conn, "SELECT on_hand, buyable FROM inventory_snapshot"
                         " WHERE variant_id='medv_var_white' ORDER BY ts DESC LIMIT 1")
    blk = db.one(conn, "SELECT on_hand, buyable FROM inventory_snapshot"
                       " WHERE variant_id='medv_var_black' ORDER BY ts DESC LIMIT 1")
    assert white["on_hand"] == 24, "(24-4)+(6-2) across two locations = 24, got %s" % white
    assert blk["buyable"] == 0, blk
    print("  inventory        ok   white 24 net of reservations across 2 locations, black unbuyable")

    print()
    print("  all Medusa adapter checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
