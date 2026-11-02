"""Medusa v2 adapter: an open-source storefront and back office, polled.

Medusa is a real shop. It has a Next.js storefront customers browse, an admin
dashboard, a Postgres database and an Admin API. We do not build any of that;
we read it and run the decisions behind it, exactly as we would with Shopify.

Medusa emits events in-process but has no outbound webhooks, so polling is not
a shortcut here, it is the documented way for an external service to read it.

  MEDUSA_URL=http://localhost:9000
  MEDUSA_EMAIL=admin@medusajs.com        # with MEDUSA_PASSWORD, or
  MEDUSA_API_KEY=sk_...                  # a secret key from Settings

What it maps:
  products + variants   -> product, variant, ext_map, supplier_terms (defaults)
  orders                -> sales_fact (quantity, unit price, discount per line)
  inventory items       -> inventory_snapshot, summed across stock locations
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from core import db

SOURCE = "medusa"
PAGE = 100
_TOKEN = {"value": None, "mode": None, "at": 0}


class MedusaError(RuntimeError):
    pass


def config():
    return (os.environ.get("MEDUSA_URL", "http://localhost:9000").rstrip("/"),
            os.environ.get("MEDUSA_EMAIL", "").strip(),
            os.environ.get("MEDUSA_PASSWORD", "").strip(),
            os.environ.get("MEDUSA_API_KEY", "").strip())


def configured():
    _, email, password, key = config()
    return bool(key or (email and password))


def _auth_header(force=False):
    """A secret key if there is one, otherwise an email/password JWT.

    The JWT is cached for an hour; Medusa issues short-lived tokens and there is
    no reason to re-authenticate on every page of a paged read.
    """
    url, email, password, key = config()
    if key:
        return "Basic %s" % key
    if not force and _TOKEN["value"] and time.time() - _TOKEN["at"] < 3600:
        return "Bearer %s" % _TOKEN["value"]
    if not (email and password):
        raise MedusaError("set MEDUSA_API_KEY, or MEDUSA_EMAIL and MEDUSA_PASSWORD")
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(url + "/auth/user/emailpass", data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MedusaError("login failed (HTTP %s): %s"
                          % (exc.code, exc.read().decode("utf-8", "replace")[:200]))
    except urllib.error.URLError as exc:
        raise MedusaError("cannot reach %s: %s" % (url, exc.reason))
    token = data.get("token")
    if not token:
        raise MedusaError("login returned no token: %s" % str(data)[:200])
    _TOKEN.update({"value": token, "mode": "jwt", "at": time.time()})
    return "Bearer %s" % token


def _get(path, params=None, retry_auth=True):
    url, _, _, _ = config()
    full = url + path
    if params:
        full += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={
        "Authorization": _auth_header(), "Accept": "application/json",
        "User-Agent": "halden-engine/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and retry_auth and not config()[3]:
            _TOKEN["value"] = None                       # expired JWT: log in once more
            return _get(path, params, retry_auth=False)
        raise MedusaError("HTTP %s on %s: %s"
                          % (exc.code, path, exc.read().decode("utf-8", "replace")[:250]))
    except urllib.error.URLError as exc:
        raise MedusaError("cannot reach %s: %s" % (full, exc.reason))


def _paged(path, key, params=None, max_pages=50):
    offset = 0
    for _ in range(max_pages):
        p = dict(params or {})
        p.update({"limit": PAGE, "offset": offset})
        body = _get(path, p)
        rows = body.get(key) or []
        yield rows
        offset += PAGE
        if offset >= int(body.get("count") or 0) or not rows:
            return


def check():
    url, email, _, key = config()
    out = {"url": url, "auth": "secret key" if key else ("email %s" % email if email else "none")}
    if not configured():
        out["error"] = "set MEDUSA_API_KEY, or MEDUSA_EMAIL and MEDUSA_PASSWORD"
        return out
    counts = {}
    for path, key_name in (("/admin/products", "products"), ("/admin/orders", "orders"),
                           ("/admin/inventory-items", "inventory_items")):
        try:
            body = _get(path, {"limit": 1})
            counts[key_name] = body.get("count", "?")
        except MedusaError as exc:
            counts[key_name] = "failed (%s)" % str(exc)[:70]
    out["counts"] = counts
    out["ok"] = all(isinstance(v, int) for v in counts.values())
    return out


def probe():
    """Fetch one of each and report what the server actually returned.

    The first contact with a live shop is where field names and shapes differ
    from the documentation. This prints the keys rather than guessing.
    """
    out = {}
    for name, path, key, params in (
        ("product", "/admin/products", "products",
         {"limit": 1, "fields": "*variants,*variants.prices,*variants.inventory_items,"
                                "+variants.inventory_quantity"}),
        ("order", "/admin/orders", "orders",
         {"limit": 1, "fields": "*items,+created_at,+currency_code"}),
        ("inventory_item", "/admin/inventory-items", "inventory_items",
         {"limit": 1, "fields": "+location_levels"}),
    ):
        try:
            body = _get(path, params)
            rows = body.get(key) or []
            if not rows:
                out[name] = {"count": body.get("count", 0), "note": "none exist yet"}
                continue
            row = rows[0]
            info = {"count": body.get("count"), "keys": sorted(row)[:28]}
            if name == "product":
                variants = row.get("variants") or []
                info["variant_count"] = len(variants)
                if variants:
                    v = variants[0]
                    info["variant_keys"] = sorted(v)[:28]
                    info["price_resolved"] = _variant_price(v)
                    info["inventory_items"] = v.get("inventory_items")
            if name == "order":
                items = row.get("items") or []
                info["item_count"] = len(items)
                if items:
                    info["item_keys"] = sorted(items[0])[:28]
            if name == "inventory_item":
                info["location_levels"] = row.get("location_levels")
                info["stocked_quantity"] = row.get("stocked_quantity")
            out[name] = info
        except MedusaError as exc:
            out[name] = {"error": str(exc)[:160]}
    return out


# ------------------------------------------------------------- ingestion ----

def _variant_price(variant, fallback=0.0):
    """Medusa v2 exposes a variant's money in more than one shape.

    `prices` is a price set (one row per currency and rule), and a storefront
    read instead carries `calculated_price`. Either may be absent depending on
    which fields were requested, so all of them are tried before giving up.
    """
    for row in variant.get("prices") or []:
        amount = row.get("amount")
        if amount:
            return float(amount)
    calc = variant.get("calculated_price") or {}
    for key in ("calculated_amount", "original_amount", "amount"):
        if calc.get(key):
            return float(calc[key])
    if variant.get("price"):
        return float(variant["price"])
    return float(fallback)


def pull_products(conn):
    """Products, variants, and the inventory-item id each variant resolves to."""
    n_p = n_v = mapped = 0
    params = {"fields": "*variants,*variants.prices,*variants.inventory_items,"
                        "+variants.inventory_quantity"}
    for rows in _paged("/admin/products", "products", params):
        for p in rows:
            pid = "med_%s" % p["id"]
            variants = p.get("variants") or []
            price = next((p for p in (_variant_price(v) for v in variants) if p), 0.0)
            conn.execute("INSERT OR REPLACE INTO product VALUES (?,?,?,?,?,?,?,?)",
                         (pid, (p.get("title") or "")[:120], config()[0],
                          (p.get("created_at") or "")[:10], price, round(price * 0.3, 2), 4.0, 0.02))
            n_p += 1
            for v in variants:
                vid = "medv_%s" % v["id"]
                vprice = _variant_price(v, price)
                cost = round(vprice * 0.3, 2)
                conn.execute("INSERT OR REPLACE INTO variant VALUES (?,?,?,?,?,?,?,?)",
                             (vid, pid, v.get("sku") or vid, (v.get("title") or "default")[:40],
                              cost, vprice, "B", pid if len(variants) > 1 else None))
                conn.execute("INSERT OR REPLACE INTO supplier_terms VALUES (?,?,?,?,?,?,?)",
                             ("medusa_default", vid, cost, 1, 1, 21.0, 5.0))
                items = v.get("inventory_items") or []
                inv_id = items[0].get("inventory_item_id") if items else None
                conn.execute("INSERT OR REPLACE INTO ext_map VALUES (?,?,?,?,?,?)",
                             (vid, SOURCE, str(p["id"]), str(v["id"]),
                              str(inv_id) if inv_id else None, v.get("sku")))
                mapped += 1 if inv_id else 0
                n_v += 1
    return {"products": n_p, "variants": n_v, "inventory_ids_resolved": mapped}


def pull_orders(conn, since_days=120):
    """Refresh the import window atomically so repeated polls never add duplicates.

    Medusa returns the full window on each poll, including canceled orders.
    Replacing that source's window also removes canceled lines. Older imported
    history and the seeded case study remain untouched.
    """
    if not isinstance(since_days, int) or since_days <= 0:
        raise ValueError("since_days must be a positive integer")
    conn.execute("SAVEPOINT medusa_order_refresh")
    try:
        conn.execute("DELETE FROM sales_fact WHERE channel='medusa' AND substr(ts,1,10)>=date('now', ?)",
                     ("-%d day" % since_days,))
        out = _pull_orders(conn, since_days)
        conn.execute("RELEASE SAVEPOINT medusa_order_refresh")
        return out
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT medusa_order_refresh")
        conn.execute("RELEASE SAVEPOINT medusa_order_refresh")
        raise


def _pull_orders(conn, since_days=120):
    """Order lines. Medusa has no device field, so device mix stays empty here:
    that signal comes from the storefront, not the commerce API."""
    cutoff = time.time() - since_days * 86400
    by_ext = {r["ext_variant_id"]: r["variant_id"]
              for r in db.rows(conn, "SELECT ext_variant_id, variant_id FROM ext_map WHERE source=?",
                               (SOURCE,))}
    lines = skipped = 0
    simulated_count = [0]
    cancelled = [0]
    devices = {}
    for rows in _paged("/admin/orders", "orders",
                       {"order": "-created_at",
                        "fields": "*items,+created_at,+currency_code,+metadata,+email,+status"}):
        for o in rows:
            if (o.get("status") or "").lower() in ("canceled", "cancelled", "archived"):
                cancelled[0] += 1
                continue
            created = (o.get("created_at") or "")[:19]
            meta = o.get("metadata") or {}
            # Orders placed by the shopper simulator carry the day they are meant
            # to represent. Real customer orders have no such field and keep their
            # real timestamp.
            simulated = meta.get("simulated_day")
            if simulated:
                created = "%sT%02d:%02d:00" % (simulated, 9 + (hash(o["id"]) % 11),
                                               hash(o["id"]) % 60)
                simulated_count[0] += 1
            if meta.get("review"):
                # named columns: the table has gained a sentiment label since, and a
                # positional insert would break the moment it gains another
                conn.execute(
                    "INSERT INTO order_review (order_id, product, day, text, device)"
                    " VALUES (?,?,?,?,?)"
                    " ON CONFLICT(order_id) DO UPDATE SET product=excluded.product,"
                    " day=excluded.day, text=excluded.text, device=excluded.device",
                    (o["id"], meta.get("product"), created[:10], meta["review"],
                     meta.get("device")))
            device = meta.get("device")
            if device:
                day_key = created[:10]
                devices.setdefault(day_key, {}).setdefault(device, 0)
                devices[day_key][device] += 1
            try:
                stamp = time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))
                if stamp < cutoff and not simulated:
                    continue
            except ValueError:
                pass
            for li in o.get("items") or []:
                vid = by_ext.get(str(li.get("variant_id")))
                if not vid:
                    skipped += 1
                    continue
                qty = int(li.get("quantity") or 0)
                unit = float(li.get("unit_price") or 0)
                disc = float(li.get("discount_total") or 0)
                pct = round(disc / (unit * qty) * 100, 2) if unit and qty else 0.0
                conn.execute(
                    "INSERT INTO sales_fact (variant_id, ts, units, unit_price, discount_pct,"
                    " is_new_customer, refunded, channel) VALUES (?,?,?,?,?,?,?,?)",
                    (vid, created, qty, unit, pct, 1, 0, "medusa"))
                lines += 1
    for day, mix in devices.items():
        total = sum(mix.values()) or 1
        for device, count in mix.items():
            conn.execute("INSERT OR REPLACE INTO device_mix VALUES (?,?,?,?)",
                         (day, device, count, round(count / total, 4)))
    return {"order_lines": lines, "skipped_unmapped": skipped,
            "dated_from_metadata": simulated_count[0], "days_with_device_mix": len(devices),
            "cancelled_skipped": cancelled[0]}


def snapshot_inventory(conn):
    """The hourly job: what was buyable, when. Summed across stock locations,
    because a variant held at one of two warehouses is still buyable."""
    rows = db.rows(conn, "SELECT variant_id, ext_inventory_item_id, sku FROM ext_map WHERE source=?",
                   (SOURCE,))
    if not rows:
        raise MedusaError("no variants mapped yet: run the product pull first")
    by_item = {r["ext_inventory_item_id"]: r["variant_id"] for r in rows if r["ext_inventory_item_id"]}
    by_sku = {r["sku"]: r["variant_id"] for r in rows if r["sku"]}
    ts = time.strftime("%Y-%m-%dT%H:00:00", time.gmtime())
    written = unmatched = 0
    for items in _paged("/admin/inventory-items", "inventory_items", {"fields": "+location_levels"}):
        for item in items:
            vid = by_item.get(str(item.get("id"))) or by_sku.get(item.get("sku"))
            if not vid:
                unmatched += 1
                continue
            levels = item.get("location_levels")
            if levels:
                available = sum(int(l.get("stocked_quantity") or 0) - int(l.get("reserved_quantity") or 0)
                                for l in levels)
            else:
                available = int(item.get("stocked_quantity") or 0) - int(item.get("reserved_quantity") or 0)
            conn.execute("INSERT OR REPLACE INTO inventory_snapshot VALUES (?,?,?,?)",
                         (vid, ts, available, 1 if available > 0 else 0))
            written += 1
    return {"snapshot_at": ts, "variants": written, "unmatched_items": unmatched}


def backfill_availability(conn, days=90):
    """Reconstruct stock history from today's stock and the order log.

    Walking backwards: what was on the shelf yesterday is what is on it today
    plus whatever sold today. It is an estimate - it cannot see deliveries or
    write-offs - but it is a far better starting point than pretending the
    shop only existed from the moment we connected to it. From now on the
    hourly snapshot records the truth and this estimate is never used again.
    """
    import datetime as _dt
    rows = db.rows(conn, "SELECT variant_id FROM ext_map WHERE source=?", (SOURCE,))
    if not rows:
        raise MedusaError("no variants mapped yet: run the product pull first")
    today = _dt.date.today()
    written = 0
    for r in rows:
        vid = r["variant_id"]
        latest = db.one(conn, "SELECT on_hand FROM inventory_snapshot WHERE variant_id=?"
                              " ORDER BY ts DESC LIMIT 1", (vid,))
        if latest is None:
            continue
        on_hand = latest["on_hand"]
        sold = {x["day"]: x["units"] for x in db.rows(conn, """
            SELECT substr(ts,1,10) AS day, SUM(units) AS units FROM sales_fact
            WHERE variant_id=? GROUP BY 1""", (vid,))}
        for back in range(days):
            day = today - _dt.timedelta(days=back)
            iso = day.isoformat()
            # one snapshot per day at midday, unless a real reading already exists
            exists = db.scalar(conn, "SELECT COUNT(*) FROM inventory_snapshot"
                                     " WHERE variant_id=? AND ts LIKE ?", (vid, iso + "%"))
            if not exists:
                conn.execute("INSERT OR REPLACE INTO inventory_snapshot VALUES (?,?,?,?)",
                             (vid, iso + "T12:00:00", max(on_hand, 0), 1 if on_hand > 0 else 0))
                written += 1
            on_hand += sold.get(iso, 0)          # it was on the shelf before it sold
    return {"days": days, "snapshots_written": written,
            "note": "estimated from current stock plus the order log; live readings take over from now"}


def sync(conn, since_days=120):
    out = {"products": pull_products(conn)}
    out["orders"] = pull_orders(conn, since_days)
    out["inventory"] = snapshot_inventory(conn)
    return out


# ---------------------------------------------------------- acting on it ----
# Reading a shop is half a system. These are the only three writes the platform
# can make, they are narrow on purpose, and each one is called by the gateway
# after an action was approved - never by an agent directly.

def _post(path, body):
    req = urllib.request.Request(config()[0] + path, data=json.dumps(body).encode(),
                                 method="POST",
                                 headers={"Authorization": _auth_header(),
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def set_product_status(conn, our_product_id, status="draft"):
    """Take a product off sale, or put it back. A killed product should stop
    being sold, not merely be marked as killed in our own database."""
    ext = db.scalar(conn, "SELECT ext_product_id FROM ext_map WHERE source=? AND variant_id IN"
                          " (SELECT id FROM variant WHERE product_id=?) LIMIT 1",
                    (SOURCE, our_product_id), None)
    if not ext:
        return {"skipped": "not a product in the live shop"}
    out = _post("/admin/products/%s" % ext, {"status": status})
    return {"product": ext, "status": (out.get("product") or {}).get("status", status)}


def receive_stock(conn, our_variant_id, quantity):
    """Goods arrive. Raises the shop's own stock level, which is what makes a
    purchase order real rather than a row in our ledger."""
    row = db.one(conn, "SELECT ext_inventory_item_id FROM ext_map WHERE variant_id=?",
                 (our_variant_id,))
    if not row or not row["ext_inventory_item_id"]:
        return {"skipped": "not a variant in the live shop"}
    item = row["ext_inventory_item_id"]
    loc = _get("/admin/stock-locations", {"limit": 1})["stock_locations"][0]["id"]
    levels = _get("/admin/inventory-items/%s" % item, {"fields": "+location_levels"})
    current = 0
    for lvl in ((levels.get("inventory_item") or {}).get("location_levels") or []):
        if lvl.get("location_id") == loc:
            current = int(lvl.get("stocked_quantity") or 0)
    new_total = current + int(quantity)
    _post("/admin/inventory-items/%s/location-levels/%s" % (item, loc),
          {"stocked_quantity": new_total})
    return {"variant": our_variant_id, "was": current, "now": new_total, "received": int(quantity)}
