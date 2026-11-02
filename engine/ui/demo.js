(function () {
  'use strict';
  const el = id => document.getElementById(id);
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = (v,d=1) => Number.isFinite(Number(v)) && v !== null ? Number(v).toLocaleString('en-GB',{maximumFractionDigits:d}) : '—';
  const eur = v => '€'+n(v,2), pct = v => n(v*100)+'%';
  const names = {reorder:'Reorder',marketing_allocator:'Marketing',product_verdict:'Product verdict'};
  let data, agent='reorder', variant='v_black', ad='google_pmax', product, rules=[], replayTimer, replayIndex=0;
  // Keep the storefront on the origin used by its Next.js development server.
  const local = ['localhost', '127.0.0.1'].includes(location.hostname);
  function setShop(url) {
    el('shop-frame').src=url;el('open-shop').href=url;
  }
  if (local) setShop('http://localhost:8000/dk/store');
  else fetch('/api/public-config').then(r => {
    if (!r.ok) throw new Error('Shop configuration unavailable');
    return r.json();
  }).then(config => {
    if (new URL(config.shop_url).protocol !== 'https:') throw new Error('HTTPS required');
    setShop(config.shop_url);
  }).catch(() => {
    el('open-shop').textContent='Shop connection unavailable';
    el('open-shop').removeAttribute('href');
  });
  async function api(url,body) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);
    try {
      const r=await fetch(url,{signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
      const result=await r.json();if(!r.ok||result.error)throw new Error(result.error||'Request failed');return result;
    } finally {clearTimeout(timer);}
  }
  function mode(behind) {
    el('shop-view').hidden=behind;el('agents-view').hidden=!behind;
    el('view-shop').classList.toggle('active',!behind);el('view-agents').classList.toggle('active',behind);
    el('view-shop').setAttribute('aria-pressed',String(!behind));el('view-agents').setAttribute('aria-pressed',String(behind));
    if(!behind)el('drawer').hidden=true;
  }
  el('view-shop').addEventListener('click',()=>mode(false));
  el('view-agents').addEventListener('click',()=>mode(true));
  function rule(id,title,value,short,why,observed,source,state='pass') {return {id,title,value,short,why,observed,source,state};}
  function reorderRules() {
    const v=data.variants[variant],r=v.reconstruction,d=v.decision;
    return [
      [rule('availability','Was it actually buyable?',`${n(r.available_days)} / ${r.period_days} days`,'Divide by buyable days, not calendar days.','Low sales can mean an empty shelf. The engine estimates a daily rate only over the time customers could buy this variant.',{shipped:r.units_shipped,buyable_days:r.available_days,rate_per_buyable_day:r.ros_per_available_day},'engines/demand.py · reconstruct',r.available_days<r.period_days?'warn':'pass'),
       rule('corrections','Did discounts or substitutions inflate sales?',`${n(r.reconstructed_demand_period)} estimated units`,'Before returns, at the intended price.','A sibling stock-out can temporarily lift sales. Discounts can do the same. The engine caps daily spikes and applies substitution and price factors.',{substitution_share:r.substitution_share,price_factor:r.price_factor,spike_cap:r.spike_cap_applied},'engines/demand.py · reconstruct'),
       rule('returns','How much came back?',pct(r.return_rate),'Remove returns before sizing the order.','A shipped unit is not necessarily a retained sale. The quantity engine uses net demand after the measured return rate.',{return_rate:r.return_rate,net_demand_period:r.net_demand_period,net_daily_demand:r.net_ros},'engines/demand.py · reconstruct')],
      [rule('economics','Which mistake is more expensive?',`${pct(d.service_level)} target quantile`,'Missed margin versus leftover cost.','The target demand quantile is Cu / (Cu + Co). An expensive missed sale raises it; expensive leftovers lower it.',{missed_sale_cost:d.Cu,leftover_cost:d.Co,service_level:d.service_level},'engines/quantity.py · service_level'),
       rule('inventory','What is already covered?',`${n(d.on_hand,0)} here + ${n(d.on_order,0)} ordered`,'Subtract both before buying again.','Protection-interval demand plus the risk allowance gives a stock target. On-hand stock and recorded orders reduce the new requirement.',{protection_days:d.protection_interval_days,mean_demand:d.demand_mu,on_hand:d.on_hand,on_order:d.on_order},'engines/quantity.py · order'),
       rule('quantity','How many boxes are needed?',`${d.qty} units · ${eur(d.capital_eur)}`,'Round to packs and apply cover limits.','The order is rounded to the supplier case pack, checked against minimum order quantity and capped by stock cover. Zero is a valid result after a previous purchase order.',d,'engines/quantity.py · order')],
      gateRules(d.capital_eur,'reorder')];
  }
  function marketingRules() {
    const c=data.marketing.cells.find(c=>c.cell_id===ad),e=c.explanation,p=data.marketing.policy;
    return [
      [rule('margin','What is an order worth?',eur(data.marketing.margin.cm_per_unit),'Margin sets the acquisition target.','The target CPA is contribution margin multiplied by the configured payback factor. Advertising measurements in this case study are simulated.',{margin:data.marketing.margin.cm_per_unit,payback:p.payback_factor,target_CPA:e.target_cpa},'engines/allocator.py · target_cpa'),
       rule('exposure','Has it earned a verdict?',`${c.orders} orders · ${c.days} days`,'Wait for conversions or enough spend.','An ad needs enough conversions or enough exhausted test spend, plus a minimum number of days. Too little evidence means hold.',{orders:c.orders,min_orders:p.min_conversions,spend:c.spend,min_spend:p.spend_exhaustion_multiple*e.target_cpa,days:c.days,min_days:p.min_days},'engines/allocator.py · exposure_met'),
       rule('measurement','Can the measurement be trusted?',data.marketing.health.healthy?'Counts agree':'Scaling frozen','Compare platform counts with shop counts.','Scaling freezes when platform order counts drift too far from the store’s own records.',data.marketing.health,'engines/allocator.py · signal_health',data.marketing.health.healthy?'pass':'warn')],
      [rule('cost','Is the ad inside its target?',`${eur(e.cost_per_order)} / ${eur(e.target_cpa)}`,'≤80% scale · ≤100% hold · ≤150% trim.','After guard checks, the deterministic bands compare CPA with the target. A promoted model may inform expected CPA; observation wins extreme disagreement.',{observed_CPA:e.cost_per_order,model_CPA:e.model_cpa,CPA_used:e.cpa_used,target:e.target_cpa},'engines/allocator.py · decide_cell'),
       rule('cooldown','Was the ad changed recently?',e.hours_since_change<p.cooldown_hours_per_cell?'Wait 48 hours':'Outside cooldown','Avoid repeatedly changing the same ad.','The gate reads the stored last-change timestamp. Model judgment cannot bypass the cooldown.',{hours_since_change:e.hours_since_change,required_hours:p.cooldown_hours_per_cell},'agents/marketing_agentic.py · options_for',e.hours_since_change<p.cooldown_hours_per_cell?'warn':'pass'),
       rule('addecision','What action survives the checks?',e.action,`${eur(e.daily_now)} → ${eur(e.budget)} per day`,'Stock cover, learning, creative fatigue, signal health and cooldown can decide before the CPA bands. The model may choose only a guarded action.',{reason:e.reason,permitted_actions:e.permitted_actions,budgets:e.budget_each_action_would_set},'agents/marketing_agentic.py · options_for')],
      gateRules(Math.abs(e.budget-e.daily_now),'marketing')];
  }
  function verdictRules() {
    const v=data.verdicts.find(v=>v.product_id===product),e=v.evidence;
    return [
      [rule('productexposure','Has the product had a fair test?',v.exposure_met?'Enough evidence':'Keep testing',`${e.units_sold} units · ${e.days_with_sales} selling days`,'Without enough orders and selling days, or the required funnel exposure, the product cannot fairly be condemned.',{exposure_met:v.exposure_met,units:e.units_sold,selling_days:e.days_with_sales,funnel:v.funnel?{sessions:v.funnel.sessions,spend:v.funnel.spend}:null},'engines/verdict_evidence.py · build',v.exposure_met?'pass':'warn'),
       rule('supply','Was supply the real problem?',v.supply_limited?'Supply constrained':'No major supply gap','An empty shelf does not prove weak demand.','Demand lost to stock-outs can explain weak observed sales. Supply-limited weakness blocks KILL unless there is direct adverse product evidence.',{unbuyable_share:e.share_of_days_unbuyable,lost_demand:e.demand_lost_to_stockouts,supply_limited:v.supply_limited},'engines/verdict_evidence.py · build',v.supply_limited?'warn':'pass'),
       rule('reviews','What do the reviews say?',e.sentiment.negative_share===null?'No labels yet':pct(e.sentiment.negative_share)+' negative',`${e.sentiment.classified} stored reviews classified`,'A sentiment model reads review text. The verdict engine consumes the resulting labels. Imported Medusa reviews belong to this local demo shop.',e.sentiment,'engines/live_verdict.py · sentiment_for',e.sentiment.negative_share>=.5?'warn':'pass')],
      [rule('funnel','Where do customers drop out?',v.diagnosis?v.diagnosis.verdict:'No funnel measurements',v.diagnosis?'Compare each stage with configured bands.':'Use measured orders, supply and reviews.','Healthy interest with poor checkout completion points to the shop. Poor add-to-cart or high refunds can point to the offer or product. An imported shop without session data is judged on a narrower evidence set.',v.diagnosis||{source:v.source},'engines/funnel.py · diagnose'),
       rule('verdictdecision','Which decision fits the evidence?',v.engine_verdict,v.engine_reason,'This is the deterministic diagnosis. A tool-using model can investigate and choose a permitted verdict, subject to exposure and supply constraints.',{decision:v.engine_verdict,allowed:v.permitted_verdicts,reason:v.engine_reason},'engines/verdict_evidence.py · build'),
       rule('fix','What happens first?',v.actions[0]||'Keep observing','One concrete next action.','The agent chooses among computed remedies or recommends no fix. These recommendations do not bypass the action gate.',{actions:v.actions},'agents/verdict_agentic.py · handle')],
      gateRules(0,'verdict',v.engine_verdict==='KILL')];
  }
  function gateRules(value,type,kill=false) {
    const a=data.policy.autonomy,tier=kill||value>=a.human_signal_above_eur?'Human approval':value>=a.auto_execute_below_eur?'Independent check':'Automatic tier';
    return [rule('ownership','Is this action owned by this agent?','Typed proposal','Agents cannot call shop writes directly.','The gate validates the action schema and which agent owns the intent. Execution credentials stay outside the model.',{owner:agent,intent:type==='reorder'?'propose_reorder':type==='marketing'?'propose_budget_change':'publish_verdict'},'core/gateway.py · INTENTS'),
      rule('authority','Who is allowed to approve it?',tier,kill?'KILL always waits for a person.':`${eur(value)} compared with the policy thresholds.`,'Small reversible actions can pass automatically after guards. Medium actions need a checker. Larger actions and KILL require a person.',{proposal_value:value,automatic_below:a.auto_execute_below_eur,human_at:a.human_signal_above_eur,kill_requires_human:kill},'core/gateway.py · _tier',tier==='Human approval'?'warn':'pass'),
      rule('audit','Where is the decision recorded?','Ledger → outbox → executor','A record is kept even for refusals.','A permitted proposal and its outbox event commit together. The executor must consume the event before the external shop changes. This read-only tree does not submit proposals.',{queue:data.queue,rule_evaluation:'read-only'},'core/gateway.py · propose')];
  }
  function outcome() {
    if(agent==='reorder') {const v=data.variants[variant],d=v.decision;return {title:d.qty?`Propose ${d.qty} units for ${eur(d.capital_eur)}`:'No additional order needed',why:d.qty?'Demand, economics, inventory and pack constraints produced this quantity.':`${d.on_hand} units on hand and ${d.on_order} already recorded on order cover the current target.`,gate:d.capital_eur>=2000?'Checker / human tier':'Small-order tier'};}
    if(agent==='marketing_allocator') {const e=data.marketing.cells.find(c=>c.cell_id===ad).explanation;return {title:`${e.action.replace(/_/g,' ')} · ${eur(e.budget)} / day`,why:e.reason,gate:'Guarded budget proposal'};}
    const v=data.verdicts.find(v=>v.product_id===product);return {title:v.engine_verdict,why:v.engine_reason,gate:v.engine_verdict==='KILL'?'Wait for human approval':'Publish guarded verdict'};
  }
  function contextOptions() {
    if(agent==='reorder')return Object.entries(data.variants).map(([id,v])=>`<option value="${esc(id)}">${esc(v.label||v.name)} · ${id.startsWith('v_')?'case study':'shop'}</option>`).join('');
    if(agent==='marketing_allocator')return data.marketing.cells.map(c=>`<option value="${esc(c.cell_id)}">${esc(c.cell_id)}${c.is_holdout?' · holdout':''}</option>`).join('');
    return data.verdicts.map(v=>`<option value="${esc(v.product_id)}">${esc(v.name)} · ${v.product_id.startsWith('med_')?'shop':'case study'}</option>`).join('');
  }
  function paint() {
    el('agent-row').innerHTML=Object.entries(names).map(([id,title],i)=>`<button class="agent ${agent===id?'active':''}" data-agent="${id}" aria-pressed="${agent===id}"><small>Agent ${i+1}</small><strong>${title}</strong><span>${['What and how much to buy','Where the ad money should go','Keep, fix, reprice or stop'][i]}</span><span class="result">${agent===id?'↓ Rules expanded':'Click to see its rules'}</span></button>`).join('');
    const groups=agent==='reorder'?reorderRules():agent==='marketing_allocator'?marketingRules():verdictRules();
    rules=groups.flat();
    el('tree').innerHTML=`<div class="tree-root"><strong>${esc(names[agent])} · the checks behind its decision</strong><label class="context">Investigate <select id="context" aria-label="Investigate">${contextOptions()}</select></label></div><div class="branch-trunk" aria-hidden="true"></div><div class="branches">${groups.map((group,i)=>`<section class="branch-group"><div class="branch-label">${['1 · Read the evidence','2 · Apply the decision rules','3 · Check permission to act'][i]}</div><div class="leaf-list">${group.map(r=>`<button class="rule" data-rule="${r.id}"><span class="state ${r.state}" aria-hidden="true"></span><b>${esc(r.title)}</b><span class="value">${esc(r.value)}</span><small>${esc(r.short)}</small></button>`).join('')}</div></section>`).join('')}</div>`;
    el('context').value=agent==='reorder'?variant:agent==='marketing_allocator'?ad:product;
    const o=outcome();el('outcome').innerHTML=`<div><div class="caption">Current rule result · no action sent from this view</div><h2>${esc(o.title)}</h2><p>${esc(o.why)}</p></div><div class="gate"><div class="caption">↓ Through the gate</div><strong>${esc(o.gate)}</strong></div>`;
    el('shop-count').textContent=`${data.shop_counts.products} products · ${data.shop_counts.order_lines} order lines`;
  }
  function showRule(id) {
    const r=rules.find(r=>r.id===id);if(!r)return;
    el('drawer-body').innerHTML=`<p class="eyebrow">${esc(names[agent])} / decision branch</p><h2>${esc(r.title)}</h2><div class="observed">${esc(r.value)}</div><h3>Why this check exists</h3><p>${esc(r.why)}</p><h3>What the engine read or calculated</h3><pre>${esc(JSON.stringify(r.observed,null,2))}</pre><details><summary>Code reference</summary><pre>${esc(r.source)}</pre></details>`;
    el('drawer').hidden=false;
  }
  function stopReplay() {clearInterval(replayTimer);replayTimer=null;el('replay').textContent='Replay last run';document.querySelectorAll('.rule.replaying').forEach(e=>e.classList.remove('replaying'));}
  function replay() {
    if(replayTimer){stopReplay();return;}
    const run=(data.traces||[]).find(r=>r.agent===agent);
    if(!run||!run.trace.length){el('notice').textContent='No recorded run for this agent yet. The tree shows the current engine evaluation.';return;}
    replayIndex=0;el('replay').textContent='Stop replay';
    const mapping={sales_panel:'corrections',availability_history:'availability',lost_demand_signals:'availability',returns_by_variant:'returns',economics:'economics',supplier_terms:'quantity',open_orders:'inventory',cash_position:'authority',margin_table:'margin',stock_cover:'supply',signal_health:'measurement',ad_metrics_panel:'cost',creative_history:'cooldown',funnel_rates:'funnel',portfolio_memory:'fix',compute_quantities:'quantity',band_options:'addecision',evidence_pack:'verdictdecision'};
    function step() {
      if(replayIndex>=run.trace.length){stopReplay();el('notice').textContent=`Replay complete · ${run.mode} · recorded ${run.started_at}`;return;}
      const s=run.trace[replayIndex++];
      el('notice').textContent=`RECORDED RUN · ${run.mode} · ${run.started_at} · ${replayIndex}/${run.trace.length}: ${s.title} — ${s.detail||''}`;
      document.querySelectorAll('.rule.replaying').forEach(e=>e.classList.remove('replaying'));
      let id=mapping[s.title]||(s.kind==='gateway'?'authority':s.kind==='judgment'?(agent==='reorder'?'quantity':agent==='marketing_allocator'?'addecision':'verdictdecision'):null);
      if(!id)id=agent==='reorder'?'quantity':agent==='marketing_allocator'?'addecision':'verdictdecision';
      const node=document.querySelector(`[data-rule="${id}"]`);if(node)node.classList.add('replaying');
      el('drawer-body').innerHTML=`<p class="eyebrow">Recorded agent run · step ${replayIndex}</p><h2>${esc(s.title)}</h2><p>${esc(s.detail)}</p><h3>Recorded evidence</h3><pre>${esc(JSON.stringify(s.data||{},null,2))}</pre><p>${esc(run.mode)} · ${esc(run.started_at)}</p>${s.evidence_id?'<p>Evidence ID: '+esc(s.evidence_id)+'</p>':''}`;
      el('drawer').hidden=false;
    }
    step();replayTimer=setInterval(step,1800);
  }
  async function load(message) {
    try {
      data=await api('/api/demo-data');
      if(!data.variants.v_black)throw new Error('Towel case study is missing');
      if(!product)product=(data.verdicts.find(v=>v.engine_verdict==='KILL')||data.verdicts[0]).product_id;
      if(!data.variants[variant])variant='v_black';
      paint();el('notice').textContent=message||`Current rule evaluation · ${data.shop_counts.order_lines} imported shop order lines · choose an agent below. Advertising is simulated.`;
    } catch(error) {el('notice').textContent='Could not load the engine. Use Refresh from shop to retry. '+error.message;}
  }
  el('agent-row').addEventListener('click',e=>{const b=e.target.closest('[data-agent]');if(!b)return;stopReplay();agent=b.dataset.agent;el('drawer').hidden=true;paint();});
  el('tree').addEventListener('click',e=>{const b=e.target.closest('[data-rule]');if(b)showRule(b.dataset.rule);});
  el('tree').addEventListener('change',e=>{if(e.target.id!=='context')return;stopReplay();if(agent==='reorder')variant=e.target.value;else if(agent==='marketing_allocator')ad=e.target.value;else product=e.target.value;el('drawer').hidden=true;paint();});
  el('close-detail').addEventListener('click',()=>{el('drawer').hidden=true;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')el('drawer').hidden=true;});
  el('replay').addEventListener('click',replay);
  el('refresh').addEventListener('click',async()=>{
    stopReplay();el('refresh').disabled=true;el('notice').textContent='Reading products, orders and stock from the existing Medusa shop…';
    try {const result=await api('/api/demo-sync',{});await load(`Shop refreshed · ${result.new_order_lines} new order lines · ${result.orders} total imported lines. Rules recalculated; no shop actions submitted.`);}
    catch(error){el('notice').textContent='Shop refresh failed. The previous evidence remains visible. '+error.message;}
    finally{el('refresh').disabled=false;}
  });
  const system={shop:'The existing Medusa storefront handles products, carts and checkout. It is embedded in the Shop view; it has not been rebuilt here.',adapter:'The adapter reads products, orders and inventory from Medusa’s API into the engine’s tables. Refresh from shop imports new facts without changing the shop.',memory:'Stored sales, availability, reviews and ad measurements are the evidence. The durable queue hands work to agents; the gate writes authorized proposals to the ledger and outbox.'};
  document.querySelectorAll('[data-system]').forEach(b=>b.addEventListener('click',()=>{el('system-detail').hidden=false;el('system-detail').textContent=system[b.dataset.system];}));
  if(location.hash==='#agents')mode(true);
  load();
})();
