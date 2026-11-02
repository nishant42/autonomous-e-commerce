"""The model layer: a real tool-using agent loop, with three providers.

Provider is detected, never assumed:

  claude_cli     the `claude` binary, headless (`claude -p`). Runs on the
                 operator's existing Claude Code subscription: no API key and
                 no per-token bill, which is why it is the default when found.
  anthropic_api  ANTHROPIC_API_KEY, for unattended servers.
  rules_only     no model available, or the agent's token budget is spent.
                 Every decision still happens: the engines are deterministic.

The loop is a genuine agent loop. The model chooses which read tool to call,
we execute it against the database, the result goes back, and it decides again,
up to a step budget. What it may NOT do is produce a number or cause a side
effect: quantities come from the engines, and writes go through the gateway.
"""
import json
import os
import re
import shutil
import subprocess
import urllib.request

PROTOCOL = """You are an operations agent inside an autonomous commerce platform.

You answer by returning ONE JSON object and nothing else. No prose outside it,
no markdown fence. Two forms are allowed:

  {"call": {"tool": "<tool name>", "args": {...}}}   to read data
  {"answer": "<your final answer>"}                  when you have enough

Rules you must follow:
- Only call tools from the list given. Arguments must match exactly.
- Every number in your answer must come from a tool result you received in this
  conversation. Never estimate, never round differently, never invent a figure.
- Be specific and brief. An operator reads this, not a customer.
"""

CLI_CANDIDATES = [
    os.environ.get("CLAUDE_CLI", ""),
    "claude",
    os.path.expanduser("~/.claude/local/claude"),
    os.path.expanduser("~/.local/bin/claude"),
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
]

# Where npm puts the platform-native binary when the postinstall copy into
# bin/claude.exe did not happen. A broken shim is common and the real binary is
# usually sitting right there, so it is worth looking rather than giving up.
NATIVE_GLOBS = [
    "~/.nvm/versions/node/*/lib/node_modules/@anthropic-ai/claude-code/node_modules/"
    "@anthropic-ai/claude-code-%s/claude",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/node_modules/"
    "@anthropic-ai/claude-code-%s/claude",
    "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/node_modules/"
    "@anthropic-ai/claude-code-%s/claude",
    "~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/node_modules/"
    "@anthropic-ai/claude-code-%s/claude",
]

STUB_MARKER = b"native binary not installed"


def _platform_tag():
    import platform
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "win32"}.get(platform.system(), "linux")
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    return "%s-%s" % (system, arch)


def _usable(path):
    """Is this a real, runnable CLI? Returns (ok, reason)."""
    if not path or not os.path.exists(path):
        return False, "not found"
    real = os.path.realpath(path)
    if not os.path.exists(real):
        return False, "dangling symlink to %s" % real
    if not os.access(real, os.X_OK):
        return False, "not executable (%s)" % real
    try:
        if os.path.getsize(real) < 100_000:
            with open(real, "rb") as fh:
                head = fh.read(400)
            if STUB_MARKER in head:
                return False, "install stub: the native binary was never downloaded"
    except OSError as exc:
        return False, str(exc)
    return True, "ok"


def survey():
    """Every candidate examined, and why each was accepted or rejected.

    Printed by `run.py check-model`, because "claude not found" is not a useful
    thing to discover during a demo.
    """
    import glob
    seen, rows = set(), []
    for cand in CLI_CANDIDATES:
        if not cand:
            continue
        path = shutil.which(cand) if os.sep not in cand else cand
        if not path or path in seen:
            continue
        seen.add(path)
        ok, reason = _usable(path)
        rows.append({"path": path, "ok": ok, "reason": reason, "source": "PATH or well-known"})
    # platform.machine() lies under Rosetta (an x86 Python on an arm64 Mac),
    # so every platform package is tried and executability decides.
    tags = [_platform_tag()] + ["darwin-arm64", "darwin-x64", "linux-x64", "linux-arm64"]
    patterns = [pat % tag for pat in NATIVE_GLOBS for tag in dict.fromkeys(tags)]
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.expanduser(pattern))):
            if path in seen:
                continue
            seen.add(path)
            ok, reason = _usable(path)
            rows.append({"path": path, "ok": ok, "reason": reason, "source": "npm platform package"})
    return rows


def find_cli():
    for row in survey():
        if row["ok"]:
            return row["path"]
    return None


# A provider that fails once is not retried for the rest of the process: a
# demo should not pay a timeout per decision to rediscover the same outage.
_DEAD = set()

LOCAL_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".venv-ml", "bin", "python")
LOCAL_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engines",
                            "llm_worker.py")
LOCAL_MODEL = os.environ.get("LOCAL_LLM", "Qwen/Qwen2.5-0.5B-Instruct")


def local_available():
    return os.path.exists(LOCAL_VENV) and os.path.exists(LOCAL_WORKER)


def chain():
    """Providers in the order they will be tried."""
    forced = os.environ.get("ENGINE_MODEL_PROVIDER")
    if forced == "rules_only":
        return []
    if forced == "local_llm":
        return [("local_llm", LOCAL_MODEL)] if local_available() else []
    out = []
    cli = find_cli()
    if cli and "claude_cli" not in _DEAD:
        out.append(("claude_cli", cli))
    if os.environ.get("ANTHROPIC_API_KEY") and "anthropic_api" not in _DEAD:
        out.append(("anthropic_api", "ANTHROPIC_API_KEY"))
    if local_available() and "local_llm" not in _DEAD:
        out.append(("local_llm", LOCAL_MODEL))
    return out


def detect():
    """Return (provider, detail) for whichever provider would be used next."""
    options = chain()
    if not options:
        forced = os.environ.get("ENGINE_MODEL_PROVIDER")
        return "rules_only", ("forced by ENGINE_MODEL_PROVIDER" if forced == "rules_only"
                              else "no model provider available")
    return options[0]


def status():
    provider, detail = detect()
    label = {"claude_cli": "Claude CLI (subscription, no API cost)",
             "anthropic_api": "Anthropic API",
             "local_llm": "local open-source model, offline and free",
             "rules_only": "rules-only (deterministic engines)"}[provider]
    return {"provider": provider, "detail": detail, "label": label,
            "chain": [p for p, _ in chain()], "unreachable": sorted(_DEAD)}


# ------------------------------------------------------------------ calls ----

def _call_cli(prompt, model, cli_path, timeout=120):
    """One headless turn through the Claude CLI. No tools granted to the CLI
    itself: our harness owns tool execution, so the model cannot touch the
    filesystem or the network on its own."""
    cmd = [cli_path, "-p", prompt, "--output-format", "json",
           "--allowedTools", "", "--permission-mode", "default"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except PermissionError:
        raise RuntimeError(
            "cannot execute %s. If you are running inside a restricted shell or sandbox, run the "
            "server from a normal terminal, or set ENGINE_MODEL_PROVIDER=rules_only." % cli_path)
    except FileNotFoundError:
        raise RuntimeError("claude CLI not found at %s" % cli_path)
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after %ss" % timeout)
    if proc.returncode != 0:
        raise RuntimeError("claude cli exited %s: %s" % (proc.returncode, proc.stderr.strip()[:300]))
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return proc.stdout.strip(), {}
    if not isinstance(data, dict) or data.get("is_error") or str(data.get("subtype", "")).startswith("error"):
        detail = data.get("result", "provider returned an error") if isinstance(data, dict) else "invalid provider response"
        raise RuntimeError(str(detail)[:200])
    text = data.get("result") or ""
    if not text.strip():
        raise RuntimeError("provider returned an empty result")
    usage = data.get("usage") or {}
    meta = {"tokens_in": usage.get("input_tokens", 0), "tokens_out": usage.get("output_tokens", 0),
            "cost_eur": 0.0, "billing": "subscription"}
    return text, meta


def _call_api(prompt, model, timeout=60):
    body = json.dumps({"model": model or "claude-sonnet-5-5", "max_tokens": 900,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"content-type": "application/json",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                          "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
    usage = data.get("usage", {})
    tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    pin, pout = PRICES.get(model or "claude-sonnet-5-5", (3.0, 15.0))
    return text, {"tokens_in": tin, "tokens_out": tout,
                  "cost_eur": (tin * pin + tout * pout) / 1_000_000, "billing": "api"}


def _call_local(prompt, timeout=300):
    """A small instruct model in .venv-ml. No key, no network, no signing."""
    payload = json.dumps({"prompt": prompt, "model": LOCAL_MODEL, "max_tokens": 160})
    proc = subprocess.run([LOCAL_VENV, LOCAL_WORKER], input=payload,
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("local model failed: " + proc.stderr.strip()[-200:])
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    return data.get("text", ""), {"tokens_in": data.get("tokens_in", 0),
                                  "tokens_out": data.get("tokens_out", 0),
                                  "cost_eur": 0.0, "billing": "local"}


def complete(prompt, model=None, timeout=120):
    """Try each provider in turn. A provider that fails is not tried again.

    The point is that a judgment never silently disappears because one vendor
    is unreachable: it falls to the next, and only then to the rules.
    """
    errors = []
    for provider, detail in chain():
        try:
            if provider == "claude_cli":
                text, meta = _call_cli(prompt, model, detail, timeout)
            elif provider == "anthropic_api":
                text, meta = _call_api(prompt, model, timeout)
            else:
                text, meta = _call_local(prompt, max(timeout, 300))
            meta["provider"] = provider
            return text, meta
        except Exception as exc:                               # noqa: BLE001
            _DEAD.add(provider)
            errors.append("%s: %s" % (provider, str(exc)[:120]))
    raise RuntimeError("no model provider worked (" + "; ".join(errors) + ")"
                       if errors else "no model provider available")


def available():
    return bool(chain())


# -------------------------------------------------------------- the loop ----

def _extract_json(text):
    """Models wrap JSON in prose or fences more often than they should."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    start = None
    return None


def agent_loop(task, tools_spec, executor, model=None, max_steps=6, on_event=None, max_tokens=None,
               required_calls=None):
    """Run a tool-using loop and return the result plus a full trace.

    tools_spec: [{"name":..., "description":..., "args": {...}}]
    executor:   callable(tool_name, args) -> (result, evidence_id)
    on_event:   callable(kind, payload) for live UI streaming
    """
    def emit(kind, payload):
        if on_event:
            on_event(kind, payload)

    transcript = [PROTOCOL, "\nTools available:\n" + json.dumps(tools_spec, indent=2),
                  "\nTask:\n" + task]
    trace = []
    required_calls = required_calls or []
    totals = {"tokens_in": 0, "tokens_out": 0, "cost_eur": 0.0, "steps": 0, "billing": "", "providers": []}

    for step in range(max_steps):
        if max_tokens is not None and totals["tokens_in"] + totals["tokens_out"] >= max_tokens:
            emit("note", {"message": "token budget exhausted"})
            return {"answer": None, "trace": trace, "totals": totals, "parsed": False}
        prompt = "\n".join(transcript)
        emit("thinking", {"step": step + 1})
        text, meta = complete(prompt, model=model)
        totals["steps"] = step + 1
        for k in ("tokens_in", "tokens_out", "cost_eur"):
            totals[k] += meta.get(k, 0) or 0
        totals["billing"] = meta.get("billing", "")
        if meta.get("provider") and meta["provider"] not in totals["providers"]:
            totals["providers"].append(meta["provider"])

        obj = _extract_json(text)
        if not isinstance(obj, dict):
            emit("note", {"message": "model returned unparseable output, stopping"})
            return {"answer": text, "trace": trace, "totals": totals, "parsed": False}

        if "call" in obj:
            name = (obj["call"] or {}).get("tool")
            args = (obj["call"] or {}).get("args") or {}
            allowed = {t["name"] for t in tools_spec}
            if name not in allowed:
                msg = "Tool %r is not available. Choose from: %s" % (name, sorted(allowed))
                trace.append({"tool": name, "args": args, "error": msg})
                emit("tool_denied", {"tool": name, "reason": msg})
                transcript += ["\nYour last output:\n" + text, "\nTool result:\n" + msg]
                continue
            try:
                result, evidence_id = executor(name, args)
                ok = True
            except Exception as exc:                                  # noqa: BLE001
                result, evidence_id, ok = {"error": repr(exc)}, None, False
            trace.append({"tool": name, "args": args, "evidence_id": evidence_id,
                          "result": result, "ok": ok})
            emit("tool_call", {"tool": name, "args": args, "evidence_id": evidence_id,
                               "ok": ok, "result": result})
            transcript += ["\nYour last output:\n" + text,
                           "\nTool result for %s:\n%s" % (name, json.dumps(result, default=str)[:4000])]
            continue

        completed = {t.get("tool") for t in trace if t.get("ok")}
        missing = [call for call in required_calls if call["tool"] not in completed]
        if missing:
            emit("note", {"message": "answer deferred: required evidence has not been read"})
            transcript += ["\nYour last output:\n" + text,
                           "\nThat answer cannot be accepted before reading evidence. "
                           "Your next response must request this read tool, using this JSON:\n"
                           + json.dumps({"call": missing[0]})]
            continue
        answer = obj.get("answer", text)
        emit("answer", {"text": answer})
        return {"answer": answer, "trace": trace, "totals": totals, "parsed": True}

    emit("note", {"message": "step budget exhausted"})
    return {"answer": "Step budget exhausted before reaching an answer.",
            "trace": trace, "totals": totals, "parsed": False}
