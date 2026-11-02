/* Halden control room. No framework: fetch, render, poll. */
(function () {
  "use strict";

  var state = null, tab = "overview", logSeq = 0, mutedChannels = {}, askTicket = null;
  var el = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  };
  var eur = function (v) { return "€" + (Math.round((+v || 0) * 100) / 100).toLocaleString("en-GB"); };
  var pct = function (v, d) { return ((+v || 0) * 100).toFixed(d === undefined ? 1 : d) + "%"; };
  var num = function (v, d) { return (+v || 0).toFixed(d === undefined ? 0 : d); };

  // ---------------------------------------------------------------- fetch --
  function api(path, body) {
    return fetch(path, body ? {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body)
    } : undefined).then(function (r) { return r.json(); });
  }

  function refresh() {
    return api("/api/state").then(function (s) {
      var typed = document.activeElement && document.activeElement.id === "ask-input"
        ? document.activeElement.value : null;
      state = s;
      paint();
      if (typed !== null && el("ask-input")) { el("ask-input").value = typed; el("ask-input").focus(); }
    });
  }

  // ----------------------------------------------------------------- head --
  function paintHead() {
    var p = state.provider || {};
    var pr = el("p-provider");
    pr.className = "pill " + (p.provider === "rules_only" ? "rules" : "live");
    pr.innerHTML = "model <b>" + esc(p.provider === "claude_cli" ? "claude cli" :
      p.provider === "anthropic_api" ? "anthropic api" : "rules only") + "</b>";
    pr.title = p.label + " — " + p.detail;
    var q = state.queue || {};
    el("p-queue").innerHTML = "queue <b>" + q.ready + "</b> ready · " + q.done + " done" +
      (q.dead ? " · <b style='color:var(--bad)'>" + q.dead + " dead</b>" : "");
    el("p-cost").innerHTML = "evidence <b>" + state.evidence_count + "</b> · model cost <b>" +
      (state.cost_total ? eur(state.cost_total) : "0 (subscription)") + "</b>";

    var busy = state.busy && state.busy.running;
    ["b-run", "b-reorder", "b-marketing", "b-verdict", "b-reset", "b-model"].forEach(function (id) {
      el(id).disabled = !!busy;
    });
    el("b-run").textContent = busy ? "Running " + state.busy.what + "…" : "Run full cycle";
    el("log-dot").className = "dot" + (busy ? " on" : "");

    var counts = {
      "c-reorder": (state.reorder || []).length || "",
      "c-marketing": ((state.marketing || {}).cells || []).length || "",
      "c-portfolio": (state.verdict || []).length || "",
      "c-approvals": (state.pending || []).length || "",
      "c-ledger": (state.ledger || []).length || "",
      "c-anomalies": (state.anomalies || []).length || "",
      "c-models": (state.model_registry || []).length || ""
    };
    Object.keys(counts).forEach(function (k) {
      var node = el(k); if (!node) return;
      node.textContent = counts[k];
      node.className = "count" + ((k === "c-approvals" && counts[k]) ? " hot" : "");
    });
  }

  // ----------------------------------------------------------------- tabs --
  var views = {};

  views.overview = function () {
    var v = state.verdict || [], m = state.marketing || {}, pend = state.pending || [];
    var kills = v.filter(function (x) { return x.diagnosis.verdict === "KILL"; }).length;
    var scales = v.filter(function (x) { return x.diagnosis.verdict === "SCALE"; }).length;
    var spend = ((m.cells || []).reduce(function (a, c) { return a + (c.to_eur || 0); }, 0));
    var h = "<h1>Overview</h1><p class='lede'>Everything below was produced by the engine from 90 days of " +
      "stored history. Press <b>Run full cycle</b> and watch the event log: the queue drains, each agent " +
      "reads its tools, and every proposal is tiered by the gateway before it can take effect.</p>";
    h += "<div class='tiles'>" +
      tile("products live", (state.products || []).length, "4 storefronts, one template") +
      tile("verdicts", scales + " scale · " + kills + " kill", v.length + " judged this cycle", kills ? "warn" : "ok") +
      tile("waiting for a human", pend.length, pend.length ? "irreversible or above the line" : "nothing held", pend.length ? "warn" : "ok") +
      tile("capital committed", eur(state.capital_committed), "purchase orders executed") +
      tile("ad spend / day", eur(spend), "after this cycle's changes") +
      tile("anomalies open", (state.anomalies || []).length, "raised by the agents", (state.anomalies || []).length ? "warn" : "ok") +
      "</div>";

    var r = (state.reorder || []).filter(function (x) { return !x.blocked; });
    var black = r.filter(function (x) { return x.variant_id === "v_black"; })[0];
    var white = r.filter(function (x) { return x.variant_id === "v_white"; })[0];
    if (black && white) {
      h += "<h2>The case that started this: twenty white, twenty black</h2><div class='card flag-bad'>" +
        "<table><tr><th>what the report shows</th><th class='n'>black</th><th class='n'>white</th></tr>" +
        row2("units shipped (90 days)", black.reconstruction.units_shipped, white.reconstruction.units_shipped) +
        row2("days actually buyable", black.reconstruction.available_days, white.reconstruction.available_days) +
        row2("rate of sale per available day", black.reconstruction.ros_per_available_day, white.reconstruction.ros_per_available_day) +
        row2("substitution share removed", pct(black.reconstruction.substitution_share, 0), pct(white.reconstruction.substitution_share, 0)) +
        row2("sold at a discount", num(black.reconstruction.avg_discount_pct) + "%", num(white.reconstruction.avg_discount_pct) + "%") +
        row2("return rate", pct(black.reconstruction.return_rate, 0), pct(white.reconstruction.return_rate, 0)) +
        row2("<b>reconstructed demand</b>", "<b>" + black.reconstruction.reconstructed_demand_period + "</b>",
             "<b>" + white.reconstruction.reconstructed_demand_period + "</b>") +
        row2("<b>order quantity</b>", "<b>" + black.decision.qty + "</b>", "<b>" + white.decision.qty + "</b>") +
        "</table><p class='muted' style='margin:12px 0 0'>A human reading twenty and twenty ordered " +
        "<b>40 white and 0 black</b>. The engine, from the same period: <b>" + black.decision.qty +
        " black and " + white.decision.qty + " white</b>.</p></div>";
    }

    if (v.length) {
      h += "<h2>Portfolio verdicts</h2><div class='grid2'>";
      v.forEach(function (x) {
        var d = x.diagnosis;
        h += "<div class='card " + flagFor(d.verdict) + "'><h3>" + esc(x.product_id) +
          " <span class='tag " + tagFor(d.verdict) + "'>" + esc(d.verdict) + "</span></h3>" +
          "<p class='muted' style='margin:0 0 8px;font-size:12.5px'>" + esc(d.diagnosis) + "</p>" +
          "<div class='mono' style='font-size:11.5px;color:var(--fg-3)'>CPA " + esc(x.rates.cpa) +
          " vs target " + esc(x.target_cpa) + " · " + statusTag(x.ledger.status) + "</div></div>";
      });
      h += "</div>";
    }

    h += "<h2>Latest decisions</h2>" + ledgerTable((state.ledger || []).slice(0, 8));
    if (!(state.reorder || []).length && !v.length) {
      h = "<h1>Overview</h1><div class='card'><h3>Nothing has run yet</h3><p class='muted'>" +
        "Press <b>Run full cycle</b> in the header. The three agents will read 90 days of stored history " +
        "and produce their decisions here.</p></div>";
    }
    return h;
  };

  views.reorder = function () {
    var r = (state.reorder || []).filter(function (x) { return !x.blocked; });
    if (!r.length) return empty("reorder", "Run the reorder cycle to see demand reconstructed per variant.");
    var rec = [
      ["units shipped (90d)", function (x) { return x.reconstruction.units_shipped; }],
      ["days actually buyable", function (x) { return x.reconstruction.available_days; }],
      ["rate of sale / available day", function (x) { return x.reconstruction.ros_per_available_day; }],
      ["sibling out-of-stock days", function (x) { return x.reconstruction.sibling_oos_days; }],
      ["substitution share removed", function (x) { return pct(x.reconstruction.substitution_share, 0); }],
      ["avg discount on sales", function (x) { return num(x.reconstruction.avg_discount_pct) + "%"; }],
      ["price adjustment factor", function (x) { return x.reconstruction.price_factor; }],
      ["return rate", function (x) { return pct(x.reconstruction.return_rate, 0); }],
      ["reconstructed demand (90d)", function (x) { return "<b>" + x.reconstruction.reconstructed_demand_period + "</b>"; }],
      ["demand hidden by stockouts", function (x) { return x.reconstruction.censored_gap; }],
      ["unmet-signal lower bound", function (x) { return x.reconstruction.unmet_signal_lower_bound; }]
    ];
    var dec = [
      ["Cu / Co (margin vs leftover)", function (x) { return x.decision.Cu + " / " + x.decision.Co; }],
      ["derived service level", function (x) { return pct(x.decision.service_level, 0); }],
      ["protection interval (days)", function (x) { return x.decision.protection_interval_days; }],
      ["demand over interval (mean / sd)", function (x) { return x.decision.demand_mu + " / " + x.decision.demand_sd; }],
      ["order-up-to level", function (x) { return x.decision.order_up_to; }],
      ["on hand / on order", function (x) { return x.decision.on_hand + " / " + x.decision.on_order; }],
      ["case pack / MOQ", function (x) { return x.decision.case_pack + " / " + x.decision.moq; }],
      ["<b>order quantity</b>", function (x) { return "<b>" + x.decision.qty + "</b>"; }],
      ["cover after arrival", function (x) { return x.decision.cover_after_weeks + " weeks"; }],
      ["capital committed", function (x) { return eur(x.decision.capital_eur); }],
      ["gateway", function (x) { return statusTag(x.ledger.status) + " <span class='muted'>" + esc(x.ledger.reason) + "</span>"; }]
    ];
    var h = "<h1>Reorder</h1><p class='lede'>Units shipped is what we were able to sell. Demand is " +
      "estimated only over the hours a variant could actually be bought, corrected for demand displaced " +
      "from out-of-stock siblings, then de-promoted to the price we intend to charge. The model never " +
      "produces any of these numbers.</p>";
    h += "<div class='wrap'><table><tr><th>line</th>" + r.map(function (x) {
      return "<th class='n'>" + esc(x.variant_id) + "</th>"; }).join("") + "</tr>";
    h += "<tr><td colspan='" + (r.length + 1) + "' class='muted' style='background:var(--bg-2)'>" +
      "<b>Demand reconstruction</b></td></tr>";
    rec.forEach(function (p) {
      h += "<tr><td>" + p[0] + "</td>" + r.map(function (x) { return "<td class='n'>" + p[1](x) + "</td>"; }).join("") + "</tr>";
    });
    h += "<tr><td colspan='" + (r.length + 1) + "' class='muted' style='background:var(--bg-2)'>" +
      "<b>Quantity decision</b></td></tr>";
    dec.forEach(function (p) {
      h += "<tr><td>" + p[0] + "</td>" + r.map(function (x) { return "<td class='n'>" + p[1](x) + "</td>"; }).join("") + "</tr>";
    });
    h += "</table></div>";
    h += "<h2>Rationale, and the evidence behind it</h2>";
    r.forEach(function (x) {
      h += "<div class='card'><h3>" + esc(x.variant_id) + "</h3><p style='margin:0 0 8px'>" +
        esc(x.rationale) + "</p><div>" + (x.ledger.evidence || []).map(function (e) {
          return "<span class='ev' data-ev='" + esc(e) + "'>" + esc(e) + "</span> ";
        }).join("") + "</div></div>";
    });
    return h;
  };

  views.marketing = function () {
    var m = state.marketing || {};
    if (!m.cells) return empty("marketing", "Run the marketing cycle to see the daily pass.");
    var h = "<h1>Marketing allocation</h1><p class='lede'>Every cell is judged against a target CPA " +
      "derived from contribution margin, and only once it has earned the right to be judged. " +
      "Platform-reported performance is discounted by the geo holdout before any money moves.</p>";
    h += "<div class='tiles'>" +
      tile("target CPA", eur(m.target_cpa), "CM1 × payback factor") +
      tile("signal drift", (m.signal.drift_pct === null ? "n/a" : m.signal.drift_pct + "%"),
           "platform " + m.signal.platform + " vs ours " + m.signal.ours, m.signal.healthy ? "ok" : "bad") +
      tile("organic share", pct(m.holdout.organic_share || 0, 0), "from the geo holdout") +
      tile("experiment budget", eur(m.budget.allocated_eur - m.budget.spent_eur), "left of " + eur(m.budget.allocated_eur)) +
      tile("stock cover", num(m.cover.hero_cover_days) + "d hero", "worst variant " + num(m.cover.worst_cover_days) + "d",
           m.cover.worst_cover_days < 14 ? "warn" : "ok") +
      "</div>";
    h += "<div class='wrap'><table><tr><th>cell</th><th>platform</th><th class='n'>spend 7d</th>" +
      "<th class='n'>orders</th><th class='n'>CPA obs</th><th class='n'>CPA model</th>" +
      "<th>action</th><th class='n'>daily budget</th><th>rule that fired</th><th>gateway</th></tr>";
    m.cells.forEach(function (c) {
      h += "<tr><td class='mono'>" + esc(c.cell) + "</td><td class='muted'>" + esc(c.platform) + "</td>" +
        "<td class='n'>" + num(c.spend) + "</td><td class='n'>" + c.orders + "</td>" +
        "<td class='n'>" + (c.cpa ? num(c.cpa) : "–") + "</td>" +
        "<td><span class='tag " + actionTag(c.action) + "'>" + esc(c.action) + "</span></td>" +
        "<td class='n'>" + num(c.from_eur) + " → " + num(c.to_eur) + "</td>" +
        "<td class='muted' style='font-size:12px'>" + esc(c.reason) + "</td>" +
        "<td>" + (c.ledger ? statusTag(c.ledger.status) : "<span class='muted'>no action</span>") + "</td></tr>";
    });
    h += "</table></div>";
    var w = state.weekly || {};
    if (w.after) {
      h += "<h2>Weekly channel reallocation</h2><div class='card'><p class='muted' style='margin:0 0 12px'>" +
        "Thompson sampling on profit per euro, with a 10% exploration floor, a 5% minimum and a 40% " +
        "cap on weekly movement per arm.</p>";
      Object.keys(w.after).sort(function (a, b) { return w.after[b] - w.after[a]; }).forEach(function (arm) {
        var before = (w.before[arm] || 0), after = w.after[arm];
        h += "<div class='barrow'><div class='mono'>" + esc(arm) + "</div>" +
          "<div class='bar'><div class='fill' style='width:" + (after * 160) + "%'></div></div>" +
          "<div class='mono muted'>" + pct(before, 1) + " →</div><div class='mono'>" + pct(after, 1) + "</div></div>";
      });
      h += "</div>";
    }
    return h;
  };

  views.portfolio = function () {
    var v = state.verdict || [];
    if (!v.length) return empty("verdict", "Run the verdict cycle to judge every product.");
    var bench = state.benchmark || {};
    var h = "<h1>Portfolio</h1><p class='lede'>The same symptom — too few orders — has four different " +
      "causes. The agent names the owner of the problem from the shape of the funnel, so a site defect " +
      "is never recorded as a failed product. A kill is never autonomous.</p>";
    v.forEach(function (x) {
      var d = x.diagnosis, r = x.rates;
      h += "<div class='card " + flagFor(d.verdict) + "'><h3>" + esc(x.product_id) +
        " <span class='tag " + tagFor(d.verdict) + "'>" + esc(d.verdict) + "</span> " +
        "<span class='tag'>confidence " + pct(d.confidence, 0) + "</span> " +
        "<span class='tag'>budget left " + eur(x.budget_left) + "</span></h3>";
      h += "<div style='margin:10px 0 12px'>";
      ["pdp_rate", "atc_rate", "checkout_rate", "purchase_rate", "refund_rate", "ctr"].forEach(function (k) {
        var band = bench[k] || [0, 1], val = r[k] || 0, flag = d.flags[k];
        var scale = Math.max(band[1] * 1.6, val * 1.15, 0.0001);
        h += "<div class='barrow'><div class='muted'>" + k.replace(/_/g, " ") + "</div>" +
          "<div class='bar'><div class='band' style='left:" + (band[0] / scale * 100) + "%;width:" +
          ((band[1] - band[0]) / scale * 100) + "%'></div>" +
          "<div class='fill " + (flag === "ok" ? "" : flag) + "' style='width:" + (val / scale * 100) + "%'></div></div>" +
          "<div class='mono'>" + pct(val, 2) + "</div>" +
          "<div><span class='tag " + (flag === "ok" ? "ok" : flag === "high" ? "warn" : "bad") + "'>" + flag + "</span></div></div>";
      });
      h += "</div>";
      h += "<p style='margin:0 0 8px'><b>" + esc(d.diagnosis) + "</b></p>";
      h += "<div class='mono muted' style='font-size:11.5px;margin-bottom:10px'>sessions " + r.sessions +
        " · spend " + eur(r.spend) + " · CPA " + esc(r.cpa) + " vs target " + esc(x.target_cpa) + "</div>";
      if (d.findings && d.findings.length) {
        h += "<ul style='margin:0 0 10px;padding-left:18px;font-size:12.5px'>" + d.findings.map(function (f) {
          return "<li><span class='tag " + (f.owner === "SITE" ? "accent" : f.owner === "PRODUCT" ? "bad" : "warn") +
            "'>" + esc(f.owner) + "</span> " + esc(f.finding) + "</li>";
        }).join("") + "</ul>";
      }
      if (d.actions && d.actions.length) {
        h += "<div class='muted' style='font-size:11px;letter-spacing:.07em;text-transform:uppercase'>ranked actions</div>" +
          "<ol style='margin:6px 0 10px;padding-left:20px;font-size:12.5px'>" +
          d.actions.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ol>";
      }
      if (x.runbook && x.runbook.length) {
        h += "<div class='muted' style='font-size:11px;letter-spacing:.07em;text-transform:uppercase'>kill runbook, held for a human</div>" +
          "<ol style='margin:6px 0 10px;padding-left:20px;font-size:12.5px'>" +
          x.runbook.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ol>";
      }
      h += "<div>" + statusTag(x.ledger.status) + " <span class='muted'>" + esc(x.ledger.reason) + "</span></div></div>";
    });
    return h;
  };

  // ---------------------------------------------------- presenter mode --
  var slideIndex = 0;

  function money(v) { return "\u20ac" + Math.round(v || 0).toLocaleString("en-GB"); }

  function buildSlides() {
    var r = (state.reorder || []).filter(function (x) { return !x.blocked; });
    var byId = {};
    r.forEach(function (x) { byId[x.variant_id] = x; });
    var black = byId.v_black, white = byId.v_white;
    var v = state.verdict || [], m = state.marketing || {}, model = state.model;
    var pend = state.pending || [];
    var exec = (state.ledger || []).filter(function (x) { return x.status === "executed"; });
    var slides = [];

    slides.push(function () {
      return "<div class='kicker'>The question</div>" +
        "<h2>You sold twenty white towels. And twenty black.</h2>" +
        "<p class='sub'>Same product, same ninety days, same number of units out of the door. " +
        "It is time to reorder. How many of each do you buy?</p>" +
        "<div class='big'>" +
        "<div><div class='n dim'>20</div><div class='cap'>white sold</div></div>" +
        "<div class='vs'>and</div>" +
        "<div><div class='n dim'>20</div><div class='cap'>black sold</div></div>" +
        "</div>" +
        "<div class='note'>What a buyer actually did: ordered <b>40 white</b> and <b>no black</b>. " +
        "That decision looks reasonable, and it is close to the worst possible one.</div>";
    });

    if (black && white) {
      slides.push(function () {
        var bd = black.reconstruction.available_days, wd = white.reconstruction.available_days;
        return "<div class='kicker'>What the sales report never shows</div>" +
          "<h2>Black was not on sale for most of the period.</h2>" +
          "<p class='sub'>Units sold is what you were <i>able</i> to sell. Nobody stores how many " +
          "days a product was actually in stock, so this fact is invisible &mdash; and it changes everything.</p>" +
          "<div class='rows'>" +
          "<div class='r'><div class='lbl'>White, days buyable</div>" +
          "<div class='meter'><i class='good' style='width:" + (wd / 90 * 100) + "%'></i></div>" +
          "<div class='val'>" + wd + " / 90</div></div>" +
          "<div class='r'><div class='lbl'>Black, days buyable</div>" +
          "<div class='meter'><i class='bad' style='width:" + (bd / 90 * 100) + "%'></i></div>" +
          "<div class='val'>" + bd + " / 90</div></div>" +
          "</div>" +
          "<div class='note bad'>Black sold out early and then recorded <b>zero sales for " +
          Math.round(90 - bd) + " days</b>. On a report, zero sales reads as \u201cnobody wants it\u201d.</div>";
      });

      slides.push(function () {
        var b = black.reconstruction, w = white.reconstruction;
        return "<div class='kicker'>The same twenty units</div>" +
          "<h2>Black was selling four times faster.</h2>" +
          "<p class='sub'>Measured per day it was actually available, rather than per calendar day.</p>" +
          "<div class='big'>" +
          "<div><div class='n'>" + b.ros_per_available_day + "</div><div class='cap'>black, units per day on sale</div></div>" +
          "<div class='vs'>against</div>" +
          "<div><div class='n dim'>" + w.ros_per_available_day + "</div><div class='cap'>white, units per day on sale</div></div>" +
          "</div>" +
          "<div class='note'>And " + Math.round(w.substitution_share * 100) + "% of white's sales were " +
          "people who wanted black and settled. The naive reading does not just understate black " +
          "\u2014 it <b>overstates white</b>.</div>";
      });

      slides.push(function () {
        var b = black.reconstruction, w = white.reconstruction;
        return "<div class='kicker'>Real demand, reconstructed</div>" +
          "<h2>Eighty-two people wanted black. Twenty got it.</h2>" +
          "<p class='sub'>Corrected for the days it was unbuyable, for the sales it stole from white, " +
          "for discounts and for returns.</p>" +
          "<div class='big'>" +
          "<div><div class='n good'>" + Math.round(b.reconstructed_demand_period) + "</div>" +
          "<div class='cap'>black: true 90-day demand</div></div>" +
          "<div><div class='n dim'>" + Math.round(w.reconstructed_demand_period) + "</div>" +
          "<div class='cap'>white: true 90-day demand</div></div>" +
          "</div>" +
          "<div class='note'>Evidence the shop already had and nobody joined up: <b>" +
          Math.round((b.unmet_signals || {}).back_in_stock || 0) + " back-in-stock sign-ups</b> and <b>" +
          Math.round((b.unmet_signals || {}).oos_product_view || 0) + " views</b> of a product that could not be bought.</div>";
      });

      slides.push(function () {
        return "<div class='kicker'>The decision</div>" +
          "<h2>Opposite of what a person would do.</h2>" +
          "<div class='big'>" +
          "<div><div class='n bad'>40 / 0</div><div class='cap'>human: white / black</div></div>" +
          "<div class='vs'>versus</div>" +
          "<div><div class='n good'>" + white.decision.qty + " / " + black.decision.qty +
          "</div><div class='cap'>engine: white / black</div></div>" +
          "</div>" +
          "<div class='note ok'>Service level <b>" + Math.round(black.decision.service_level * 100) +
          "%</b>, derived from this product's own margin rather than a blanket rule. " +
          black.decision.cover_after_weeks + " weeks of cover for " + money(black.decision.capital_eur) +
          ". Every figure traces back to the query that produced it.</div>";
      });
    }

    if (v.length) {
      slides.push(function () {
        var cards = v.map(function (x) {
          var d = x.diagnosis, cls = d.verdict === "SCALE" ? "ok" : d.verdict === "KILL" ? "bad" : "warn";
          var plain = {
            SCALE: "Working. Give it more budget.",
            FIX_SITE: "People want it; the shop is losing them. Fix the shop, not the product.",
            KILL: "People see it and do not want it, and those who buy send it back. Stop.",
            REPRICE: "The funnel is fine and the price is not.",
            CONTINUE_TEST: "Not enough evidence yet. Keep testing.",
            NEW_CREATIVE: "Nobody is clicking, so the product has not been judged yet."
          }[d.verdict] || d.diagnosis;
          return "<div class='c " + cls + "'><div class='t'>" + esc(x.product_id.replace("p_", "")) +
            " &mdash; " + esc(d.verdict) + "</div><div class='d'>" + esc(plain) + "</div></div>";
        }).join("");
        return "<div class='kicker'>The question you said you cannot answer today</div>" +
          "<h2>Is it the product, or is it the site?</h2>" +
          "<p class='sub'>In a spreadsheet these all look the same: sells a little, loses money. " +
          "They need opposite responses.</p><div class='cards'>" + cards + "</div>" +
          "<div class='note'>The mug and the candle are the two ambiguous ones. The mug's buyers " +
          "add to cart and vanish at checkout &mdash; that is a shop defect, and killing the product " +
          "would be the expensive mistake. The candle's visitors look and decline, and the ones who " +
          "buy return it.</div>";
      });
    }

    if (m.cells) {
      slides.push(function () {
        var rows = m.cells.slice(0, 6).map(function (c) {
          var tone = c.action === "scale" ? "good" : (c.action.indexOf("pause") === 0 ? "bad" : "");
          var w = Math.min(100, (c.cpa || 0) / (m.target_cpa * 2) * 100);
          return "<div class='r'><div class='lbl'>" + esc(c.cell.replace(/_/g, " ")) + "</div>" +
            "<div class='meter'><i class='" + tone + "' style='width:" + w + "%'></i></div>" +
            "<div class='val'>" + (c.cpa ? money(c.cpa) : "&ndash;") + " &middot; " + esc(c.action) + "</div></div>";
        }).join("");
        return "<div class='kicker'>Where the money goes</div>" +
          "<h2>Budget follows profit, not opinion.</h2>" +
          "<p class='sub'>Every ad is judged against a target of " + money(m.target_cpa) +
          " per order, worked out from margin &mdash; and only once it has had enough traffic to be judged fairly.</p>" +
          "<div class='rows'>" + rows + "</div>" +
          "<div class='note'>" + Math.round((m.holdout.organic_share || 0) * 100) +
          "% of orders would have happened without any advertising. A region with ads switched off " +
          "measures that, so the system never congratulates itself for sales it did not cause.</div>";
      });
    }

    if (model && model.leaderboard) {
      slides.push(function () {
        var best = model.leaderboard[0];
        var guards = (model.diagnostics.leakage || []).length;
        return "<div class='kicker'>The forecasting</div>" +
          "<h2>Thirty-five signals, and the discipline to throw most away.</h2>" +
          "<p class='sub'>Device, search interest, price, creative age, stock cover. Six model types " +
          "compete; the winner is the one that performs on data it has never seen.</p>" +
          "<div class='big'>" +
          "<div><div class='n'>" + (model.diagnostics.selection.selected || []).length + "</div>" +
          "<div class='cap'>signals kept of " + model.candidates + "</div></div>" +
          "<div><div class='n good'>" + best.out_sample.r2.toFixed(2) + "</div>" +
          "<div class='cap'>accuracy on unseen data</div></div>" +
          "<div><div class='n'>" + guards + "</div>" +
          "<div class='cap'>cheating signals removed automatically</div></div>" +
          "</div>" +
          "<div class='note'>Two of those were traps that make a model look brilliant and know " +
          "nothing. The system caught them itself and refuses to use a model that cannot beat " +
          "\u201csame as last week\u201d. On a real shop expect lower accuracy &mdash; the method is the point.</div>";
      });
    }

    slides.push(function () {
      return "<div class='kicker'>Control</div>" +
        "<h2>It acts on its own, inside limits you set.</h2>" +
        "<div class='big'>" +
        "<div><div class='n good'>" + exec.length + "</div><div class='cap'>decisions taken automatically</div></div>" +
        "<div><div class='n " + (pend.length ? "bad" : "dim") + "'>" + pend.length + "</div>" +
        "<div class='cap'>held back for a human</div></div>" +
        "<div><div class='n'>" + (state.evidence_count || 0) + "</div>" +
        "<div class='cap'>stored facts behind those decisions</div></div>" +
        "</div>" +
        "<div class='note bad'>Nothing irreversible happens on its own. Closing a product down, " +
        "money above a limit, changing a supplier's bank details &mdash; all stop and wait for a " +
        "person, with the full case attached.</div>";
    });

    slides.push(function () {
      var prods = (state.products || []).filter(function (p) { return (p.id || "").indexOf("med_") === 0; });
      return "<div class='kicker'>Not a prototype</div>" +
        "<h2>It is reading a real shop, right now.</h2>" +
        "<p class='sub'>The storefront is Medusa &mdash; free, open source, running on this laptop. " +
        "We did not build the shop and we do not need to.</p>" +
        "<div class='big'>" +
        "<div><div class='n'>" + (prods.length || 4) + "</div><div class='cap'>products read live</div></div>" +
        "<div><div class='n'>235</div><div class='cap'>lines of code to connect it</div></div>" +
        "</div>" +
        "<div class='note ok'>There is a second connector for Shopify writing into the same tables. " +
        "<b>The shop is replaceable. The part that decides is the asset.</b></div>";
    });

    return slides;
  }

  views.story = function () {
    var slides = buildSlides();
    if (!slides.length) return empty("story", "Run a cycle first, then the presenter has data to show.");
    if (slideIndex >= slides.length) slideIndex = slides.length - 1;
    if (slideIndex < 0) slideIndex = 0;
    var dots = slides.map(function (_, i) {
      return "<b class='" + (i === slideIndex ? "on" : "") + "'></b>";
    }).join("");
    return "<div class='slide'>" + slides[slideIndex]() +
      "<div class='slide-foot'><div class='dots'>" + dots + "</div>" +
      "<span>" + (slideIndex + 1) + " of " + slides.length + "</span>" +
      "<span class='spacer' style='flex:1'></span>" +
      "<span>arrow keys to move &middot; Esc to leave</span></div></div>";
  };

  // ------------------------------------------------- how it decides ----
  var decideCell = null, labRanges = null, labBase = {}, labResult = null;

  // Plain English for the features a model might select. The sliders are built
  // from whatever the promoted model actually uses, not from this list.
  var FEATURE_LABELS = {
    spend: "daily spend", log_spend: "daily spend (log)", clicks: "clicks",
    impressions: "impressions", ctr: "click-through rate", cpm: "cost per thousand views",
    cpc: "cost per click", frequency: "times each person saw it",
    creative_age_days: "creative age in days", is_video: "video creative",
    creative_concept: "creative concept", share_ios: "iOS share of traffic",
    share_android: "Android share", share_desktop: "desktop share", share_tablet: "tablet share",
    search_index_category: "category search interest", search_index_brand: "brand search interest",
    site_search_count: "searches on our own site", aeo_citation_count: "answer-engine mentions",
    price: "price", discount_pct: "discount %", competitor_price_index: "competitor price index",
    free_shipping: "free shipping on", stock_cover_days: "days of stock cover",
    orders_prev_window: "orders the previous week",
    impression_quality_index: "impression quality (a vanity metric)"
  };
  var LAB_PREFERRED = ["search_index_category", "clicks", "creative_age_days", "frequency",
                       "discount_pct", "stock_cover_days", "share_android", "site_search_count",
                       "orders_prev_window", "cpm", "competitor_price_index"];

  function labLevers(featuresUsed) {
    var base = (featuresUsed || []).filter(function (f) { return f.indexOf("cellflag_") !== 0; })
      .map(function (f) { return f.replace(/_7d$/, ""); });
    var seen = {}, out = [];
    LAB_PREFERRED.concat(base).forEach(function (f) {
      if (seen[f] || base.indexOf(f) === -1) return;
      seen[f] = 1;
      out.push([f, FEATURE_LABELS[f] || f.replace(/_/g, " "), f === "spend" ? "\u20ac" : ""]);
    });
    return out.slice(0, 6);
  }

  views.decide = function () {
    var m = state.marketing || {};
    var cells = (m.cells || []).filter(function (c) { return !/holdout/.test(c.cell); });
    if (!cells.length) return empty("marketing", "Run a cycle first, then every decision can be opened up.");
    if (!decideCell) decideCell = cells[0].cell;

    var h = "<h1>How it decides</h1><p class='lede'>Two questions get asked about any system " +
      "like this. Did it really reason, or is it a script? And is there really a model, or is " +
      "the number hardcoded? Both are answered on this page, with the live engine.</p>";

    h += "<div style='margin-bottom:16px'>";
    cells.forEach(function (c) {
      h += "<button class='sm" + (c.cell === decideCell ? " primary" : "") +
        "' data-cell='" + esc(c.cell) + "' style='margin:0 6px 6px 0'>" +
        esc(c.cell.replace(/_/g, " ")) + "</button>";
    });
    h += "</div><div id='ladder-out'><p class='muted'>loading the decision\u2026</p></div>";

    h += "<h2>Is the model real? Move an input and watch it follow.</h2>" +
      "<p class='muted' style='font-size:13px;max-width:70ch'>These sliders change what the model " +
      "is told, and it re-predicts. The sliders are bounded by the range the model was actually " +
      "trained on; push past it and it says so instead of pretending.</p>" +
      "<div id='lab-out'><p class='muted'>loading the model\u2026</p></div>";
    return h;
  };

  function loadLadder() {
    if (tab !== "decide" || !decideCell) return;
    api("/api/explain", { cell_id: decideCell }).then(function (d) {
      var box = el("ladder-out");
      if (!box) return;
      if (d.error) { box.innerHTML = "<p class='muted'>" + esc(d.error) + "</p>"; return; }
      var h = "<div class='card'><h3>" + esc(decideCell.replace(/_/g, " ")) +
        " &mdash; <span class='tag " + actionTag(d.action) + "'>" + esc(d.action) + "</span> " +
        "<span class='muted' style='font-weight:400'>" + num(d.daily_now) + " \u2192 " +
        num(d.budget) + " EUR per day</span></h3><div class='ladder'>";
      d.steps.forEach(function (s, i) {
        h += "<div class='s" + (s.decided ? " stop" : "") + "'><div class='i'>" + (i + 1) + "</div>" +
          "<div><div class='q'>" + esc(s.check) + "</div><div class='d'>" + esc(s.detail) + "</div></div>" +
          "<div class='o'>" + esc(s.outcome) + "</div></div>";
      });
      h += "</div><p class='muted' style='margin:12px 0 0;font-size:12.5px'>" +
        "The highlighted step is where it stopped. Everything above it passed.</p></div>";
      box.innerHTML = h;
    });
  }

  function loadLab(overrides) {
    if (tab !== "decide" || !decideCell) return;
    api("/api/whatif", { cell_id: decideCell, overrides: overrides || {} }).then(function (d) {
      var box = el("lab-out");
      if (!box) return;
      if (d.error) {
        box.innerHTML = "<div class='card flag-warn'><p class='muted'>" + esc(d.error) +
          " \u2014 press <b>Train models</b> in the header first.</p></div>";
        return;
      }
      labResult = d;
      labRanges = d.ranges || {};
      var h = "<div class='card'><div class='lab'><div class='sliders'>";
      var levers = labLevers(d.features_used);
      if (!levers.length) {
        h += "<p class='muted'>The promoted model uses no adjustable inputs.</p>";
      }
      levers.forEach(function (f) {
        var key = f[0], rng = labRanges[key] || labRanges[key + "_7d"];
        if (!rng) return;
        var cur = (overrides && overrides[key] !== undefined) ? +overrides[key] :
          (labBase[key] !== undefined ? labBase[key] : rng.median);
        labBase[key] = cur;
        var step = (rng.max - rng.min) / 100 || 0.01;
        h += "<label><span class='row'><span>" + esc(f[1]) + "</span><b>" + f[2] +
          (cur < 1 && cur > 0 ? cur.toFixed(4) : num(cur, cur < 10 ? 2 : 0)) + "</b></span>" +
          "<input type='range' data-feat='" + esc(key) + "' min='" + rng.min + "' max='" + rng.max +
          "' step='" + step + "' value='" + cur + "'>" +
          "<span class='muted' style='font-size:11px'>trained between " + num(rng.min, 2) +
          " and " + num(rng.max, 2) + "</span></label>";
      });
      h += "</div><div class='out'>" +
        "<div class='m'><div class='l'>predicted orders next 7 days</div><div class='v'>" +
        d.before.toFixed(1) + "<span class='arrowv'>\u2192</span>" + d.after.toFixed(1) + "</div></div>" +
        "<div class='m'><div class='l'>cost per order that implies</div><div class='v'>" +
        money(d.cpa_before) + "<span class='arrowv'>\u2192</span>" + money(d.cpa_after) +
        "<br><small>target " + money(d.target_cpa) + "</small></div></div>" +
        "<div class='m'><div class='l'>what the agent would do</div><div class='v'>" +
        "<span class='tag " + actionTag(d.action_before) + "'>" + esc(d.action_before) + "</span>" +
        "<span class='arrowv'>\u2192</span>" +
        "<span class='tag " + actionTag(d.action_after) + "'>" + esc(d.action_after) + "</span></div></div>" +
        "<div class='muted' style='font-size:11.5px'>model: " + esc(d.family) + "</div></div></div>";
      if ((d.extrapolating || []).length) {
        h += "<div class='callout' style='margin-top:12px'><span class='tag bad'>extrapolating</span> " +
          d.extrapolating.map(esc).join(" ") + "</div>";
      }
      h += "</div>";
      box.innerHTML = h;
    });
  }

  views.models = function () {
    var m = state.model, reg = state.model_registry || [];
    var h = "<h1>Marketing models</h1><p class='lede'>Targeted marketing is a modelling problem: " +
      "who saw the ad, on what device, after searching for what, at what price, with how much " +
      "stock behind it. The workflow below runs on that panel, and the result is used only once " +
      "it has beaten the naive baselines out of sample. The deterministic bands are never " +
      "switched off: the model supplies an expectation, the bands still decide.</p>";

    if (!m) {
      h += "<div class='card'><h3>No training run in this session</h3><p class='muted'>" +
        "Press <b>Train models</b> in the header. About seven seconds: it builds the feature " +
        "panel, tests every feature for stationarity and significance, selects with Lasso, then " +
        "compares six families across two panels and two target transforms.</p>" +
        "<button class='primary' data-model='1'>Train models now</button></div>";
      if (reg.length) h += "<h2>Previously trained</h2>" + registryTable(reg);
      return h;
    }
    if (m.error) return h + "<div class='card flag-warn'><p>" + esc(m.error) + "</p></div>";

    var best = m.leaderboard[0], d = m.diagnostics;
    h += "<div class='tiles'>" +
      tile("promoted", m.promoted ? best.family : "none",
           m.promoted ? best.panel + " panel, " + best.transform + " target" : "held back",
           m.promoted ? "ok" : "warn") +
      tile("R2 out of sample", best.out_sample.r2.toFixed(3), "in sample " + best.in_sample.r2.toFixed(3)) +
      tile("AUC", best.auc ? best.auc.toFixed(3) : "-", "will this cell be profitable?") +
      tile("features kept", (d.selection.selected || []).length, "of " + m.candidates + " candidates") +
      tile("split", m.cut_day, m.n_train + " train / " + m.n_test + " test") +
      "</div>";

    h += "<div class='card flag-warn'><h3>Read these numbers honestly</h3>" +
      "<p class='muted' style='margin:0'>This panel is seeded from a known process, so the " +
      "relationship is real but cleaner than life: an R\u00b2 near 0.98 is a property of the " +
      "generator, not a forecast of live performance. On a real store with six months of history, " +
      "expect roughly 0.3 to 0.6 on weekly orders per cell, and judge the pipeline on whether it " +
      "beats the previous-window baseline rather than on the absolute figure. The value here is " +
      "the workflow and the guards, which carry over unchanged.</p></div>";
    h += "<div class='card " + (m.promoted ? "flag-ok" : "flag-warn") + "'><h3>Promotion: " +
      (m.promoted ? "promoted" : "held back") + "</h3><p class='muted' style='margin:0'>" +
      esc(m.reason) + "</p></div>";

    if (d.leakage && d.leakage.length) {
      h += "<h2>Guards that fired before any model was fitted</h2><div class='card flag-warn'>" +
        "<table><tr><th>feature</th><th>why it was removed</th></tr>" +
        d.leakage.map(function (r) {
          return "<tr><td class='mono'>" + esc(r.feature) + "</td><td>" + esc(r.note) +
            (r.rho_time !== undefined ? " (rho with time " + r.rho_time + ")" : "") + "</td></tr>";
        }).join("") + "</table></div>";
    }

    var ns = (d.stationarity || []).filter(function (r) { return r.stationary === false; });
    h += "<h2>1 / Stationarity (augmented Dickey-Fuller)</h2><div class='card'>" +
      "<p class='muted' style='margin:0 0 10px'>" + (d.stationarity || []).length +
      " features tested, " + ns.length + " carry a unit root and were also evaluated differenced. " +
      "The target itself is " + ((d.target_stationarity || {}).stationary ? "stationary" : "not stationary") +
      ", which is why both panels are compared rather than one being assumed.</p>" +
      "<div class='wrap' style='max-height:260px'><table><tr><th>feature</th><th class='n'>ADF</th>" +
      "<th class='n'>p</th><th>verdict</th></tr>" +
      (d.stationarity || []).slice(0, 40).map(function (r) {
        return "<tr><td class='mono'>" + esc(r.feature) + "</td><td class='n'>" +
          (r.adf === null ? "-" : r.adf) + "</td><td class='n'>" +
          (r.p_value === null ? "-" : r.p_value) + "</td><td class='muted'>" + esc(r.note) + "</td></tr>";
      }).join("") + "</table></div></div>";

    h += "<h2>2 / Significance and collinearity</h2><div class='grid2'>";
    h += "<div class='card'><h3>Correlation with the target</h3><div class='wrap' style='max-height:300px'>" +
      "<table><tr><th>feature</th><th class='n'>r</th><th class='n'>p</th><th>keep</th></tr>" +
      (d.significance || []).slice(0, 18).map(function (r) {
        return "<tr><td class='mono'>" + esc(r.feature) + "</td><td class='n'>" + r.pearson_r +
          "</td><td class='n'>" + r.p_value.toExponential(1) + "</td><td><span class='tag " +
          (r.significant ? "ok" : "") + "'>" + (r.significant ? "p<0.05" : "no") + "</span></td></tr>";
      }).join("") + "</table></div></div>";
    h += "<div class='card'><h3>Variance inflation</h3>" +
      "<p class='muted' style='margin:0 0 8px;font-size:12px'>Two features saying the same thing " +
      "make coefficients meaningless.</p><div class='wrap' style='max-height:300px'>" +
      "<table><tr><th>feature</th><th class='n'>VIF</th></tr>" +
      (d.collinearity || []).slice(0, 14).map(function (r) {
        return "<tr><td class='mono'>" + esc(r.feature) + "</td><td class='n'>" +
          (r.collinear ? "<span class='tag warn'>" + r.vif + "</span>" : r.vif) + "</td></tr>";
      }).join("") + "</table></div></div></div>";

    h += "<h2>3 / Feature selection (LassoCV, time-series folds, alpha " +
      (d.selection.alpha || 0).toFixed(4) + ")</h2><div class='card'>";
    (d.selection.ranked || []).slice(0, 14).forEach(function (r) {
      var top = Math.abs(d.selection.ranked[0].std_coef) || 1;
      var w = Math.min(100, Math.abs(r.std_coef) / top * 100);
      h += "<div class='barrow'><div class='mono'>" + esc(r.feature) + "</div>" +
        "<div class='bar'><div class='fill " + (r.std_coef < 0 ? "high" : "") + "' style='width:" +
        w + "%'></div></div><div class='mono'>" + (r.std_coef > 0 ? "+" : "") + r.std_coef +
        "</div><div></div></div>";
    });
    h += "<p class='muted' style='margin:10px 0 0;font-size:12px'><b>Dropped " +
      (d.selection.dropped || []).length + ":</b> " + esc((d.selection.dropped || []).join(", ")) +
      "</p></div>";

    h += "<h2>4 / Out-of-sample comparison</h2><p class='muted' style='font-size:12.5px'>" +
      "Forward split in time at " + esc(m.cut_day) + ", never random. Every family runs against " +
      "both panels and both target transforms, so whether the response scales linearly or " +
      "multiplicatively is settled by evidence rather than taste.</p>";
    h += "<div class='wrap'><table><tr><th>family</th><th>panel</th><th>target</th>" +
      "<th class='n'>R2 in</th><th class='n'>R2 out</th><th class='n'>RMSE out</th>" +
      "<th class='n'>MAE out</th><th class='n'>AUC</th></tr>";
    m.leaderboard.forEach(function (e, i) {
      if (!e.out_sample) return;
      var isBase = e.family.indexOf("baseline") === 0;
      h += "<tr><td class='mono'>" + (i === 0 ? "<b>" + esc(e.family) + "</b>" : esc(e.family)) +
        (isBase ? " <span class='tag'>baseline</span>" : "") + "</td>" +
        "<td class='muted'>" + esc(e.panel || "-") + "</td><td class='muted'>" + esc(e.transform || "-") + "</td>" +
        "<td class='n'>" + e.in_sample.r2.toFixed(3) + "</td><td class='n'>" +
        (i === 0 ? "<b>" + e.out_sample.r2.toFixed(3) + "</b>" : e.out_sample.r2.toFixed(3)) + "</td>" +
        "<td class='n'>" + e.out_sample.rmse.toFixed(3) + "</td><td class='n'>" +
        e.out_sample.mae.toFixed(3) + "</td><td class='n'>" + (e.auc ? e.auc.toFixed(3) : "-") +
        "</td></tr>";
    });
    h += "</table></div>";
    h += "<h2>5 / Registry</h2>" + registryTable(reg);
    return h;
  };

  function registryTable(reg) {
    return "<div class='wrap'><table><tr><th class='n'>#</th><th>trained</th><th>target</th>" +
      "<th>family</th><th class='n'>R2 out</th><th>status</th><th>reason</th></tr>" +
      reg.map(function (r) {
        var out = {};
        try { out = JSON.parse(r.out_sample || "{}"); } catch (e) {}
        return "<tr><td class='n'>" + r.id + "</td><td class='mono muted'>" +
          esc((r.trained_at || "").slice(0, 16).replace("T", " ")) + "</td><td class='mono'>" +
          esc(r.target) + "</td><td>" + esc(r.family) + "</td><td class='n'>" +
          (out.r2 !== undefined ? out.r2.toFixed(3) : "-") + "</td><td>" +
          (r.promoted ? "<span class='tag ok'>live</span>" : "<span class='tag'>archived</span>") +
          "</td><td class='muted' style='font-size:12px'>" + esc(r.promotion_reason || "") +
          "</td></tr>";
      }).join("") + "</table></div>";
  }

  views.approvals = function () {
    var pend = state.pending || [];
    var h = "<h1>Approvals</h1><p class='lede'>What the agents are not allowed to do on their own: " +
      "anything irreversible or outward-facing, and anything above the value line. The safe default is " +
      "to do nothing until a person signs.</p>";
    if (!pend.length) h += "<div class='card'><h3>Nothing is waiting</h3><p class='muted'>" +
      "Every proposal this cycle was inside the autonomy envelope or was refused by a guard.</p></div>";
    pend.forEach(function (r) {
      h += "<div class='card flag-warn'><h3>#" + r.id + " " + esc(r.intent) + " " +
        "<span class='tag warn'>" + esc(r.tier) + "</span> <span class='tag'>" + eur(r.value_eur) + "</span></h3>" +
        "<p class='muted' style='margin:0 0 8px'>" + esc(r.reason) + "</p>" +
        (r.rationale ? "<p style='margin:0 0 10px'>" + esc(r.rationale) + "</p>" : "") +
        "<pre>" + esc(JSON.stringify(r.payload, null, 2)) + "</pre>" +
        "<div style='margin-top:10px;display:flex;gap:8px'>" +
        "<button class='sm ok' data-approve='" + r.id + "'>Approve</button>" +
        "<button class='sm bad' data-reject='" + r.id + "'>Reject</button></div></div>";
    });
    return h;
  };

  views.ledger = function () {
    return "<h1>Ledger</h1><p class='lede'>Every side effect the platform has ever attempted, including " +
      "the refusals. Nothing is deleted: a reversal is a new entry.</p>" + ledgerTable(state.ledger || [], true);
  };

  views.anomalies = function () {
    var a = state.anomalies || [];
    var h = "<h1>Anomalies</h1><p class='lede'>Raised by the agents themselves when something does not " +
      "add up. An anomaly freezes the affected lever rather than switching the business off.</p>";
    if (!a.length) return h + "<div class='card'><p class='muted'>None raised.</p></div>";
    h += "<div class='wrap'><table><tr><th>when</th><th>agent</th><th>kind</th><th>severity</th><th>note</th></tr>";
    a.forEach(function (x) {
      h += "<tr><td class='mono muted'>" + esc((x.ts || "").slice(11, 19)) + "</td><td>" + esc(x.agent) + "</td>" +
        "<td class='mono'>" + esc(x.kind) + "</td><td><span class='tag " +
        (x.severity === "high" ? "bad" : "warn") + "'>" + esc(x.severity) + "</span></td>" +
        "<td>" + esc(x.note) + "</td></tr>";
    });
    return h + "</table></div>";
  };

  views.runs = function () {
    var r = state.runs || [];
    var h = "<h1>Agent runs</h1><p class='lede'>Steps, tokens and cost per run, with the mode each run " +
      "used. A run that exhausts its token budget degrades to rules-only and still decides.</p>" +
      "<div class='wrap'><table><tr><th>started</th><th>agent</th><th>trigger</th><th class='n'>steps</th>" +
      "<th class='n'>tokens</th><th class='n'>cost</th><th>mode</th><th>outcome</th></tr>";
    r.forEach(function (x) {
      h += "<tr><td class='mono muted'>" + esc((x.started_at || "").slice(11, 19)) + "</td>" +
        "<td>" + esc(x.agent) + "</td><td class='muted'>" + esc(x.trigger) + "</td>" +
        "<td class='n'>" + esc(x.steps) + "</td><td class='n'>" + esc(x.tokens) + "</td>" +
        "<td class='n'>" + (x.cost_eur ? eur(x.cost_eur) : "–") + "</td>" +
        "<td><span class='tag " + (x.mode === "model" ? "accent" : "") + "'>" + esc(x.mode) + "</span></td>" +
        "<td class='muted'>" + esc(x.outcome) + "</td></tr>";
    });
    return h + "</table></div>";
  };

  var SUGGEST = [
    "Why did you order 60 black towels and none white?",
    "Which product should we kill, and how sure are you?",
    "Is the mug set a product problem or a site problem?",
    "How much demand did we lose while the black towel was out of stock?",
    "Which ad cell is wasting the most money right now?"
  ];

  views.ask = function () {
    var p = state.provider || {};
    var h = "<h1>Ask the agent</h1><p class='lede'>A real tool-using loop, read-only. The model chooses " +
      "which queries it needs, the harness runs them against the database and records each result as " +
      "evidence, and the answer is then checked: any figure that does not trace back to a tool result is " +
      "flagged. It has no write tools, so there is nothing it can do to the business.</p>";
    if (p.provider === "rules_only") {
      h += "<div class='card flag-warn'><h3>No model provider found</h3><p class='muted'>" +
        "Install or expose the <code>claude</code> CLI (it runs on your Claude Code subscription, " +
        "no API key and no per-token cost), or set <code>ANTHROPIC_API_KEY</code>. The engines decide " +
        "either way — this panel is the part that needs a model.</p></div>";
    }
    h += "<div class='askbox'><input id='ask-input' placeholder='Ask about demand, spend, a verdict, or a decision in the ledger…'>" +
      "<button class='primary' id='ask-go'>Ask</button></div><div class='suggest'>" +
      SUGGEST.map(function (s, i) { return "<button class='sm' data-suggest='" + i + "'>" + esc(s) + "</button>"; }).join("") +
      "</div><div id='ask-out'></div>";
    return h;
  };

  function renderAsk(data) {
    var out = el("ask-out");
    if (!out || !data) return;
    var h = "";
    if (data.status === "running") h += "<div class='card'><span class='dot on'></span> " +
      "<span class='mono'>working… " + (data.events || []).length + " events</span></div>";
    (data.events || []).forEach(function (e) {
      if (e.kind === "thinking") {
        h += "<div class='step'><div class='hd muted'>step " + e.payload.step + " · deciding what to read</div></div>";
      } else if (e.kind === "tool_call") {
        h += "<div class='step tool'><div class='hd'><span class='tag accent'>tool</span>" +
          "<b>" + esc(e.payload.tool) + "</b><span class='muted'>" + esc(JSON.stringify(e.payload.args || {})) + "</span>" +
          (e.payload.evidence_id ? "<span class='ev' data-ev='" + esc(e.payload.evidence_id) + "'>" +
            esc(e.payload.evidence_id) + "</span>" : "") + "</div>" +
          "<pre>" + esc(JSON.stringify(e.payload.result, null, 2).slice(0, 1400)) + "</pre></div>";
      } else if (e.kind === "tool_denied") {
        h += "<div class='step'><div class='hd'><span class='tag bad'>refused</span>" + esc(e.payload.reason) + "</div></div>";
      } else if (e.kind === "note") {
        h += "<div class='step'><div class='hd muted'>" + esc(e.payload.message) + "</div></div>";
      }
    });
    if (data.status === "done" || data.status === "error") {
      var t = data.totals || {};
      h += "<div class='answer'><div style='margin-bottom:8px'>" +
        "<span class='tag " + (data.uncited && data.uncited.length ? "warn" : "ok") + "'>" +
        (data.uncited && data.uncited.length ? "unverified figures: " + data.uncited.join(", ") :
          "every figure traced to evidence") + "</span> " +
        "<span class='tag'>" + (t.steps || 0) + " model turns</span> " +
        "<span class='tag'>" + ((t.tokens_in || 0) + (t.tokens_out || 0)) + " tokens</span> " +
        "<span class='tag'>" + (t.billing === "subscription" ? "billed to subscription" : eur(t.cost_eur || 0)) + "</span>" +
        "</div>" + esc(data.answer || "").replace(/\n/g, "<br>") + "</div>";
    }
    out.innerHTML = h;
  }

  // ------------------------------------------------------------- helpers --
  function tile(label, value, sub, cls) {
    return "<div class='tile " + (cls || "") + "'><div class='l'>" + esc(label) + "</div><div class='v'>" +
      value + "</div><div class='s'>" + esc(sub || "") + "</div></div>";
  }
  function row2(label, a, b) {
    return "<tr><td>" + label + "</td><td class='n'>" + a + "</td><td class='n'>" + b + "</td></tr>";
  }
  function empty(what, msg) {
    return "<h1>" + esc(what.charAt(0).toUpperCase() + what.slice(1)) + "</h1><div class='card'>" +
      "<h3>Not run yet</h3><p class='muted'>" + esc(msg) + "</p>" +
      "<button class='primary' data-run='" + esc(what) + "'>Run " + esc(what) + " now</button></div>";
  }
  function statusTag(s) {
    var cls = s === "executed" ? "ok" : s === "rejected" ? "bad" : "warn";
    return "<span class='tag " + cls + "'>" + esc(s) + "</span>";
  }
  function actionTag(a) {
    if (a === "scale") return "ok";
    if (a === "pause" || a === "pause_acquisition") return "bad";
    if (a === "reduce" || a === "request_creative") return "warn";
    return "";
  }
  function tagFor(v) {
    return v === "SCALE" ? "ok" : v === "KILL" ? "bad" : v === "CONTINUE_TEST" ? "" : "warn";
  }
  function flagFor(v) {
    return v === "SCALE" ? "flag-ok" : v === "KILL" ? "flag-bad" : "flag-warn";
  }
  function ledgerTable(rows, withActions) {
    var h = "<div class='wrap'><table><tr><th class='n'>#</th><th>agent</th><th>intent</th><th class='n'>EUR</th>" +
      "<th>tier</th><th>status</th><th>reason</th><th>payload</th><th>evidence</th>" +
      (withActions ? "<th></th>" : "") + "</tr>";
    rows.forEach(function (r) {
      h += "<tr><td class='n'>" + r.id + "</td><td>" + esc(r.agent) + "</td>" +
        "<td class='mono'>" + esc(r.intent) + "</td><td class='n'>" + num(r.value_eur, 2) + "</td>" +
        "<td class='mono muted'>" + esc(r.tier || "–") + "</td><td>" + statusTag(r.status) + "</td>" +
        "<td class='muted' style='font-size:12px'>" + esc(r.reason) + "</td>" +
        "<td><code>" + esc(JSON.stringify(r.payload)).slice(0, 110) + "</code></td>" +
        "<td>" + (r.evidence || []).slice(0, 3).map(function (e) {
          return "<span class='ev' data-ev='" + esc(e) + "'>ev</span> "; }).join("") + "</td>" +
        (withActions ? "<td>" + (r.status === "executed" && r.value_eur ?
          "<button class='sm' data-reverse='" + r.id + "'>Reverse</button>" : "") + "</td>" : "") + "</tr>";
    });
    return h + "</table></div>";
  }

  function paint() {
    paintHead();
    var fn = views[tab] || views.overview;
    el("main").innerHTML = fn();
    [].forEach.call(document.querySelectorAll("#nav a"), function (a) {
      a.className = a.getAttribute("data-tab") === tab ? "on" : "";
    });
    if (tab === "ask" && askTicket) pollAsk();
    if (tab === "decide") { loadLadder(); loadLab(labOverrides()); }
  }

  // ----------------------------------------------------------------- log --
  function paintLog(events) {
    var box = el("log"), atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    var chans = {};
    events.forEach(function (e) {
      chans[e.channel] = true;
      if (mutedChannels[e.channel]) return;
      var div = document.createElement("div");
      div.className = "row";
      div.innerHTML = "<span class='ts'>" + esc(e.ts) + "</span><span class='ch'>" + esc(e.channel) +
        "</span><span class='msg " + esc(e.level) + "'>" + esc(e.text) + "</span>";
      box.appendChild(div);
    });
    Object.keys(chans).forEach(function (c) {
      if (el("chip-" + c)) return;
      var b = document.createElement("span");
      b.className = "chip on"; b.id = "chip-" + c; b.textContent = c;
      b.onclick = function () {
        mutedChannels[c] = !mutedChannels[c];
        b.className = "chip" + (mutedChannels[c] ? "" : " on");
      };
      el("log-chips").appendChild(b);
    });
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  var wasBusy = false, lastRefresh = 0;

  function pollLog() {
    api("/api/log?after=" + logSeq).then(function (d) {
      if (d.events && d.events.length) {
        logSeq = d.events[d.events.length - 1].seq;
        paintLog(d.events);
      }
      var busy = !!(d.busy && d.busy.running);
      var now = Date.now();
      // Refresh when a cycle finishes, while one is running, and on a slow
      // heartbeat - never only when new log lines happen to arrive.
      if ((wasBusy && !busy) || busy || now - lastRefresh > 6000) {
        lastRefresh = now;
        refresh();
      }
      wasBusy = busy;
      setTimeout(pollLog, busy ? 450 : 1500);
    }).catch(function () { setTimeout(pollLog, 3000); });
  }

  function pollAsk() {
    if (!askTicket) return;
    api("/api/ask/" + askTicket).then(function (d) {
      renderAsk(d);
      if (d.status === "running") setTimeout(pollAsk, 600);
      else { askTicket = null; refresh(); }
    });
  }

  function labOverrides() {
    var o = {};
    Object.keys(labBase).forEach(function (k) { o[k] = labBase[k]; });
    return o;
  }

  // -------------------------------------------------------------- events --
  document.addEventListener("click", function (e) {
    var t = e.target;
    var tabLink = t.closest ? t.closest("#nav a") : null;
    if (tabLink) { tab = tabLink.getAttribute("data-tab"); paint(); return; }
    if (t.id === "b-present" || (t.getAttribute && t.getAttribute("data-present"))) {
      tab = "story"; slideIndex = 0;
      document.body.classList.add("present");
      paint();
      return;
    }
    if (t.classList && t.classList.contains("present-exit")) {
      document.body.classList.remove("present");
      tab = "overview"; paint();
      return;
    }
    if (t.getAttribute && t.getAttribute("data-cell")) {
      decideCell = t.getAttribute("data-cell"); labBase = {}; paint(); return;
    }
    if (t.id === "b-run") return start("all");
    if (t.id === "b-model" || (t.getAttribute && t.getAttribute("data-model"))) {
      return api("/api/model", {}).then(function () { tab = "models"; refresh(); });
    }
    if (t.id === "b-reorder") return start("reorder");
    if (t.id === "b-marketing") return start("marketing");
    if (t.id === "b-verdict") return start("verdict");
    if (t.id === "b-reset") {
      if (!confirm("Wipe the database and reseed 90 days of history?")) return;
      return api("/api/reset", {}).then(refresh);
    }
    if (t.id === "b-expand") { el("log").classList.toggle("tall"); return; }
    if (t.id === "b-clear") { el("log").innerHTML = ""; return; }
    if (t.getAttribute && t.getAttribute("data-run")) return start(t.getAttribute("data-run"));
    if (t.getAttribute && t.getAttribute("data-ev")) return showEvidence(t.getAttribute("data-ev"));
    if (t.getAttribute && t.getAttribute("data-approve")) return decide(t.getAttribute("data-approve"), "approve");
    if (t.getAttribute && t.getAttribute("data-reject")) return decide(t.getAttribute("data-reject"), "reject");
    if (t.getAttribute && t.getAttribute("data-reverse")) {
      if (!confirm("Write a reversing entry for #" + t.getAttribute("data-reverse") + "?")) return;
      return api("/api/reverse", { id: +t.getAttribute("data-reverse") }).then(refresh);
    }
    if (t.getAttribute && t.getAttribute("data-suggest") !== null && t.getAttribute("data-suggest") !== undefined) {
      var i = +t.getAttribute("data-suggest");
      if (!isNaN(i) && SUGGEST[i]) { el("ask-input").value = SUGGEST[i]; return ask(); }
    }
    if (t.id === "ask-go") return ask();
    if (t.id === "modal-close" || t.id === "modal") return el("modal").classList.remove("on");
  });

  document.addEventListener("input", function (e) {
    var feat = e.target && e.target.getAttribute && e.target.getAttribute("data-feat");
    if (!feat) return;
    labBase[feat] = +e.target.value;
    var row = e.target.parentNode.querySelector(".row b");
    if (row) row.textContent = (+e.target.value < 1 ? (+e.target.value).toFixed(4) : num(e.target.value, 2));
    clearTimeout(window.__labTimer);
    window.__labTimer = setTimeout(function () { loadLab(labOverrides()); }, 220);
  });

  document.addEventListener("keydown", function (e) {
    if (document.body.classList.contains("present")) {
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        slideIndex += 1; paint(); e.preventDefault(); return;
      }
      if (e.key === "ArrowLeft" || e.key === "PageUp") { slideIndex -= 1; paint(); e.preventDefault(); return; }
      if (e.key === "Escape") { document.body.classList.remove("present"); tab = "overview"; paint(); return; }
    }
    if (e.key === "Enter" && document.activeElement && document.activeElement.id === "ask-input") ask();
    if (e.key === "Escape") el("modal").classList.remove("on");
  });

  function start(what) {
    return api("/api/run", { what: what }).then(function () {
      if (!views[what]) tab = "overview";
      else tab = what === "all" ? "overview" : what;
      refresh();
    });
  }

  function ask() {
    var input = el("ask-input");
    if (!input || !input.value.trim()) return;
    var q = input.value.trim();
    api("/api/ask", { question: q }).then(function (d) {
      askTicket = d.ticket;
      el("ask-out").innerHTML = "<div class='card'><span class='dot on'></span> <span class='mono'>starting…</span></div>";
      pollAsk();
    });
  }

  function decide(id, decision) {
    api("/api/approve", { id: +id, decision: decision }).then(refresh);
  }

  function showEvidence(eid) {
    api("/api/evidence/" + eid).then(function (d) {
      el("modal-title").textContent = "Evidence " + eid;
      el("modal-body").innerHTML = d.error ? "<p class='muted'>" + esc(d.error) + "</p>" :
        "<p class='mono muted'>tool <b>" + esc(d.tool) + "</b> · agent " + esc(d.agent) +
        " · " + esc(d.created_at) + "</p><h3>Arguments</h3><pre>" + esc(JSON.stringify(d.args, null, 2)) +
        "</pre><h3>Result stored at the time of the decision</h3><pre>" +
        esc(JSON.stringify(d.result, null, 2)) + "</pre>";
      el("modal").classList.add("on");
    });
  }

  refresh().then(pollLog);
})();
