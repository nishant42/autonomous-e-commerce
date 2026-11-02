# The engine

Three agents, the harness around them, the bus they run on, and the gateway that
holds every side effect. Runnable, with no dependencies and no API key.

## Two-screen interview demo

Open **http://127.0.0.1:8787** after starting the console. **Shop** embeds the
existing Medusa storefront. **Behind the scenes** shows the connected agents
and expandable rule branches, with current evidence and recorded-run replay.
The former system map remains at `/map`; detailed arithmetic is at `/explain`.
See [the short demo guide](../INTERVIEW-DEMO.md).

## Inside the decisions

Open **http://127.0.0.1:8787/explain** after starting the console. One page covers
reorder, product/channel/ad marketing allocation, the product-verdict agent,
the harness, durable queue, gateway, and the model evidence currently stored.
The quantity sliders call the same Python engine used for order decisions;
all page calculations are read-only. Seeded and imported demo data are labeled.

See [the interview walkthrough](../INTERVIEW-DEMO.md) for a short presentation
sequence, model availability checks and verification commands.

## The console

```bash
cd engine
python3 run.py ui            # -> http://127.0.0.1:8787
```

A real operator console, not a report: press **Run full cycle** and watch the
queue drain job by job in the event log while each agent reads its tools and
each proposal is tiered by the gateway. Tabs for the reorder reconstruction,
the marketing pass, the portfolio verdicts with their benchmark bands, the
approval queue (approve or reject what the agents are not allowed to do alone),
the ledger with one-click reversal, and **Ask the agent**. Every evidence id in
the UI is clickable: it opens the stored tool result exactly as it was at the
moment of the decision.

Standard library only — `http.server`, one SQLite connection per request, no
build step and no npm.

## The model: real agent, no API bill

`core/model.py` detects a provider rather than assuming one:

| Provider | When | Cost |
|---|---|---|
| `claude_cli` | the `claude` binary is on the machine | **none beyond an existing Claude Code subscription** |
| `anthropic_api` | `ANTHROPIC_API_KEY` is set | per token |
| `rules_only` | neither, or an agent's token budget is spent | none |

Check it before a demo rather than during one:

```bash
python3 run.py check-model             # detects, then calls the provider for real
python3 run.py ask "Why did you order 60 black towels and none white?"
```

**Ask the agent** is a genuine tool-using loop, not a prompt with a template.
The model is given a tool list and must answer with one JSON object: either
`{"call": {...}}` to read something or `{"answer": "..."}` when it has enough.
The harness executes the read against the database, records the result as
evidence, and feeds it back, up to a step budget. Then the answer is verified:
any figure that does not trace to a tool result in that conversation is
reported as uncited, in the UI and in the terminal.

What the model is not allowed to do:

- **No write tools.** The analyst has reads only; there is nothing it can do to
  the business.
- **No numbers of its own.** Quantities, budgets and verdicts come from the
  deterministic engines. The model selects between options and writes the
  sentence, and a sentence containing an unsupported number is replaced by the
  template.
- **No tools of its own.** The CLI is invoked with `--allowedTools ""`, so the
  model cannot touch the filesystem or the network. Our harness owns tool
  execution.
- **No silent claims.** If the provider cannot be reached, the run is recorded
  as `rules-only (model unreachable)` with the reason, not as a model run.

## The marketing model

Targeted marketing is a modelling problem, not a rules problem: who saw the ad,
on what device, after searching for what, at what price, with how much stock
behind it. `engines/ml.py` runs the whole workflow on a panel of 35 features
per cell-day and hands nothing to the allocator until it has earned it.

```bash
python3 run.py model            # the full workflow, printed
python3 run.py model orders     # daily target instead of the weekly one
```

1. **Panel** — spend and delivery, creative age and format, device mix
   (iOS / Android / desktop / tablet share), search interest by category and
   brand, on-site search counts, AEO citations, price, discount, competitor
   index, calendar, stock cover, platform. Modelled at the seven-day cadence
   the allocator actually decides on, because a single cell-day is mostly noise.
2. **Stationarity** — augmented Dickey-Fuller per feature and on the target.
   Features with a unit root are not silently fitted; a differenced panel is
   built and evaluated alongside the levels panel.
3. **Guards, before any model is fitted** — two kinds of leakage are removed
   and reported: features that are a calendar in disguise (monotonic in time),
   and features computed from the target. `orders_lag1_7d` shares six of its
   seven days with a seven-day target and will score 0.97 while knowing
   nothing; `cpa_roll7` carries orders in its denominator. Only a strictly
   non-overlapping lag survives, and it becomes the baseline to beat.
4. **Significance** — Pearson r with p-values, and variance inflation for
   collinearity.
5. **Selection** — LassoCV with time-series folds. The deliberately useless
   vanity metric in the panel is there to be thrown away.
6. **Families** — ridge, lasso, random forest, gradient boosting, XGBoost
   (LightGBM when installed), each against both panels and both target
   transforms, so whether the response scales linearly or multiplicatively is
   settled out of sample rather than assumed.
7. **Out-of-sample** — a forward split in time with an embargo across the
   window, never a random split. R², RMSE, MAE, and AUC on the question that
   matters: will this cell be profitable?
8. **Promotion** — the winner ships only if it clears an absolute R² floor,
   beats both naive baselines, and does not regress against the live model. The
   decision and its reason go in `model_registry`.

How it reaches a decision: the allocator asks the promoted model for an
expected CPA per cell, blends it with the observation, and the **deterministic
bands still decide**. If the two disagree by more than a factor of two the
observation wins and the gap is logged. With no promoted model the agent runs
exactly as it did before.

One caveat, stated plainly: the demo panel is generated from a known process,
so an R² near 0.98 is a property of the generator. On a real store expect
roughly 0.3–0.6 on weekly orders per cell, and judge the pipeline on whether it
beats the previous-window baseline. The workflow and the guards are what carry
over.

## A real shop: open source, on your machine

The engine does not include a storefront and should not. Medusa v2 is open
source and provides the whole shop: a Next.js storefront customers browse, an
admin back office, a Postgres database and an Admin API. We read it and run the
decisions behind it.

```bash
bash scripts/setup-medusa.sh        # Postgres in Docker, then create the shop
```

Prerequisites the script checks for you: **Docker Desktop running** and **Node
22 or newer** (Medusa v2 requires it; the script will use nvm to install 22 if
it can). Expect several minutes for the build.

Once it is up:

| | |
|---|---|
| storefront, what a customer sees | http://localhost:8000 |
| admin back office | http://localhost:9000/app |
| API the engine reads | http://localhost:9000 |

```bash
export MEDUSA_URL=http://localhost:9000
export MEDUSA_EMAIL=admin@medusajs.com
export MEDUSA_PASSWORD=supersecret
python3 run.py medusa check      # auth, and counts of products, orders, stock
python3 run.py medusa sync       # pull it all into the engine
python3 run.py medusa watch 300  # the snapshot job: leave this running
```

Polling, not webhooks, because Medusa's events are in-process and it has no
outbound webhook feature: polling the Admin API is the documented way for an
external service to read it. Authentication is either an email/password JWT
(cached for an hour) or a secret key from Settings → Secret API Keys.

What it maps: products and variants into the catalogue, order lines into
`sales_fact` with the discount percentage per line, and inventory into
`inventory_snapshot` — summed across stock locations and net of reservations,
because a variant held at one of two warehouses is still buyable.
`tests/test_medusa_adapter.py` covers all of it against canned payloads.

**Start the snapshot job first and leave it running.** Availability history
cannot be reconstructed later, so until it has been running a while, demand
reconstruction on a live shop has nothing to work with. Everything the towel
case depends on comes from that job.

## A real Shopify store

```bash
export SHOPIFY_STORE=your-store.myshopify.com
export SHOPIFY_TOKEN=shpat_...
python3 run.py shopify check      # credentials, scopes, counts
python3 run.py shopify sync       # products, orders, first inventory snapshot
python3 run.py shopify watch 900  # the snapshot job, every 15 minutes
```

The token comes from a custom app in the store admin (Settings → Apps and sales
channels → Develop apps), with `read_products`, `read_orders`, `read_inventory`
and `read_locations`.

Polling, not webhooks. A webhook needs a public URL and a tunnel, which is one
more thing to fail during a demo; the Admin API gives the same facts on a
schedule with nothing exposed. Webhooks are a latency upgrade for production,
not a prerequisite.

What it maps: products and variants into the catalogue, orders and refunds into
`sales_fact` with the discount percentage per line, the device mix parsed from
each order's `client_details`, and inventory levels into `inventory_snapshot` —
summed across locations, because a variant in stock at one of two warehouses is
still buyable. `tests/test_shopify_adapter.py` covers all of that against canned
payloads, including the `inventory_item_id` mapping that silently breaks most
integrations.

**The snapshot job is the thing to start first and leave running.** Availability
history cannot be reconstructed afterwards, so until it has been running for a
while, demand reconstruction on a live store has nothing to work with.

## Before a demo

```bash
python3 run.py selftest
```

Sixteen checks in about six seconds, then both storefront adapters: the seed, the model pipeline and its
guards, the bus draining with no dead letters, the towel case reaching the
right quantities, all three gateway tiers exercised, a kill held for a human,
no rationale without evidence, idempotency on a repeated trigger, and the model
provider actually responding.

## The terminal

```bash
python3 run.py demo          # seed 90 days of history, run all three agents, print every decision
python3 run.py towels        # just the reorder case, with every intermediate number
python3 run.py marketing     # the daily allocation pass and the weekly reallocation
python3 run.py verdict       # the portfolio verdicts
python3 run.py guardrails    # four proposals that must be refused, and what refuses them
python3 run.py ledger        # the audit trail
python3 run.py console       # regenerate ../engine-run.html (static snapshot of a run)
python3 run.py reverse 3     # reverse ledger entry 3 (nothing is ever deleted)
```

Python 3.8+ and SQLite, both already on the machine. Set `ANTHROPIC_API_KEY` and
the harness switches from rules-only mode to having the model write the
rationales; the decisions do not change, because the model never produces a
number. That is also the degradation path when an agent exhausts its token
budget.

## What each agent does

| Agent | Trigger | Decides | Code |
|---|---|---|---|
| `reorder` | schedule, stockout risk, published verdict | how much of each variant to buy, from whom, by when | `agents/reorder.py`, `engines/demand.py`, `engines/quantity.py` |
| `marketing_allocator` | hourly guards, daily bands, weekly reallocation | where the ad budget goes, and what gets paused | `agents/marketing.py`, `engines/allocator.py` |
| `product_verdict` | weekly | scale, fix the site, reprice, or kill — and whether the fault is the product or the shop | `agents/verdict.py`, `engines/funnel.py` |

## The case the reorder agent was built around

Twenty white towels sold. Twenty black towels sold. The buyer reordered twice as
much white and no black. The engine, from the same ninety days:

```
                                   v_black     v_white
units shipped (90d)                     20          20
days actually buyable                   22          90
rate of sale / available day         0.909       0.222
substitution share removed              0%         17%
avg discount on sales                    0%         24%
return rate                              5%         20%
reconstructed demand (90d)            81.8        11.6
demand hidden by stockouts            61.8        -8.4
ORDER QUANTITY                          60           0
```

Black was unbuyable for 68 of 90 days, so it recorded zero sales and looked dead.
White was always available and discounted, so it dribbled out twenty units and
looked steady — and 17% of those units were demand displaced from black.
Availability history is what makes this recoverable, and it cannot be
reconstructed after the fact: that is why the hourly snapshot job is the first
thing built, before any agent.

## How the pieces fit

```
adapters / cron  ->  outbox  ->  work_queue  ->  worker
                                                   |
                                        harness (7 stages, bounded)
                                                   |
                              deterministic engines (demand, quantity,
                                     allocation, funnel)
                                                   |
                                     propose_action -> GATEWAY
                                                        schema
                                                        ownership
                                                        evidence check
                                                        guards (cash, cover, caps, cooldown, exposure)
                                                        tier: auto / checker / human
                                                        idempotency
                                                        ledger + event
```

- `core/bus.py` — durable queue with session ordering, bounded retries, dead
  letter, and a transactional outbox. Swap the driver for Service Bus or
  Temporal without touching an agent.
- `core/gateway.py` — the only place a side effect can happen. Agents cannot
  choose their own tier, skip a guard, or call a third party: credentials live
  here.
- `core/harness.py` — reads are tool calls recorded as evidence; writes are typed
  proposals; steps and tokens are bounded; a rationale containing a number that
  no evidence supports is refused.
- `config/*.json` — the whole difference between verticals. `reorder.json`
  carries `review_period_days`, `shelf_life_days`, `cover_cap_weeks` and the
  autonomy ladder, and `_vertical_examples` shows the same agent configured for
  a supermarket's fresh aisle and for sunglasses.

## What is deliberately not here

No broker, no workflow engine, no warehouse, no framework. At ten products the
queue is a table and the whole thing runs on one small machine. Each upgrade has
a written trigger (sustained queue depth, a timer longer than a day, a third
engineer) so adopting it is a decision rather than a drift.
