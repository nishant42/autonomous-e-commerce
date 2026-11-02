# Live recruiter deployment

Status: deployment configuration prepared; not a claim that services are live.

The existing Cloudflare address is `https://halden.amakor.workers.dev`. It currently
hosts static architecture pages. Keep it unchanged until the live services pass
checks. Do not expose a tunnel from the developer's laptop as permanent hosting.

## Infrastructure

`render.yaml` now uses only free plans, as requested:

- Medusa backend, Next.js storefront and Python agents: Free (512 MB each).
- PostgreSQL: Free, 1 GB, expires 30 days after creation.
- No persistent disk. Agent SQLite history resets when its service sleeps,
  restarts or redeploys; the shop database survives until its expiry.

Free web services sleep after 15 idle minutes and share 750 instance-hours per
workspace per month. Cold starts can take about a minute. These limits make this
a temporary recruiter demo, not an always-on production installation. Medusa may
exceed the free service's memory; do not upgrade it without user approval. Keep
build/bandwidth usage within the included quota and do not enable paid overages.

The authenticated wrapper and source are prepared. Live status must be verified
for each service before sharing links with a recruiter.

## Provision in stages

1. Connect this GitHub repository to Render. Use the Blueprint or create the
   database and backend first with the exact settings in `render.yaml`. Blueprint
   environment fields marked `sync: false` must be provided; actual service URL
   suffixes are assigned by Render, so do not assume names are globally available.
2. Set CORS to exact HTTPS origins: STORE_CORS to the storefront origin;
   ADMIN_CORS to the backend origin; AUTH_CORS to both, comma-separated. Initially
   the backend origin can be used while provisioning; update before testing the shop.
3. Backend startup runs migrations. Free services have no Render Shell. A deployment bootstrap must create the administrator before the first shop demo; on paid services, the manual command would be:
   `cd shop/apps/backend/.medusa/server` then
   `../../../../node_modules/.bin/medusa user -e YOUR_EMAIL -p YOUR_PASSWORD`.
   Choose a unique password; do not use the local demo password.
4. Open backend `/app`. Confirm the region includes Denmark, products have prices,
   shipping options and inventory, and obtain a publishable API key assigned to the
   store's sales channel. Migrations seed initial store data; verify rather than
   rerunning seed scripts blindly.
5. Set the storefront NEXT_PUBLIC variables to the actual backend URL, publishable
   key and storefront URL, then deploy it. These values are needed at build time;
   redeploy after changing them. Only test/manual payment should be enabled for
   recruiter demonstrations. No real payment provider credentials are bundled.
6. Configure the agent MEDUSA_URL/email/password, SHOP_PUBLIC_URL (storefront URL
   plus `/dk/store`) and ENGINE_PUBLIC_URL (agent origin without trailing slash).
   Open the agent URL using `operator` and OPERATOR_PASSWORD from Render's secret
   environment. Import shop evidence, then run a cycle. Give the recruiter the
   separate `recruiter` / VIEWER_PASSWORD credentials, which cannot approve,
   reset, sync, train models or run cycles. Read-only quantity previews are allowed.
7. Confirm the shop, checkout, admin login, inventory rejection, agent read access,
   denied recruiter writes, and data survival across a restart. Only then add live
   links to the Cloudflare site; no localhost links should appear on the hosted demo.

## Runtime limits and models

The hosted console binds to PORT on 0.0.0.0 and requires long, distinct passwords.
It restricts static file access to the UI directory and disables dynamic source
imports. TLS must terminate at the host. Use only staged demo data for recruiter
access; viewers can read evidence and reviews. This wrapper is a prototype hosting
boundary, not a claim of a completed production security review.

Default LLM provider is explicitly rules_only. Numerical ML packages are included,
but Ridge must be trained/promoted on the hosted dataset before claiming it is in
use. Existing local pickle files are not copied across library versions. Model
artifacts currently live under engine/models and must be retrained after redeploy;
SQLite evidence/ledger and model files are both ephemeral on this free setup. DistilBERT/Qwen/Chronos
are not downloaded automatically on small instances. Enabling them requires
appropriate memory and explicit dependency/model setup.

This setup remains single-instance for each application. A purchase is recorded
by Medusa; the operator must sync and run a cycle. New products can correctly fail
the 28-day history requirement. Do not manufacture historical observations to
make those guards pass.
