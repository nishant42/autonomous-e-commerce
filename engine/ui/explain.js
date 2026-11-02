/* Interview view. All operational values come from read-only engine endpoints. */
(function () {
  'use strict';
  const page = document.getElementById('page');
  let data, budget, inventory = 'live', product = 'p_towel', cell, verdict;
  let cu, co, quantityTimer, quantityVersion = 0, budgetVersion = 0;
  const fixes = {cap: true, sub: true, promo: true, ret: true};
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v, digits = 1) => Number.isFinite(Number(v)) && v !== null ? Number(v).toLocaleString('en-GB', {maximumFractionDigits: digits, minimumFractionDigits: digits}) : '—';
  const money = v => '€' + num(v, 2);
  const pct = v => num(v * 100, 1) + '%';
  const el = id => document.getElementById(id);
  async function api(url, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const r = await fetch(url, {signal: controller.signal, ...(body ? {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)} : {})});
      if (!r.ok) throw new Error('Engine request failed (' + r.status + ')');
      const result = await r.json();
      if (result.error) throw new Error(result.error);
      return result;
    } finally { clearTimeout(timer); }
  }
  function compare(v, title) {
    const r = v.reconstruction;
    return `<article class="card ${title === 'Black towel' ? 'featured' : ''}"><div class="caption">${esc(title)}</div>
      <div class="big">${num(r.units_shipped, 0)} <em>units shipped</em></div>
      <p class="small muted">Buyable ${num(r.available_days, 0)} of ${r.period_days} days · ${num(r.ros_per_available_day, 3)} units / buyable day</p>
      <div class="comparison"><strong>${num(r.reconstructed_demand_period)}</strong><span>estimated units at the intended price<br>before returns</span></div>
      <p class="small muted">After returns: <b>${num(r.net_demand_period)} units</b> over the same period.</p></article>`;
  }
  function correctionRows() {
    const w = data.variants.v_white.reconstruction;
    const rows = [
      ['cap', 'Cap unusually large days', 'Limit each buyable day to the observed 95th-percentile daily sales.', `≤ ${w.spike_cap_applied} / day`],
      ['sub', 'Remove estimated substitution', 'An in-stock colour can absorb sales from a sold-out sibling. This is an estimate, not a known shopper preference.', `× ${num(w.correction_factors.substitution,3)}`],
      ['promo', 'Adjust to the intended price', `Average discount ${num(w.avg_discount_pct)}%. A category elasticity assumption estimates demand at full price.`, `× ${num(w.correction_factors.price,3)}`],
      ['ret', 'Allow for returns', 'Returned units reduce the demand retained by the business.', `× ${num(w.correction_factors.returns,3)}`]
    ];
    return rows.map(([id,title,detail,effect]) => `<label class="correction"><input type="checkbox" data-fix="${id}" checked><span><strong>${esc(title)}</strong><small>${esc(detail)}</small></span><span class="effect">${effect}</span></label>`).join('');
  }
  function correctionsResult() {
    const w = data.variants.v_white.reconstruction;
    let value = (fixes.cap ? w.spike_capped_units : w.units_shipped) / w.available_days * w.period_days;
    const factors = [fixes.sub ? w.correction_factors.substitution : 1, fixes.promo ? w.correction_factors.price : 1, fixes.ret ? w.correction_factors.returns : 1];
    value *= factors.reduce((a,b) => a*b, 1);
    el('corrected-demand').textContent = num(value);
    el('correction-math').textContent = `${fixes.cap ? w.spike_capped_units : w.units_shipped} ÷ ${w.available_days} buyable days × ${w.period_days} days × ${factors.map(v => num(v,3)).join(' × ')} = ${num(value)} units`;
    el('correction-caption').textContent = fixes.ret ? 'estimated retained demand after returns' : 'estimated demand before returns';
  }
  function quantityRows(d) {
    const buffer = d.order_up_to - d.demand_mu;
    return `<div class="waterfall">
      <div class="row"><span>Mean demand over ${d.protection_interval_days} days</span><b>${num(d.demand_mu)}</b></div>
      <div class="row"><span>${buffer < 0 ? 'Risk adjustment below the mean' : 'Safety allowance above the mean'} (z = ${d.z})</span><b>${buffer < 0 ? '−' : '+'}${num(Math.abs(buffer))}</b></div>
      <div class="row"><span>Stock on hand</span><b>−${d.on_hand}</b></div>
      <div class="row"><span>Orders already recorded</span><b>−${d.on_order}</b></div>
      <div class="row"><span>Case pack / minimum order</span><b>${d.case_pack} / ${d.moq}</b></div>
      <div class="row total"><span>Proposed order</span><b>${d.qty} units · ${money(d.capital_eur)}</b></div></div>
      <p class="small muted">${d.cover_cap_applied ? 'Stock-cover cap applied. ' : ''}${d.qty === 0 ? 'Current stock and recorded orders already meet this target.' : 'Rounded to case packs, with minimum-order and cover constraints.'}</p>`;
  }
  function gateText(d) {
    const a = data.policy.autonomy;
    const tier = d.capital_eur >= a.human_signal_above_eur ? 'Human approval required' : d.capital_eur >= a.auto_execute_below_eur ? 'Independent checker required' : 'Eligible for automatic approval';
    return `${money(d.capital_eur)} → ${tier}. Cash, quantity and stock-cover guards still apply. This page calculates; it does not place an order.`;
  }
  function serviceUpdate() {
    const sl = cu / (cu + co);
    el('cu-value').textContent = money(cu); el('co-value').textContent = money(co);
    el('service-value').textContent = pct(sl);
    el('service-meter').style.width = pct(sl);
    el('service-math').textContent = `${money(cu)} ÷ (${money(cu)} + ${money(co)}) = ${pct(sl)}`;
    clearTimeout(quantityTimer);
    const version = ++quantityVersion;
    el('quantity-status').textContent = 'Recalculating with the quantity engine…';
    quantityTimer = setTimeout(async () => {
      try {
        const d = await api('/api/explain-quantity', {cu, co, inventory});
        if (version !== quantityVersion) return;
        el('quantity-output').innerHTML = quantityRows(d);
        el('quantity-gate').textContent = gateText(d);
        el('quantity-status').textContent = 'Scenario calculated by the Python engine. No proposal submitted.';
      } catch (error) {
        if (version === quantityVersion) el('quantity-status').textContent = 'Calculation unavailable. The previous order below is unchanged; retry the slider.';
      }
    }, 180);
  }
  function renderBudget() {
    const b = budget;
    el('budget-summary').textContent = `${money(b.allocated)} allocated · ${money(b.held_back)} held back · ${money(b.explore_reserve)} exploration reserve within the held-back amount`;
    el('budget-table').innerHTML = `<div class="table-wrap"><table><thead><tr><th>Product</th><th>Margin / order</th><th>Ad cost / order</th><th>Margin / €1 spent</th><th>Weekly budget</th><th>Reason / constraints</th></tr></thead><tbody>${b.lines.map(l => `<tr class="${l.product_id === product ? 'selected' : ''}"><td>${esc(l.product)}<br><span class="small muted">${l.product_id.startsWith('med_') ? 'Imported demo shop' : 'Seeded case study'}</span></td><td class="number">${money(l.margin)}</td><td class="number">${l.cpa === null ? '—' : money(l.cpa)}<br><span class="small muted">${esc(l.cpa_source)}</span></td><td class="number">${l.return_per_euro === null ? '—' : num(l.return_per_euro,2)}</td><td class="number good">${money(l.allocated)}</td><td class="reason">${esc(l.reason || (l.unproven ? 'Capped first test; performance is unproven.' : 'Eligible, subject to supply, concentration and ramp limits.'))}</td></tr>`).join('')}</tbody></table></div>`;
    const select = el('channel-product');
    select.innerHTML = b.lines.map(l => `<option value="${esc(l.product_id)}">${esc(l.product)}</option>`).join('');
    if (!b.lines.some(l => l.product_id === product)) product = b.lines[0].product_id;
    select.value = product;
    renderChannels();
  }
  function renderChannels() {
    const line = budget.lines.find(l => l.product_id === product);
    const rows = line.channels || [];
    el('channel-output').innerHTML = rows.length ? rows.map(c => `<div class="bar-row"><span>${esc(c.channel)}</span><div class="track"><i style="width:${Math.max(0, Math.min(100, c.amount / (line.allocated || 1) * 100))}%"></i></div><span class="amount">${money(c.amount)}${c.return_per_euro === null ? '' : ' · ' + num(c.return_per_euro,2) + '/€'}</span></div><p class="small muted">${esc(c.why)}</p>`).join('') : `<p class="muted">No channel allocation. ${esc(line.reason || 'This product has no budget this cycle.')}</p>`;
  }
  function renderCell() {
    const c = data.marketing.cells.find(c => c.cell_id === cell);
    if (!c) return;
    const e = c.explanation;
    el('cell-output').innerHTML = `<div class="grid3 stats"><div class="stat"><small>Observed CPA</small><strong>${e.cost_per_order === null ? '—' : money(e.cost_per_order)}</strong></div><div class="stat"><small>Target CPA</small><strong>${money(e.target_cpa)}</strong></div><div class="stat"><small>Guarded rule result</small><strong style="font-size:17px">${esc(e.action)}</strong></div></div>
      <p class="note">${esc(e.reason)} · ${money(e.daily_now)} → ${money(e.budget)} per day</p>
      <details><summary>Inspect this ad’s checks and permitted AI choices</summary><ol class="steps">${e.steps.map(s => `<li class="${s.decided ? 'decided' : ''}"><b>${esc(s.check)}</b><small>${esc(s.detail)} · ${esc(s.outcome)}</small></li>`).join('')}</ol><p class="small muted">The ladder lists every diagnostic check. The first applicable guard takes precedence; later diagnostic flags do not override it.</p><pre>Permitted actions: ${esc(e.permitted_actions.join(', '))}\nComputed budgets: ${esc(JSON.stringify(e.budget_each_action_would_set))}</pre></details>`;
  }
  function renderBand() {
    const ratio = +el('band-ratio').value / 100;
    const p = data.marketing.policy;
    const action = ratio <= .8 ? `scale +${p.max_change_pct}%` : ratio <= 1 ? 'hold' : ratio <= p.pause_above_target_multiple ? `reduce ${p.max_change_pct}%` : 'pause';
    el('band-value').textContent = pct(ratio);
    el('band-result').textContent = `${money(ratio * data.marketing.target_cpa)} CPA → ${action}`;
  }
  function renderVerdict() {
    const v = data.verdicts.find(v => v.product_id === verdict);
    if (!v) return;
    const e = v.evidence, s = e.sentiment;
    const diag = v.diagnosis;
    el('verdict-output').innerHTML = `<div class="grid2"><div><div class="caption">${esc(v.source)}</div><div class="verdict-label">${esc(v.engine_verdict)}</div><p>${esc(v.engine_reason)}</p><p class="small muted">First action: ${esc(v.actions[0] || 'Review the evidence again.')}</p><div class="note">${v.engine_verdict === 'KILL' ? 'KILL is a recommendation. The gate requires human approval before an executor acts.' : !v.exposure_met ? 'Exposure is below the configured minimum. Continue observing; do not infer product failure.' : 'A model may investigate and choose a permitted verdict. Exposure, supply and human-approval rules remain enforced in code.'}</div></div><div><div class="grid3 stats"><div class="stat"><small>Sold</small><strong>${num(e.units_sold,0)}</strong></div><div class="stat"><small>Unit margin</small><strong style="font-size:19px">${money(e.margin_per_unit)}</strong></div><div class="stat"><small>Negative reviews</small><strong>${s.negative_share === null ? '—' : pct(s.negative_share)}</strong></div></div><p class="small muted">${s.classified} classified reviews${s.negative === undefined ? '' : ' · ' + s.negative + ' negative'} · ${num(e.share_of_days_unbuyable * 100)}% of measured selling-variant days unbuyable.</p>${v.funnel ? ['pdp_rate','atc_rate','checkout_rate','purchase_rate','refund_rate'].map((k,i) => `<div class="funnel-row"><span>${['Session → product page','Product page → cart','Cart → checkout','Checkout → paid','Paid → refund'][i]}</span><b>${pct(v.funnel[k])}${diag && diag.flags[k] !== 'ok' ? ' · ' + esc(diag.flags[k]) : ''}</b></div>`).join('') : '<p class="small muted">No funnel measurements for this imported product. Diagnosis uses orders, availability and reviews.</p>'}</div></div>
      <details><summary>Inspect the evidence and decision boundary</summary><pre>${esc(JSON.stringify({source:v.source,exposure_met:v.exposure_met,supply_limited:v.supply_limited,permitted_verdicts:v.permitted_verdicts,evidence:e},null,2))}</pre></details>`;
  }
  function modelTable() {
    const m = data.model, f = data.forecast_benchmark;
    return `<div class="table-wrap"><table><thead><tr><th>Model / method</th><th>Job</th><th>Evidence on this machine</th></tr></thead><tbody>
      <tr><td>${m ? esc(m.family) : 'Ad-order model'}</td><td>Predict next week’s orders; reconcile expected CPA with observation.</td><td>${m ? `Promoted · out-of-sample R² ${num(m.out_sample.r2,3)} · ${m.features.length} selected features · ${m.n_test} test rows` : 'No promoted model. Observed CPA drives the bands.'}</td></tr>
      <tr><td>DistilBERT sentiment</td><td>Classify customer review text; pass labels to product diagnosis.</td><td>${data.reviews.classified} / ${data.reviews.total} stored reviews classified. These are local demo-shop reviews.</td></tr>
      <tr><td>MiniLM embeddings</td><td>Identify plausible substitutes from product text.</td><td>${data.substitution_pairs} stored substitute links. Without learned links the engine uses configured product groups.</td></tr>
      <tr><td>Chronos demand forecast</td><td>Challenge the statistical demand baseline.</td><td>${f ? `${esc(f.family)} · ${f.promoted ? 'promoted in registry' : 'not promoted'} · ${esc(f.promotion_reason)}` : 'No benchmark persisted in this database. No claim of a measured win or loss.'}</td></tr>
      <tr><td>Tool-using language model</td><td>Choose read tools, investigate causes, select validated actions.</td><td>Detected provider: ${esc(data.provider.label)}. Provider detection does not prove a successful model response; inspect run mode and decision source.</td></tr>
      </tbody></table></div>`;
  }
  function render() {
    const b = data.variants.v_black, w = data.variants.v_white, y = data.variants.v_yoghurt;
    const d = b.decision;
    cu = d.Cu; co = d.Co;
    const p = data.marketing.policy, a = data.policy.autonomy;
    cell = (data.marketing.cells.find(c => !c.is_holdout) || {}).cell_id;
    verdict = (data.verdicts.find(v => v.engine_verdict === 'KILL') || data.verdicts[0] || {}).product_id;
    page.innerHTML = `<div class="eyebrow">Commerce operations / technical walkthrough</div>
      <h1>Three agents.<br>Every decision has a reason.</h1>
      <p class="intro">What should we buy? Where should we advertise? Which products deserve another chance? Follow the evidence, change the assumptions, and see where each proposal meets the gate.</p>
      <div class="statusline"><span class="badge good">Engine data loaded</span><span class="badge">Towels + advertising: seeded / simulated</span><span class="badge">Shop: imported local demo</span></div>
      <nav class="agent-nav" aria-label="Page sections"><a href="#reorder">01 Reorder</a><a href="#marketing">02 Marketing</a><a href="#verdict">03 Product verdict</a><a href="#harness">04 Harness + bus</a><a href="#ml">05 ML evidence</a></nav>
      <section class="section" id="reorder"><div class="num">01 / REORDER AGENT</div><h2>Sales are what we could sell.<br>Demand is what we need to estimate.</h2><p class="lede">Two colours sold the same quantity. Black was buyable for only ${b.reconstruction.available_days} days. Dividing by calendar days would reward the colour that stayed on the shelf.</p>
      <div class="grid2">${compare(b,'Black towel')}${compare(w,'White towel')}</div>
      <div class="card"><h3>Reconstruct white’s demand</h3><p class="small muted">Toggle a correction. These are deterministic estimates from the demand engine; the model does not invent the factors.</p>${correctionRows()}<div class="result-line"><s>${w.reconstruction.units_shipped}</s><span>shipped →</span><output id="corrected-demand"></output><span id="correction-caption" class="small muted"></span></div><p class="math" id="correction-math"></p><p class="small muted">The ${num(w.reconstruction.reconstructed_demand_period)} and ${num(b.reconstruction.reconstructed_demand_period)} figures are before returns. The quantities below use net demand after returns.</p></div>
      <div class="grid2"><div class="card"><h3>Let the cost of each mistake set the target</h3><p class="small muted">Cu is the profit lost from a missed sale; Co is the cost of a leftover unit.</p>
      <label class="control" for="cu"><span>Cu · missed sale <output id="cu-value"></output></span><input id="cu" type="range" min="0.01" max="60" step="0.01" value="${cu}"></label>
      <label class="control" for="co"><span>Co · leftover unit <output id="co-value"></output></span><input id="co" type="range" min="0.01" max="40" step="0.01" value="${co}"></label>
      <div class="formula-result" id="service-value">${pct(d.service_level)}</div><div class="meter"><i id="service-meter" style="width:${pct(d.service_level)}"></i></div><p class="math" id="service-math"></p><p class="small muted">This selects a demand quantile: the target probability of meeting demand over the protection interval under the distribution assumption. It is not the percentage of units we plan to fulfil.</p></div>
      <div class="card"><h3>Yoghurt uses the same formula</h3>${y ? `<div class="big">${pct(y.decision.service_level)}</div><p class="math">${money(y.decision.Cu)} ÷ (${money(y.decision.Cu)} + ${money(y.decision.Co)})</p><p class="muted">Leftovers expire, so overstocking is more expensive than a missed sale. The target falls below the median. Shelf-life and stock constraints also limit the order.</p><p class="small muted">Current calculated order: ${y.decision.qty} units. Same quantity engine, perishable configuration.</p>` : '<p>No perishable case study loaded.</p>'}</div></div>
      <div class="card"><h3>Turn the forecast into a purchase order</h3><div class="controls"><label for="inventory-mode">Inventory scenario</label><select id="inventory-mode"><option value="live">Current stock + recorded orders</option><option value="before">Before-order example: zero stock, zero on order</option></select><button class="btn" id="reset-economics">Reset costs</button></div><p class="small muted">“Before-order” is an explicit scenario. Current mode includes previous decisions, so repeating the demo can correctly produce a zero order.</p><p class="small muted" id="quantity-status" role="status"></p><div id="quantity-output">${quantityRows(d)}</div><div class="note" id="quantity-gate">${gateText(d)}</div><details><summary>Where the AI contributes</summary><p class="small muted">The reorder model chooses what to investigate: availability, returns, unmet-demand signals, economics or supplier terms. It must read compute_quantities, then choose a computed option, decline, or escalate. A contradictory option set forces escalation in code.</p><pre>python3 run.py agentic v_black v_white\nSource: agents/reorder_agentic.py → engines/demand.py → engines/quantity.py</pre></details></div></section>
      <section class="section" id="marketing"><div class="num">02 / MARKETING AGENT</div><h2>One budget. Three decisions.</h2><p class="lede">Choose products, then channels, then the daily ad action. Contribution margin divided by acquisition cost measures margin returned per advertising euro, before subtracting that advertising cost.</p>
      <div class="card"><h3>Level 1 · Which product earns a share?</h3><p class="math">margin per order ÷ acquisition cost per order = margin / €1 spent</p><div class="controls"><label for="budget-amount">Weekly budget (€)</label><input id="budget-amount" type="number" min="1" max="1000000" step="100" value="3000"><button class="btn" id="apply-budget">Recalculate allocation</button></div><p class="small muted" id="budget-summary" role="status"></p><div id="budget-table"></div><p class="small muted">The configured payback multiplier is 1.2, so the allocator’s funding threshold is ${num(1/1.2,2)} margin / €. Cash break-even on the same margin measure is 1.00. Stock, verdict, experiment limits, ramp limits and a 40% concentration cap can leave money unspent.</p></div>
      <div class="card"><h3>Level 2 · Which channel?</h3><div class="controls"><label for="channel-product">Product</label><select id="channel-product"></select></div><div id="channel-output"></div><p class="small muted">The product-budget splitter preserves an 8% exploration floor per measured channel, then weights the remaining budget by return above the configured funding threshold. The console’s separate weekly experiment uses Thompson sampling; these are distinct allocation methods.</p></div>
      <div class="card"><h3>Level 3 · What should this ad do today?</h3><div class="controls"><label for="ad-cell">Measured ad cell</label><select id="ad-cell">${data.marketing.cells.map(c => `<option value="${esc(c.cell_id)}">${esc(c.cell_id)}${c.is_holdout ? ' · protected holdout' : ''}</option>`).join('')}</select></div><div id="cell-output"></div>
      <details open><summary>Explore the CPA bands</summary><p class="small muted">Band-only illustration: assume sufficient exposure, healthy supply, no cooldown and no fatigue. The measured ad result above also applies its guards and any promoted model estimate.</p><label class="control" for="band-ratio"><span>CPA / target CPA <output id="band-value"></output></span><input id="band-ratio" type="range" min="40" max="200" value="80" step="1"></label><p class="math" id="band-result"></p><div class="table-wrap"><table><thead><tr><th>CPA / target</th><th>Action</th></tr></thead><tbody><tr><td>≤ 80%</td><td>Increase ${p.max_change_pct}%</td></tr><tr><td>&gt; 80%, ≤ 100%</td><td>Hold</td></tr><tr><td>&gt; 100%, ≤ ${p.pause_above_target_multiple*100}%</td><td>Reduce ${p.max_change_pct}%, subject to the minimum measurable budget</td></tr><tr><td>&gt; ${p.pause_above_target_multiple*100}%</td><td>Pause</td></tr><tr><td>Insufficient exposure</td><td>Hold and collect evidence</td></tr></tbody></table></div></details>
      <p class="note">Guardrails: ${p.min_conversions} conversions or spend of ${p.spend_exhaustion_multiple}× target CPA, over at least ${p.min_days} days; ${p.cooldown_hours_per_cell}h between edits; fatigue detection; scaling freezes on unhealthy measurement.</p><p class="small muted">${pct(p.weekly.holdout_geo_share)} configured geo holdout. Observed holdout order share: ${data.marketing.holdout.organic_share == null ? 'unavailable' : pct(data.marketing.holdout.organic_share)}. A raw order share is descriptive; it is not a causal lift estimate without comparable region exposure.</p><details><summary>Where the AI contributes</summary><p class="small muted">The model investigates performance and chooses a permitted action. It cannot change the computed euro amount or override minimum exposure, cooldown, stock or signal guards. Creative requests are recorded as anomalies for follow-up.</p><pre>python3 run.py agentic-marketing\nSource: agents/marketing_agentic.py → engines/allocator.py</pre></details></div></section>
      <section class="section" id="verdict"><div class="num">03 / PRODUCT VERDICT — THE ADDITIONAL AGENT</div><h2>Fix the shop, change the offer,<br>or stop backing the product?</h2><p class="lede">I chose product diagnosis as the third agent because it governs what the other two should fund. A checkout failure needs a repair. A supply failure needs stock. Neither alone proves the product is unwanted.</p><div class="card"><div class="controls"><label for="verdict-product">Investigate a product</label><select id="verdict-product">${data.verdicts.map(v => `<option value="${esc(v.product_id)}">${esc(v.name)} · ${v.product_id.startsWith('med_') ? 'imported demo' : 'seeded funnel'}</option>`).join('')}</select></div><div id="verdict-output"></div></div><div class="note">The language classifier turns review text into stored labels. The verdict engine combines those labels with measured evidence. The tool-using agent can investigate and recommend a permitted verdict. The gate owns authorization; KILL always waits for a person.</div><details><summary>Run the third agent</summary><pre>python3 run.py agentic-verdict p_mug p_candle\nSource: agents/verdict_agentic.py → engines/verdict_evidence.py\nFor an imported product, pass its product ID from the evidence panel above.</pre></details></section>
      <section class="section" id="harness"><div class="num">04 / HARNESS, BUS AND GATE</div><h2>Reasoning is bounded.<br>Execution is a separate step.</h2><div class="flow"><span>Durable job</span><i>→</i><span>Read tools + evidence</span><i>→</i><span>Validated choice</span><i>→</i><span>Typed proposal</span><i>→</i><span>Gate + ledger</span><i>→</i><span>Outbox + executor</span></div>
      <div class="grid2"><div class="card"><h3>The harness surrounds each decision</h3><ol class="steps"><li>Grant only configured read tools<small>Model arguments stay within the current product or SKU.</small></li><li>Store tool inputs and outputs as evidence<small>Mandatory reads must succeed before accepting the model’s answer. Numeric rationale claims are checked against evidence.</small></li><li>Bound the investigation<small>Reorder: 8 turns. Marketing: 6. Verdict: 7. A token threshold stops further calls after reported usage reaches the budget; an individual call can cross it.</small></li><li>Validate the choice and its proposal<small>Computed quantities and budgets, explicit verdicts, validated confidence, and deterministic fallback on model failure.</small></li></ol></div><div class="card"><h3>The bus preserves the work</h3><p class="small muted">SQLite rows hold jobs, attempts, leases and results. Retries back off; ${data.bus.max_attempts} failed attempts lead to a dead letter. Expired ${data.bus.lease_seconds}s leases can be reclaimed. A session key is intended to serialize work on the same SKU.</p><p class="math">${data.queue.ready} ready · ${data.queue.running} running · ${data.queue.done} done · ${data.queue.dead} dead</p><p class="small muted">This is a local demo queue. Long model calls need a renewed lease or a longer visibility timeout before deploying multiple workers.</p><details><summary>Inspect recent run modes</summary><pre>${esc(data.runs.map(r => `${r.agent} · ${r.mode} · ${r.steps} reads · ${r.tokens} tokens\n${r.outcome}`).join('\n\n') || 'No runs recorded.')}</pre></details></div></div>
      <div class="card"><h3>The model does not choose its own authority</h3><div class="grid3"><div><div class="caption">T1 · automatic</div><p>Below ${money(a.auto_execute_below_eur)}</p><p class="small muted">Only after the deterministic guards pass.</p></div><div><div class="caption">T2 · maker / checker</div><p>${money(a.auto_execute_below_eur)} to below ${money(a.human_signal_above_eur)}</p><p class="small muted">Requires an independent checker. Agentic proposals without one remain pending.</p></div><div><div class="caption">T3 · human</div><p>${money(a.human_signal_above_eur)}+ or KILL</p><p class="small muted">The executor waits for approval. Evidence and the decision remain in the ledger.</p></div></div><p class="small muted">The ledger’s “executed” state authorizes an outbox event. The executor must consume that event for an external shop change to occur. Advertising changes are simulated; no real ad account is connected.</p></div></section>
      <section class="section" id="ml"><div class="num">05 / THE ML, WITH ITS LIMITS</div><h2>A model earns its place<br>by beating the baseline.</h2><p class="lede">The pipeline checks stationarity, rejects leakage, selects features and compares model families on a forward time split with an embargo. Promotion requires beating the naive baselines. The registered result below comes from simulated advertising data.</p><div class="card">${modelTable()}<div class="note">A high R² on a generated demo panel validates this demonstration’s pipeline. It does not establish real-world marketing accuracy. Model scores and availability are shown only when stored or detected here.</div>${data.model ? `<details><summary>Inspect selected features and promotion evidence</summary><pre>${esc(JSON.stringify({selected_features:data.model.features,train_rows:data.model.n_train,test_rows:data.model.n_test,metrics:data.model.out_sample,promotion_reason:data.model.promotion_reason,diagnostics:data.model.diagnostics},null,2))}</pre></details>` : ''}</div></section>
      <div class="footer">Snapshot ${esc(data.generated_at)} · All calculations on this page are read-only. <button class="btn" id="refresh">Refresh evidence</button></div>`;
    el('ad-cell').value = cell; el('verdict-product').value = verdict;
    correctionsResult(); renderBudget(); renderCell(); renderBand(); renderVerdict();
    el('cu-value').textContent = money(cu); el('co-value').textContent = money(co);
    el('service-value').textContent = pct(cu/(cu+co));
    el('service-math').textContent = `${money(cu)} ÷ (${money(cu)} + ${money(co)}) = ${pct(cu/(cu+co))}`;
  }
  page.addEventListener('input', e => {
    if (e.target.id === 'cu' || e.target.id === 'co') {
      if (e.target.id === 'cu') cu = +e.target.value; else co = +e.target.value;
      serviceUpdate();
    }
    if (e.target.id === 'band-ratio') renderBand();
  });
  page.addEventListener('change', e => {
    if (e.target.dataset.fix) { fixes[e.target.dataset.fix] = e.target.checked; correctionsResult(); }
    if (e.target.id === 'inventory-mode') { inventory = e.target.value; serviceUpdate(); }
    if (e.target.id === 'channel-product') { product = e.target.value; renderChannels(); }
    if (e.target.id === 'ad-cell') { cell = e.target.value; renderCell(); }
    if (e.target.id === 'verdict-product') { verdict = e.target.value; renderVerdict(); }
  });
  page.addEventListener('click', async e => {
    if (e.target.id === 'reset-economics') {
      cu = data.variants.v_black.decision.Cu; co = data.variants.v_black.decision.Co;
      el('cu').value = cu; el('co').value = co; serviceUpdate();
    }
    if (e.target.id === 'refresh' || e.target.id === 'retry') load();
    if (e.target.id === 'apply-budget') {
      const amount = +el('budget-amount').value;
      if (!Number.isFinite(amount) || amount <= 0 || amount > 1000000) {
        el('budget-summary').textContent = 'Enter a budget from €1 to €1,000,000.'; return;
      }
      const version = ++budgetVersion;
      el('budget-summary').textContent = 'Recalculating product and channel allocations…';
      try {
        const next = await api('/api/budget?amount=' + encodeURIComponent(amount));
        if (version !== budgetVersion) return;
        budget = next; renderBudget();
      } catch (error) { el('budget-summary').textContent = 'Allocation unavailable. Previous values remain visible. Try again.'; }
    }
  });
  async function load() {
    ++quantityVersion; ++budgetVersion; clearTimeout(quantityTimer);
    try {
      const next = await api('/api/explain');
      if (!next.variants || !next.variants.v_black || !next.variants.v_white) throw new Error('The towel case study is not loaded');
      data = next; budget = data.budget; inventory = 'live';
      Object.keys(fixes).forEach(k => fixes[k] = true); render();
    } catch (error) {
      page.innerHTML = `<div class="error" role="alert"><h2>The engine could not load this view.</h2><p>${esc(error.message)}. Check that the local console is running and its database contains the demo case study.</p><button class="btn" id="retry">Try again</button></div>`;
    }
  }
  load();
})();
