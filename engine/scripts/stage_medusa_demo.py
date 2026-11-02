#!/usr/bin/env python3
"""Make the live Medusa shop tell the story the engine was built for.

The seeded demo ships everything at EUR 10 with a million units in stock, which
is fine for Medusa's own tutorial and useless for a replenishment decision. This
sets believable prices and stock levels, and deliberately leaves one variant per
product out of stock so the engine's availability logic has something real to
find.

Writes go through the Admin API, not through the adapter: the adapter stays
read-only on purpose, because an integration that can change the shop is a very
different thing to review.

  python3 scripts/stage_medusa_demo.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters import medusa                                    # noqa: E402

# product title -> (price in EUR, stock per variant in order; 0 means unbuyable)
PLAN = {
    "Medusa T-Shirt": (29.0, [60, 0, 42, 18, 90, 12, 0, 150]),
    "Medusa Sweatshirt": (59.0, [34, 0, 22, 96]),
    "Medusa Sweatpants": (49.0, [28, 16, 0, 210]),
    "Medusa Shorts": (39.0, [44, 31, 7, 0]),
}


def post(path, body):
    url = medusa.config()[0] + path
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": medusa._auth_header(), "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP %s on %s: %s"
                           % (exc.code, path, exc.read().decode("utf-8", "replace")[:250]))


def main():
    if not medusa.configured():
        print("Set MEDUSA_URL, MEDUSA_EMAIL and MEDUSA_PASSWORD first.")
        return 1

    locations = medusa._get("/admin/stock-locations", {"limit": 5})["stock_locations"]
    location_id = locations[0]["id"]
    print("stock location: %s (%s)" % (locations[0].get("name"), location_id))

    body = medusa._get("/admin/products", {
        "limit": 50, "fields": "*variants,*variants.prices,*variants.inventory_items"})
    priced = stocked = failed = 0

    for product in body["products"]:
        title = product.get("title")
        if title not in PLAN:
            print("  skipping %s (not in the plan)" % title)
            continue
        price, stock_plan = PLAN[title]
        print("\n%s  -> EUR %.2f" % (title, price))
        for i, variant in enumerate(product.get("variants") or []):
            want = stock_plan[i] if i < len(stock_plan) else 25
            label = variant.get("title") or variant["id"]

            try:
                post("/admin/products/%s/variants/%s" % (product["id"], variant["id"]),
                     {"prices": [{"amount": price, "currency_code": "eur"}]})
                priced += 1
            except RuntimeError as exc:
                print("    %-6s price FAILED: %s" % (label, exc))
                failed += 1

            items = variant.get("inventory_items") or []
            if not items:
                print("    %-6s no inventory item, stock left alone" % label)
                continue
            item_id = items[0]["inventory_item_id"]
            try:
                post("/admin/inventory-items/%s/location-levels/%s" % (item_id, location_id),
                     {"stocked_quantity": want})
                stocked += 1
                print("    %-6s stock %-6s %s" % (label, want, "<- deliberately out of stock" if want == 0 else ""))
            except RuntimeError as exc:
                print("    %-6s stock FAILED: %s" % (label, exc))
                failed += 1

    print("\n%d prices set, %d stock levels set, %d failures" % (priced, stocked, failed))
    print("Now re-read it into the engine:  python3 run.py medusa sync")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
