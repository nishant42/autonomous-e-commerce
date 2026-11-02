/* The system, animated from its own trace.
   Every packet you see corresponds to a step an agent really took: the timeline
   is built from agent_run.trace, not from a script. */
(function () {
  "use strict";
  var SVG = "http://www.w3.org/2000/svg";
  var svg = document.getElementById("svg");
  var panel = document.getElementById("panel");
  var ticker = document.getElementById("ticker");
  var state = null, flow = null, timeline = [], playing = false, cursor = 0, speed = 5;

  // ---- the map -----------------------------------------------------------
  var N = {
    shop:     { x: 90,  y: 330, w: 190, h: 92,  t: "The shop",      s: "Medusa · open source",
                about: "A real storefront running on this machine. Customers browse it, add to cart and check out. We did not build it and we do not want to: it is swappable, and there is a second adapter for Shopify writing into the same tables." },
    adapter:  { x: 330, y: 345, w: 150, h: 62,  t: "Adapter",       s: "302 lines",
                about: "Polls the shop's API for products, orders and stock. Medusa has no outbound webhooks, so polling is the documented way for an outside service to read it. The adapter can read; it can never write to the shop." },
    memory:   { x: 530, y: 330, w: 170, h: 92,  t: "Memory",        s: "every fact, kept",
                about: "Hourly readings of what was in stock, every order line, every ad day, and the stored result of every query an agent ever ran. Stock history is the one thing that cannot be recovered later, which is why it is written down before anything clever happens." },
    bus:      { x: 750, y: 345, w: 130, h: 62,  t: "Queue",         s: "durable work",
                about: "Work is handed over as a row in the database, not a function call. If the process dies mid-decision the work survives, and two workers can never process the same product at once." },
    marketing:{ x: 940, y: 120, w: 240, h: 104, t: "Marketing agent", s: "where the money goes",
                about: "Judges every ad against a target cost per order worked out from margin, and only once it has had enough traffic to be judged fairly. It proposes budget changes; it cannot spend." },
    reorder:  { x: 940, y: 320, w: 240, h: 104, t: "Reorder agent",  s: "what to buy",
                about: "Reconstructs what demand really was, correcting for the days a product could not be bought, for sales stolen from a sold-out sibling, for discounts and for returns. Then it sizes the order from the item's own margin." },
    verdict:  { x: 940, y: 520, w: 240, h: 104, t: "Verdict agent",  s: "keep, fix or kill",
                about: "Breaks the funnel into stages and names which one is at fault, so a broken checkout is never recorded as a failed product. A kill is never automatic." },
    chronos:  { x: 470, y: 530, w: 170, h: 74,  t: "Chronos",        s: "foundation model, on trial",
                about: "Amazon's pretrained time-series transformer, from Hugging Face, running locally. It forecasts a series it has never seen with no fitting. It is on trial against the statistics the reorder agent already uses, scored on demand it was not shown, and it may only be used while it wins." },
    engines:  { x: 700, y: 530, w: 170, h: 74,  t: "Engines",        s: "deterministic maths",
                about: "Censored-demand reconstruction, the newsvendor quantity rule, funnel decomposition. No AI anywhere near them: these produce every number, so every number is reproducible." },
    ml:       { x: 700, y: 120, w: 170, h: 74,  t: "Trained model",  s: "ridge · R² 0.98",
                about: "Six model families compete on 35 features; the winner is whichever performs on data it has never seen. It is used only while it beats the benchmark of ‘the same as last week’, and it advises the rules rather than overriding them." },
    hf:       { x: 470, y: 120, w: 170, h: 74,  t: "Hugging Face",   s: "two jobs, in the browser",
                about: "Two open models do work no rule can. A sentence-embedding model reads the product text and decides which items compete for the same purchase, which is what makes the substitution correction possible. A sentiment model reads the review text customers leave. Neither forecasts: on tabular data, gradient boosting and ridge win, and the leaderboard on the console proves it." },
    claude:   { x: 700, y: 225, w: 170, h: 74,  t: "Claude",         s: "bounded judgment",
                about: "Called only where a rule genuinely cannot decide. It is given a fixed list of options and the facts the engines established, it may read data first, and it must pick one of those options. It cannot invent an option, produce a number, or cause an effect." },
    gate:     { x: 1250, y: 320, w: 170, h: 104, t: "The gate",      s: "nothing passes freely",
                about: "The only place a side effect can happen, and the only place that holds the passwords. It checks the shape of the action, whether that agent owns it, whether the money is there, and how large it is. Small and reversible runs itself; larger gets a second opinion; irreversible waits for a person." },
    ledger:   { x: 1460, y: 180, w: 120, h: 80,  t: "Record",        s: "append only",
                about: "Every action ever attempted, including the refusals, each with its reason and the stored facts behind it. Undoing something writes an opposite entry; nothing is deleted." },
    human:    { x: 1460, y: 330, w: 120, h: 80,  t: "You",           s: "the human line",
                about: "Closing a product down, money above the limit, a supplier's bank details. These stop here with the whole case attached, and wait." },
    world:    { x: 1460, y: 480, w: 120, h: 80,  t: "The world",     s: "suppliers · ads",
                about: "Purchase orders to suppliers and budget changes at the ad platforms. Reached only by the gate, never by an agent directly." }
  };

  var EDGES = [
    ["shop", "adapter"], ["adapter", "memory"], ["memory", "bus"],
    ["bus", "marketing"], ["bus", "reorder"], ["bus", "verdict"],
    ["memory", "marketing"], ["memory", "reorder"], ["memory", "verdict"],
    ["ml", "marketing"], ["claude", "marketing"], ["claude", "verdict"], ["claude", "reorder"],
    ["engines", "reorder"], ["engines", "verdict"], ["engines", "marketing"],
    ["memory", "hf"], ["hf", "engines"], ["hf", "verdict"],
    ["memory", "chronos"], ["chronos", "engines"],
    ["marketing", "gate"], ["reorder", "gate"], ["verdict", "gate"],
    ["gate", "ledger"], ["gate", "human"], ["gate", "world"]
  ];

  function cx(n) { return n.x + n.w / 2; }
  function cy(n) { return n.y + n.h / 2; }

  function mk(tag, attrs) {
    var e = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  function edgePath(a, b) {
    var x1 = cx(a), y1 = cy(a), x2 = cx(b), y2 = cy(b);
    var mx = (x1 + x2) / 2;
    return "M" + x1 + "," + y1 + " C" + mx + "," + y1 + " " + mx + "," + y2 + " " + x2 + "," + y2;
  }

  var paths = {}, nodeEls = {}, layerEdges, layerNodes, layerPk;

  function draw() {
    svg.innerHTML = "";
    layerEdges = mk("g", {}); layerPk = mk("g", {}); layerNodes = mk("g", {});
    svg.appendChild(layerEdges); svg.appendChild(layerPk); svg.appendChild(layerNodes);

    EDGES.forEach(function (e) {
      var p = mk("path", { d: edgePath(N[e[0]], N[e[1]]), class: "edge" });
      layerEdges.appendChild(p);
      paths[e[0] + ">" + e[1]] = p;
    });

    Object.keys(N).forEach(function (key) {
      var n = N[key];
      var g = mk("g", { class: "nd", "data-node": key });
      g.appendChild(mk("rect", { x: n.x, y: n.y, width: n.w, height: n.h, rx: 13, class: "plate" }));
      var t = mk("text", { x: n.x + 15, y: n.y + 27, class: "ttl" }); t.textContent = n.t;
      var s = mk("text", { x: n.x + 15, y: n.y + 45, class: "sub" }); s.textContent = n.s;
      var v = mk("text", { x: n.x + 15, y: n.y + n.h - 14, class: "num", id: "num-" + key });
      g.appendChild(t); g.appendChild(s); g.appendChild(v);
      layerNodes.appendChild(g);
      nodeEls[key] = g;
    });
  }

  function setNum(key, text) {
    var el = document.getElementById("num-" + key);
    if (el) el.textContent = text || "";
  }

  function flash(key, cls, ms) {
    var g = nodeEls[key];
    if (!g) return;
    g.classList.add(cls || "hot");
    setTimeout(function () { g.classList.remove(cls || "hot"); }, ms || 700);
  }

  // ---- packets -----------------------------------------------------------
  function sendPacket(from, to, kind, done) {
    if (from === to) {                            // thinking, not moving
      var g = nodeEls[to];
      if (g) {
        var n = N[to];
        var ring = mk("circle", { cx: cx(n), cy: cy(n), r: 8, class: "pk " + kind, opacity: ".9" });
        layerPk.appendChild(ring);
        var t1 = performance.now(), dur1 = Math.max(180, 700 / speed);
        (function pulse(now) {
          var p = Math.min(1, ((now || performance.now()) - t1) / dur1);
          ring.setAttribute("r", 8 + p * 46);
          ring.setAttribute("opacity", (1 - p) * 0.75);
          if (p < 1) requestAnimationFrame(pulse);
          else { ring.remove(); if (done) done(); }
        })();
      } else if (done) { done(); }
      return;
    }
    var key = from + ">" + to, path = paths[key];
    if (!path && N[from] && N[to]) {
      // no drawn edge for this hop: fly straight, so no step is ever invisible
      path = mk("path", { d: "M" + cx(N[from]) + "," + cy(N[from]) + " L" + cx(N[to]) + "," +
                             cy(N[to]), class: "edge", opacity: "0" });
      layerEdges.appendChild(path);
      paths[key] = path;
    }
    if (!path) {
      if (done) done();
      return;
    }
    var len = path.getTotalLength();
    var dot = mk("circle", { class: "pk " + kind, r: 3.4 });
    layerPk.appendChild(dot);
    var dur = Math.max(220, 1400 / speed);
    var t0 = performance.now();
    function frame(now) {
      var p = Math.min(1, (now - t0) / dur);
      var pt = path.getPointAtLength(len * p);
      dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y);
      dot.setAttribute("opacity", p < 0.1 ? p * 10 : (p > 0.9 ? (1 - p) * 10 : 1));
      if (p < 1) requestAnimationFrame(frame);
      else { dot.remove(); if (done) done(); }
    }
    requestAnimationFrame(frame);
  }

  // ---- the timeline, built from the real traces --------------------------
  var AGENT_NODE = { reorder: "reorder", marketing_allocator: "marketing", product_verdict: "verdict" };

  function buildTimeline(runs) {
    var items = [];
    (runs || []).forEach(function (run) {
      var target = AGENT_NODE[run.agent];
      if (!target) return;
      items.push({ from: "bus", to: target, kind: "rule", agent: run.agent,
                   text: run.agent.replace("_", " ") + " picked up its job from the queue" });
      run.trace.forEach(function (st) {
        var from = { read: "memory", engine: "engines", model: "ml", judgment: "claude",
                     rule: target, gateway: target }[st.kind] || target;
        var to = st.kind === "gateway" ? "gate" : target;
        items.push({ from: from, to: to, kind: st.kind, agent: run.agent, step: st,
                     text: st.title + (st.detail ? " — " + st.detail : "") });
      });
    });
    return items;
  }

  function runStep() {
    if (!playing || cursor >= timeline.length) {
      playing = false;
      document.getElementById("b-replay").textContent = "Replay last run";
      return;
    }
    var item = timeline[cursor++];
    showTick(item);
    flash(item.from === item.to ? item.to : item.from, "hot", 500);
    sendPacket(item.from, item.to, item.kind, function () {
      flash(item.to, item.kind === "gateway" ? "ok" : "hot", 450);
      if (item.kind === "gateway" && item.step) {
        var detail = (item.step.detail || "").toLowerCase();
        var dest = detail.indexOf("pending_human") >= 0 ? "human"
                 : detail.indexOf("rejected") >= 0 ? "ledger" : "world";
        var tone = detail.indexOf("pending_human") >= 0 ? "bad"
                 : detail.indexOf("rejected") >= 0 ? "bad" : "ok";
        sendPacket("gate", "ledger", "gateway");
        sendPacket("gate", dest, "gateway", function () { flash(dest, tone, 700); });
      }
      setTimeout(runStep, Math.max(60, 420 / speed));
    });
  }

  function showTick(item) {
    var colour = { read: "#6ea8ff", engine: "#4fd1c5", model: "#3fb950", rule: "#d29922",
                   gateway: "#f85149", judgment: "#c084fc" }[item.kind] || "#9aa7b4";
    ticker.innerHTML = "<span class='kind' style='color:" + colour + ";border-color:" + colour +
      "55'>" + item.kind + "</span><b style='color:var(--fg-2)'>" +
      (item.agent || "").replace("_", " ") + "</b><span style='color:var(--fg)'>" +
      escapeHtml(item.text).slice(0, 180) + "</span>" +
      "<span class='spacer' style='flex:1'></span><span class='muted'>" + cursor + " / " +
      timeline.length + "</span>";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---- live numbers on the nodes ----------------------------------------
  function paintNumbers() {
    if (!state) return;
    setNum("shop", state.shop.variants + " variants · " + state.shop.out_of_stock + " unbuyable");
    setNum("memory", (state.memory.snapshots / 1000).toFixed(1) + "k readings");
    setNum("bus", state.bus.done + " done · " + state.bus.dead + " failed");
    setNum("gate", state.gate.executed + " auto · " + state.gate.waiting + " held");
    setNum("ledger", state.ledger.entries + " entries");
    setNum("human", state.gate.waiting + " waiting");
    setNum("world", "€" + Math.round(state.gate.capital) + " committed");
    setNum("ml", state.model ? "R² " + ((state.model.out_sample || {}).r2 || 0).toFixed(2) : "not trained");
    (state.agents || []).forEach(function (a) {
      var key = AGENT_NODE[a.key];
      if (key) setNum(key, a.steps + " steps · " + a.judgments + " judgments");
    });
    var totalJ = (state.agents || []).reduce(function (s, a) { return s + a.judgments; }, 0);
    setNum("claude", totalJ + " judgments made");
    setNum("hf", (state.substitutes || 0) + " substitution pairs");
    setNum("chronos", state.bench ? (state.bench.winner === "chronos" ? "promoted" : "lost the trial")
                                  : "not yet tested");
    setNum("engines", "exact, reproducible");
    setNum("adapter", state.shop.orders + " order lines");
    document.getElementById("shoppill").innerHTML = "shop <b>" + escapeHtml(state.shop.name) + "</b>";
    document.getElementById("provpill").innerHTML = "thinking <b>" +
      (state.provider.provider === "rules_only" ? "rules only" : "Claude") + "</b>";
  }

  // ---- side panel --------------------------------------------------------
  function openPanel(key) {
    var n = N[key];
    if (!n) return;
    var extra = "";
    var agent = (state && (state.agents || []).filter(function (a) { return AGENT_NODE[a.key] === key; })[0]);
    if (agent) {
      extra = "<p style='color:var(--fg)'><b>Last run:</b> " + escapeHtml(agent.headline) + "</p>" +
        st("steps taken", agent.steps) + st("facts read", agent.kinds.read || 0) +
        st("rules applied", (agent.kinds.rule || 0) + (agent.kinds.engine || 0)) +
        st("actions proposed", agent.kinds.gateway || 0) +
        st("judgments by Claude", agent.judgments);
      (agent.judgment_detail || []).forEach(function (j) {
        extra += "<p style='margin-top:10px'><b>Asked:</b> " + escapeHtml(j.q) +
          "<br><b>Answered:</b> " + escapeHtml(j.a) + "</p>";
      });
    }
    if (key === "shop" && state) {
      extra = st("variants", state.shop.variants) + st("unbuyable right now", state.shop.out_of_stock) +
        st("order lines imported", state.shop.orders);
    }
    if (key === "hf") {
      extra = "<div id='hf' style='margin-top:6px'></div>";
    }
    if (key === "marketing") {
      extra += "<div style='margin-top:14px'><b style='font-size:13px'>This week's budget, " +
        "split across every product</b><div id='bg-out' class='muted' style='font-size:12px;" +
        "margin-top:6px'>loading…</div></div>";
      setTimeout(loadBudget, 30);
    }
    if (key === "verdict") {
      extra += "<div style='margin-top:14px'><b style='font-size:13px'>The live shop, judged on " +
        "real evidence</b><div id='lv-out' class='muted' style='font-size:12px;margin-top:6px'>" +
        "loading…</div><button class='sm' id='lv-classify' style='margin-top:8px'>" +
        "Read the reviews with a language model</button></div>";
      setTimeout(loadLiveVerdicts, 30);
    }
    if (key === "chronos") {
      var b = state && state.bench;
      extra = "<button class='sm' id='bench-go' style='margin:4px 0 12px'>Run the head-to-head</button>" +
        "<div id='bench-out'>" + (b ? benchHtml(b) : "<span class='muted' style='font-size:12px'>" +
        "Holds out the last 14 days of each product and asks both methods to predict it. " +
        "Neither sees the answer.</span>") + "</div>";
    }
    if (key === "gate" && state) {
      extra = st("allowed automatically", state.gate.executed) +
        st("waiting for a person", state.gate.waiting) + st("refused outright", state.gate.refused) +
        st("committed to stock", "€" + Math.round(state.gate.capital));
    }
    if (key === "ml" && state && state.model) {
      extra = st("family", state.model.family) +
        st("score on unseen data", ((state.model.out_sample || {}).r2 || 0).toFixed(3)) +
        st("trained", (state.model.trained_at || "").slice(0, 16).replace("T", " "));
    }
    panel.innerHTML = "<h3>" + escapeHtml(n.t) + "</h3><div class='role'>" + escapeHtml(n.s) +
      "</div><p>" + escapeHtml(n.about) + "</p>" + extra +
      "<button class='sm' id='p-close' style='margin-top:12px'>Close</button>";
    panel.classList.add("on");
    if (key === "hf") loadHF();
  }

  function loadBudget() {
    var box = document.getElementById("bg-out");
    if (!box) return;
    api("/api/budget?amount=3000").then(function (d) {
      if (d.error) { box.innerHTML = escapeHtml(d.error); return; }
      var h = "<div style='margin-bottom:8px'>\u20ac" + d.allocated + " allocated, \u20ac" +
        d.held_back + " held back to test new things</div>";
      (d.lines || []).forEach(function (l) {
        var tone = l.allocated > 0 ? "var(--ok)" : "var(--fg-3)";
        h += "<div style='margin:7px 0;padding-left:9px;border-left:2px solid " + tone + "'>" +
          "<b style='color:var(--fg)'>" + escapeHtml(l.product) + "</b> &mdash; <b style='color:" +
          tone + "'>\u20ac" + l.allocated + "</b><br><span style='color:var(--fg-2)'>" +
          escapeHtml(l.reason || ("returns \u20ac" + l.return_per_euro + " per euro spent")) +
          "</span>";
        (l.channels || []).forEach(function (c) {
          if (!c.amount) return;
          h += "<div style='margin-left:10px;margin-top:4px;font-size:11.5px;color:var(--fg-3)'>" +
            "\u2192 <b style='color:var(--fg-2)'>" + escapeHtml(c.channel) + "</b> \u20ac" +
            c.amount + " &middot; " + escapeHtml(c.why).slice(0, 70) + "</div>";
        });
        h += "</div>";
      });
      box.innerHTML = h;
    });
  }

  function loadLiveVerdicts() {
    var box = document.getElementById("lv-out");
    if (!box) return;
    api("/api/live-verdict").then(function (d) {
      var rows = (d.verdicts || []).filter(function (v) { return !v.error; });
      if (!rows.length) { box.innerHTML = "no live products yet"; return; }
      var h = "";
      rows.forEach(function (v) {
        var e = v.evidence, s2 = e.sentiment;
        var tone = v.verdict === "KILL" ? "var(--bad)" : v.verdict === "SCALE" ? "var(--ok)" : "var(--warn)";
        h += "<div style='margin:10px 0;padding-left:10px;border-left:2px solid " + tone + "'>" +
          "<b style='color:var(--fg)'>" + escapeHtml(v.name) + " &mdash; <span style='color:" +
          tone + "'>" + escapeHtml(v.verdict) + "</span></b><br>" +
          e.units_sold + " units really sold &middot; " + Math.round(e.margin_pct * 100) +
          "% margin &middot; " +
          (s2.classified ? (Math.round((s2.negative_share || 0) * 100) + "% of " + s2.classified +
             " reviews negative") : "reviews not read yet") + "<br>" +
          "<span style='color:var(--fg-2)'>" + escapeHtml(v.because) + "</span></div>";
      });
      box.innerHTML = h;
    });
  }

  function benchHtml(b) {
    if (!b) return "";
    if (b.error) return "<span class='muted'>" + escapeHtml(b.error) + "</span>";
    var h = "<div class='hfbox'><b>" + escapeHtml((b.winner || "").toUpperCase()) + " wins by " +
      Math.abs(b.margin_pct) + "%</b><br><span class='muted'>average error over 14 held-out days, " +
      b.tested + " products</span><br><br>";
    h += st("Chronos off by", b.chronos_mae + " units");
    h += st("statistics off by", b.statistics_mae + " units");
    h += st("Chronos band contained the truth", Math.round(b.band_coverage * 100) + "% of the time");
    if (b.by_volume && b.by_volume.busy_products.n) {
      h += "<div style='margin-top:10px;font-size:12px'><b>Split by volume</b><br>" +
        "5+ a day (" + b.by_volume.busy_products.n + "): Chronos " + b.by_volume.busy_products.chronos +
        " vs statistics " + b.by_volume.busy_products.statistics + "<br>" +
        "long tail (" + b.by_volume.slow_products.n + "): Chronos " + b.by_volume.slow_products.chronos +
        " vs statistics " + b.by_volume.slow_products.statistics + "</div>";
    }
    if (b.insight) h += "<p style='font-size:12px;margin-top:10px'>" + escapeHtml(b.insight) + "</p>";
    h += "<p style='font-size:12px;color:" + (b.winner === "chronos" ? "var(--ok)" : "var(--warn)") +
      "'>" + (b.winner === "chronos"
        ? "Promoted: the reorder agent may use it, and loses it the moment it stops winning."
        : "Not promoted. It lost, so it is not used. That is the gate doing its job.") + "</p></div>";
    return h;
  }

  function st(label, value) {
    return "<div class='st'><span>" + escapeHtml(label) + "</span><b>" + escapeHtml(value) + "</b></div>";
  }

  // ---- Hugging Face: a real model, in the browser ------------------------
  var hfReady = null, embedReady = null;

  function loadHF() {
    var box = document.getElementById("hf");
    if (!box) return;
    box.innerHTML = "<div class='hfbox'>" +
      "<b>1 · What competes with what</b><br><span class='muted'>all-MiniLM-L6-v2 reads the " +
      "product text and scores how interchangeable two items are. The reorder agent uses this " +
      "to tell demand that moved from a sold-out item apart from demand of its own.</span><br>" +
      "<button class='sm' id='hf-embed' style='margin:8px 0 14px'>Learn the substitution map</button>" +
      "<div id='hf-embed-out'></div>" +
      "<b>2 · What customers actually said</b><br><span class='muted'>distilbert-sst2 over the " +
      "review text left with real orders.</span><br>" +
      "<button class='sm' id='hf-go' style='margin-top:8px'>Read the reviews</button>" +
      "<div id='hf-sent-out'></div></div>";
    document.getElementById("hf-go").onclick = runSentiment;
    document.getElementById("hf-embed").onclick = runEmbeddings;
  }

  function loadTransformers() {
    if (!embedReady) {
      embedReady = import("https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.0.2")
        .catch(function () { return import("https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2"); });
    }
    return embedReady;
  }

  function cosine(a, b) {
    var dot = 0, na = 0, nb = 0;
    for (var i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
    return dot / (Math.sqrt(na) * Math.sqrt(nb) || 1);
  }

  function runEmbeddings() {
    var out = document.getElementById("hf-embed-out");
    out.innerHTML = "<div class='muted' style='margin:6px 0'>loading the embedding model…</div>";
    flash("hf", "hot", 1500);
    Promise.all([fetch("/api/catalogue-text").then(function (r) { return r.json(); }),
                 loadTransformers()]).then(function (res) {
      var items = res[0].variants || [], mod = res[1];
      return mod.pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2").then(function (pipe) {
        out.innerHTML = "<div class='muted' style='margin:6px 0'>embedding " + items.length +
          " product descriptions…</div>";
        return Promise.all(items.map(function (it) {
          return pipe(it.text, { pooling: "mean", normalize: true })
            .then(function (t) { return { id: it.id, text: it.text, vec: Array.from(t.data) }; });
        }));
      });
    }).then(function (vecs) {
      var pairs = [], shown = [];
      for (var i = 0; i < vecs.length; i++) {
        for (var j = i + 1; j < vecs.length; j++) {
          var sc = cosine(vecs[i].vec, vecs[j].vec);
          if (sc >= 0.62) pairs.push({ a: vecs[i].id, b: vecs[j].id, score: +sc.toFixed(4) });
          shown.push({ a: vecs[i].text, b: vecs[j].text, score: sc });
        }
      }
      shown.sort(function (x, y) { return y.score - x.score; });
      return fetch("/api/substitutes", { method: "POST",
        headers: { "content-type": "application/json" }, body: JSON.stringify({ pairs: pairs }) })
        .then(function (r) { return r.json(); })
        .then(function (saved) {
          var h = "<div style='margin:6px 0 10px'><b>" + saved.stored + " pairs</b> scored above " +
            "0.62 and written to the engine. The reorder agent now uses this instead of guessing " +
            "from the product id.</div>";
          shown.slice(0, 5).forEach(function (p) {
            h += "<div style='font-size:12px'>" + escapeHtml(p.a) + " ↔ " + escapeHtml(p.b) +
              " <b>" + p.score.toFixed(2) + "</b></div>";
          });
          var low = shown[shown.length - 1];
          h += "<div style='font-size:12px;margin-top:8px;color:var(--fg-3)'>least alike: " +
            escapeHtml(low.a) + " ↔ " + escapeHtml(low.b) + " " + low.score.toFixed(2) + "</div>";
          out.innerHTML = h;
          flash("reorder", "ok", 1200);
          refresh();
        });
    }).catch(function (e) {
      out.innerHTML = "<div class='muted'>could not load the model (" + escapeHtml(e.message) +
        "). It needs internet the first time.</div>";
    });
  }

  function runSentiment() {
    var box = document.getElementById("hf-sent-out");
    box.innerHTML = "<div class='hfbox'>loading the model from Hugging Face… (first run downloads it)</div>";
    fetch("/api/reviews").then(function (r) { return r.json(); }).then(function (d) {
      var reviews = d.reviews || [];
      if (!reviews.length) {
        box.innerHTML = "<div class='hfbox'>No review text on the orders yet. Place orders with " +
          "<code>scripts/shoppers.py</code> and they will carry one.</div>";
        return;
      }
      if (!hfReady) {
        hfReady = loadTransformers().then(function (m) {
          return m.pipeline("sentiment-analysis",
                            "Xenova/distilbert-base-uncased-finetuned-sst-2-english");
        });
      }
      hfReady.then(function (pipe) {
        return Promise.all(reviews.slice(0, 40).map(function (r) {
          return pipe(r.text).then(function (out) {
            return { product: r.product, label: out[0].label, score: out[0].score };
          });
        }));
      }).then(function (scored) {
        var by = {};
        scored.forEach(function (s) {
          by[s.product] = by[s.product] || { neg: 0, n: 0 };
          by[s.product].n += 1;
          if (s.label === "NEGATIVE") by[s.product].neg += 1;
        });
        var html = "<div class='hfbox'><b>Customer sentiment</b> " +
          "<span class='muted'>distilbert-sst2, run locally in this browser on " + scored.length +
          " real reviews</span><br><br>";
        Object.keys(by).sort(function (a, b) {
          return (by[b].neg / by[b].n) - (by[a].neg / by[a].n); }).forEach(function (p) {
          var pct = by[p].neg / by[p].n;
          html += escapeHtml(p) + " — " + Math.round(pct * 100) + "% negative of " + by[p].n +
            "<div class='bar'><i class='" + (pct > 0.4 ? "" : "good") + "' style='width:" +
            (pct * 100) + "%'></i></div>";
        });
        html += "<span class='muted'>A product people return and complain about is a product " +
          "problem, not a shop problem. This feeds the verdict agent.</span></div>";
        box.innerHTML = html;
        flash("verdict", "bad", 1200);
      }).catch(function (e) {
        box.innerHTML = "<div class='hfbox'>Could not load the model (" + escapeHtml(e.message) +
          "). It needs internet the first time; everything else on this page works offline.</div>";
      });
    });
  }

  // ---- wiring ------------------------------------------------------------
  function api(p, b) {
    return fetch(p, b ? { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(b) } : undefined).then(function (r) { return r.json(); });
  }

  function refresh() {
    return Promise.all([api("/api/boxes"), api("/api/flow")]).then(function (res) {
      state = res[0]; flow = res[1];
      timeline = buildTimeline(flow.runs);
      paintNumbers();
    });
  }

  document.addEventListener("click", function (e) {
    var nd = e.target.closest ? e.target.closest(".nd") : null;
    if (nd) { openPanel(nd.getAttribute("data-node")); return; }
    if (e.target.id === "p-close") { panel.classList.remove("on"); return; }
    if (e.target.id === "b-replay") {
      if (playing) { playing = false; e.target.textContent = "Replay last run"; return; }
      cursor = 0; playing = true; e.target.textContent = "Stop"; runStep(); return;
    }
    if (e.target.id === "lv-classify") {
      var box = document.getElementById("lv-out");
      box.innerHTML = "reading the reviews…";
      flash("hf", "hot", 2000);
      api("/api/classify-reviews", {}).then(function () {
        var tries = 0;
        var poll = setInterval(function () {
          tries += 1;
          api("/api/boxes").then(function (d) {
            if ((!d.busy || !d.busy.running) || tries > 60) {
              clearInterval(poll);
              loadLiveVerdicts();
              flash("verdict", "bad", 1500);
            }
          });
        }, 1200);
      });
      return;
    }
    if (e.target.id === "bench-go") {
      var out = document.getElementById("bench-out");
      out.innerHTML = "<span class='muted'>running the model… first run downloads it from Hugging Face</span>";
      flash("chronos", "hot", 2000);
      api("/api/forecast-bench", {}).then(function () {
        var tries = 0;
        var poll = setInterval(function () {
          tries += 1;
          api("/api/boxes").then(function (d) {
            state = d;
            if (d.bench || tries > 90) {
              clearInterval(poll);
              out.innerHTML = benchHtml(d.bench);
              paintNumbers();
            }
          });
        }, 1500);
      });
      return;
    }
    if (e.target.id === "b-run") {
      e.target.disabled = true;
      ticker.innerHTML = "<span class='muted'>running the agents for real…</span>";
      api("/api/run", { what: "all" }).then(function () {
        var tries = 0;
        var poll = setInterval(function () {
          tries += 1;
          api("/api/boxes").then(function (d) {
            state = d; paintNumbers();
            ["marketing", "reorder", "verdict", "bus"].forEach(function (k) { flash(k, "hot", 400); });
            if ((!d.busy || !d.busy.running) || tries > 90) {
              clearInterval(poll);
              document.getElementById("b-run").disabled = false;
              refresh().then(function () { cursor = 0; playing = true; runStep(); });
            }
          });
        }, 900);
      });
    }
  });

  document.getElementById("speed").addEventListener("input", function (e) { speed = +e.target.value; });

  draw();
  refresh();
  setInterval(function () { if (!playing) refresh(); }, 8000);
})();
