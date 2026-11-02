#!/usr/bin/env python3
"""Place real orders in the real shop.

Every order here goes through Medusa's own Store API: a cart is created, line
items are added, an address and a shipping method are chosen, a payment session
is opened and the cart is completed. Medusa decrements its own stock. These are
real orders in a real shop, not rows inserted into our database.

Two things are simulated and said so plainly: who the shopper is, and when they
bought. The date is written into the order's metadata as `simulated_day`, and
the adapter uses it so the agents have history on a shop that is hours old.

  python3 scripts/shoppers.py --count 300 --days 60
  python3 scripts/shoppers.py --count 5 --days 0        # a few, dated today
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters import medusa                                    # noqa: E402

DEVICES = [("ios", 0.46), ("android", 0.29), ("desktop", 0.19), ("tablet", 0.06)]

# Shoppers leave a line about the product. One line is deliberately a problem
# product, so there is a real signal for a language model to find rather than
# uniform noise.
GOOD = ["Lovely quality, exactly as pictured.", "Fits perfectly and arrived early.",
        "Really happy with this, would buy again.", "Great fabric, washes well.",
        "Better than I expected for the price.", "Comfortable and well made.",
        "Delivery was quick and the item is lovely."]
BAD = ["The stitching came apart after one wash.", "Much thinner than it looks online.",
       "Sizing is completely wrong, had to send it back.", "Colour faded immediately, disappointed.",
       "Felt cheap for the money, returning it.", "Arrived misshapen and the seams are rough.",
       "Not as described at all, I want a refund."]
PROBLEM_PRODUCT = "Medusa Sweatpants"


def review_for(product):
    bad_chance = 0.72 if product == PROBLEM_PRODUCT else 0.12
    return random.choice(BAD if random.random() < bad_chance else GOOD)
FIRST = ["Mette", "Lars", "Sofie", "Anders", "Ida", "Jonas", "Freja", "Emil", "Clara", "Noah"]
LAST = ["Jensen", "Nielsen", "Hansen", "Pedersen", "Andersen", "Larsen", "Sorensen"]


def pick(weighted):
    r, acc = random.random(), 0.0
    for value, weight in weighted:
        acc += weight
        if r <= acc:
            return value
    return weighted[-1][0]


class Store(object):
    def __init__(self, base, key):
        self.base, self.key = base.rstrip("/"), key

    def call(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "content-type": "application/json", "x-publishable-api-key": self.key,
            "accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:220]
            raise RuntimeError("%s %s -> HTTP %s: %s" % (method, path, exc.code, detail))
        except urllib.error.URLError as exc:
            raise RuntimeError("cannot reach %s: %s" % (url, exc.reason))


def publishable_key():
    if os.environ.get("MEDUSA_PUBLISHABLE_KEY"):
        return os.environ["MEDUSA_PUBLISHABLE_KEY"]
    body = medusa._get("/admin/api-keys", {"limit": 20})
    for k in body.get("api_keys", []):
        if k.get("type") == "publishable" and k.get("token"):
            return k["token"]
    raise RuntimeError("no publishable key found; create one in Settings -> Publishable API Keys")


def catalogue(store, region_id):
    """Only variants that can actually be bought. Some are deliberately out of
    stock, and a shopper cannot buy those either."""
    out = []
    body = store.call("GET", "/store/products?limit=50&region_id=" + region_id +
                      "&fields=title,handle,*variants,+variants.inventory_quantity")
    for p in body.get("products", []):
        for v in p.get("variants") or []:
            qty = v.get("inventory_quantity")
            if v.get("manage_inventory") and qty is not None and qty <= 0:
                continue
            out.append({"product": p.get("title"), "variant_id": v["id"], "stock": qty,
                        "title": v.get("title"), "sku": v.get("sku")})
    return out


def place(store, region_id, item, qty, day, device):
    cart = store.call("POST", "/store/carts", {"region_id": region_id})["cart"]
    cid = cart["id"]
    store.call("POST", "/store/carts/%s/line-items" % cid,
               {"variant_id": item["variant_id"], "quantity": qty})
    name = random.choice(FIRST)
    store.call("POST", "/store/carts/%s" % cid, {
        "email": "%s.%s@example.test" % (name.lower(), random.randint(100, 999)),
        "metadata": {"simulated_day": day, "device": device, "source": "shopper-simulator",
                     "review": review_for(item["product"]), "product": item["product"]},
        "shipping_address": {"first_name": name, "last_name": random.choice(LAST),
                             "address_1": "%d Gade" % random.randint(1, 180), "city": "Copenhagen",
                             "postal_code": "%04d" % random.randint(1000, 2999), "country_code": "dk"},
        "billing_address": {"first_name": name, "last_name": random.choice(LAST),
                            "address_1": "%d Gade" % random.randint(1, 180), "city": "Copenhagen",
                            "postal_code": "%04d" % random.randint(1000, 2999), "country_code": "dk"}})
    opts = store.call("GET", "/store/shipping-options?cart_id=" + cid).get("shipping_options") or []
    if not opts:
        raise RuntimeError("no shipping option is available for this cart; add one in the admin "
                           "under Settings -> Locations & Shipping")
    store.call("POST", "/store/carts/%s/shipping-methods" % cid, {"option_id": opts[0]["id"]})
    coll = store.call("POST", "/store/payment-collections", {"cart_id": cid})["payment_collection"]
    store.call("POST", "/store/payment-collections/%s/payment-sessions" % coll["id"],
               {"provider_id": "pp_system_default"})
    done = store.call("POST", "/store/carts/%s/complete" % cid, {})
    order = done.get("order") or {}
    if not order.get("id"):
        raise RuntimeError("cart did not complete: %s" % json.dumps(done)[:200])
    return order["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--days", type=int, default=45, help="spread the simulated dates over this many days")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds between orders")
    args = ap.parse_args()

    if not medusa.configured():
        print("Set MEDUSA_URL, MEDUSA_EMAIL and MEDUSA_PASSWORD first.")
        return 1
    base = medusa.config()[0]
    key = publishable_key()
    store = Store(base, key)
    regions = store.call("GET", "/store/regions").get("regions") or []
    if not regions:
        print("no region configured in the shop")
        return 1
    region_id = regions[0]["id"]
    items = catalogue(store, region_id)
    if not items:
        print("no purchasable products found")
        return 1

    # a few variants are deliberately more popular, as in any real catalogue
    weights = [max(0.2, random.random() ** 1.6) for _ in items]
    total_w = sum(weights)
    weighted = [(items[i], weights[i] / total_w) for i in range(len(items))]

    print("shop %s, %d buyable variants, placing %d real orders over %d simulated days"
          % (base, len(items), args.count, args.days))
    placed, failed, start, sold_out = 0, 0, time.time(), set()
    for i in range(args.count):
        day = (datetime.utcnow() - timedelta(days=random.randint(0, max(args.days, 0)))).strftime("%Y-%m-%d")
        item = pick(weighted)
        qty = 1 if random.random() < 0.82 else 2
        ok = False
        for attempt in range(3):          # a sold-out variant is a retry, not a failure
            try:
                place(store, region_id, item, qty, day, pick(DEVICES))
                placed, ok = placed + 1, True
                break
            except RuntimeError as exc:
                if "insufficient_inventory" in str(exc):
                    sold_out.add(item["variant_id"])
                    live = [(it, w) for it, w in weighted if it["variant_id"] not in sold_out]
                    if not live:
                        print("  every variant is sold out; stopping")
                        ok = None
                        break
                    item = pick([(it, w / sum(x[1] for x in live)) for it, w in live])
                    continue
                failed += 1
                if failed <= 3:
                    print("  order failed: %s" % exc)
                break
        if ok is None:
            break
        if not ok and attempt == 2:
            failed += 1
        if failed > 12 and placed == 0:
            print("  giving up: the first dozen all failed")
            break
        if (i + 1) % 25 == 0:
            print("  %d placed, %d failed, %.0fs elapsed" % (placed, failed, time.time() - start))
        if args.pause:
            time.sleep(args.pause)

    print("\n%d real orders placed, %d failed, in %.0fs" % (placed, failed, time.time() - start))
    print("Now read them into the engine:  python3 run.py medusa sync")
    return 0 if placed else 1


if __name__ == "__main__":
    sys.exit(main())
