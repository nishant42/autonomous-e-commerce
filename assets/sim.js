/* Live operations simulation.
   A scripted, pause-aware animation of the architecture: every packet is an event,
   tool call, action proposal or decision. Numbers match the scenario page. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("st");
  const $ = (id) => document.getElementById(id);
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------- stage
  const KC = { ext: "--fg-faint", bus: "--info", ml: "--flax", det: "--fg-muted", agent: "--llm", control: "--danger", gateway: "--warn", data: "--ok", human: "--fg" };
  const N = {
    customers: [85, 95, "Customers", "shoppers", "ext", "Shoppers placing orders, asking questions and returning items."],
    shopify: [85, 205, "Shopify", "storefront", "ext", "Bought storefront and order system. Emits order webhooks; receives price and stock pushes."],
    stripe: [85, 315, "Stripe", "payments", "ext", "Payments, refunds and payouts. Every call carries an idempotency key."],
    supplier: [85, 425, "Yves Delorme", "hypothetical", "ext", "Supplier reached by EDI for POs and by email for expedites and exceptions."],
    tpl: [85, 535, "3PL · UK1", "warehouse", "ext", "Outsourced warehouse: receipts, picking and shipping."],
    bus: [270, 315, "Event bus", "service bus", "bus", "Durable fan-out of CloudEvents between departments, with dead-letter queues."],
    sensing: [455, 85, "Demand Sensing", "ML · change-point", "ml", "Detects when sell-through departs from forecast and classifies the cause."],
    forecast: [625, 85, "Forecasting", "ML · P10-P90", "ml", "Probabilistic forecasts per SKU and node; intraday re-forecast on anomalies."],
    planner: [795, 85, "Replenishment", "rules + opt", "ml", "Reorder point and order-up-to quantity from forecast and lead-time distributions."],
    fraud: [455, 195, "Fraud Screening", "ML + rules", "ml", "Scores orders; also answers 'is this demand real?' before any money is spent."],
    orders: [625, 195, "Order Orchestrator", "workflow", "det", "Deterministic order lifecycle: payment, fraud, allocation, 3PL release."],
    procurement: [795, 195, "Procurement", "LLM agent", "agent", "Turns recommendations into POs; quantities come from the deterministic PO Builder."],
    pricing: [455, 305, "Pricing", "ML + rules", "ml", "Price moves within margin floors, MAP and reference-price rules. Price Guard can veto."],
    marketing: [625, 305, "Marketing", "LLM + bandit", "agent", "Stock-aware campaigns and budget allocation across channels."],
    liaison: [795, 305, "Supplier Liaison", "LLM agent", "agent", "Owns every supplier conversation: EDI, email, portal."],
    care: [455, 415, "Customer Care", "LLM · grounded", "agent", "Answers from real order and PO data with citations; refunds decided by policy engine."],
    finance: [625, 415, "Finance", "deterministic", "det", "Reconciliation, accounts payable, cash and budgets."],
    panel: [795, 415, "Buy Panel", "3 personas", "agent", "Demand Planner, CFO and Risk Officer judge T2 buys from a frozen decision pack."],
    extractor: [455, 525, "Extractor + Verifier", "maker · checker", "agent", "Reads supplier PDFs and emails into typed JSON; an independent verifier checks every value."],
    inventory: [625, 525, "Inventory Position", "ATP · cover", "det", "Computes available-to-promise and cover; pushes stock to Shopify."],
    lifecycle: [795, 525, "Lifecycle / CRM", "Klaviyo flows", "agent", "Back-in-stock, replenishment and waitlist emails, consent-checked."],
    sentinel: [1000, 95, "Sentinel", "quarantine", "control", "Watches agent behaviour and business metrics; quarantines agents and trips kill switches."],
    gateway: [1000, 255, "Action Gateway", "policy · tiers", "gateway", "The only path to side effects: identity, kill switch, idempotency, schema, policy, tier."],
    ledger: [1000, 415, "Ops Ledger", "state · audit", "data", "System of record for stock, POs, prices and every proposal and decision."],
    owner: [1000, 545, "Owners", "exceptions only", "human", "Humans. Set limits; see T3 exceptions and incident briefs."],
  };
  const BW = 146, BH = 48;
  const el = (tag, a, p) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; };

  // lanes
  [[20, "External"], [205, "Backbone"], [370, "Departments & agents"], [920, "Control & state"]].forEach(([x, t], i) => {
    const w = [130, 130, 510, 160][i];
    el("rect", { class: "lane", x, y: 18, width: w, height: 578, rx: 14 }, svg);
    el("text", { class: "lane-t", x: x + 12, y: 38 }, svg).textContent = t;
  });
  const wires = el("g", {}, svg);
  const W = (a, b) => { const [x1, y1] = N[a], [x2, y2] = N[b]; el("path", { class: "wire", d: `M${x1},${y1} L${x2},${y2}` }, wires); };
  ["customers", "shopify", "stripe", "supplier", "tpl"].forEach((x) => W(x, "bus"));
  ["sensing", "forecast", "planner", "fraud", "orders", "procurement", "pricing", "marketing", "liaison", "care", "finance", "panel", "extractor", "inventory", "lifecycle"].forEach((x) => W("bus", x));
  W("gateway", "ledger"); W("sentinel", "gateway"); W("owner", "ledger");
  const gNodes = el("g", {}, svg), gPk = el("g", {}, svg);
  const nodeEl = {};
  Object.entries(N).forEach(([id, [x, y, label, sub, kind]]) => {
    const g = el("g", { class: "sn", transform: `translate(${x - BW / 2},${y - BH / 2})`, tabindex: "0", role: "button", "aria-label": label }, gNodes);
    g.style.setProperty("--kc", "var(" + KC[kind] + ")");
    el("rect", { class: "glow", width: BW, height: BH, rx: 11 }, g);
    el("rect", { class: "b", width: BW, height: BH, rx: 11 }, g);
    el("circle", { class: "k", cx: 13, cy: 17, r: 4 }, g);
    el("text", { class: "l", x: 24, y: 21 }, g).textContent = label;
    const s = el("text", { class: "s", x: 13, y: 37 }, g); s.textContent = sub;
    g.addEventListener("click", () => showInfo(id));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter") showInfo(id); });
    nodeEl[id] = { g, s, sub };
  });
  function setStatus(id, cls, text) {
    const n = nodeEl[id]; if (!n) return;
    n.g.classList.remove("quar", "shadow", "halt");
    if (cls) n.g.classList.add(cls);
    n.s.textContent = text || n.sub;
  }
  function pulse(id) { const n = nodeEl[id]; if (!n) return; n.g.classList.remove("active"); n.g.getBBox(); n.g.classList.add("active"); }
  function busy(id, on) { const n = nodeEl[id]; if (n) n.g.classList.toggle("busy", on); }
  function showInfo(id) {
    const [, , label, sub, , info] = N[id], box = $("info");
    box.innerHTML = '<button type="button" aria-label="Close">✕</button><h4>' + label + '</h4><p>' + info + '</p><span class="tier">' + nodeEl[id].s.textContent + "</span>";
    box.hidden = false;
    box.querySelector("button").onclick = () => (box.hidden = true);
  }

  // ---------------------------------------------------------------- time & pause-aware animation
  let speed = 1, playing = false, stepping = false, gen = 0, loopGen = -1;
  const running = () => playing || stepping;
  function frames(ms, onFrame) {
    const g = gen;
    return new Promise((res) => {
      let t = 0, last = performance.now();
      const dur = reduce ? 1 : ms;
      function f(now) {
        if (g !== gen) { res(); return; }
        const dt = now - last; last = now;
        if (running()) t += dt * speed;
        const k = Math.min(1, t / dur);
        onFrame && onFrame(k);
        if (k >= 1) res(); else requestAnimationFrame(f);
      }
      requestAnimationFrame(f);
    });
  }
  const wait = (ms) => frames(ms);
  const COL = { ev: "--accent", act: "--flax", llm: "--llm", ok: "--ok", rej: "--danger" };
  function curve(a, b) {
    const [x1, y1] = N[a], [x2, y2] = N[b];
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1;
    const bend = a === b ? 60 : 0.16 * L;
    const cx = a === b ? x1 + 70 : mx - (dy / L) * bend, cy = a === b ? y1 - 60 : my + (dx / L) * bend;
    return { x1, y1, x2: a === b ? x1 + 30 : x2, y2: a === b ? y1 - 4 : y2, cx, cy };
  }
  function fly(from, to, kind, label, dur) {
    const c = curve(from, to), color = "var(" + COL[kind] + ")";
    const g = el("g", { class: "pk" }, gPk);
    const trail = el("path", { class: "trail", d: `M${c.x1},${c.y1} Q${c.cx},${c.cy} ${c.x2},${c.y2}`, stroke: color }, g);
    const L = trail.getTotalLength();
    trail.style.strokeDasharray = L; trail.style.strokeDashoffset = L;
    const dot = el("circle", { r: kind === "ev" ? 5 : 6, fill: color }, g);
    const txt = label ? el("text", { fill: color, "text-anchor": "middle" }, g) : null;
    if (txt) txt.textContent = label;
    busy(from, true);
    return frames(dur || 900, (k) => {
      const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const p = trail.getPointAtLength(e * L);
      dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y);
      trail.style.strokeDashoffset = L * (1 - e);
      if (txt) { txt.setAttribute("x", p.x); txt.setAttribute("y", p.y - 12); }
    }).then(() => {
      busy(from, false); pulse(to);
      g.style.transition = "opacity .5s"; g.style.opacity = "0";
      setTimeout(() => g.remove(), 520);
    });
  }

  // ---------------------------------------------------------------- state & rendering
  let S, scenario, idx = 0, logN = 0;
  const DAYS = ["Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon"];
  const parseAt = (s) => { const m = /D(\d+) (\d\d):(\d\d)/.exec(s); return (m[1] - 1) * 1440 + (+m[2]) * 60 + (+m[3]); };
  const fmtT = (m) => String(Math.floor(m / 60) % 24).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
  const eur = (v) => "€" + Math.round(v).toLocaleString("en-GB");
  function fresh() {
    return { t: 540, orders: 0, rev: 0, cash: 412000, runway: 19.0, ads: 1850, po: 3, human: 0, atp: 42, onord: 60, demand: 3.0, price: 71.1, list: 79, promo: true,
      tiers: { T0: 0, T1: 0, T2: 0, T3: 0, REJ: 0 }, kill: false, series: [] };
  }
  function render() {
    const day = Math.floor(S.t / 1440);
    $("c-day").textContent = "Day " + (day + 1) + " · " + DAYS[day % 7];
    $("c-time").textContent = fmtT(S.t % 1440);
    set("k-orders", S.orders.toLocaleString("en-GB")); set("k-rev", eur(S.rev)); set("k-cash", "€" + Math.round(S.cash / 1000) + "k");
    $("k-run").textContent = S.runway.toFixed(1); set("k-ads", eur(S.ads)); set("k-po", S.po); set("k-human", S.human);
    $("k-atp").textContent = S.atp; $("k-onord").textContent = S.onord;
    const cover = S.demand ? S.atp / S.demand : 99;
    $("k-cover").textContent = cover.toFixed(1);
    const band = cover < 14 ? ["crit", "critical"] : cover < 28 ? ["tight", "tight"] : ["", "healthy"];
    const pill = $("k-band"); pill.className = "pill " + band[0]; pill.textContent = band[1];
    const bar = $("k-coverbar"); bar.style.width = Math.max(2, Math.min(100, (cover / 56) * 100)) + "%";
    bar.style.background = "var(" + (band[0] === "crit" ? "--danger" : band[0] === "tight" ? "--warn" : "--ok") + ")";
    $("k-price").innerHTML = S.promo ? "€" + S.price.toFixed(2) + ' <s class="muted">€' + S.list + "</s>" : "€" + S.price.toFixed(2);
    Object.keys(S.tiers).forEach((k) => ($("t-" + k).textContent = S.tiers[k]));
    $("k-live").textContent = playing ? (S.kill ? "kill switch on" : "running") : "paused";
    drawChart();
  }
  const prevVals = {};
  function set(id, v) { const e = $(id); if (prevVals[id] !== v) { e.textContent = v; if (prevVals[id] !== undefined) { e.classList.add("flash"); setTimeout(() => e.classList.remove("flash"), 500); } prevVals[id] = v; } }
  function record() { const k = scenario.chart.key; S.series.push({ t: S.t, v: typeof k === "function" ? k(S) : S[k] }); }

  function drawChart() {
    const c = $("chart"), dpr = window.devicePixelRatio || 1, r = c.getBoundingClientRect();
    if (!r.width) return;
    c.width = r.width * dpr; c.height = r.height * dpr;
    const x = c.getContext("2d"); x.scale(dpr, dpr);
    const cs = getComputedStyle(document.documentElement), col = (v) => cs.getPropertyValue(v).trim();
    const pad = { l: 34, r: 8, t: 10, b: 20 }, w = r.width - pad.l - pad.r, h = r.height - pad.t - pad.b;
    const { max, span, unit } = scenario.chart;
    const t0 = 540, t1 = t0 + span * 1440;
    x.font = "10.5px " + col("--mono"); x.fillStyle = col("--fg-faint"); x.strokeStyle = col("--border"); x.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const yv = (max / 4) * i, y = pad.t + h - (yv / max) * h;
      x.beginPath(); x.moveTo(pad.l, y); x.lineTo(pad.l + w, y); x.stroke();
      x.fillText(unit === "€" ? "€" + Math.round(yv) : Math.round(yv), 2, y + 3);
    }
    const days = Math.min(span, 12);
    for (let d = 0; d <= days; d += Math.max(1, Math.round(days / 6))) {
      const xx = pad.l + (d / span) * w; x.fillText("D" + (d + 1), xx - 6, r.height - 5);
    }
    const pts = S.series.filter((p) => p.t <= t1);
    if (!pts.length) return;
    const X = (t) => pad.l + ((t - t0) / (t1 - t0)) * w, Y = (v) => pad.t + h - (Math.max(0, Math.min(max, v)) / max) * h;
    const grad = x.createLinearGradient(0, pad.t, 0, pad.t + h);
    grad.addColorStop(0, col("--accent") + "55"); grad.addColorStop(1, col("--accent") + "00");
    x.beginPath(); x.moveTo(X(pts[0].t), Y(pts[0].v));
    pts.forEach((p, i) => { if (i) { x.lineTo(X(p.t), Y(pts[i - 1].v)); x.lineTo(X(p.t), Y(p.v)); } });
    const lastX = X(pts[pts.length - 1].t);
    x.lineTo(lastX, pad.t + h); x.lineTo(X(pts[0].t), pad.t + h); x.closePath(); x.fillStyle = grad; x.fill();
    x.beginPath(); x.moveTo(X(pts[0].t), Y(pts[0].v));
    pts.forEach((p, i) => { if (i) { x.lineTo(X(p.t), Y(pts[i - 1].v)); x.lineTo(X(p.t), Y(p.v)); } });
    x.strokeStyle = col("--accent"); x.lineWidth = 2; x.stroke();
    const lp = pts[pts.length - 1];
    x.beginPath(); x.arc(X(lp.t), Y(lp.v), 4, 0, Math.PI * 2); x.fillStyle = col("--flax"); x.fill();
    x.fillStyle = col("--fg"); x.font = "600 11px " + col("--mono");
    const lbl = (unit === "€" ? "€" : "") + (Math.round(lp.v * 10) / 10);
    x.fillText(lbl, Math.min(X(lp.t) + 6, pad.l + w - 30), Math.max(12, Y(lp.v) - 6));
  }

  function log(agent, msg, tier) {
    const ul = $("log");
    if (!logN) ul.innerHTML = "";
    logN++;
    if (S.tiers[tier] !== undefined) S.tiers[tier]++;
    if (tier === "HALT") S.tiers.REJ++;
    const day = Math.floor(S.t / 1440) + 1;
    const li = document.createElement("li");
    li.className = "new";
    li.innerHTML = '<span class="t">D' + day + " " + fmtT(S.t % 1440) + '</span><span class="a">' + agent + '</span><span class="m">' + msg + '</span><span class="tier ' + tier + '">' + (tier === "EV" ? "event" : tier === "REJ" ? "veto" : tier === "HALT" ? "halted" : tier) + "</span>";
    ul.prepend(li);
    while (ul.children.length > 120) ul.lastChild.remove();
    $("log-n").textContent = logN + " entries";
  }
  function narrate(who, text, alert) {
    $("n-text").innerHTML = '<span class="who">' + who + "</span>" + text;
    $("narr").classList.toggle("alert", !!alert);
  }
  function progress() {
    const n = scenario.steps.length;
    $("n-prog").textContent = Math.min(idx, n) + " / " + n;
    $("n-bar").style.width = (Math.min(idx, n) / n) * 100 + "%";
  }

  // ---------------------------------------------------------------- ambient order flow (deterministic path, never halted)
  let ambT = 0, ambLast = performance.now();
  function ambient(now) {
    const dt = now - ambLast; ambLast = now;
    if (playing && scenario.ambient) {
      ambT += dt * speed;
      if (ambT > 1500) {
        ambT = 0;
        const hero = S.heroShare && Math.random() < S.heroShare, my = gen;
        (async () => {
          await fly("customers", "shopify", "ev", "", 380);
          await fly("shopify", "bus", "ev", "", 380);
          await fly("bus", "orders", "ev", "", 380);
          if (my !== gen) return;
          S.orders++; S.rev += hero ? S.price : 60 + Math.random() * 240;
          await fly("orders", "tpl", "ok", "", 380);
          render();
        })();
      }
    }
    requestAnimationFrame(ambient);
  }
  requestAnimationFrame(ambient);

  // ---------------------------------------------------------------- step runner
  async function runStep(st) {
    const my = gen;
    S.t = parseAt(st.at);
    narrate(st.who, st.text, st.alert);
    render();
    for (const f of st.flows || []) {
      const [a, b, kind, label] = f;
      await fly(a, b, kind, label, f[4]);
      if (my !== gen) return;
      if (kind === "act" && b === "gateway" && S.kill) {
        await fly("gateway", a, "rej", "HALTED · kill switch", 700);
        log("Action Gateway", "Rejected " + (label || "action") + ": autonomous side effects are halted", "HALT");
        narrate("Kill switch", "The gateway refused <b>" + (label || "the action") + "</b>. Orders keep flowing on the deterministic path; nothing else changes until the switch is released.", true);
        render();
        return;
      }
    }
    (st.log || []).forEach(([a, m, t]) => log(a, m, t));
    if (st.fx) st.fx(S);
    record(); render();
  }
  async function loop() {
    if (loopGen === gen) return;
    const my = gen;
    loopGen = my;
    while (idx < scenario.steps.length && running()) {
      await runStep(scenario.steps[idx]);
      if (my !== gen) return;
      idx++; progress();
      if (stepping) { stepping = false; break; }
      await wait(scenario.gap || 900);
      if (my !== gen) return;
    }
    loopGen = -1;
    if (idx >= scenario.steps.length) {
      setPlaying(false);
      narrate("Scenario complete", scenario.done + ' <button class="icon-btn" type="button" id="replay" style="margin-left:8px">Replay</button>');
      const rb = $("replay"); if (rb) rb.onclick = () => { reset(); setPlaying(true); };
    }
  }
  function setPlaying(on) {
    playing = on;
    const b = $("play");
    b.querySelector("span").textContent = on ? "Pause" : idx > 0 && idx < scenario.steps.length ? "Resume" : "Start";
    b.querySelector("svg").innerHTML = on ? '<path d="M6 4h4v16H6zM14 4h4v16h-4z"/>' : '<path d="M7 4v16l13-8z"/>';
    render();
    if (on) loop();
  }
  function reset() {
    gen++; loopGen = -1;
    playing = false; stepping = false; idx = 0; logN = 0;
    gPk.innerHTML = "";
    S = fresh(); Object.assign(S, scenario.init || {});
    Object.keys(nodeEl).forEach((id) => { setStatus(id); nodeEl[id].g.classList.remove("busy", "active"); });
    const k = $("kill"); k.setAttribute("aria-pressed", "false");
    $("log").innerHTML = '<li class="empty-log">The log fills as agents act. Every line is an audited proposal, decision or event.</li>';
    $("log-n").textContent = "0 entries";
    $("chart-l").textContent = scenario.chart.label;
    record();
    narrate("Ready · " + scenario.name, scenario.intro);
    progress(); setPlaying(false);
  }

  // ---------------------------------------------------------------- scenarios
  const SC = {
    towel: {
      name: "Towel sells 3×", ambient: true, gap: 900,
      chart: { key: "atp", label: "Étoile towel ATP (units) over 12 days", max: 140, span: 12 },
      intro: "A Yves Delorme bath towel is about to sell <b>three times faster</b> than forecast. Watch every department react with no human involved.",
      done: "Spike handled end to end: 14 backorders, 0 cancellations, 0 human touches.",
      steps: [
        { at: "D1 09:40", who: "Normal operations", text: "Orders flow <b>Shopify → event bus → Order Orchestrator → 3PL</b> on a deterministic path. No LLM is involved in taking an order.",
          flows: [["customers", "shopify", "ev", "order"], ["shopify", "bus", "ev", "order.placed"], ["bus", "orders", "ev"], ["orders", "tpl", "ok", "release"]],
          log: [["Order Orchestrator", "Released order #48213 to 3PL UK1", "T0"]], fx: (s) => { s.orders += 1; s.rev += 158; } },
        { at: "D1 10:02", who: "Demand Sensing · ML", text: "A change-point detector sees the Étoile towel selling at <b>9.3/day vs 3.0 planned</b> (3.1×) and publishes <b>demand.anomaly</b>.",
          flows: [["bus", "sensing", "ev", "order stream"], ["sensing", "bus", "ev", "demand.anomaly 3.1×"]],
          log: [["Demand Sensing", "Velocity 3.1× plan on Étoile bath towel · cause: organic referral", "EV"]], fx: (s) => { s.heroShare = 0.5; s.atp = 40; } },
        { at: "D1 10:03", who: "Fraud Screening", text: "First question: <b>is the demand real?</b> 311 distinct customers, normal risk mix. If this were a fraud ring the flow would stop here.",
          flows: [["sensing", "fraud", "ev", "is it real?"], ["fraud", "sensing", "ok", "311 real customers ✓"]],
          log: [["Fraud Screening", "Spike validated: 311 distinct customers, Radar risk within baseline", "T0"]] },
        { at: "D1 10:05", who: "Forecasting · ML", text: "Intraday re-forecast: <b>P50 9.1/day, P90 13.4/day</b>, decaying over ~3 weeks. Tagged <b>anomaly_influenced</b>, which lifts the tier of any PO it drives.",
          flows: [["bus", "forecast", "ev"], ["forecast", "bus", "ev", "P50 9.1 · P90 13.4"]],
          log: [["Forecasting", "Published fcst-v17 intraday · anomaly_influenced=true", "EV"]], fx: (s) => { s.demand = 9.1; s.atp = 38; } },
        { at: "D1 10:06", who: "Inventory Position", text: "ATP 38 ÷ 9.1/day = <b>about 4 days of cover</b>, the critical band. Inbound 60 units are 12 days away.",
          flows: [["bus", "inventory", "ev"], ["inventory", "bus", "ev", "stock.low · CRITICAL"]],
          log: [["Inventory Position", "Cover critical: 4.2 days · EU→UK transfer rejected (cost > benefit)", "EV"]] },
        { at: "D1 10:07", who: "Marketing · coupling rule", text: "Critical cover means <b>stop buying demand we can't serve</b>. SKU ads paused, €140/day moved to sister SKUs with 10+ weeks of cover.",
          flows: [["bus", "marketing", "ev", "cover critical"], ["marketing", "gateway", "act", "SetAdBudget"], ["gateway", "ledger", "ok", "T0 ✓"]],
          log: [["Budget Allocator", "Paused SKU acquisition ads; €140/day → Nuit sheet set", "T0"]] },
        { at: "D1 10:07", who: "Pricing", text: "The 10% promotion ends (T0). A scarcity uplift is <b>withheld by policy</b>: confirmed inbound exists within lead time.",
          flows: [["bus", "pricing", "ev"], ["pricing", "gateway", "act", "EndPromo"], ["gateway", "shopify", "ok", "€79.00"]],
          log: [["Pricing Agent", "Ended 10% promo on Étoile bath towel · Price Guard pass", "T0"]], fx: (s) => { s.promo = false; s.price = 79; } },
        { at: "D1 10:10", who: "Replenishment Planner", text: "Order-up-to over P90 lead time (33 days) at 97% service level: <b>240 units</b>. Cover after receipt 11 weeks, under the 16-week cap.",
          flows: [["bus", "planner", "ev", "stock.low"], ["planner", "procurement", "ev", "recommend 240"]],
          log: [["Replenishment", "Recommended 240 units (P90 lead time 33 d, SL 97%)", "EV"]] },
        { at: "D1 10:12", who: "Procurement → Action Gateway", text: "PO for 240 units = <b>€6,720</b>, normally T1. Because the forecast is anomaly-influenced, policy lifts it to <b>T2: Buy Panel</b>.",
          flows: [["procurement", "gateway", "act", "CreatePO 240 · €6,720"], ["gateway", "panel", "act", "T2 → panel"]],
          log: [["Action Gateway", "CreatePurchaseOrder €6,720 escalated to T2 (anomaly-influenced)", "T2"]] },
        { at: "D1 10:14", who: "Buy Panel · 3 personas", text: "Planner says 240. CFO says 180 (spikes decay). Risk says OK, prefers split delivery. Synthesis: <b>majority → 180 now, review 60 more in 10 days</b>.",
          flows: [["panel", "panel", "llm", "Planner · CFO · Risk"], ["panel", "procurement", "llm", "majority: 180"]],
          log: [["Buy Panel", "Verdict: majority · 180 now + review option for 60 in 10 days", "EV"]] },
        { at: "D1 10:15", who: "Procurement → Gateway → Ledger", text: "<b>CreatePurchaseOrder(180) €5,040</b> executes once, with idempotency key po:sup_yd:ETOILE:2026-W40. Ledger and outbox commit in one transaction.",
          flows: [["procurement", "gateway", "act", "CreatePO 180 · €5,040"], ["gateway", "ledger", "ok", "po.created"], ["ledger", "bus", "ev", "outbox"]],
          log: [["Action Gateway", "Executed CreatePurchaseOrder 180 × €28 = €5,040 (panel-approved)", "T2"]], fx: (s) => { s.po += 1; s.onord += 180; s.atp = 34; } },
        { at: "D1 10:16", who: "Supplier Liaison", text: "PO goes by <b>EDI 850</b>; the 997 acknowledgement is back in seconds. The expedite request goes by <b>email</b>: template plus a short LLM paragraph, only to the verified domain.",
          flows: [["bus", "liaison", "ev", "po.created"], ["liaison", "supplier", "act", "EDI 850"], ["supplier", "liaison", "ok", "997 ack"], ["liaison", "supplier", "llm", "expedite email"]],
          log: [["Supplier Liaison", "EDI 850 sent; 997 received in 42 s · expedite email sent", "T1"]] },
        { at: "D2 12:30", who: "Maker → Checker", text: "Supplier replies: <b>120 in 5 days, 60 in 3 weeks, fee €380</b>. Extractor turns it into JSON; the verifier checks PO ref, quantities and fee ≤ 8% policy.",
          flows: [["supplier", "extractor", "llm", "reply email"], ["extractor", "extractor", "llm", "verify ✓"], ["extractor", "liaison", "ok", "verified"], ["liaison", "gateway", "act", "AmendPO split"], ["gateway", "ledger", "ok", "T1 ✓"]],
          log: [["Extractor + Verifier", "6/6 fields verified against PO-2026-0931", "T1"], ["Action Gateway", "AmendPO: split delivery 120 + 60, expedite fee €380", "T1"]], fx: (s) => { s.atp = 22; } },
        { at: "D2 12:32", who: "Finance", text: "Commitment <b>€5,420</b> recorded, open-to-buy reduced, landed cost +€2.11/unit. Cash runway <b>18.6 weeks</b>, above the 12-week floor.",
          flows: [["bus", "finance", "ev", "po.changed"], ["finance", "ledger", "ok", "cash forecast"]],
          log: [["Cash & Budget", "Commitment €5,420 · runway 18.6 wks · margin above floor", "T0"]], fx: (s) => { s.cash -= 5420; s.runway = 18.6; } },
        { at: "D3 09:00", who: "Order Orchestrator", text: "ATP hits <b>0</b>. Confirmed inbound within 10 days, so the SKU switches to <b>backorder mode</b> with an honest ship-by date.",
          flows: [["inventory", "bus", "ev", "ATP 0"], ["bus", "orders", "ev"], ["orders", "gateway", "act", "EnableBackorder"], ["gateway", "shopify", "ok", "ships by 9 Oct"]],
          log: [["Order Orchestrator", "Backorder mode on Étoile towel · ships by 9 Oct", "T1"]], fx: (s) => { s.atp = 0; s.heroShare = 0.25; } },
        { at: "D3 09:05", who: "Customer Care · grounded", text: "14 backordered customers get a proactive email. Dates come from the <b>PO record</b>, never from the model; Reply QA checks every claim.",
          flows: [["bus", "care", "ev"], ["care", "customers", "llm", "14 proactive emails"]],
          log: [["Customer Care", "14 proactive delivery-date emails (cited: PO-2026-0931)", "T1"]] },
        { at: "D7 08:00", who: "Logistics · 3PL", text: "ASN (EDI 856) arrives, 3PL receives <b>120 units</b>. Backorders are allocated first, then stock is pushed to Shopify.",
          flows: [["supplier", "tpl", "ev", "120 units + ASN"], ["tpl", "bus", "ev", "goods.received"], ["bus", "inventory", "ev"], ["inventory", "shopify", "ok", "ATP 106"]],
          log: [["Inbound Coordinator", "Receipt 120 = ASN 120 · 14 backorders allocated", "T0"]], fx: (s) => { s.atp = 106; s.onord -= 120; s.demand = 4.6; } },
        { at: "D7 08:10", who: "Lifecycle / CRM", text: "Back-in-stock flow emails <b>212 waitlisted</b> customers (consent-checked).",
          flows: [["bus", "lifecycle", "ev", "back in stock"], ["lifecycle", "customers", "ok", "212 emails"]],
          log: [["Lifecycle Agent", "Back-in-stock flow sent to 212 waitlisters", "T0"]], fx: (s) => { s.heroShare = 0.35; } },
        { at: "D8 09:00", who: "Marketing · hysteresis", text: "Cover is above the 5-week exit threshold, so ads resume at <b>50%</b> and ramp by bandit. Hysteresis stops the loop from flapping.",
          flows: [["inventory", "bus", "ev", "cover recovered"], ["bus", "marketing", "ev"], ["marketing", "gateway", "act", "SetAdBudget +50%"], ["gateway", "ledger", "ok", "T0 ✓"]],
          log: [["Budget Allocator", "SKU acquisition ads resumed at 50%", "T0"]], fx: (s) => { s.atp = 92; s.demand = 2.6; } },
        { at: "D11 10:00", who: "Scheduled review", text: "Velocity has decayed to <b>1.7×</b>, close to the CFO's view. Planner recommends <b>30 more</b>, not 60: a small T0 PO.",
          flows: [["planner", "procurement", "ev", "+30 units"], ["procurement", "gateway", "act", "CreatePO 30 · €840"], ["gateway", "ledger", "ok", "T0 ✓"]],
          log: [["Procurement", "CreatePurchaseOrder 30 units €840", "T0"]], fx: (s) => { s.onord += 30; s.atp = 81; s.po += 1; } },
        { at: "D12 11:00", who: "Accounts Payable", text: "Invoice (EDI 810) <b>three-way matches</b> PO ↔ receipt ↔ invoice. Payment scheduled to terms; supplier scorecard updated.",
          flows: [["supplier", "finance", "ev", "invoice 810"], ["finance", "gateway", "act", "SchedulePayment"], ["gateway", "stripe", "ok", "to terms"]],
          log: [["Accounts Payable", "3-way match OK · payment scheduled (30 days EOM)", "T0"]] },
        { at: "D12 18:00", who: "Control Tower", text: "Case closed. Auditor sampled the decisions. Weekly owner report: <b>spike handled, 0 human touches, +€4.9k margin vs baseline</b>.",
          flows: [["sentinel", "ledger", "ev", "audit sample"], ["sentinel", "owner", "ev", "weekly report"]],
          log: [["Auditor", "Case CASE-0930-017 reviewed · no findings", "EV"]], fx: (s) => { s.atp = 78; } },
      ],
    },

    normal: {
      name: "A normal day", ambient: true, gap: 800,
      chart: { key: "rev", label: "Revenue today (€)", max: 12000, span: 1, unit: "€" },
      intro: "An ordinary Tuesday: orders, a suspicious payment, customer questions, a small reorder, a refund and reconciliation, all inside the envelope.",
      done: "A full day of operations with every action at T0/T1 and zero human touches.",
      steps: [
        { at: "D1 09:10", who: "Orders", text: "Orders arrive and are released to the 3PL on the deterministic path.", flows: [["customers", "shopify", "ev", "order"], ["shopify", "bus", "ev"], ["bus", "orders", "ev"], ["orders", "tpl", "ok", "release"]], log: [["Order Orchestrator", "Released 18 orders to 3PL UK1", "T0"]], fx: (s) => { s.orders += 18; s.rev += 2940; } },
        { at: "D1 09:40", who: "Fraud Screening", text: "An order with Radar score 78 and a mismatched address is <b>held</b> (T0). Holding is reversible, so no approval is needed.", flows: [["bus", "fraud", "ev", "order #48231"], ["fraud", "gateway", "act", "HoldOrder"], ["gateway", "ledger", "ok", "T0 ✓"]], log: [["Fraud Screening", "Held order #48231 · Radar 78 + address mismatch", "T0"]] },
        { at: "D1 10:30", who: "Customer Care", text: "\"Where is my order?\" The agent answers from <b>carrier tracking</b> with citations; Reply QA passes it.", flows: [["customers", "care", "llm", "WISMO"], ["care", "care", "llm", "Reply QA ✓"], ["care", "customers", "llm", "ETA Thu (cited)"]], log: [["Customer Care", "Answered WISMO #48190 with tracking ETA (cited r_2)", "T1"]] },
        { at: "D1 11:15", who: "Replenishment → Procurement", text: "Nuit pillowcases fall below reorder point. <b>48 units, €1,680</b>: a T0 PO sent by EDI.", flows: [["planner", "procurement", "ev", "reorder 48"], ["procurement", "gateway", "act", "CreatePO €1,680"], ["gateway", "liaison", "ok", "T0 ✓"], ["liaison", "supplier", "act", "EDI 850"]], log: [["Procurement", "PO 48 × Nuit pillowcase €1,680 (EDI)", "T0"]], fx: (s) => { s.po += 1; s.cash -= 1680; } },
        { at: "D1 13:00", who: "Budget Allocator", text: "Marginal ROAS is higher on Meta for the linen duvet: <b>+€120/day</b>, within the ±20% daily limit.", flows: [["marketing", "gateway", "act", "SetAdBudget +€120"], ["gateway", "ledger", "ok", "T0 ✓"]], log: [["Budget Allocator", "Meta +€120/day, Google −€120/day (ROAS)", "T0"]] },
        { at: "D1 14:20", who: "Refund policy engine", text: "A damaged towel: <b>€58 refund</b> is policy-clean and under €150, so it's T0. The LLM drafts the message; the deterministic engine decides the refund.", flows: [["customers", "care", "llm", "damaged item"], ["care", "gateway", "act", "IssueRefund €58"], ["gateway", "stripe", "ok", "refund ✓"]], log: [["Refund Policy", "Refund €58 · policy-clean · idempotency re_48177", "T0"]], fx: (s) => { s.rev -= 58; } },
        { at: "D1 16:00", who: "Orders", text: "Afternoon peak.", flows: [["shopify", "bus", "ev", "orders"], ["bus", "orders", "ev"], ["orders", "tpl", "ok", "release"]], log: [["Order Orchestrator", "Released 24 orders to 3PL UK1", "T0"]], fx: (s) => { s.orders += 24; s.rev += 3120; } },
        { at: "D1 18:00", who: "Reconciliation", text: "Stripe payout <b>€18,420</b> matched to 312 charges and the bank feed. Journals posted automatically.", flows: [["stripe", "finance", "ev", "payout"], ["finance", "ledger", "ok", "312 matched"]], log: [["Reconciliation", "Payout po_7Q2 €18,420 · 312/312 charges matched", "T0"]], fx: (s) => { s.cash += 18420; } },
        { at: "D1 23:00", who: "Sentinel", text: "All behaviour metrics are inside baseline. Refund ratio 0.8%. <b>Zero human touches today.</b>", flows: [["sentinel", "ledger", "ev", "daily check"]], log: [["Sentinel", "Daily health: all agents within baseline", "EV"]] },
      ],
    },

    delay: {
      name: "Supplier delay", ambient: true, gap: 900,
      chart: { key: (s) => (s.demand ? s.atp / s.demand : 0), label: "Watched SKU cover (days)", max: 30, span: 4 },
      init: { atp: 64, demand: 3.2 },
      intro: "The supplier emails that a confirmed PO will ship <b>10 days late</b>. Watch the system re-plan without anyone asking it to.",
      done: "Delay absorbed: split air shipment, ads throttled, customers informed, scorecard updated.",
      steps: [
        { at: "D1 08:30", who: "Inbound email", text: "An email says <b>PO-0931 delayed 10 days</b>. Sender passes SPF/DKIM/DMARC; body treated as untrusted data.", flows: [["supplier", "extractor", "llm", "delay email"]], log: [["Supplier mailbox", "Inbound from verified domain · intent: delay", "EV"]] },
        { at: "D1 08:31", who: "Maker → Checker", text: "Extractor reads the new date; the verifier confirms the PO reference and quantities match the Ledger.", flows: [["extractor", "extractor", "llm", "verify"], ["extractor", "liaison", "ok", "new ship 15 Oct"]], log: [["Extractor + Verifier", "Delay verified: PO-2026-0931 ship date 5 → 15 Oct", "T1"]] },
        { at: "D1 08:32", who: "Supplier Liaison", text: "<b>AmendPO (dates)</b> recorded at T1; po.changed goes out through the outbox.", flows: [["liaison", "gateway", "act", "AmendPO dates"], ["gateway", "ledger", "ok", "T1 ✓"], ["ledger", "bus", "ev", "po.changed"]], log: [["Action Gateway", "AmendPO: ship date 15 Oct", "T1"]] },
        { at: "D1 08:35", who: "Replenishment Planner", text: "Cover gap of <b>6 days</b> before the new arrival. Options: wait, split air freight, or an alternative SKU.", flows: [["bus", "planner", "ev"], ["planner", "procurement", "ev", "gap 6 d"]], log: [["Replenishment", "Projected stock-out 6 days before receipt", "EV"], ], fx: (s) => { s.demand = 3.4; } },
        { at: "D1 08:40", who: "Procurement", text: "Asks for <b>40 units by air</b> ahead of the main shipment: cheaper than lost sales at this margin.", flows: [["procurement", "liaison", "llm", "request air split"], ["liaison", "supplier", "llm", "email"]], log: [["Procurement", "Requested partial air shipment 40 units", "T1"]] },
        { at: "D2 11:00", who: "Maker → Checker", text: "Supplier agrees: <b>40 by air, +€310</b>. Fee within expedite policy → AmendPO T1.", flows: [["supplier", "extractor", "llm", "reply"], ["extractor", "liaison", "ok", "verified"], ["liaison", "gateway", "act", "AmendPO split"], ["gateway", "ledger", "ok", "T1 ✓"]], log: [["Action Gateway", "AmendPO: 40 air (+€310) + 140 sea", "T1"]], fx: (s) => { s.cash -= 310; s.atp = 48; } },
        { at: "D2 11:05", who: "Marketing", text: "Cover is tight: acquisition spend on this SKU goes to <b>retargeting only</b>.", flows: [["bus", "marketing", "ev", "cover tight"], ["marketing", "gateway", "act", "SetAdBudget"], ["gateway", "ledger", "ok", "T0 ✓"]], log: [["Budget Allocator", "SKU ads → retargeting only", "T0"]] },
        { at: "D2 11:10", who: "Customer Care", text: "9 customers on backorder get a <b>proactive</b> updated date, cited from the amended PO.", flows: [["bus", "care", "ev"], ["care", "customers", "llm", "9 updates"]], log: [["Customer Care", "9 proactive date updates (cited PO-2026-0931 v3)", "T1"]] },
        { at: "D4 09:00", who: "Air shipment lands", text: "40 units received; cover recovers above the tight band.", flows: [["supplier", "tpl", "ev", "40 units"], ["tpl", "bus", "ev", "goods.received"], ["bus", "inventory", "ev"]], log: [["Inbound Coordinator", "Receipt 40 = ASN 40", "T0"]], fx: (s) => { s.atp = 81; } },
        { at: "D4 09:10", who: "Supplier Scorecard", text: "OTIF drops <b>94% → 91%</b>; lead-time distribution widens, so future safety stock rises automatically.", flows: [["ledger", "sentinel", "ev", "scorecard"]], log: [["Supplier Scorecard", "sup_yd OTIF 94% → 91%; lead-time P90 33 → 36 d", "EV"]] },
      ],
    },

    rogue: {
      name: "Rogue pricing agent", ambient: true, gap: 900,
      chart: { key: "price", label: "Étoile towel shelf price (€)", max: 100, span: 4, unit: "€" },
      init: { promo: false, price: 79 },
      intro: "A bad release makes the pricing agent propose <b>−60%</b> discounts. Watch the layers that don't depend on the model contain it.",
      done: "Contained in seconds: 0 bad prices published, 1 owner brief, fixed version back via shadow and canary.",
      steps: [
        { at: "D1 11:00", who: "Pricing · bad release", text: "pricing-agent@4.2 proposes <b>€31.60 (−60%)</b>. Price Guard rejects it: below the margin floor.", alert: true,
          flows: [["pricing", "gateway", "act", "ChangePrice −60%"], ["gateway", "pricing", "rej", "VETO · margin floor"]], log: [["Price Guard", "Rejected ChangePrice €31.60: below floor €45.20", "REJ"]] },
        { at: "D1 11:00", who: "Pricing · bad release", text: "It tries again, <b>−58%</b> and <b>−61%</b>. Each attempt is rejected and counted as an anomaly signal.", alert: true,
          flows: [["pricing", "gateway", "act", "−58%"], ["gateway", "pricing", "rej", "VETO", 600], ["pricing", "gateway", "act", "−61%", 600], ["gateway", "pricing", "rej", "VETO", 600]],
          log: [["Price Guard", "Rejected ChangePrice €33.18", "REJ"], ["Price Guard", "Rejected ChangePrice €30.81", "REJ"]] },
        { at: "D1 11:01", who: "Sentinel", text: "Reject rate is <b>40× baseline</b>. Sentinel <b>quarantines</b> the pricing agent automatically; no human needed.", alert: true,
          flows: [["gateway", "sentinel", "ev", "reject spike"], ["sentinel", "pricing", "rej", "QUARANTINE"]],
          log: [["Sentinel", "Quarantined pricing-agent@4.2 (reject rate 40× baseline)", "T0"]], fx: () => setStatus("pricing", "quar", "QUARANTINED") },
        { at: "D1 11:01", who: "Fallback", text: "Prices <b>freeze at last known good</b>. Scheduled promotions still run. Every other department keeps working.",
          flows: [["sentinel", "gateway", "ev", "halt pricing.*"], ["gateway", "ledger", "ok", "freeze"]], log: [["Action Gateway", "pricing.* halted · fallback: last good price book", "EV"]] },
        { at: "D1 11:03", who: "Incident Commander", text: "Blast-radius query: <b>0 prices changed</b>. The owner receives an informational brief; no decision is needed.",
          flows: [["sentinel", "ledger", "ev", "blast radius"], ["ledger", "sentinel", "ok", "0 changed"], ["sentinel", "owner", "ev", "incident brief"]],
          log: [["Incident Commander", "INC-219: 0 customer impact · rollback to 4.1 queued", "EV"]], fx: (s) => { s.human += 1; } },
        { at: "D1 14:00", who: "Recovery · shadow", text: "Rolled back to <b>pricing-agent@4.1</b> in <b>shadow mode</b>: it decides but does not act, and decisions are diffed.",
          flows: [["sentinel", "pricing", "ev", "rollback 4.1 · shadow"]], log: [["Release", "pricing-agent@4.1 in shadow", "EV"]], fx: () => setStatus("pricing", "shadow", "SHADOW MODE") },
        { at: "D2 09:00", who: "Shadow evaluation", text: "412 shadow decisions: <b>100% inside guardrails</b>, 97% agreement with the golden set.",
          flows: [["pricing", "sentinel", "ev", "412 decisions diffed"]], log: [["Evaluation", "Shadow pass: 0 violations, 97% golden agreement", "EV"]] },
        { at: "D3 09:00", who: "Canary 5%", text: "Canary on 5% of SKUs. A normal <b>+3%</b> move passes Price Guard.",
          flows: [["pricing", "gateway", "act", "ChangePrice +3%"], ["gateway", "shopify", "ok", "T0 ✓"]], log: [["Pricing Agent", "Canary: ChangePrice +3% on 1 SKU", "T0"]], fx: (s) => { setStatus("pricing", "shadow", "CANARY 5%"); s.price = 81.37; } },
        { at: "D4 09:00", who: "Active", text: "24 hours clean. The agent is <b>active</b> again and the post-mortem adds three new evaluation cases.",
          flows: [["sentinel", "pricing", "ok", "reinstated"]], log: [["Sentinel", "pricing-agent@4.1 active · +3 eval cases", "EV"]], fx: () => setStatus("pricing") },
      ],
    },
  };

  // ---------------------------------------------------------------- controls
  const scenBox = $("scen");
  scenBox.innerHTML = Object.entries(SC).map(([k, v]) => '<button type="button" data-k="' + k + '">' + v.name + "</button>").join("");
  function choose(k) {
    scenario = SC[k];
    scenBox.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === k)));
    reset();
  }
  scenBox.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) choose(b.dataset.k); });
  $("play").addEventListener("click", () => setPlaying(!playing));
  $("step").addEventListener("click", () => {
    if (playing) return;
    if (idx >= scenario.steps.length) reset();
    stepping = true;
    loop();
  });
  $("reset").addEventListener("click", reset);
  $("speed").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    speed = +b.dataset.s;
    $("speed").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
  $("kill").addEventListener("click", () => {
    S.kill = !S.kill;
    $("kill").setAttribute("aria-pressed", String(S.kill));
    ["gateway"].forEach((id) => setStatus(id, S.kill ? "halt" : null, S.kill ? "KILL SWITCH ON" : null));
    log("Owner · kill switch", S.kill ? "Global kill switch ON: all autonomous side effects stopped" : "Kill switch released", S.kill ? "HALT" : "EV");
    narrate("Kill switch", S.kill ? "Every action proposal is now refused at the gateway. <b>Orders keep flowing</b> on the deterministic path, so the shop stays open." : "Released. Agents resume inside their envelopes.", S.kill);
    render();
  });
  document.addEventListener("keydown", (e) => { if (e.code === "Space" && e.target === document.body) { e.preventDefault(); setPlaying(!playing); } });
  document.addEventListener("themechange", () => render());
  window.addEventListener("resize", () => drawChart());

  const start = (location.hash || "").slice(1);
  choose(SC[start] ? start : "towel");
})();
