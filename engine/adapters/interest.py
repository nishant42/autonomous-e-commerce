"""Real external demand, from open data.

A new shop has no ad account, so there is no search-term report to read. What
there is, free and without a key, is Wikimedia's pageviews API: how many people
looked up a thing each day. It is a real, public, daily interest signal, and it
is the honest substitute for a Google Ads report until there is a Google Ads
account to read.

  python3 run.py interest
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from core import db

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/%s/daily/%s/%s")
UA = {"User-Agent": "halden-engine/1.0 (commerce demand research)"}

# what each product is, in words the world searches for
TERMS = {
    "Medusa T-Shirt": "T-shirt",
    "Medusa Sweatshirt": "Sweater",
    "Medusa Sweatpants": "Sweatpants",
    "Medusa Shorts": "Shorts",
    "Halden Towel": "Towel",
    "Daily Yoghurt 500g": "Yogurt",
}


def fetch(term, days=120):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    url = API % (urllib.parse.quote(term.replace(" ", "_")),
                 start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"error": "HTTP %s for %s" % (exc.code, term)}
    except urllib.error.URLError as exc:
        return {"error": "cannot reach wikimedia: %s" % exc.reason}
    out = []
    for item in body.get("items", []):
        stamp = item.get("timestamp", "")[:8]
        out.append({"day": "%s-%s-%s" % (stamp[:4], stamp[4:6], stamp[6:8]),
                    "views": int(item.get("views") or 0)})
    return {"term": term, "points": out}


def sync(conn, days=120, say=None):
    stored, failed = 0, []
    for product, term in TERMS.items():
        res = fetch(term, days)
        if res.get("error"):
            failed.append("%s: %s" % (term, res["error"]))
            continue
        for p in res["points"]:
            conn.execute("INSERT OR REPLACE INTO external_interest VALUES (?,?,?,?)",
                         (term, p["day"], p["views"], "wikimedia"))
            stored += 1
        if say:
            vals = [p["views"] for p in res["points"]]
            say("%-18s %4d days, %d to %d views a day"
                % (term, len(vals), min(vals or [0]), max(vals or [0])))
        time.sleep(0.4)                     # be polite to a free public API
    return {"rows": stored, "terms": len(TERMS) - len(failed), "failed": failed}


def series_for(conn, product_name):
    term = TERMS.get(product_name)
    if not term:
        return {}
    return {r["day"]: r["views"] for r in db.rows(
        conn, "SELECT day, views FROM external_interest WHERE term=?", (term,))}
