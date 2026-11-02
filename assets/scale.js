/* Time machine for scale.html. Everything is generated from assets/scale-model.js and recomputed
   whenever an input changes. */
(function () {
  const S = window.SCALE;
  if (!S) return;
  const $ = (id) => document.getElementById(id);
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const money = (v) => {
    const s = v < 0 ? "−" : ""; v = Math.abs(v);
    if (v >= 1e6) return s + "£" + (v / 1e6).toFixed(v >= 1e7 ? 1 : 2) + "M";
    if (v >= 1e4) return s + "£" + Math.round(v / 1000) + "k";
    if (v >= 1e3) return s + "£" + (v / 1000).toFixed(1) + "k";
    if (v > 0 && v < 1) return s + "£" + v.toFixed(2);
    return s + "£" + Math.round(v);
  };
  const num = (v) => {
    if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(v >= 1e7 ? 0 : 2) + "M";
    if (v >= 1e4) return Math.round(v / 1000) + "k";
    if (v >= 1e3) return (v / 1000).toFixed(1) + "k";
    return String(Math.round(v));
  };
  const rate = (x) => (x < 0.01 ? "<0.01" : x.toFixed(2));
  const ph = (m) => S.phaseOf(m).n;

  // ---------- icons (generic glyphs, no vendor logos) ----------
  const I = {
    store: '<path d="M4 9l1.5-5h13L20 9"/><path d="M4 9h16v2a3 3 0 0 1-5.3 2A3 3 0 0 1 12 14a3 3 0 0 1-2.7-1A3 3 0 0 1 4 11z"/><path d="M5 14v6h14v-6"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    chat: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    cpu: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    layers: '<path d="M12 4l9 5-9 5-9-5z"/><path d="M3 14l9 5 9-5"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.5 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.5-3.5-8.5s1-6 3.5-8.5z"/>',
    dns: '<rect x="4" y="4" width="16" height="6" rx="1.5"/><rect x="4" y="14" width="16" height="6" rx="1.5"/><path d="M8 7h.01M8 17h.01"/>',
    net: '<circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v5M12 12l-6 5M12 12l6 5"/>',
    db: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    queue: '<rect x="3" y="5" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="15" width="18" height="4" rx="1"/>',
    archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l2 2M15 8l2 2"/>',
    toggle: '<rect x="3" y="7" width="18" height="10" rx="5"/><circle cx="16" cy="12" r="3"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M12 8l1.5 2.5L16 12l-2.5 1.5L12 16l-1.5-2.5L8 12l2.5-1.5z"/>',
    flow: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="12" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8.5 6H12a3 3 0 0 1 3 3v.5M8.5 18H12a3 3 0 0 0 3-3v-.5"/>',
    gate: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    chart: '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M7 15l4-4 3 3 5-6"/>',
    pulse: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    box: '<path d="M4 8l8-4 8 4v8l-8 4-8-4z"/><path d="M4 8l8 4 8-4M12 12v8"/>',
    book: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    git: '<circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="9" r="2.2"/><path d="M6 8.2v7.6M18 11.2c0 3-3 4-7 4.6"/>',
    play: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M10 9l5 3-5 3z"/>',
    claude: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 10l3 2-3 2M12 15h5"/>',
    office: '<rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M8 7h2M14 7h2M8 11h2M14 11h2M10 21v-4h4v4"/>',
    kanban: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16M5 8h2M11 8h2M11 11h2M17 8h2"/>',
    api: '<path d="M7 8l-4 4 4 4M17 8l4 4-4 4M14 5l-4 14"/>',
    lake: '<path d="M3 15c2-2 4 2 6 0s4 2 6 0 4 2 6 0M3 19c2-2 4 2 6 0s4 2 6 0 4 2 6 0"/><path d="M8 11l4-7 4 7"/>',
    stream: '<path d="M3 8c3-3 6 3 9 0s6 3 9 0M3 13c3-3 6 3 9 0s6 3 9 0M3 18c3-3 6 3 9 0s6 3 9 0"/>',
    card: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18M7 15h3"/>',
    wallet: '<path d="M4 7h14a2 2 0 0 1 2 2v9H6a2 2 0 0 1-2-2z"/><path d="M4 7l11-3v3"/><circle cx="16" cy="13" r="1.2"/>',
    people: '<circle cx="9" cy="9" r="3"/><circle cx="17" cy="10" r="2.5"/><path d="M3 20c.8-3.5 3.3-5 6-5s5.2 1.5 6 5M15 15c2.5 0 4.5 1.5 5.5 4"/>',
  };
  const icon = (k) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (I[k] || I.box) + "</svg>";

  // ---------- inputs panel ----------
  const C = S.CFG;
  try { const saved = JSON.parse(localStorage.getItem("halden-scale-cfg") || "null"); if (saved) { ["storefront", "email", "p3Servers", "p4Servers", "p4Regions", "p4Db", "p4Storage"].forEach((k) => { if (saved[k] != null) C[k] = saved[k]; }); } } catch (e) {}
  const saveCfg = () => { try { const o = {}; ["storefront", "email", "p3Servers", "p4Servers", "p4Regions", "p4Db", "p4Storage"].forEach((k) => (o[k] = C[k])); localStorage.setItem("halden-scale-cfg", JSON.stringify(o)); } catch (e) {} };
  const inputs = $("tm-inputs");
  const optNames = { gorgias: "Help-desk UI (Gorgias)", privnet: "Private networking pack", apim: "API Management", fabric: "Fabric lakehouse", eventhubs: "Event Hubs clickstream", wafPremium: "WAF managed rules in phase 3", temporalBiz: "Temporal Business plan", ghEnterprise: "GitHub Enterprise" };
  inputs.innerHTML =
    '<div class="in-grid">' +
    '<label>Customers by month 24<select id="in-cust"><option value="250000">250,000</option><option value="500000">500,000</option><option value="1000000" selected>1,000,000</option><option value="2000000">2,000,000</option></select></label>' +
    '<label>Average order value (£)<input id="in-aov" type="number" min="10" max="500" step="5" value="' + C.aov + '"></label>' +
    '<label>Developers per phase (1 / 2 / 3 / 4)<span class="in-row">' + [0, 1, 2, 3].map((i) => '<input class="in-dev" data-i="' + i + '" type="number" min="0" max="20" step="0.5" value="' + C.devs[i] + '" aria-label="Developers in phase ' + (i + 1) + '">').join("") + "</span></label>" +
    '<label>Cost per developer / month (£)<input id="in-devcost" type="number" min="0" max="30000" step="250" value="' + C.devCost + '"></label>' +
    '<label>Owners (accounts only)<input id="in-owners" type="number" min="1" max="10" step="1" value="' + C.owners + '"></label>' +
    '<label>Claude Code plan<select id="in-claude"><option value="pro">Pro · $20</option><option value="max" selected>Max · from $100</option><option value="team">Team premium · $125</option></select></label>' +
    '<label>Prompt size<select id="in-mult"><option value="0.5">0.5× lean</option><option value="1" selected>1× planned</option><option value="2">2× verbose</option><option value="4">4× worst case</option></select></label>' +
    '<label class="chk"><input id="in-team" type="checkbox" checked> Include developers in totals</label>' +
    "</div>" +
    '<div class="in-grid in-choice">' +
    '<label>Storefront<select id="in-store"><option value="shopify">Shopify (buy)</option><option value="own">Build our own (Stripe, own hosting)</option></select></label>' +
    '<label>Bulk email<select id="in-email"><option value="shopify">Shopify Email</option><option value="ses3">Amazon SES from phase 3</option><option value="ses">Amazon SES from day one</option></select></label>' +
    '<label id="in-own-wrap">Extra developers for own storefront (1 / 2 / 3 / 4)<span class="in-row">' + [0, 1, 2, 3].map((i) => '<input class="in-own" data-i="' + i + '" type="number" min="0" max="20" step="0.5" value="' + C.ownDevs[i] + '" aria-label="Extra storefront developers in phase ' + (i + 1) + '">').join("") + "</span></label>" +
    '<p class="in-hint" id="in-hint"></p>' +
    "</div>" +
    '<div class="in-grid in-choice">' +
    '<label>Phase 3 servers (D4)<input id="in-p3s" type="number" min="1" max="20" step="1" value="' + C.p3Servers + '"></label>' +
    '<label>Phase 4 servers per region (D4)<input id="in-p4s" type="number" min="1" max="20" step="1" value="' + C.p4Servers + '"></label>' +
    '<label>Phase 4 regions<select id="in-p4r"><option value="1">1 · UK South + DR copy (UK West)</option><option value="2">2 · UK South + US East</option></select></label>' +
    '<label>Phase 4 database<span class="in-row two"><select id="in-p4db" aria-label="Phase 4 database size"><option value="D4">D4 · 4 vCPU</option><option value="D8">D8 · 8 vCPU</option></select><select id="in-p4st" aria-label="Phase 4 database storage"><option value="256">256 GB</option><option value="512">512 GB</option><option value="1024">1 TB</option><option value="2048">2 TB</option></select></span></label>' +
    '<p class="in-hint">Default is the lean setup: one D4 server is $0.43/hour (~£237/month). Each extra region doubles servers, Redis and Service Bus; the database always keeps an HA standby plus one replica.</p>' +
    "</div>" +
    '<div class="in-opts"><span>Optional add-ons:</span>' + Object.keys(optNames).map((k) => '<label class="chk"><input type="checkbox" data-opt="' + k + '"> ' + optNames[k] + "</label>").join("") + "</div>";
  inputs.addEventListener("input", (e) => {
    const t = e.target;
    if (t.id === "in-cust") C.customers24 = +t.value;
    else if (t.id === "in-aov") C.aov = Math.max(1, +t.value || 1);
    else if (t.classList.contains("in-dev")) C.devs[+t.dataset.i] = Math.max(0, +t.value || 0);
    else if (t.id === "in-devcost") C.devCost = Math.max(0, +t.value || 0);
    else if (t.id === "in-owners") C.owners = Math.max(0, +t.value || 0);
    else if (t.id === "in-claude") C.claudePlan = t.value;
    else if (t.id === "in-mult") C.promptMult = +t.value;
    else if (t.id === "in-team") C.includeTeam = t.checked;
    else if (t.dataset.opt) C.optional[t.dataset.opt] = t.checked;
    else if (t.id === "in-store") { C.storefront = t.value; saveCfg(); }
    else if (t.id === "in-email") { C.email = t.value; saveCfg(); }
    else if (t.classList.contains("in-own")) C.ownDevs[+t.dataset.i] = Math.max(0, +t.value || 0);
    else if (t.id === "in-p3s") { C.p3Servers = Math.max(1, Math.round(+t.value || 1)); saveCfg(); }
    else if (t.id === "in-p4s") { C.p4Servers = Math.max(1, Math.round(+t.value || 1)); saveCfg(); }
    else if (t.id === "in-p4r") { C.p4Regions = +t.value; saveCfg(); }
    else if (t.id === "in-p4db") { C.p4Db = t.value; saveCfg(); }
    else if (t.id === "in-p4st") { C.p4Storage = +t.value; saveCfg(); }
    else return;
    refresh();
  });

  function syncChoices() {
    $("in-store").value = C.storefront; $("in-email").value = C.email;
    $("in-p3s").value = C.p3Servers; $("in-p4s").value = C.p4Servers; $("in-p4r").value = String(C.p4Regions); $("in-p4db").value = C.p4Db; $("in-p4st").value = String(C.p4Storage);
    $("in-email").disabled = C.storefront === "own";
    $("in-own-wrap").hidden = C.storefront !== "own";
    $("in-hint").textContent = C.storefront === "own"
      ? "Own storefront: no Shopify plan, but Stripe card fees, fraud screening, US sales tax, hosting, logins and extra developers. Email must use Amazon SES."
      : C.email === "shopify" ? "Shopify Email: no engineering, 10,000 emails free, then $1 per 1,000." : "Amazon SES: $0.10 per 1,000 emails; we build templates, unsubscribe and bounce handling (about 1–2 weeks once).";
  }
  syncChoices();

  // ---------- tiles ----------
  const lanesEl = $("tm-lanes");
  const tiles = [], laneRows = {};
  S.LANES.forEach((ln) => {
    const row = document.createElement("div");
    row.className = "tm-lane lane-" + ln.bucket;
    row.dataset.bucket = ln.bucket;
    row.innerHTML = '<div class="tm-lane-h"><span>' + ln.name + (ln.note ? " <em>" + ln.note + "</em>" : "") + '</span><b data-lane="' + ln.id + '"></b></div><div class="tm-tiles"></div>';
    lanesEl.appendChild(row);
    laneRows[ln.id] = row;
    const box = row.querySelector(".tm-tiles");
    S.LINES.forEach((line, idx) => {
      if (line.lane !== ln.id) return;
      const el = document.createElement("div");
      el.className = "tm-tile";
      const src = line.src ? S.SRC[line.src] : null;
      el.innerHTML = '<span class="ic">' + icon(line.icon) + '</span><span class="tt">' + line.name + "</span>" +
        '<span class="pv"></span><span class="un"></span><span class="pr"></span>' +
        (src ? '<span class="src"><a href="' + src.url + '" target="_blank" rel="noopener" title="' + src.label + '">pricing page ↗</a>' + (src.api ? ' · <a href="' + src.api + '" data-ev="' + line.src + '" title="Show the exact official meters used">exact price</a>' : "") + "</span>" : "") + '<span class="bd"></span>';
      box.appendChild(el);
      tiles.push({ line, idx, el, pv: el.querySelector(".pv"), un: el.querySelector(".un"), pr: el.querySelector(".pr"), bd: el.querySelector(".bd"), on: null, what: null, val: 0 });
    });
  });
  const tabsEl = $("tm-tabs");
  let activeBucket = "all";
  tabsEl.innerHTML = [{ id: "all", name: "Everything" }].concat(S.BUCKETS).map((b) => '<button type="button" class="tm-tab" data-b="' + b.id + '" aria-pressed="' + (b.id === "all") + '">' + b.name + ' <b data-bt="' + b.id + '"></b><i data-bc="' + b.id + '" hidden></i></button>').join("");
  tabsEl.addEventListener("click", (e) => {
    const t = e.target.closest(".tm-tab"); if (!t) return;
    activeBucket = t.dataset.b;
    tabsEl.querySelectorAll(".tm-tab").forEach((x) => x.setAttribute("aria-pressed", String(x === t)));
    Object.values(laneRows).forEach((r) => (r.hidden = !(activeBucket === "all" || r.dataset.bucket === activeBucket)));
  });

  const FOOT = [
    { name: "Azure UK South", on: () => "on" },
    { name: "Azure UK West (DR replica)", on: (m) => (ph(m) === 3 || (ph(m) === 4 && C.p4Regions === 1) ? "warm" : "") },
    { name: "Azure US East", on: (m) => (ph(m) === 4 && C.p4Regions === 2 ? "on" : "") },
    { name: "Shopify Markets · UK", on: () => "on" },
    { name: "Shopify Markets · US & EU", on: (m) => (ph(m) >= 2 ? "on" : "") },
  ];
  const footEl = $("tm-foot");
  FOOT.forEach((f) => { const s = document.createElement("span"); s.className = "chip-f"; s.innerHTML = "<i></i><span></span>"; footEl.appendChild(s); f.el = s; });
  const TOUCH = ["< 50", "< 20", "< 10", "< 5"];
  const PO_T0 = ["£1k", "£4k", "£15k", "£40k"];

  // ---------- tween ----------
  const tw = new Map();
  function tween(el, to, fmt) {
    const prev = tw.get(el), from = prev ? prev.cur : to;
    if (reduce || from === to) { el.textContent = fmt(to); tw.set(el, { cur: to }); return; }
    const t0 = performance.now(), st = { cur: from }; tw.set(el, st);
    const step = (now) => {
      if (tw.get(el) !== st) return;
      const k = Math.min(1, (now - t0) / 520), e = 1 - Math.pow(1 - k, 3);
      st.cur = from + (to - from) * e; el.textContent = fmt(st.cur);
      if (k < 1) requestAnimationFrame(step); else st.cur = to;
    };
    requestAnimationFrame(step);
  }
  const flash = (el, cls) => { if (reduce) return; el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); };
  const shape = (s) => String(s).replace(/[\d.,]+\s*[kMB]?/g, "#");

  // ---------- data ----------
  let months = [];
  function compute() { months = Array.from({ length: 24 }, (_, i) => S.month(i + 1)); }

  function events() {
    const ev = [[1, "Launch", "24 frame models go live as pre-orders; ads are split across them by a bandit. One small Postgres server, apps that scale to zero."]];
    for (let i = 1; i < 24 && C.storefront === "shopify"; i++) {
      const a = months[i - 1].items[0].what.split(" ")[0], b = months[i].items[0].what.split(" ")[0];
      if (a !== b) ev.push([i + 1, "Shopify → " + b, "At " + money(months[i].sales) + " of sales a month, " + b + " is now cheaper than " + a + " once card fees are counted."]);
    }
    ev.push([3, "Winners", "The weakest models stop getting ad spend; 6 winners get small air-freighted batches."]);
    ev.push([5, "Gate → Traction", "Postgres moves to a zone-redundant HA pair; Redis and Front Door arrive; the gateway runs two replicas."]);
    ev.push([8, "Forecasting", "Enough history for a nightly statsforecast job to replace reorder-point rules."]);
    ev.push([10, "Gate → Scale", "Dedicated nodes across zones, a DR replica in UK West, Defender for Containers, Xero multi-currency."]);
    ev.push([17, "Gate → Million", C.p4Regions === 2 ? "A second region (US East) with its own runtime cell and a geo-replica of the ledger; Front Door Premium with managed WAF rules." : C.p4Servers + " servers and a " + C.p4Db + " database in one region, with a disaster-recovery copy in UK West; Front Door Premium with managed WAF rules. A second region is optional."]);
    ev.push([24, "Month 24", "Card and PayPal fees are now the largest technology-related cost by far; negotiate them before anything else."]);
    return ev.sort((x, y) => x[0] - y[0]);
  }

  // ---------- chart ----------
  const W = 720, H = 230, L = 52, R = 10, T = 28, B = 24, bw = (W - L - R) / 24;
  let yMin = 10, yMax = 1e6;
  const ly = (v) => T + (H - T - B) * (1 - (Math.log10(Math.max(v, yMin)) - Math.log10(yMin)) / (Math.log10(yMax) - Math.log10(yMin)));
  function drawChart() {
    const svg = $("tm-chart");
    const maxV = Math.max(...months.map((r) => Math.max(r.allIn, r.fees)));
    const minV = Math.min(...months.map((r) => Math.min(r.allIn, r.fees)));
    yMin = Math.pow(10, Math.floor(Math.log10(Math.max(1, minV))));
    yMax = Math.pow(10, Math.ceil(Math.log10(maxV)));
    let s = "";
    S.PHASES.forEach((p, i) => {
      const x = L + (p.from - 1) * bw, w = (p.to - p.from + 1) * bw;
      s += '<rect class="band' + (i % 2 ? " alt" : "") + '" x="' + x + '" y="' + (T - 20) + '" width="' + w + '" height="' + (H - B - T + 20) + '"/><text class="bandl" x="' + (x + 6) + '" y="' + (T - 8) + '">' + p.n + " · " + p.name + "</text>";
    });
    for (let v = yMin; v <= yMax; v *= 10) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + ly(v) + '" y2="' + ly(v) + '"/><text class="ax" x="' + (L - 8) + '" y="' + (ly(v) + 4) + '" text-anchor="end">' + money(v) + "</text>";
    let fees = "";
    months.forEach((r, i) => {
      const x = L + i * bw + 2, y = ly(r.allIn);
      s += '<path class="bar" data-m="' + (i + 1) + '" d="M' + x + "," + (H - B) + "V" + (y + 3) + "q0,-3 3,-3h" + (bw - 10) + "q3,0 3,3V" + (H - B) + 'z"/>';
      fees += (i ? "L" : "M") + (L + i * bw + bw / 2) + "," + ly(r.fees);
      if ((i + 1) % 3 === 0 || i === 0) s += '<text class="ax" x="' + (L + i * bw + bw / 2) + '" y="' + (H - 7) + '" text-anchor="middle">' + (i + 1) + "</text>";
    });
    s += '<path class="feeline" d="' + fees + '"/>';
    months.forEach((r, i) => (s += '<rect class="hit" data-m="' + (i + 1) + '" x="' + (L + i * bw) + '" y="' + (T - 20) + '" width="' + bw + '" height="' + (H - T - B + 20) + '"/>'));
    s += '<line id="tm-play" class="playhead" y1="' + (T - 20) + '" y2="' + (H - B) + '"/>';
    svg.innerHTML = s;
  }
  (function bindChart() {
    const svg = $("tm-chart"), tip = $("tm-tip");
    svg.addEventListener("pointermove", (e) => {
      const hit = e.target.closest(".hit"); if (!hit) { tip.hidden = true; return; }
      const r = months[+hit.dataset.m - 1], wrap = svg.parentNode.getBoundingClientRect();
      tip.hidden = false;
      tip.innerHTML = "<b>Month " + r.m + " · " + r.phase.name + "</b><span>Runtime " + money(r.runtime) + " · engineering " + money(r.eng) + (r.opt ? " · add-ons " + money(r.opt) : "") + "</span><span>Developers " + money(r.teamCost) + (C.includeTeam ? "" : " (excluded)") + "</span><span>All-in <b>" + money(r.allIn) + "</b> · " + (r.allInPct * 100).toFixed(1) + "% of sales</span><span>Payment fees <b>" + money(r.fees) + "</b></span>";
      tip.style.left = Math.min(Math.max(e.clientX - wrap.left, 120), wrap.width - 120) + "px";
      tip.style.top = Math.max(0, e.clientY - wrap.top - 16) + "px";
    });
    svg.addEventListener("pointerleave", () => (tip.hidden = true));
    svg.addEventListener("click", (e) => { const hit = e.target.closest(".hit"); if (hit) { stop(); go(+hit.dataset.m, false, true); } });
  })();

  // ---------- render a month ----------
  const slider = $("tm-range");
  let cur = 0;
  function go(m, fromSlider, force) {
    m = Math.max(1, Math.min(24, m));
    if (!fromSlider) slider.value = m;
    if (m === cur && !force) return;
    const forward = m > cur;
    cur = m;
    const r = months[m - 1], p = r.phase;
    slider.style.setProperty("--pct", ((m - 1) / 23) * 100 + "%");
    $("tm-month").textContent = "Month " + m;
    $("tm-phase").textContent = "Phase " + p.n + " · " + p.name;
    document.querySelectorAll(".tm-ph").forEach((el) => el.classList.toggle("on", +el.dataset.p === p.n));

    tween($("k-cust"), r.customers, num);
    tween($("k-opd"), r.ordersPerDay, num);
    $("k-pk").textContent = rate(r.peakOrdersPerSec);
    tween($("k-sales"), r.sales, money);
    tween($("k-all"), r.allIn, money);
    $("k-pct").textContent = (r.allInPct * 100).toFixed(1) + "%";
    $("k-pct-tech").textContent = "tech only " + (r.techPct * 100).toFixed(2) + "%";
    tween($("k-run"), r.runtime, money);
    tween($("k-eng"), r.eng, money);
    tween($("k-opt"), r.opt, money);
    tween($("k-team"), r.teamCost, money);
    $("k-team").parentNode.classList.toggle("muted", !C.includeTeam);
    tween($("k-fees"), r.fees, money);
    tween($("k-llm"), r.llm.cost, money);
    $("k-tok").textContent = num(r.llm.tokens) + " tokens";
    $("k-agents").textContent = r.agents;
    $("k-touch").textContent = TOUCH[p.n - 1];
    $("k-t0").textContent = PO_T0[p.n - 1];

    const laneTot = {}, changes = {};
    const prev = m > 1 ? months[m - 2] : null;
    tiles.forEach((o) => {
      const it = r.items[o.idx];
      o.el.hidden = !it.used;
      if (!it.used) { o.on = null; o.what = null; o.val = 0; return; }
      const optOff = o.line.opt && !S.CFG.optional[o.line.opt];
      o.el.classList.toggle("off", !it.avail);
      o.el.classList.toggle("optoff", it.avail && !!optOff);
      o.un.textContent = it.unitTxt;
      if (!it.avail) {
        o.pv.textContent = "from month " + o.line.from; o.pr.textContent = ""; o.bd.textContent = ""; o.bd.className = "bd";
        o.on = false; o.what = null; o.val = 0; return;
      }
      laneTot[o.line.lane] = (laneTot[o.line.lane] || 0) + it.cost;
      if (o.on === false && forward) flash(o.el, "pop");
      if (o.what !== null && shape(o.what) !== shape(it.what)) flash(o.el, "swap");
      o.pv.textContent = it.what;
      if (optOff) { o.pr.textContent = "not included"; o.pr.classList.add("var"); }
      else if (it.incl) { o.pr.textContent = "included"; o.pr.classList.add("var"); }
      else if (it.note) { o.pr.textContent = "switched on"; o.pr.classList.add("var"); }
      else { o.pr.classList.remove("var"); if (o.val > 0 && it.cost > o.val * 1.3 && forward) flash(o.pr, "up"); tween(o.pr, it.cost, (x) => money(x) + "/mo"); }
      const pi = prev ? prev.items[o.idx] : null;
      const isNew = pi ? !pi.avail : m === 1;
      const changed = !optOff && !isNew && pi && shape(pi.what) !== shape(it.what);
      if (optOff) { o.bd.textContent = ""; o.bd.className = "bd"; o.on = true; o.what = it.what; o.val = 0; return; }
      o.bd.textContent = isNew ? "new" : changed ? "changed" : "";
      o.bd.className = "bd" + (isNew ? " new" : changed ? " up" : "");
      if (isNew || changed) { changes[o.line.bucket] = (changes[o.line.bucket] || 0) + 1; changes.all = (changes.all || 0) + 1; }
      o.on = true; o.what = it.what; o.val = it.cost;
    });
    document.querySelectorAll("[data-lane]").forEach((b) => tween(b, laneTot[b.dataset.lane] || 0, (x) => money(x) + "/mo"));
    document.querySelectorAll("[data-bt]").forEach((b) => { const id = b.dataset.bt; tween(b, id === "all" ? r.allIn + r.fees : r.by[id], money); });
    document.querySelectorAll("[data-bc]").forEach((b) => { const c = changes[b.dataset.bc] || 0; b.textContent = c ? c + " changed" : ""; b.hidden = !c; });

    FOOT.forEach((f) => { const st = f.on(m); f.el.className = "chip-f" + (st ? " " + st : ""); f.el.querySelector("span").textContent = f.name + (st === "warm" ? " · standby" : ""); });
    const past = events().filter((e) => e[0] <= m).slice(-2).reverse();
    $("tm-log").innerHTML = past.map((e, i) => '<li class="' + (i === 0 && e[0] === m ? "now" : "") + '"><span class="when">M' + e[0] + "</span><b>" + e[1] + "</b><span>" + e[2] + "</span></li>").join("");

    document.querySelectorAll("#tm-chart .bar").forEach((b) => b.classList.toggle("sel", +b.dataset.m === m));
    const line = $("tm-play"); if (line) { const x = L + (m - 0.5) * bw; line.setAttribute("x1", x); line.setAttribute("x2", x); }
    renderAI();
  }
  slider.addEventListener("input", () => { stop(); go(+slider.value, true); });

  let timer = null;
  const playBtn = $("tm-playbtn");
  function stop() { if (timer) { clearInterval(timer); timer = null; } playBtn.querySelector("span").textContent = "Play"; playBtn.setAttribute("aria-pressed", "false"); }
  function play() { if (cur >= 24) go(1); playBtn.querySelector("span").textContent = "Pause"; playBtn.setAttribute("aria-pressed", "true"); timer = setInterval(() => { if (cur >= 24) { stop(); return; } go(cur + 1); }, 1500); }
  playBtn.addEventListener("click", () => (timer ? stop() : play()));
  document.querySelectorAll(".tm-ph").forEach((b) => b.addEventListener("click", () => { stop(); go(S.PHASES[+b.dataset.p - 1].from); }));

  // ---------- AI table ----------
  function renderAI() {
    const tb = $("ai-table"); if (!tb) return;
    const L_ = months[cur - 1].llm, r = months[cur - 1];
    $("ai-month").textContent = "Month " + cur + " · " + r.phase.name;
    tb.innerHTML = L_.rows.map((x) => "<tr><td>" + x.agent + "<small>" + x.task + "</small></td><td>" + x.modelName + '</td><td class="num">' + (x.calls ? num(x.calls) : "—") + '</td><td class="num">' + (x.inTok ? num(x.inTok * C.promptMult) + " / " + num(x.outTok * C.promptMult) : "—") + '</td><td class="num">' + (x.inTok ? Math.round(x.cache * 100) + "%" : "—") + '</td><td class="num">' + num(x.tokens) + '</td><td class="num">' + money(x.cost) + "</td></tr>").join("") +
      '<tr class="tot"><td colspan="5">Total, month ' + cur + '</td><td class="num">' + num(L_.tokens) + '</td><td class="num">' + money(L_.cost) + "</td></tr>";
    $("ai-share").textContent = money(L_.cost) + " is " + ((L_.cost / Math.max(1, r.runtime)) * 100).toFixed(0) + "% of this month's runtime platform (" + money(r.runtime) + ") and " + ((L_.cost / r.orders) * 100).toFixed(1) + "p per order.";
  }

  // ---------- bill of materials ----------
  let bomPhase = 1;
  function renderBOM() {
    const box = $("bom-box"); if (!box) return;
    const m = S.PHASES[bomPhase - 1].to, r = months[m - 1];
    document.querySelectorAll(".bom-tab").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.p === bomPhase)));
    let html = '<table><thead><tr><th>Item</th><th>What we run (month ' + m + ')</th><th>Official unit price</th><th class="num">£/month</th><th>Source</th></tr></thead><tbody>';
    S.BUCKETS.forEach((bk) => {
      const items = r.items.filter((i) => i.bucket === bk.id && i.used && i.avail && (!i.opt || S.CFG.optional[i.opt]) && !i.note);
      if (!items.length) return;
      html += '<tr class="bkt"><td colspan="3">' + bk.name + (bk.variable ? " (variable)" : "") + '</td><td class="num">' + money(r.by[bk.id]) + "</td><td></td></tr>";
      items.forEach((i) => {
        const s = i.src ? S.SRC[i.src] : null;
        html += "<tr><td>" + i.name + "</td><td>" + i.what + "</td><td><small>" + i.unitTxt + '</small></td><td class="num">' + (i.incl ? "incl." : money(i.cost)) + "</td><td>" + (s ? '<a href="' + s.url + '" target="_blank" rel="noopener">' + s.label + "</a>" + (s.api ? '<br><a href="' + s.api + '" data-ev="' + i.src + '">exact UK South price</a>' : "") : "your input") + "</td></tr>";
      });
    });
    html += '<tr class="tot"><td colspan="3">Technology (runtime + engineering + add-ons) · ' + num(r.orders) + " orders · " + money(r.sales) + ' sales</td><td class="num">' + money(r.tech) + "</td><td>" + (r.techPct * 100).toFixed(2) + "% of sales</td></tr>";
    html += '<tr class="tot"><td colspan="3">All-in' + (C.includeTeam ? " including developers" : " (developers excluded)") + '</td><td class="num">' + money(r.allIn) + "</td><td>" + (r.allInPct * 100).toFixed(1) + "% of sales</td></tr>";
    html += '<tr class="tot alt"><td colspan="3">Payment fees (not a platform choice)</td><td class="num">' + money(r.fees) + "</td><td>" + (r.feesPct * 100).toFixed(2) + "% of sales</td></tr></tbody></table>";
    box.innerHTML = html;
  }
  document.querySelectorAll(".bom-tab").forEach((b) => b.addEventListener("click", () => { bomPhase = +b.dataset.p; renderBOM(); }));

  function renderMonths() {
    const mt = $("tm-table"); if (!mt) return;
    mt.innerHTML = months.map((r) => "<tr><td>" + r.m + "</td><td>" + r.phase.name + '</td><td class="num">' + num(r.customers) + '</td><td class="num">' + num(r.ordersPerDay) + '</td><td class="num">' + money(r.sales) + '</td><td class="num">' + money(r.runtime) + '</td><td class="num">' + money(r.eng + r.opt) + '</td><td class="num">' + money(r.teamCost) + '</td><td class="num">' + money(r.allIn) + '</td><td class="num">' + (r.allInPct * 100).toFixed(1) + '%</td><td class="num">' + money(r.fees) + '</td><td class="num">' + money(r.llm.cost) + "</td></tr>").join("");
  }


  // ---------- price evidence dialog ----------
  const EV = window.PRICE_EVIDENCE;
  const dlg = $("ev-dlg");
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-ev]");
    if (!a || !EV || !dlg || !EV.evidence[a.dataset.ev]) return;
    e.preventDefault();
    const key = a.dataset.ev, src = S.SRC[key], d = EV.evidence[key];
    const fmtP = (x) => (x === 0 ? "0 (free)" : x < 0.001 ? x.toFixed(6) : x < 1 ? x.toFixed(4).replace(/0+$/, "") : x.toLocaleString("en-US"));
    $("ev-title").textContent = src.label;
    $("ev-body").innerHTML = '<table><thead><tr><th>Meter</th><th>SKU</th><th class="num">Price (USD)</th><th>Unit</th><th>Applies from</th><th>Region</th></tr></thead><tbody>' +
      d.rows.map((r) => "<tr><td>" + r.meter + "<small>" + r.product + "</small></td><td>" + r.sku + '</td><td class="num"><b>$' + fmtP(r.price) + "</b></td><td>" + r.unit + "</td><td>" + (r.tierMin ? r.tierMin.toLocaleString("en-US") + " units" : "first unit") + "</td><td>" + r.region + "</td></tr>").join("") +
      "</tbody></table>";
    $("ev-meta").innerHTML = d.rows.length + " meter" + (d.rows.length > 1 ? "s" : "") + " · these are the only meters this line uses · snapshot " + EV.retrieved + ", converted to GBP at " + S.FX + ' · <a href="' + d.api + '" target="_blank" rel="noopener">re-check live in Microsoft\'s Retail Prices API ↗</a> · <a href="' + src.url + '" target="_blank" rel="noopener">pricing page ↗</a>';
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  });
  if (dlg) dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.closest("[data-close]")) dlg.close(); });

  // ---------- scenario comparison (buy vs build) ----------
  function renderCompare() {
    const tb = $("cmp-table"); if (!tb) return;
    const keep = { storefront: C.storefront, email: C.email };
    const scen = [["Shopify + Shopify Email", "shopify", "shopify"], ["Shopify + Amazon SES (from phase 3)", "shopify", "ses3"], ["Build our own storefront (Stripe + SES)", "own", "ses"]];
    const rows = scen.map(([label, st, em]) => {
      C.storefront = st; C.email = em;
      let tech = 0, all = 0, fees = 0, team = 0;
      for (let m = 1; m <= 24; m++) { const q = S.month(m); tech += q.tech; fees += q.fees; team += q.teamCost; }
      const e = S.month(24);
      return { label, st, em, m24tech: e.tech, m24fees: e.fees, m24team: e.teamCost, tech, fees, team, total: tech + fees + team };
    });
    C.storefront = keep.storefront; C.email = keep.email;
    const best = Math.min(...rows.map((r) => r.total));
    tb.innerHTML = rows.map((r) => '<tr class="' + (r.st === C.storefront && r.em === C.email ? "cur" : "") + '"><td>' + r.label + (r.total === best ? ' <span class="tag">cheapest</span>' : "") + '</td><td class="num">' + money(r.m24tech) + '</td><td class="num">' + money(r.m24fees) + '</td><td class="num">' + money(r.m24team) + '</td><td class="num">' + money(r.tech) + '</td><td class="num">' + money(r.fees) + '</td><td class="num">' + money(r.team) + '</td><td class="num"><b>' + money(r.total) + "</b></td></tr>").join("");
  }

  // ---------- numbers quoted in the text ----------
  function bindText() {
    const range = (pn, key) => {
      const ms = months.filter((r) => r.phase.n === pn).map((r) => r[key]);
      const lo = Math.min(...ms), hi = Math.max(...ms);
      return Math.abs(hi - lo) / Math.max(1, hi) < 0.08 ? money(hi) : money(lo) + "–" + money(hi);
    };
    const sum = (k) => months.reduce((s, r) => s + r[k], 0);
    const last = months[23];
    const vals = {
      tech1: range(1, "tech"), tech2: range(2, "tech"), tech3: range(3, "tech"), tech4: range(4, "tech"),
      team1: money(months[0].teamCost), team2: money(months[4].teamCost), team3: money(months[9].teamCost), team4: money(months[16].teamCost),
      techPct24: ((sum("tech") / sum("sales")) * 100).toFixed(2) + "%", tech24: money(sum("tech")),
      allPct24: ((sum("allIn") / sum("sales")) * 100).toFixed(1) + "%", all24: money(sum("allIn")),
      fees24: money(sum("fees")), feesM24: money(last.fees), feesPctM24: (last.feesPct * 100).toFixed(1) + "%",
      runM24: money(last.runtime), llmM24: money(last.llm.cost), tokM24: num(last.llm.tokens),
      opdM24: num(last.ordersPerDay), pkM24: rate(last.peakOrdersPerSec), aov: "£" + C.aov,
      m1tech: money(months[0].tech), m1all: money(months[0].allIn), m1pct: (months[0].allInPct * 100).toFixed(0) + "%", m1techpct: (months[0].techPct * 100).toFixed(1) + "%", m1sales: money(months[0].sales),
      cust24: num(C.customers24), shopM24: last.items[0].what.split(" ")[0], devs: C.devs.join(" / "), devCost: money(C.devCost),
    };
    document.querySelectorAll("[data-k]").forEach((el) => { if (vals[el.dataset.k] != null) el.textContent = vals[el.dataset.k]; });
  }

  function refresh() {
    syncChoices(); compute(); drawChart(); renderBOM(); renderMonths(); bindText(); renderCompare();
    const m = cur || 1; cur = 0; go(m, false, true);
  }

  compute(); drawChart(); renderBOM(); renderMonths(); bindText(); renderCompare();
  let start = 1;
  try { start = parseInt(new URLSearchParams(location.search).get("m"), 10) || 1; } catch (e) {}
  go(start);
  try { const evk = new URLSearchParams(location.search).get("ev"); const a = evk && document.querySelector('a[data-ev="' + evk + '"]'); if (a) a.click(); } catch (e) {}
})();
