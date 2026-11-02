"""The harness: everything around the model that makes it usable and safe.

Stages, in order, for every agent run:
  1 intake            - what triggered this, what is in scope
  2 context           - read tools only; every result is stored as evidence
  3 loop              - bounded steps, bounded tokens
  4 tool gateway      - writes leave only as typed proposals (core.gateway)
  5 verification      - rules that must pass before a proposal is submitted
  6 commit + memory   - ledger entry, outbox event, what the agent learned
  7 observe           - run record with steps, tokens, cost, outcome

The model is optional. With no API key the harness runs in rules-only mode:
deterministic engines still decide, and the rationale is templated. That is the
same degradation path used when an agent exhausts its token budget (rule R10).
"""
import inspect
import json
import os
import re

from core import db, gateway, model

class Harness(object):
    def __init__(self, conn, agent, config, trigger="manual"):
        self.conn = conn
        self.agent = agent
        self.cfg = config
        self.trigger = trigger
        self.run_id = db.new_id("run")
        self.steps = 0
        self.tokens = 0
        self.cost = 0.0
        self.evidence = []
        self.tools = {}
        self.mode = "model" if model.available() else "rules-only"
        self.trace = []
        self.steps_this_decision = 0
        self.decision_label = ""
        self.model_calls = 0
        self.model_failures = 0
        self.model_error = None
        conn.execute(
            "INSERT INTO agent_run (id, agent, started_at, trigger, steps, tokens, cost_eur, mode, outcome)"
            " VALUES (?,?,?,?,0,0,0,?,'running')",
            (self.run_id, agent, db.now(), trigger, self.mode),
        )

    # ---- the trace: what ran, in order, and where that code lives --------
    def step(self, kind, title, detail="", data=None, fn=None, evidence_id=None):
        """Record one step of the path actually taken.

        `fn` is the function that did the work; its module, name and line are
        stored so the console can show the code that produced the number rather
        than a description of it.
        """
        ref = None
        if fn is not None:
            try:
                ref = {"module": fn.__module__, "name": getattr(fn, "__qualname__", fn.__name__),
                       "line": inspect.getsourcelines(fn)[1]}
            except (OSError, TypeError):
                ref = {"module": getattr(fn, "__module__", "?"),
                       "name": getattr(fn, "__qualname__", "?"), "line": None}
        self.trace.append({"seq": len(self.trace) + 1, "kind": kind, "title": title,
                           "detail": detail, "data": data or {}, "code": ref,
                           "evidence_id": evidence_id})

    # ---- stage 2: reads, each one recorded as evidence -------------------
    def register(self, name, fn):
        self.tools[name] = fn

    def read(self, name, **args):
        """Call a read tool. Returns (result, evidence_id).

        A tool not declared in the agent's config does not exist for it.
        """
        if name not in self.cfg["reads"]:
            raise gateway.Rejected("tool %s not granted to agent %s" % (name, self.agent))
        if name not in self.tools:
            raise gateway.Rejected("tool %s not implemented" % name)
        self._step()
        result = self.tools[name](self.conn, **args)
        eid = db.new_id("ev")
        self.conn.execute(
            "INSERT INTO evidence (id, agent, tool, args, result, created_at) VALUES (?,?,?,?,?,?)",
            (eid, self.agent, name, db.dumps(args), db.dumps(result), db.now()),
        )
        self.evidence.append({"id": eid, "tool": name, "result": result})
        def _short(value):
            text = str(value)
            if isinstance(value, dict):
                text = "{%d fields}" % len(value)
            elif isinstance(value, (list, tuple)):
                text = "[%d items]" % len(value)
            return text if len(text) <= 36 else text[:33] + "..."

        summary = (", ".join("%s=%s" % (k, _short(v))
                             for k, v in list((result or {}).items())[:4])
                   if isinstance(result, dict) else str(result)[:80])
        self.step("read", name, summary, data={"args": args}, fn=self.tools[name], evidence_id=eid)
        return result, eid

    def new_decision(self, label=""):
        """Start a fresh step budget.

        The budget exists to stop one decision looping forever, not to limit how
        many decisions a cycle may contain. Judging seven products is seven
        budgets, not one that runs out on the fifth.
        """
        self.steps_this_decision = 0
        self.decision_label = label

    def _step(self):
        self.steps += 1
        self.steps_this_decision = getattr(self, "steps_this_decision", 0) + 1
        cap = self.cfg["model"]["max_steps"]
        if self.steps_this_decision > cap:
            raise gateway.Rejected("step budget exhausted for %s (%d steps)"
                                   % (self.decision_label or "this decision", cap))

    # ---- stage 5: verification ------------------------------------------
    def uncited_numbers(self, text, extra=()):
        """R3: every number in a rationale must trace to stored evidence."""
        pool = set()
        for item in list(self.evidence) + [{"result": e} for e in extra]:
            for num in re.findall(r"-?\d+(?:\.\d+)?", db.dumps(item["result"])):
                f = float(num)
                pool.update({num, str(int(round(f))), "%.1f" % f, "%.2f" % f})
        missing = []
        for num in re.findall(r"-?\d+(?:\.\d+)?", text):
            f = float(num)
            forms = {num, str(int(round(f))), "%.1f" % f, "%.2f" % f}
            if not forms & pool:
                missing.append(num)
        return missing

    def verify(self, checks):
        """checks: list of (name, bool, message). Returns list of failures."""
        return [(n, m) for n, ok, m in checks if not ok]

    # ---- stage 4/6: the only write path ---------------------------------
    def propose(self, intent, payload, policy, ctx=None, rationale="", period="", checker=None):
        row = gateway.propose(
            self.conn, self.agent, intent, payload, policy,
            ctx=ctx, rationale=rationale, period=period, checker=checker,
            evidence=[e["id"] for e in self.evidence],
        )
        self.step("gateway", intent,
                  "%s / %s / %s" % (row["tier"] or "-", row["status"], row["reason"]),
                  data={"payload": payload, "value_eur": row["value_eur"],
                        "ledger_id": row["id"]}, fn=gateway.propose)
        return row

    def anomaly(self, kind, severity, note):
        self.conn.execute("INSERT INTO anomaly (ts, agent, kind, severity, note) VALUES (?,?,?,?,?)",
                          (db.now(), self.agent, kind, severity, note))

    # ---- stage 3: the model, when there is one --------------------------
    def rationale(self, facts, template):
        """Ask the model to narrate a decision the engines already made.

        The model never produces a number: `facts` is the complete set of
        values, and the template is what runs in rules-only mode or whenever
        the model returns a figure it cannot support.
        """
        fallback = template.format(**facts)
        if self.mode != "model":
            return fallback
        budget = self.cfg["model"].get("token_budget_month", 0)
        if budget and self.tokens > budget:
            return fallback
        prompt = (
            "You are writing one sentence of justification for an automated commerce decision.\n"
            "Use ONLY these values. Do not introduce any new number and do not round "
            "differently. Each key names its own unit - weeks are weeks, days are days, "
            "EUR is money - and describing a value in the wrong unit is an error:\n"
            + json.dumps(facts, indent=2, default=str)
            + "\n\nWrite one plain sentence a buyer or marketer would accept. No preamble, no JSON."
        )
        try:
            text, meta = model.complete(prompt, model=self.cfg["model"].get("plan"))
            self.model_calls += 1
            self.tokens += (meta.get("tokens_in", 0) or 0) + (meta.get("tokens_out", 0) or 0)
            self.cost += meta.get("cost_eur", 0.0) or 0.0
            text = text.strip()
            # Verified like any other claim: an uncited number means we fall back.
            if text and not self.uncited_numbers(text, extra=[facts]):
                return text
            return fallback
        except Exception as exc:                             # noqa: BLE001
            # Claim nothing that did not happen: the run is recorded as having
            # degraded, with the reason, rather than as a model run.
            self.model_failures += 1
            self.model_error = repr(exc)[:160]
            self.mode = "rules-only (model unreachable)"
            return fallback

    # ---- stage 3b: a bounded judgment, made by the model ----------------
    def investigate(self, task, spec, scope, required, max_steps=6):
        """Run a scoped, audited investigation; reject answers without required reads.

        A model may choose its reads, but cannot change the current product/SKU.
        Failed or missing mandatory reads cannot support a model decision.
        """
        events = []
        if not model.available():
            self.mode = "rules-only"
            return None, events

        def executor(name, args):
            clean = {k: v for k, v in (args or {}).items() if v not in (None, "")}
            for key, allowed in scope.items():
                if key in clean and clean[key] not in allowed:
                    raise gateway.Rejected("%s is outside this decision's scope" % key)
            return self.read(name, **clean)

        def event(kind, payload):
            events.append({"kind": kind, "payload": payload})

        try:
            required_calls = []
            for name in required:
                fields = next((s.get("args", {}) for s in spec if s["name"] == name), {})
                args = {key: values[0] for key, values in scope.items() if key in fields and len(values) == 1}
                required_calls.append({"tool": name, "args": args})
            out = model.agent_loop(task, spec, executor, model=self.cfg["model"].get("plan"),
                                   max_steps=min(max_steps, self.cfg["model"]["max_steps"]),
                                   max_tokens=self.cfg["model"].get("max_tokens_per_decision", 16000),
                                   required_calls=required_calls,
                                   on_event=event)
            totals = out.get("totals") or {}
            self.model_calls += totals.get("steps", 0)
            self.tokens += totals.get("tokens_in", 0) + totals.get("tokens_out", 0)
            self.cost += totals.get("cost_eur", 0.0)
            if totals.get("providers"):
                self.mode = "model (%s)" % ", ".join(totals["providers"])
            succeeded = {t.get("tool") for t in out.get("trace", []) if t.get("ok")}
            answer = out.get("answer")
            if isinstance(answer, str):
                try:
                    answer = json.loads(answer)
                except ValueError:
                    answer = None
            if not isinstance(answer, dict) or not set(required) <= succeeded:
                self.step("verification", "model answer rejected",
                          "invalid answer or mandatory evidence was not read")
                return None, events
            why = answer.get("why", "")
            if not isinstance(why, str) or not why.strip() or self.uncited_numbers(why):
                self.step("verification", "model answer rejected", "missing rationale or unsupported numbers")
                return None, events
            out["answer"] = answer
            return out, events
        except Exception as exc:
            self.model_failures += 1
            self.model_error = str(exc)[:160]
            self.mode = "rules-only (model unreachable)"
            self.step("verification", "model unavailable; deterministic fallback", self.model_error)
            return None, events

    def judge(self, question, options, facts, default, tool_names=None, max_steps=4):
        """Let the model make a real decision, inside a fence.

        This is not narration. The model picks one of `options` and may call the
        agent's read tools first to inform itself. What it cannot do is invent an
        option, produce a number, or cause an effect: the choice is validated
        against the list, every tool call is recorded as evidence, and the result
        still goes through the gateway like any other proposal.

        If no model is available, if it times out, or if it answers with
        something not on the list, `default` is used and the trace says so.
        """
        allowed = list(options)
        outcome = {"choice": default, "why": "", "source": "default",
                   "model_trace": [], "options": allowed}

        if not model.available():
            outcome["why"] = "no model provider available, deterministic default used"
            self.step("judgment", question, "%s (no model)" % default,
                      data=outcome, fn=Harness.judge)
            return outcome

        tool_names = [t for t in (tool_names or list(self.cfg.get("reads", []))) if t in self.tools]
        spec = [{"name": n, "description": "read tool", "args": {}} for n in tool_names]
        task = (
            "You are deciding one thing inside an automated commerce system.\n\n"
            "QUESTION: " + question + "\n\n"
            "You must choose exactly one of these options:\n"
            + "\n".join("  - " + o for o in allowed) + "\n\n"
            "Facts already established by the deterministic engines (do not recompute, "
            "do not contradict, do not invent new numbers):\n"
            + json.dumps(facts, indent=2, default=str) + "\n\n"
            "You may call a read tool first if you genuinely need more. When ready answer with\n"
            '  {"answer": {"choice": "<one option exactly as written>", "why": "<one sentence>"}}'
        )

        def executor(name, args):
            clean = {k: v for k, v in (args or {}).items() if v not in (None, "")}
            return self.read(name, **clean)

        try:
            out = model.agent_loop(task, spec, executor, model=self.cfg["model"].get("plan"),
                                   max_steps=max_steps)
        except Exception as exc:                                   # noqa: BLE001
            self.model_failures += 1
            self.mode = "rules-only (model unreachable)"
            outcome["why"] = "model unreachable (%s), deterministic default used" % repr(exc)[:90]
            self.step("judgment", question, "%s (model unreachable)" % default,
                      data=outcome, fn=Harness.judge)
            return outcome

        answer = out.get("answer")
        if isinstance(answer, str):
            try:
                answer = json.loads(answer)
            except ValueError:
                answer = {"choice": answer, "why": ""}
        choice = (answer or {}).get("choice")
        why = (answer or {}).get("why", "")
        self.tokens += out["totals"].get("tokens_in", 0) + out["totals"].get("tokens_out", 0)
        self.cost += out["totals"].get("cost_eur", 0.0)
        outcome["model_trace"] = [{"tool": t.get("tool"), "args": t.get("args"),
                                   "evidence_id": t.get("evidence_id")} for t in out.get("trace", [])]

        if choice in allowed:
            outcome.update({"choice": choice, "why": why, "source": "model"})
            detail = "%s - %s" % (choice, why[:120])
        else:
            outcome["why"] = ("model answered %r, which is not one of the permitted options, "
                              "so the deterministic default stands" % str(choice)[:60])
            detail = "%s (model answer rejected)" % default
        self.step("judgment", question, detail, data=outcome, fn=Harness.judge)
        return outcome

    # ---- stage 7 ---------------------------------------------------------
    def finish(self, outcome):
        if self.model_failures:
            outcome += " (model unreachable x%d: %s)" % (self.model_failures, self.model_error)
        self.conn.execute(
            "UPDATE agent_run SET finished_at=?, steps=?, tokens=?, cost_eur=?, mode=?,"
            " outcome=?, trace=? WHERE id=?",
            (db.now(), self.steps, self.tokens, round(self.cost, 5), self.mode, outcome,
             db.dumps(self.trace), self.run_id),
        )


def load_config(name):
    path = os.path.join(os.path.dirname(__file__), "..", "config", name + ".json")
    with open(path) as fh:
        return json.load(fh)
