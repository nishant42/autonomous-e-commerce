"""Shopify adapter: pulls a real store into the engine's tables.

Polling, not webhooks, on purpose. A webhook needs a public URL and a tunnel,
which is one more thing to fail during a demo; the Admin API gives the same
facts on a schedule with nothing exposed. The webhook receiver is a later
addition for production latency, not a prerequisite.

What it pulls, and into which table:

  products + variants      -> product, variant, supplier_terms (defaults)
  orders (+ refunds)       -> sales_fact, and device mix from client_details
  inventory levels         -> inventory_snapshot   (the hourly job that makes
                              the towel case solvable at all)

Set two environment variables and nothing else:

  SHOPIFY_STORE=your-store.myshopify.com
  SHOPIFY_TOKEN=shpat_...        (Admin API access token from a custom app)
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from core import db

API_VERSION = "2025-01"
PAGE_SIZE = 250
SCOPES_NEEDED = ["read_products", "read_orders", "read_inventory", "read_locations"]


class ShopifyError(RuntimeError):
    pass


def config():
    store = os.environ.get("SHOPIFY_STORE", "").strip()
    token = os.environ.get("SHOPIFY_TOKEN", "").strip()
    if store.startswith("http"):
        store = urllib.parse.urlparse(store).netloc
    return store, token


def configured():
    store, token = config()
    return bool(store and token)


def _request(path, params=None):
    store, token = config()
    if not store or not token:
        raise ShopifyError("SHOPIFY_STORE and SHOPIFY_TOKEN are not set")
    url = "https://%s/admin/api/%s/%s" % (store, API_VERSION, path.lstrip("/"))
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-Shopify-Access-Token": token, "Accept": "application/json",
        "User-Agent": "halden-engine/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                link = resp.headers.get("Link", "")
                return body, _next_page(link)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:                      # rate limited: back off and retry
                time.sleep(1.5 * (attempt + 1))
                continue
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ShopifyError("HTTP %s on %s: %s" % (exc.code, path, detail))
        except urllib.error.URLError as exc:
            raise ShopifyError("cannot reach %s: %s" % (store, exc.reason))
    raise ShopifyError("rate limited five times on %s" % path)


def _next_page(link_header):
    m = re.search(r'<[^>]*page_info=([^>&]+)[^>]*>;\s*rel="next"', link_header or "")
    return m.group(1) if m else None


def _paged(path, params=None, limit_pages=40):
    params = dict(params or {})
    params["limit"] = PAGE_SIZE
    page_info = None
    for _ in range(limit_pages):
        p = {"limit": PAGE_SIZE, "page_info": page_info} if page_info else params
        body, page_info = _request(path, p)
        yield body
        if not page_info:
            return


def check():
    """Prove the credentials and scopes work before anything depends on them."""
    store, token = config()
    out = {"store": store, "configured": bool(store and token)}
    if not out["configured"]:
        out["error"] = "SHOPIFY_STORE and SHOPIFY_TOKEN are not set"
        return out
    body, _ = _request("shop.json")
    shop = body.get("shop", {})
    out.update({"name": shop.get("name"), "currency": shop.get("currency"),
                "plan": shop.get("plan_display_name"), "timezone": shop.get("iana_timezone")})
    counts = {}
    for path, key in (("products/count.json", "products"), ("orders/count.json", "orders"),
                      ("locations.json", "locations")):
        try:
            b, _ = _request(path, {"status": "any"} if key == "orders" else None)
            counts[key] = b.get("count", len(b.get("locations", [])))
        except ShopifyError as exc:
            counts[key] = "denied (%s)" % str(exc)[:60]
    out["counts"] = counts
    return out


# ------------------------------------------------------------- ingestion ----

def _device_from(user_agent):
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if "iphone" in ua or "ipod" in ua:
        return "ios"
    if "android" in ua:
        return "android"
    if not ua:
        return "unknown"
    return "desktop"


def pull_products(conn):
    """Products and variants. Supplier terms get conservative defaults that a
    buyer is expected to correct; they are never invented from thin air later."""
    n_p = n_v = 0
    for body in _paged("products.json"):
        for p in body.get("products", []):
            pid = "shp_%s" % p["id"]
            variants = p.get("variants", [])
            price = float(variants[0]["price"]) if variants else 0.0
            conn.execute("INSERT OR REPLACE INTO product VALUES (?,?,?,?,?,?,?,?)",
                         (pid, p.get("title", "")[:120], config()[0], (p.get("created_at") or "")[:10],
                          price, round(price * 0.3, 2), 4.0, 0.02))
            n_p += 1
            for v in variants:
                vid = "shv_%s" % v["id"]
                cost = float(v.get("price") or 0) * 0.3
                conn.execute("INSERT OR REPLACE INTO variant VALUES (?,?,?,?,?,?,?,?)",
                             (vid, pid, v.get("sku") or vid, (v.get("title") or "default")[:40],
                              round(cost, 2), float(v.get("price") or 0), "B",
                              pid if len(variants) > 1 else None))
                conn.execute(
                    "INSERT OR REPLACE INTO supplier_terms VALUES (?,?,?,?,?,?,?)",
                    ("shopify_default", vid, round(cost, 2), 1, 1, 21.0, 5.0))
                conn.execute("INSERT OR REPLACE INTO ext_map VALUES (?,?,?,?,?,?)",
                             (vid, "shopify", str(p["id"]), str(v["id"]),
                              str(v.get("inventory_item_id")), v.get("sku")))
                n_v += 1
    return {"products": n_p, "variants": n_v}


def pull_orders(conn, since_days=120):
    """Orders and refunds, plus the device the buyer actually used."""
    since = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() - since_days * 86400))
    n_lines = devices = 0
    device_rows = {}
    for body in _paged("orders.json", {"status": "any", "created_at_min": since,
                                       "fields": "id,created_at,line_items,refunds,client_details,"
                                                 "customer,total_discounts,financial_status"}):
        for o in body.get("orders", []):
            ts = o.get("created_at", "")[:19]
            day = ts[:10]
            device = _device_from((o.get("client_details") or {}).get("user_agent"))
            if device != "unknown":
                devices += 1
            device_rows.setdefault(day, {}).setdefault(device, 0)
            device_rows[day][device] += 1
            refunded_ids = set()
            for r in o.get("refunds", []):
                for li in r.get("refund_line_items", []):
                    refunded_ids.add(li.get("line_item_id"))
            for li in o.get("line_items", []):
                vid = "shv_%s" % li.get("variant_id")
                price = float(li.get("price") or 0)
                disc = sum(float(d.get("amount") or 0) for d in li.get("discount_allocations", []))
                qty = int(li.get("quantity") or 0)
                pct = round(disc / (price * qty) * 100, 2) if price and qty else 0.0
                conn.execute(
                    "INSERT INTO sales_fact (variant_id, ts, units, unit_price, discount_pct,"
                    " is_new_customer, refunded, channel) VALUES (?,?,?,?,?,?,?,?)",
                    (vid, ts, qty, price, pct, 1, 1 if li.get("id") in refunded_ids else 0, "shopify"))
                n_lines += 1
    for day, mix in device_rows.items():
        total = sum(mix.values()) or 1
        for device, count in mix.items():
            conn.execute("INSERT OR REPLACE INTO device_mix VALUES (?,?,?,?)",
                         (day, device, count, round(count / total, 4)))
    return {"order_lines": n_lines, "orders_with_device": devices, "days_with_device": len(device_rows)}


def snapshot_inventory(conn):
    """The hourly job. Availability history cannot be reconstructed afterwards,
    which is the entire reason the towel case is solvable."""
    ts = time.strftime("%Y-%m-%dT%H:00:00", time.gmtime())
    item_to_variant = {r["ext_inventory_item_id"]: r["variant_id"]
                       for r in db.rows(conn, "SELECT variant_id, ext_inventory_item_id FROM ext_map"
                                              " WHERE source='shopify'")}
    if not item_to_variant:
        raise ShopifyError("no variants mapped yet: run the product pull first")
    ids = list(item_to_variant)
    written = 0
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        body, _ = _request("inventory_levels.json", {"inventory_item_ids": ",".join(chunk),
                                                     "limit": PAGE_SIZE})
        totals = {}
        for lvl in body.get("inventory_levels", []):
            key = str(lvl.get("inventory_item_id"))
            totals[key] = totals.get(key, 0) + int(lvl.get("available") or 0)
        for key, available in totals.items():
            vid = item_to_variant.get(key)
            if not vid:
                continue
            conn.execute("INSERT OR REPLACE INTO inventory_snapshot VALUES (?,?,?,?)",
                         (vid, ts, available, 1 if available > 0 else 0))
            written += 1
    return {"snapshot_at": ts, "variants": written}


def sync(conn, since_days=120):
    out = {"products": pull_products(conn)}
    out["orders"] = pull_orders(conn, since_days)
    out["inventory"] = snapshot_inventory(conn)
    return out
