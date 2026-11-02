/* Shared shell: navigation, page header band, on-this-page rail, progress bar,
   copy buttons, theme toggle, and zoomable / pannable Mermaid diagrams. */
(function () {
  const NAV = [
    { group: "Interactive", items: [
      ["index.html", "◆", "Dashboard"],
      ["store.html", "◎", "Live store", "LIVE"],
      ["simulate.html", "▶", "Live operations", "LIVE"],
      ["canvas.html", "⌘", "Architecture canvas"],
      ["forecast-lab.html", "∿", "Forecast Lab"],
    ]},
    { group: "Next level", items: [
      ["scale.html", "↗", "Scale plan: sunglasses to 1M", "NEW"],
      ["scale-brief.html", "▤", "Scaling brief (presenter)"],
    ]},
    { group: "Implementation", items: [
      ["engine-run.html", "▶", "Live engine output", "RUNS"],
      ["deeper.html", "D0", "Operating rules, bus & third parties", "NEW"],
      ["agent-marketing.html", "D1", "Marketing allocation agent", "NEW"],
      ["agent-reorder.html", "D2", "Reorder agent & the towel case", "NEW"],
      ["agent-verdict.html", "D3", "Product verdict agent (kill/fix/scale)", "NEW"],
    ]},
    { group: "Start here", items: [
      ["brief.html", "★", "Architecture brief (read first)"],
      ["team.html", "◉", "Agents at a glance"],
      ["diagrams.html", "◇", "Architecture diagrams"],
      ["overview.html", "00", "Overview & principles"],
    ]},
    { group: "Required deliverable", items: [
      ["domain.html", "01", "Company / domain"],
      ["agents.html", "02", "Agent hierarchy"],
      ["hld.html", "03", "Technical architecture (HLD)"],
      ["data.html", "04", "Shared state & data"],
      ["orchestration.html", "05", "Agent orchestration"],
      ["flows.html", "06", "Procurement & marketing flows"],
      ["security.html", "07", "Security & failsafes"],
      ["build-vs-buy.html", "08", "Build vs buy"],
      ["stack.html", "09", "Technology stack"],
      ["tradeoffs.html", "10", "Key trade-offs"],
      ["scenario.html", "11", "Scenario: towel sells 3×"],
    ]},
    { group: "Deep dives", items: [
      ["harness.html", "A", "Agent harness (7 stages)"],
      ["lld.html", "B", "Low-level design (LLD)"],
      ["identity.html", "C", "Identity, secrets & runtime"],
      ["suppliers.html", "D", "Supplier integration ladder"],
      ["grounding.html", "E", "Grounding & anti-hallucination"],
      ["reliability.html", "F", "Reliability & recovery"],
      ["evaluation.html", "G", "Evaluation & observability"],
      ["cost.html", "H", "Cost model & optimisation"],
      ["forecasting.html", "I", "Forecasting & ML models"],
    ]},
  ];
  window.SITE_NAV = NAV;
  const CANVAS_FOR = { "domain.html": "domain", "hld.html": "platform", "agents.html": "agents", "flows.html": "procurement" };

  const flat = NAV.flatMap((g) => g.items);
  // Hosts like Cloudflare serve /brief for brief.html; normalise so nav, pager and links still match.
  let here = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  if (!here.includes(".")) here += ".html";

  // ---- theme ----
  function storedTheme() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
  function setTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("theme", t); } catch (e) {}
    document.dispatchEvent(new CustomEvent("themechange"));
  }
  const st = storedTheme();
  if (st) document.documentElement.setAttribute("data-theme", st);
  function isDark() {
    const t = document.documentElement.getAttribute("data-theme");
    if (t) return t === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  window.SITE_isDark = isDark;

  const WEAVE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h4m4 0h8M4 12h8m4 0h4M4 17h4m4 0h8"/><path d="M8 4v16M16 4v16" opacity=".55"/></svg>';
  const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

  function buildShell() {
    const main = document.querySelector("main");
    if (!main) return;
    main.id = main.id || "main";
    const skip = document.createElement("a");
    skip.className = "skip"; skip.href = "#" + main.id; skip.textContent = "Skip to content";
    document.body.prepend(skip);
    if (!document.querySelector('link[rel="icon"]')) {
      const fav = document.createElement("link");
      fav.rel = "icon";
      fav.href = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#3448c5"/><g stroke="#fff" stroke-width="2.6" stroke-linecap="round"><path d="M7 11h5m5 0h8M7 16h10m5 0h3M7 21h5m5 0h8"/></g></svg>');
      document.head.appendChild(fav);
    }
    const isApp = document.body.hasAttribute("data-app");

    const bar = document.createElement("div");
    bar.className = "progress";
    document.body.prepend(bar);

    const top = document.createElement("header");
    top.className = "topbar";
    top.innerHTML =
      '<button class="icon-btn menu-btn" aria-label="Show sections">☰</button>' +
      '<a class="brand" href="index.html"><span class="brand-mark">' + WEAVE + '</span>Halden Home <small>Autonomous Commerce</small></a>' +
      '<span class="spacer"></span>' +
      '<nav class="top-links" aria-label="Interactive">' +
      '<a class="top-link' + (here === "index.html" ? " active" : "") + '" href="index.html">Dashboard</a>' +
      '<a class="top-link' + (here === "store.html" ? " active" : "") + '" href="store.html"><span class="dot"></span>Live store</a>' +
      '<a class="top-link' + (here === "simulate.html" ? " active" : "") + '" href="simulate.html">Operations</a>' +
      '<a class="top-link' + (here === "canvas.html" ? " active" : "") + '" href="canvas.html">Canvas</a>' +
      '<a class="top-link' + (here === "forecast-lab.html" ? " active" : "") + '" href="forecast-lab.html">Forecast Lab</a>' +
      '<a class="top-link' + (here === "brief.html" ? " active" : "") + '" href="brief.html">Brief</a>' +
      '<a class="top-link' + (here === "diagrams.html" ? " active" : "") + '" href="diagrams.html">Diagrams</a>' +
      "</nav>" +
      '<button class="icon-btn theme-btn" aria-label="Toggle light or dark theme"></button>';
    bar.after(top);
    const themeBtn = top.querySelector(".theme-btn");
    const paintThemeBtn = () => { themeBtn.innerHTML = isDark() ? ICON_SUN : ICON_MOON; };
    paintThemeBtn();
    themeBtn.addEventListener("click", () => { setTheme(isDark() ? "light" : "dark"); paintThemeBtn(); renderDiagrams(); });

    const shell = document.createElement("div");
    shell.className = "shell";
    const side = document.createElement("nav");
    side.className = "sidebar";
    side.setAttribute("aria-label", "Sections");
    side.innerHTML = NAV.map((g) =>
      '<div class="nav-group"><h6>' + g.group + "</h6>" +
      g.items.map(([href, n, label, badge]) =>
        '<a href="' + href + '"' + (href === here ? ' class="active" aria-current="page"' : "") +
        '><span class="n">' + n + "</span><span>" + label + "</span>" + (badge ? '<span class="live">' + badge + "</span>" : "") + "</a>").join("") +
      "</div>").join("");
    main.parentNode.insertBefore(shell, main);
    shell.appendChild(side);
    shell.appendChild(main);
    if (isApp) document.body.classList.add("app");
    top.querySelector(".menu-btn").addEventListener("click", () => document.body.classList.toggle("nav-open"));
    document.addEventListener("click", (e) => {
      if (document.body.classList.contains("nav-open") && !side.contains(e.target) && !e.target.closest(".menu-btn")) document.body.classList.remove("nav-open");
    });

    window.addEventListener("scroll", () => {
      const h = document.documentElement;
      const pct = h.scrollHeight > h.clientHeight ? (h.scrollTop / (h.scrollHeight - h.clientHeight)) * 100 : 0;
      bar.style.width = pct + "%";
    }, { passive: true });

    if (isApp) return;
    const content = main.querySelector(".content");
    if (!content) return;

    // Page header band: eyebrow + h1 + lede
    const head = document.createElement("div");
    head.className = "page-head";
    const inner = document.createElement("div");
    inner.className = "inner enter";
    head.appendChild(inner);
    for (const sel of [".eyebrow", "h1", ".lede"]) {
      const el = content.querySelector(":scope > " + sel);
      if (el) inner.appendChild(el);
    }
    main.insertBefore(head, content);
    collapseSections(content, inner);

    // On-this-page rail
    const h2s = [...content.querySelectorAll("h2")];
    h2s.forEach((h, i) => { if (!h.id) h.id = "s-" + i; });
    const wrap = document.createElement("div");
    wrap.className = "with-rail";
    main.insertBefore(wrap, content);
    wrap.appendChild(content);
    if (h2s.length > 2) {
      const rail = document.createElement("aside");
      rail.className = "rail";
      rail.innerHTML = "<h6>On this page</h6>" + h2s.map((h) => '<a href="#' + h.id + '">' + h.textContent + "</a>").join("");
      wrap.appendChild(rail);
      const links = [...rail.querySelectorAll("a")];
      const io = new IntersectionObserver((entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id));
        });
      }, { rootMargin: "-20% 0px -70% 0px" });
      h2s.forEach((h) => io.observe(h));
    }

    // Copy buttons on code
    content.querySelectorAll("pre").forEach((pre) => {
      const w = document.createElement("div");
      w.className = "pre-wrap";
      pre.parentNode.insertBefore(w, pre);
      w.appendChild(pre);
      const b = document.createElement("button");
      b.className = "icon-btn copy-btn";
      b.type = "button";
      b.textContent = "Copy";
      b.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(pre.innerText); b.textContent = "Copied"; }
        catch (e) { const r = document.createRange(); r.selectNodeContents(pre); const s = getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = "Selected"; }
        setTimeout(() => (b.textContent = "Copy"), 1400);
      });
      w.appendChild(b);
    });

    // Pager
    const idx = flat.findIndex(([h]) => h === here);
    if (idx >= 0) {
      const prev = flat[idx - 1], next = flat[idx + 1];
      const pager = document.createElement("div");
      pager.className = "pager";
      pager.innerHTML =
        (prev ? '<a href="' + prev[0] + '"><small>← Previous</small>' + prev[2] + "</a>" : "<span></span>") +
        (next ? '<a class="next" href="' + next[0] + '"><small>Next →</small>' + next[2] + "</a>" : "<span></span>");
      content.appendChild(pager);
    }
  }

  // ---- collapsible sections: long pages show summary + first two sections ----
  function collapseSections(content, headInner) {
    const h2s = [...content.querySelectorAll(":scope > h2")];
    if (h2s.length < 4) return;
    h2s.forEach((h, i) => {
      if (!h.id) h.id = "s-" + i;
      const det = document.createElement("details");
      det.className = "sec";
      if (i < 2) det.open = true;
      const sum = document.createElement("summary");
      content.insertBefore(det, h);
      sum.appendChild(h);
      det.appendChild(sum);
      let n = det.nextSibling;
      while (n && !(n.nodeType === 1 && n.tagName === "H2")) { const nx = n.nextSibling; det.appendChild(n); n = nx; }
      det.addEventListener("toggle", () => { if (det.open) det.querySelectorAll(".mermaid[data-nw]").forEach((m) => { if (!m.dataset.touched) fit(m, false); }); });
    });
    const bar = document.createElement("div");
    bar.className = "sec-tools";
    bar.innerHTML = '<span>' + h2s.length + ' sections</span><button class="icon-btn" type="button" data-x="1">Expand all</button><button class="icon-btn" type="button" data-x="0">Collapse all</button>';
    bar.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; content.querySelectorAll("details.sec").forEach((d) => (d.open = b.dataset.x === "1")); });
    headInner.appendChild(bar);
    const openFor = (hash) => { const t = hash && document.getElementById(hash.slice(1)); const d = t && t.closest("details.sec"); if (d) d.open = true; };
    document.addEventListener("click", (e) => { const a = e.target.closest('a[href^="#"]'); if (a) openFor(a.getAttribute("href")); });
    window.addEventListener("hashchange", () => openFor(location.hash));
    openFor(location.hash);
  }

  // ---- mermaid ----
  function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  let renderSeq = 0;

  function prepareDiagrams() {
    let first = true;
    document.querySelectorAll('script[type="text/x-mermaid"]').forEach((s) => {
      const frame = s.closest(".diagram");
      const div = document.createElement("div");
      div.className = "mermaid";
      div.setAttribute("data-src", s.textContent.trim());
      if (!frame) { s.replaceWith(div); return; }
      const view = document.createElement("div");
      view.className = "dg-view";
      s.replaceWith(view);
      view.appendChild(div);
      const tools = document.createElement("div");
      tools.className = "dg-tools";
      const canvasView = first && CANVAS_FOR[here];
      tools.innerHTML =
        '<span class="hint">drag to pan · zoom to inspect</span>' +
        (canvasView ? '<a class="icon-btn" href="canvas.html#' + canvasView + '">Open interactive · drag boxes</a>' : "") +
        '<button class="icon-btn" data-z="-" type="button" aria-label="Zoom out">−</button>' +
        '<button class="icon-btn" data-z="fit" type="button">Fit</button>' +
        '<button class="icon-btn" data-z="+" type="button" aria-label="Zoom in">+</button>' +
        '<button class="icon-btn" data-z="full" type="button">⤢ Expand</button>';
      frame.prepend(tools);
      first = false;
      tools.addEventListener("click", (e) => {
        const b = e.target.closest("button[data-z]");
        if (!b) return;
        const z = b.getAttribute("data-z");
        div.dataset.touched = "1";
        if (z === "full") {
          const on = frame.classList.toggle("full");
          b.textContent = on ? "✕ Close" : "⤢ Expand";
          document.body.style.overflow = on ? "hidden" : "";
          fit(div, true);
          return;
        }
        const cur = +div.dataset.scale || 1;
        if (z === "fit") fit(div, true);
        else setScale(div, z === "+" ? cur * 1.2 : cur / 1.2);
      });
      // drag to pan
      let sx, sy, sl, stp, down = false;
      view.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        down = true; sx = e.clientX; sy = e.clientY; sl = view.scrollLeft; stp = view.scrollTop;
      });
      window.addEventListener("pointermove", (e) => {
        if (!down) return;
        const dx = e.clientX - sx, dy = e.clientY - sy;
        if (Math.abs(dx) + Math.abs(dy) > 3) view.classList.add("panning");
        view.scrollLeft = sl - dx; view.scrollTop = stp - dy;
      });
      window.addEventListener("pointerup", () => { down = false; view.classList.remove("panning"); });
    });
  }

  function naturalWidth(el) { return +el.dataset.nw || 0; }
  function setScale(el, sc) {
    sc = Math.max(0.3, Math.min(3, sc));
    el.dataset.scale = sc;
    const s = el.querySelector("svg");
    if (!s) return;
    s.style.maxWidth = "none";
    s.style.width = Math.round(naturalWidth(el) * sc) + "px";
  }
  function fit(el, force) {
    const view = el.closest(".dg-view");
    const avail = (view ? view.clientWidth : el.clientWidth) - 36;
    const nw = naturalWidth(el);
    if (!nw || !avail) return;
    let sc = Math.min(1, avail / nw);
    if (!force) sc = Math.max(sc, 0.75);
    setScale(el, sc);
  }

  async function renderDiagrams() {
    if (!window.mermaid) return;
    const dark = isDark();
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      fontFamily: cssVar("--font"),
      flowchart: { curve: "basis", htmlLabels: true, padding: 12 },
      sequence: { mirrorActors: false, showSequenceNumbers: true },
      themeVariables: {
        darkMode: dark,
        background: cssVar("--bg-elev"),
        primaryColor: cssVar("--accent-soft"),
        primaryBorderColor: cssVar("--accent"),
        primaryTextColor: cssVar("--fg"),
        secondaryColor: cssVar("--info-soft"),
        tertiaryColor: cssVar("--bg-sunk"),
        lineColor: cssVar("--fg-faint"),
        textColor: cssVar("--fg"),
        mainBkg: cssVar("--accent-soft"),
        nodeBorder: cssVar("--accent"),
        clusterBkg: cssVar("--bg-sunk"),
        clusterBorder: cssVar("--border-strong"),
        edgeLabelBackground: cssVar("--bg-elev"),
        actorBkg: cssVar("--accent-soft"),
        actorBorder: cssVar("--accent"),
        actorTextColor: cssVar("--fg"),
        signalColor: cssVar("--fg-muted"),
        signalTextColor: cssVar("--fg"),
        sequenceNumberColor: cssVar("--bg-elev"),
        noteBkgColor: cssVar("--flax-soft"),
        noteTextColor: cssVar("--fg"),
        noteBorderColor: cssVar("--flax"),
        labelBoxBkgColor: cssVar("--bg-sunk"),
        labelTextColor: cssVar("--fg"),
        loopTextColor: cssVar("--fg"),
        pie1: cssVar("--accent"), pie2: cssVar("--flax"), pie3: cssVar("--llm"), pie4: cssVar("--ok"),
        pieStrokeColor: cssVar("--bg-elev"), pieTitleTextColor: cssVar("--fg"), pieSectionTextColor: cssVar("--accent-fg"), pieLegendTextColor: cssVar("--fg"),
        quadrant1Fill: cssVar("--accent-soft"), quadrant2Fill: cssVar("--info-soft"), quadrant3Fill: cssVar("--bg-sunk"), quadrant4Fill: cssVar("--flax-soft"),
        quadrantPointFill: cssVar("--accent"), quadrantPointTextColor: cssVar("--fg"), quadrantTitleFill: cssVar("--fg"),
        quadrant1TextFill: cssVar("--fg"), quadrant2TextFill: cssVar("--fg"), quadrant3TextFill: cssVar("--fg"), quadrant4TextFill: cssVar("--fg"),
        quadrantXAxisTextFill: cssVar("--fg-muted"), quadrantYAxisTextFill: cssVar("--fg-muted"),
        fontSize: "14px",
      },
    });
    for (const el of document.querySelectorAll(".mermaid[data-src]")) {
      try {
        const { svg } = await window.mermaid.render("m" + (++renderSeq), el.getAttribute("data-src"));
        el.innerHTML = svg;
        const s = el.querySelector("svg");
        const mw = s && parseFloat(s.style.maxWidth);
        if (mw) el.dataset.nw = mw;
        if (el.dataset.scale && el.dataset.touched) setScale(el, +el.dataset.scale);
        else fit(el, false);
      } catch (err) {
        el.innerHTML = '<pre style="color:var(--danger)">Diagram error: ' + String((err && err.message) || err) + "</pre>";
      }
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".diagram.full [data-z='full']").forEach((b) => b.click());
  });

  document.addEventListener("DOMContentLoaded", () => {
    buildShell();
    prepareDiagrams();
    renderDiagrams();
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (!document.documentElement.getAttribute("data-theme")) { renderDiagrams(); document.dispatchEvent(new CustomEvent("themechange")); }
      });
    }
  });
})();
