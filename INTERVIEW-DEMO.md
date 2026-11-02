# The demo — two screens only

Open **http://localhost:8787**.

## 1. Shop

This embeds the **existing Medusa shop**. Browse a product, add it to the cart
and check out using your demo setup. If checkout needs a full window, press
**Open shop in a tab**. The embedded menu, four-product catalogue, in-stock add-to-cart and checkout
address form passed real Chrome checks. T-Shirt S / Black correctly blocks
purchase; choose L / White to buy. No payment or final order was submitted.

Say: “This is the open-source shop I integrated. My work is the decision system
connected behind it.”

## 2. Behind the scenes

Press **Behind the scenes**, then **Refresh from shop**. New orders and stock
are imported through the existing adapter. The rule trees use those stored facts.

Click an agent to expand its branches:

- **Reorder:** buyable days → corrections → returns → economics → existing
  inventory → order quantity. Choose an imported shop variant or the towel case.
- **Marketing:** margin → minimum evidence → measurement health → CPA bands
  → cooldown → action. Its advertising data is simulated.
- **Product verdict:** exposure → supply → reviews → funnel → diagnosis →
  next action. Choose the mug to show FIX_SITE or Sweatpants to show KILL.

Click any branch. The side panel gives its reason, actual numbers and code
reference. **Replay last run** highlights the steps of a stored execution and
shows its original timestamp and mode. It is a replay, not a new AI run.

Say: “Each agent follows explicit checks. It proposes an action; the gate
checks whether it may happen. Stopping a product always needs approval.”

## How to describe the AI accurately

“The commerce integration and rule engines work. A tool-using model layer can
investigate and choose validated actions, with deterministic fallback. During
preflight, the local model replied but skipped a required tool read, so its
answer was rejected and the rules decided. I would not claim that test proved
fully autonomous AI operation.”

Refreshing this screen evaluates rules. It does not submit a purchase order or
change the shop. Checkout import is verified through the adapter; advertising
execution is simulated. Scheduled unattended operation is a separate deployment
concern, and this screen does not imply a background worker is running.

Keep **Detailed maths** closed unless asked. Use the tree as the main demo.

If the console needs restarting, from `engine/`:

```bash
ENGINE_MODEL_PROVIDER=local_llm /opt/anaconda3/bin/python3 -u server.py 8787
```

Do not reset the database or run `--fresh` before presenting: that discards
imported history and approvals.

Verification: 25 backend regression tests and 16 simplified-demo interaction
checks passed, alongside the existing self-test and adapter checks. The in-app browser
connector was unavailable; an isolated Chrome session verified the shopping
flow visually. Screenshots are in artifacts/.
