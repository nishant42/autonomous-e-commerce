# Autonomous e-commerce prototype

A Medusa/Next.js shop with three decision agents, an evidence-recording harness,
a durable job queue, and an approval gateway. Includes a customer storefront and
interactive pages explaining how decisions are made.

## Components

- **Reorder:** reconstructs demand from sales and availability, calculates stock
  requirements, and checks supplier, cash and approval constraints.
- **Marketing:** estimates orders and cost per order, then applies budget bands,
  exposure checks, stock protection and cooldowns.
- **Product verdict:** combines funnel and review evidence to recommend scaling,
  fixing or stopping an offer. KILL recommendations require human approval.
- **Harness:** limits tool access, records evidence, validates model outputs and
  falls back to explicit rules when investigation fails.

## Run the agent demo

Python 3.9+; the rules-only demo uses the standard library.

```bash
cd engine
ENGINE_MODEL_PROVIDER=rules_only python3 run.py ui
```

Open http://localhost:8787. The first run seeds a local demonstration database.

- `/console`: run cycles, inspect decisions and review approvals.
- `/flow`: recorded decision walkthrough.
- `/map`: system map.
- `/ui/agents-guide.html`: plain-English explanations of the agents and models.
- `/explain`: demand calculations and what-if quantities.

The embedded Shop view needs the separate shop services below. Architecture
pages at the repository root can be served with `python3 -m http.server 8080`.

## Run the shop

The included `shop/` is an npm workspace with its lockfile retained. Requires
Node 22.23.4+, npm 10.9.9 and PostgreSQL 15+. See `shop/README.md` for the starter's
additional configuration, using npm for this checkout.

```bash
cd shop
npm ci
cp apps/backend/.env.template apps/backend/.env
cp apps/storefront/.env.template apps/storefront/.env.local
```

Set the backend database connection and fresh JWT/cookie secrets. Create the
PostgreSQL database before migrating. Configure Redis if required by your setup.

```bash
cd apps/backend
npx medusa db:migrate
npx medusa user -e YOUR_ADMIN_EMAIL -p YOUR_CHOSEN_PASSWORD
```

From `shop/`, start the backend with `npm run backend:dev`. Configure the
storefront's publishable API key from Medusa Admin, then run
`npm run storefront:dev` in another terminal.

- Shop: http://localhost:8000 (the demo embed uses `/dk/store`; configure Denmark
  in your region or adjust that path for your store).
- Medusa Admin: http://localhost:9000/app.

To connect the engine, copy `engine/.env.example` to `engine/.env` and supply your
local Medusa credentials. Import shop evidence with `python3 run.py medusa sync`
from `engine/`, then run a cycle in the console. A purchase does not automatically
trigger a cycle in the demonstrated setup.

## ML and current limits

- Lasso feature selection and a promoted Ridge model estimate advertising orders;
  the demonstrated advertising training data is simulated.
- DistilBERT classifies review sentiment locally through Transformers.
- Local Qwen investigation is optional. The small model did not reliably complete
  mandatory tool reads in the demonstrated run, so those decisions used fallback
  rules. Do not equate model availability with a successful LLM decision.
- Chronos and similarity-model integrations are optional, not proof of active use.
- New live products can be blocked by insufficient inventory history (28 days
  required by the configured policy). No production performance is claimed.
- ML dependencies and downloaded weights are optional and are not bundled. See
  `engine/README.md` and the worker modules before enabling them.

This is a local prototype, not a hardened public service. Do not expose the demo
console directly to the internet. Review execution adapters before enabling real
external writes; an internal executed ledger entry alone does not prove a change
was applied to an external ad platform.

## Checks

```bash
cd engine
ENGINE_MODEL_PROVIDER=rules_only python3 -m unittest discover -s tests -p test_agentic.py -q
```

No credentials, order databases, trained model files, virtual environments or
installed dependencies are included. See `shop/LICENSE` for the Medusa starter's
license and retain third-party notices in vendored assets.
