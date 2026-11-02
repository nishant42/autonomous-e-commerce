# Demo runbook — Sunday 15:00

> Current interview walkthrough: [INTERVIEW-DEMO.md](INTERVIEW-DEMO.md). It covers the completed three-agent page, accurate demand terminology and the non-resetting demo sequence. The older setup notes below include database resets; use the current walkthrough for the interview.


## Before you start (do tonight)

```bash
# 1. the shop must be running: three things
docker start halden-postgres                      # Postgres on 55432
cd ~/halden-shop && npm run dev                   # backend + admin, :9000
cd ~/halden-shop/apps/storefront && npm run dev   # storefront, :8000

# 2. leave this running overnight — it builds the stock history
cd ~/Documents/halden-architecture-site/engine
export MEDUSA_URL=http://localhost:9000 MEDUSA_EMAIL=admin@medusajs.com MEDUSA_PASSWORD=supersecret
python3 run.py medusa watch 300

# 3. prove the model provider works (the one thing never verified)
python3 run.py check-model

# 4. place 4–6 orders on http://localhost:8000 by hand.
#    Buy the LAST unit of "Medusa Shorts M" (7 left) so a variant sells out live.
python3 run.py medusa sync        # the orders appear in the engine
```

## Thirty minutes before

```bash
python3 run.py selftest           # 16 checks, ~6 seconds
python3 run.py ui                 # the console, :8787
```

Tabs open: the console (`:8787`), the shop (`:8000`), the Medusa admin (`:9000/app`).

---

## The demo, in order

```bash
cd ~/Documents/halden-architecture-site/engine
python3 run.py liveprep     # cold start to demo-ready, about 90 seconds
python3 run.py ui
```

Open **http://127.0.0.1:8787**. Four views, same data, increasing depth. Use
them in this order and stop whenever he is satisfied.

### 1 · The system, running (the landing page) — 8 min

An animated map. Press **Run it for real**: the agents run, then the page
replays what they actually did, one packet per step along the wires.

- blue packets are facts being read, teal is deterministic maths, green is the
  trained model, purple is Claude making a judgment, red is an action reaching
  the gate
- the ticker at the bottom names every step as it fires
- the speed slider controls the replay
- **click any box** for what that layer is, in plain words, with its live numbers

What to say while it runs: *"Every dot is a step one of the agents really took.
This is a replay of the run you just triggered, not an animation I drew."*

Then click **The shop** and press **Run the model** inside the panel: a Hugging
Face sentiment model downloads into the browser and classifies the review text
real shoppers left with their orders. One product comes back mostly negative.
*"A product people complain about and return is a product problem, not a shop
problem. That feeds the verdict agent."*

### 2 · In words — 4 min

The same system as six plain-English boxes with live counts. Use this if he
wants the summary rather than the motion.

### 3 · Step by step — 10 min

Pick an agent, press Play, and walk the chain. Stop on **reconstruct demand**
and click it: the right-hand panel shows the actual source of the function that
produced the number. *"That is the code that produced it, not a description."*

### 4 · Console — only if he digs

Approvals queue, ledger with evidence, model leaderboard, the what-if sliders.

### If he asks "how do I know the model is real?" (10 min)

Press **Advanced console** in the top right, then **How it decides**.

This is the strongest ten minutes in the demo, so do not rush it.

**Part one, the decision opened up.** Pick an ad cell. You get the eight checks
the agent made, in order, each with the number it was made on:

> 1 Is this the measurement holdout? → no
> 2 Can supply serve more demand? → cover 233 days, yes
> 3 Has it earned a verdict? → 25 orders, EUR 996 spent, yes
> 4 Still in the learning phase? → no
> 5 Changed recently? → no
> 6 Is the creative worn out? → frequency 2.8, CTR 0.92% against its own baseline, no
> 7 What does the model expect? → model EUR 37, observed EUR 40, blended
> 8 Cost per order against target → EUR 39 against EUR 36 = 107%, trim

Say: *"It did not pick an answer. It asked eight questions in order and stopped
where one of them decided. Every value on screen came from the shop's own data."*

**Part two, prove the model is a model.** Below that are sliders. They are built
from the features the promoted model actually chose, and bounded by the range it
was trained on.

Drag **category search interest** from 60 upward:

| search interest | predicted orders | cost per order | the agent would |
|---|---|---|---|
| 60 | 21.2 | EUR 43.65 | reduce |
| 90 | 29.8 | EUR 31.14 | hold |
| 120 | 41.6 | EUR 22.29 | **scale** |
| 150 | 58.0 | EUR 15.99 | **scale** |

Then drag **creative age** and let him watch fatigue happen:

| creative age | predicted orders | cost per order | the agent would |
|---|---|---|---|
| 0 days | 36.8 | EUR 25.22 | scale |
| 20 days | 27.0 | EUR 34.41 | hold |
| 40 days | 19.7 | EUR 47.11 | reduce |

Say: *"A hardcoded number does not move. Change what the model is told and it
re-predicts, and the decision changes with it."*

Then push a slider past its range on purpose. It refuses to pretend:

> search_index_category set to 300, outside the trained range 57 to 163: the
> prediction is an extrapolation and should not be trusted

Say: *"That is the difference between a model you can run a business on and a
demo. It knows where its knowledge stops."*

**Part three, the AI agent itself.** Go to **Ask the agent** and type:
*"Why did you order 60 black towels and none white?"* The tool calls appear one
by one as it reads the data, then the answer, then a badge confirming every
figure traced back to stored evidence.

### Then, if he wants under the hood (10 min)

Esc out of Presenter and use the normal tabs:

- **Approvals** — the kill sitting there unsigned
- **Ledger** — click an evidence id, show a number tracing to its query
- **Models** — the guards that fired, the leaderboard
- **Ask the agent** — type *"Why did you order 60 black towels and none white?"*

Only open a terminal if he asks to see the code, or for `python3 run.py guardrails`
(four forbidden actions, all refused).

### The live shop (5 min, optional)

Open `localhost:8000/dk/store`, buy something in front of him, then in a terminal:

```bash
python3 run.py medusa sync
```

Skip this entirely if anything is misbehaving. Nothing else depends on it.

## If something breaks

| Symptom | Do this |
|---|---|
| Presenter shows "Not run yet" | Esc, press Run full cycle, wait, press Presenter again |
| Console shows stale data | It refreshes every 6s; reload the page |
| `connection refused` on 9000 | The Medusa backend stopped — `cd ~/halden-shop && npm run dev` |
| Medusa won't boot | `docker start halden-postgres` first |
| `check-model` fails | Harmless — the engines decide without it. Say so and move on |
| Anything else | `python3 run.py demo` prints the whole story in the terminal with no server at all |

## Numbers worth knowing by heart

- 20 and 20 units shipped; 22 vs 90 days buyable; 0.909 vs 0.222 per day
- Reconstructed demand 81.8 vs 11.6 → order 60 black, 0 white
- Service level 88%, derived from margin (Cu 25.75 / Co 3.68), not a blanket 95%
- Platform cost at ten products: roughly €600–1,100 a month
- Engine: ~3,500 lines, no dependencies for the core, 16 self-test checks
