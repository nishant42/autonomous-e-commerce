(function(){
'use strict';
const el=id=>document.getElementById(id);
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={reorder:['Reorder','What stock should we buy?'],marketing_allocator:['Marketing','Which advertising deserves money?'],product_verdict:['Product verdict','Grow it, fix it, or stop it?']};
const kinds={read:'Read evidence',engine:'Calculate',rule:'Apply a rule',model:'ML prediction',judgment:'Bounded judgment',gateway:'Check permission'};
let runs=[],agent='reorder',example='',idx=0,steps=[],groups=[],playing=null,revision=0;
const cache={};
async function api(url){const r=await fetch(url);if(!r.ok)throw Error('Request failed ('+r.status+')');return r.json();}
function run(){return runs.find(r=>r.agent===agent);}
function label(id){return ({v_black:'Black towel',v_white:'White towel',v_grey:'Grey towel',p_towel:'Halden Towel',p_lamp:'Halden Lamp',p_mug:'Halden Mug Set',p_candle:'Halden Candle'})[id]||id.replace(/_/g,' ');}
function segment(r){
 if(agent==='marketing_allocator'){
  const cells=r.trace.filter(s=>s.title.startsWith('decide ')).map(s=>s.title.slice(7));
  if(!cells.length)return [{id:'all',trace:r.trace}];
  return cells.map(id=>({id,trace:r.trace.filter(s=>{
   if(s.title.startsWith('decide '))return s.title==='decide '+id;
   if(s.kind==='gateway')return (s.data?.payload||{}).cell_id===id;
   if(s.kind==='judgment')return s.title.includes(id);
   return true;
  })}));
 }
 const start=agent==='reorder'?['sales_panel','compute_quantities']:['funnel_rates','evidence_pack'];
 const result=[];let active;
 for(const s of r.trace){
  const args=s.data?.args||{},id=args.variant_id||args.product_id;
  if(start.includes(s.title)&&id&&(!active||active.id!==id)){active={id,trace:[]};result.push(active);}
  if(active)active.trace.push(s);
 }
 return result.length?result:[{id:'all',trace:r.trace}];
}
function concise(trace){
 const first=name=>trace.find(s=>s.title===name);
 const prefix=name=>trace.find(s=>s.title.startsWith(name));
 let selected;
 if(agent==='reorder')selected=[first('availability_history')||first('sales_panel'),first('reconstruct demand')||first('compute_quantities'),first('open_orders'),first('newsvendor quantity'),trace.find(s=>s.kind==='gateway')||trace.find(s=>s.kind==='judgment')];
 else if(agent==='marketing_allocator')selected=[first('target cost per order')||first('margin_table'),first('signal health')||first('signal_health'),trace.find(s=>s.kind==='model'),prefix('decide '),trace.find(s=>s.kind==='gateway')];
 else selected=[first('funnel_rates')||first('evidence_pack'),prefix('decompose the funnel'),first('supply check before any verdict')||first('stock_cover'),first('which stage is at fault')||trace.find(s=>s.kind==='judgment'),trace.find(s=>s.kind==='gateway')];
 selected=selected.filter(Boolean);
 return selected.length?selected:trace.filter(s=>s.kind!=='read').slice(0,5);
}
function title(s){
 const map={availability_history:'Was it available to buy?',sales_panel:'Read sales and availability','reconstruct demand':'Estimate the demand we could not see',open_orders:'Avoid buying the same stock twice','newsvendor quantity':'Calculate how much to order',compute_quantities:'Compare the calculated order options','target cost per order':'Set an affordable acquisition target',margin_table:'Work out what one sale is worth','signal health':'Check whether the measurements agree',signal_health:'Check whether the measurements agree','promoted model supplies expected cost per order':'Estimate weekly advertising orders',funnel_rates:'Read the customer buying journey','supply check before any verdict':'Check whether stock explains weak sales',stock_cover:'Check whether stock explains weak sales','which stage is at fault':'Identify what actually needs fixing',evidence_pack:'Read the product evidence'};
 if(map[s.title])return map[s.title];
 if(s.kind==='gateway')return 'Check permission and record the proposal';
 if(s.title.startsWith('decide '))return 'Choose the action for this advertisement';
 if(s.title.startsWith('decompose the funnel'))return 'Find where shoppers are dropping out';
 if(s.kind==='judgment')return 'Choose among the permitted options';
 return s.title.replace(/_/g,' ');
}
function meaning(s){
 const map={availability_history:'An item cannot sell while it is unavailable. This check separates low demand from an empty shelf.',sales_panel:'The agent reads recorded sales and the time this variant was actually buyable.','reconstruct demand':'Estimate demand from buyable days, then adjust for substitution, discounts and returns. The quantity calculation uses demand after returns.',open_orders:'Subtract stock that is already on order. Replaying a decision must not buy the same stock again.','newsvendor quantity':'Compare the cost of a missed sale with the cost of a leftover unit. Use the resulting target, supplier lead time, current stock and case packs to calculate the order.',compute_quantities:'The calculator returns permitted quantities. The language model can choose an option or escalate; it cannot invent a quantity.','target cost per order':'Contribution margin and the configured payback allowance set the target cost per acquired order.',margin_table:'Start with what the business keeps after product cost, shipping, fees and returns.','signal health':'Compare platform-reported orders with the store’s own records. Unhealthy measurement freezes scaling.',signal_health:'Compare platform-reported orders with the store’s own records. Unhealthy measurement freezes scaling.','promoted model supplies expected cost per order':'Ridge estimates weekly orders from advertising signals. Expected orders imply an expected acquisition cost. The rule engine compares that expectation with observed performance.',funnel_rates:'Count how many people reached the product, added to the cart, began checkout and paid. This helps separate a weak product from a broken shop.','supply check before any verdict':'An out-of-stock product has not necessarily failed. Supply constraints can explain weak sales and prevent an unfair stop decision.',stock_cover:'Check whether missing stock explains weak observed sales.','which stage is at fault':'Healthy interest with poor checkout points to a shop problem. Weak demand, poor economics or high refunds point to different remedies.',evidence_pack:'Combine measured orders, supply and review evidence, and funnel data where it exists.'};
 if(map[s.title])return map[s.title];
 if(s.kind==='gateway')return 'The proposal passes through ownership, size and policy checks. Larger actions need a checker or a person. A KILL recommendation always waits for human approval.';
 if(s.title.startsWith('decide '))return 'After exposure, stock, cooldown and fatigue checks, compare acquisition cost with its target: scale, hold, trim or pause.';
 if(s.title.startsWith('decompose the funnel'))return 'Compare each conversion stage with configured benchmark bands. The pattern helps identify a checkout, offer, traffic or price problem.';
 return 'This is a step from the stored execution. Its observed result is shown below; the original data and source are available in technical details.';
}
const fieldNames={units_shipped:'Units shipped',available_days:'Buyable days',unbuyable_days:'Unavailable days',on_hand_now:'Stock on hand',ros_per_available_day:'Units / buyable day',reconstructed_demand_period:'Estimated demand before returns',net_ros:'Daily demand after returns',on_order:'Units already ordered',case_pack:'Units per case',on_hand:'Stock on hand',order_up_to:'Target stock level',qty:'Proposed units',value_eur:'Proposal value (€)',cm_per_unit:'Contribution per order (€)',orders:'Measured orders',spend:'Measured spend (€)',from_eur:'Previous daily budget (€)',to_eur:'Proposed daily budget (€)',expected_orders_7d:'Estimated weekly orders',expected_cpa:'Predicted cost / order (€)',observed_cpa:'Observed cost / order (€)',model:'Forecasting model',verdict:'Verdict',action:'Action',cpa:'Cost / order (€)',target_cpa:'Target cost / order (€)',sessions:'Sessions',pdp_views:'Product-page views',add_to_cart:'Added to cart',checkout_start:'Started checkout',purchase_rate:'Checkout completion rate',refund_rate:'Refund rate',drift_pct:'Order-count difference (%)',healthy:'Measurement healthy',ours:'Orders in store records',platform:'Platform-reported orders',hero_cover_days:'Best-stocked variant cover (days)',worst_cover_days:'Least-stocked variant cover (days)'};
function facts(data){
 if(!data||typeof data!=='object')return '';
 const keys=Object.keys(data).filter(k=>fieldNames[k]&&data[k]!==null&&typeof data[k]!=='object').slice(0,6);
 return keys.map(k=>{let v=data[k];if(typeof v==='number')v=k.endsWith('_rate')?Math.round(v*1000)/10+'%':Number.isInteger(v)?v:Math.round(v*1000)/1000;if(typeof v==='boolean')v=v?'Yes':'No';return `<div class="fact"><small>${fieldNames[k]}</small><b>${esc(v)}</b></div>`;}).join('');
}
function stop(){clearInterval(playing);playing=null;}
function talk(){
 if(agent==='reorder')return '“Sales are what we were able to sell. This agent estimates the demand hidden by stock-outs, then checks economics, supplier terms and existing stock before proposing an order.”';
 if(agent==='marketing_allocator')return '“The model predicts what might happen. The rules decide what to do with that prediction and the observed results. Stock, minimum evidence and cooldown checks can stop a budget change.”';
 return '“Low sales do not automatically mean a bad product. This agent checks whether the problem is the shop, supply, price or product, then recommends a remedy. Stopping a product needs approval.”';
}
function paint(){
 const r=run();if(!r){el('chain').innerHTML='<p class="empty">No recorded execution for this agent.</p>';return;}
 groups=segment(r);
 if(!groups.some(g=>g.id===example))example=(groups.find(g=>g.id===({reorder:'v_black',marketing_allocator:'google_pmax',product_verdict:'p_mug'})[agent])||groups[0]).id;
 el('agents').innerHTML=Object.entries(names).map(([id,n])=>`<button data-agent="${id}" class="${id===agent?'on':''}" aria-pressed="${id===agent}"><b>${n[0]}</b><small>${n[1]}</small></button>`).join('');
 el('example').innerHTML=groups.map(g=>`<option value="${esc(g.id)}">${esc(label(g.id))}</option>`).join('');el('example').value=example;el('example').disabled=el('raw').checked;
 const selected=groups.find(g=>g.id===example);
 steps=el('raw').checked?r.trace:concise(selected.trace);
 idx=Math.max(0,Math.min(idx,steps.length-1));
 el('recording').textContent=`Recorded ${r.started_at} · ${el('raw').checked?'all '+steps.length+' raw steps':steps.length+' key checks for '+label(example)} · recorded mode: ${r.mode}. This is a replay.`;
 el('chain').innerHTML=steps.map((s,i)=>`<button class="step-button ${i===idx?'on':''}" data-step="${i}" aria-current="${i===idx?'step':'false'}"><span class="step-number">${i+1}</span><span><b>${esc(title(s))}</b><small>${kinds[s.kind]||s.kind}</small></span></button>`).join('');
 el('say').textContent=talk();document.body.classList.toggle('show-raw',el('raw').checked);
 detail(steps[idx]);
}
async function detail(s){
 if(!s){el('detail').innerHTML='<p class="empty">No steps in this recording.</p>';return;}
 const version=++revision;let data=s.data||{};
 if(s.kind==='model'&&data[example])data=data[example];
 if(s.kind==='gateway')data={...(data.payload||{}),value_eur:data.value_eur};
 el('detail').innerHTML=`<div class="step-caption">Check ${idx+1} of ${steps.length} · ${kinds[s.kind]||s.kind}</div><h2>${esc(title(s))}</h2><p class="meaning">${esc(meaning(s))}</p><div class="observed">${esc(s.detail||'Recorded evidence is available below.')}</div><div class="fact-grid" id="facts">${facts(data)}</div><div class="step-actions"><button id="prev" ${idx===0?'disabled':''}>← Previous</button><button id="play" class="play">${playing?'Pause':'Play checks'}</button><button id="next" ${idx>=steps.length-1?'disabled':''}>Next check →</button></div><details class="technical" id="technical"><summary>Technical details: evidence and code</summary><h3>Original recorded data</h3><pre>${esc(JSON.stringify(s.data||{},null,2))}</pre>${s.evidence_id?'<h3>Evidence ID</h3><pre>'+esc(s.evidence_id)+'</pre>':''}<h3>Source code</h3><div id="source"><p>Open this section to load the source.</p></div></details>`;
 let ev=s;
 if(s.title==='reconstruct demand')ev=(groups.find(g=>g.id===example)?.trace||[]).find(t=>t.title==='sales_panel')||s;
 if(ev.evidence_id){
  try{const record=cache[ev.evidence_id]||(cache[ev.evidence_id]=await api('/api/evidence/'+encodeURIComponent(ev.evidence_id)));if(version!==revision)return;el('facts').innerHTML=facts(record.result)||facts(data);if(s.kind==='read')el('detail').querySelector('.observed').textContent='The recorded values used for this check:';}
  catch(error){if(version===revision&&el('facts'))el('facts').innerHTML=facts(data);}
 }
}
async function source(){
 const s=steps[idx],version=revision;if(!s?.code?.module){el('source').textContent='No source reference was recorded for this step.';return;}
 try{const d=await api('/api/code?module='+encodeURIComponent(s.code.module)+'&name='+encodeURIComponent(s.code.name));if(version===revision)el('source').innerHTML=d.error?`<p>${esc(d.error)}</p>`:`<pre>${esc(d.file)} · line ${d.line}\n\n${esc(d.source)}</pre>`;}
 catch(error){if(version===revision)el('source').textContent='Source could not be loaded. The recorded decision is still shown above.';}
}
function move(delta){idx=Math.max(0,Math.min(steps.length-1,idx+delta));paint();}
function play(){if(playing){stop();paint();return;}if(idx===steps.length-1)idx=0;playing=setInterval(()=>{if(idx>=steps.length-1){stop();paint();return;}move(1);},3200);paint();}
el('agents').addEventListener('click',e=>{const b=e.target.closest('[data-agent]');if(!b)return;stop();agent=b.dataset.agent;example='';idx=0;el('raw').checked=false;paint();});
el('example').addEventListener('change',e=>{stop();example=e.target.value;idx=0;paint();});
el('raw').addEventListener('change',()=>{stop();idx=0;paint();});
el('chain').addEventListener('click',e=>{const b=e.target.closest('[data-step]');if(b){stop();idx=+b.dataset.step;paint();}});
el('detail').addEventListener('click',e=>{if(e.target.id==='next'){stop();move(1);}if(e.target.id==='prev'){stop();move(-1);}if(e.target.id==='play')play();});
el('detail').addEventListener('toggle',e=>{if(e.target.id==='technical'&&e.target.open)source();},true);
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.key==='ArrowRight'){stop();move(1);}if(e.key==='ArrowLeft'){stop();move(-1);}});
async function load(){stop();try{const d=await api('/api/flow');runs=(d.runs||[]).filter(r=>names[r.agent]);if(!runs.length){el('recording').textContent='No agent executions have been recorded yet.';return;}if(!run())agent=runs[0].agent;paint();}catch(error){el('recording').textContent='Could not load recordings. Use Refresh recordings to retry.';}}
el('refresh').addEventListener('click',load);load();
})();
