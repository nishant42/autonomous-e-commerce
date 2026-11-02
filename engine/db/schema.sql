-- Operational store for the agent platform.
-- SQLite here so the demo runs with no install; the same DDL runs on Postgres
-- with serial/jsonb swapped in (see core/db.py for the one place that differs).

CREATE TABLE IF NOT EXISTS product (
  id TEXT PRIMARY KEY, name TEXT, store TEXT, launched_on TEXT,
  price REAL, cogs REAL, ship_cost REAL, payment_fee_pct REAL
);

CREATE TABLE IF NOT EXISTS variant (
  id TEXT PRIMARY KEY, product_id TEXT, sku TEXT, colour TEXT,
  unit_cost REAL, price REAL, abc_class TEXT,
  substitution_group TEXT,
  FOREIGN KEY (product_id) REFERENCES product(id)
);

-- Hourly truth about whether a variant could actually be bought.
-- This table is the whole reason the towel case is solvable.
CREATE TABLE IF NOT EXISTS inventory_snapshot (
  variant_id TEXT, ts TEXT, on_hand INTEGER, buyable INTEGER,
  PRIMARY KEY (variant_id, ts)
);

CREATE TABLE IF NOT EXISTS sales_fact (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id TEXT, ts TEXT, units INTEGER,
  unit_price REAL, discount_pct REAL,
  is_new_customer INTEGER, refunded INTEGER DEFAULT 0,
  channel TEXT
);
CREATE INDEX IF NOT EXISTS ix_sales_variant_ts ON sales_fact(variant_id, ts);

-- Lower bound on censored demand: what people did while they could not buy.
CREATE TABLE IF NOT EXISTS demand_signal (
  variant_id TEXT, day TEXT, kind TEXT, value REAL,
  PRIMARY KEY (variant_id, day, kind)
);

CREATE TABLE IF NOT EXISTS supplier_terms (
  supplier_id TEXT, variant_id TEXT, unit_cost REAL,
  moq INTEGER, case_pack INTEGER,
  lead_time_mean_days REAL, lead_time_sd_days REAL,
  PRIMARY KEY (supplier_id, variant_id)
);

CREATE TABLE IF NOT EXISTS ad_metrics (
  cell_id TEXT, day TEXT, platform TEXT, product_id TEXT,
  spend REAL, impressions INTEGER, clicks INTEGER,
  orders INTEGER, new_customers INTEGER, revenue REAL,
  frequency REAL, is_holdout INTEGER DEFAULT 0,
  PRIMARY KEY (cell_id, day)
);

CREATE TABLE IF NOT EXISTS funnel_daily (
  product_id TEXT, day TEXT,
  sessions INTEGER, pdp_views INTEGER, add_to_cart INTEGER,
  checkout_start INTEGER, orders INTEGER, refunds INTEGER,
  PRIMARY KEY (product_id, day)
);

CREATE TABLE IF NOT EXISTS experiment_budget (
  product_id TEXT PRIMARY KEY, allocated_eur REAL, spent_eur REAL
);

-- ---- platform tables (bus, gateway, audit) ----

CREATE TABLE IF NOT EXISTS work_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT, session_key TEXT, payload TEXT,
  run_after TEXT, attempts INTEGER DEFAULT 0,
  locked_by TEXT, locked_at TEXT,
  status TEXT DEFAULT 'ready',       -- ready | running | done | dead
  last_error TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_queue_poll ON work_queue(status, run_after);

-- Written in the same transaction as the fact it describes, then relayed.
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT, session_key TEXT, payload TEXT,
  created_at TEXT, published_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, agent TEXT, tool TEXT,
  args TEXT, result TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, agent TEXT, intent TEXT, payload TEXT,
  value_eur REAL, tier TEXT,
  status TEXT,                        -- executed | pending_checker | pending_human | rejected
  reason TEXT, rationale TEXT, evidence TEXT,
  idempotency_key TEXT UNIQUE,
  reversed_by INTEGER
);

CREATE TABLE IF NOT EXISTS cooldown (
  lever TEXT PRIMARY KEY, last_changed_at TEXT
);

CREATE TABLE IF NOT EXISTS anomaly (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, agent TEXT, kind TEXT, severity TEXT, note TEXT, resolved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_run (
  id TEXT PRIMARY KEY, agent TEXT, started_at TEXT, finished_at TEXT,
  trigger TEXT, steps INTEGER, tokens INTEGER, cost_eur REAL,
  mode TEXT, outcome TEXT, trace TEXT
);

-- ---- marketing feature store and model registry ----

-- One row per cell-day holding every modelling feature as JSON, so the feature
-- set can change without a migration. The target lives in ad_metrics.
CREATE TABLE IF NOT EXISTS ad_feature (
  cell_id TEXT, day TEXT, product_id TEXT, features TEXT,
  PRIMARY KEY (cell_id, day)
);

-- Every model trained, with its out-of-sample metrics. A model is only used
-- once it is promoted, and promotion is a recorded decision with a reason.
CREATE TABLE IF NOT EXISTS model_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trained_at TEXT, target TEXT, family TEXT,
  features TEXT, n_train INTEGER, n_test INTEGER,
  in_sample TEXT, out_sample TEXT,
  promoted INTEGER DEFAULT 0, promotion_reason TEXT,
  diagnostics TEXT
);

-- ---- Shopify adapter ----

-- Device mix per day, parsed from each order's client_details. One of the few
-- device signals a store genuinely owns without a tracking vendor.
CREATE TABLE IF NOT EXISTS device_mix (
  day TEXT, device TEXT, orders INTEGER, share REAL,
  PRIMARY KEY (day, device)
);

-- ---- external storefront mapping (Medusa, Shopify, anything else) ----
-- Our ids to theirs. Inventory is keyed by an inventory-item id in both
-- platforms, which is not the variant id; getting that wrong silently
-- snapshots nothing, which is why it is stored explicitly.
CREATE TABLE IF NOT EXISTS ext_map (
  variant_id TEXT PRIMARY KEY,
  source TEXT,
  ext_product_id TEXT,
  ext_variant_id TEXT,
  ext_inventory_item_id TEXT,
  sku TEXT
);
CREATE INDEX IF NOT EXISTS ix_ext_item ON ext_map(ext_inventory_item_id);
CREATE INDEX IF NOT EXISTS ix_ext_sku ON ext_map(sku);

-- Review text left with an order. Classified by a language model, never by a rule.
CREATE TABLE IF NOT EXISTS order_review (
  order_id TEXT PRIMARY KEY, product TEXT, day TEXT, text TEXT, device TEXT,
  sentiment TEXT, sentiment_score REAL, classified_at TEXT
);

-- Which variants compete for the same purchase, learned from product text by a
-- sentence-embedding model rather than assumed from the product id.
CREATE TABLE IF NOT EXISTS substitute_pair (
  a TEXT, b TEXT, score REAL, source TEXT, created_at TEXT,
  PRIMARY KEY (a, b)
);

-- Real public interest, from Wikimedia's open pageviews API. No key, no account,
-- no vendor: a genuine external demand signal for a shop with no ad account yet.
CREATE TABLE IF NOT EXISTS external_interest (
  term TEXT, day TEXT, views INTEGER, source TEXT,
  PRIMARY KEY (term, day)
);
