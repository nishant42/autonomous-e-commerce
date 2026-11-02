/* DOM integration tests. Install jsdom in a temporary directory, then run:
   NODE_PATH=/tmp/halden-ui-qa/node_modules node engine/tests/explain-ui.cjs
   HALDEN_BASE_URL may point to a different local console. No write actions run. */
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.HALDEN_BASE_URL || 'http://127.0.0.1:8787';
const root = path.resolve(__dirname, '../ui');
const html = fs.readFileSync(path.join(root, 'explain.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'explain.js'), 'utf8');
let checks = 0;
async function waitFor(check, message, timeout=45000) {
  const start = Date.now();
  while (!check()) {
    if (Date.now()-start > timeout) throw new Error('Timed out: '+message);
    await new Promise(resolve => setTimeout(resolve,30));
  }
}
function check(name, fn) { fn(); checks++; console.log('PASS',name); }
(async () => {
  const dom = new JSDOM(html, {url:base+'/explain', runScripts:'outside-only'});
  const w = dom.window, d = w.document;
  w.AbortController = AbortController;
  w.fetch = (url, options) => fetch(base+url,options);
  w.eval(script);
  await waitFor(() => d.getElementById('corrected-demand'),'initial render');
  check('all three agents, harness and ML render', () => {
    for (const id of ['reorder','marketing','verdict','harness','ml']) assert.ok(d.getElementById(id));
    assert.ok(!d.body.textContent.includes('undefined'));
    assert.ok(!d.body.textContent.includes('NaN'));
  });
  check('returns and gross demand are distinguished', () => {
    assert.equal(d.getElementById('corrected-demand').textContent,'9.3');
    assert.ok(d.getElementById('reorder').textContent.includes('11.6'));
    assert.ok(d.getElementById('reorder').textContent.includes('81.8'));
  });
  const toggle = d.querySelector('[data-fix="ret"]');
  toggle.checked=false;toggle.dispatchEvent(new w.Event('change',{bubbles:true}));
  check('returns correction is interactive',()=>assert.equal(d.getElementById('corrected-demand').textContent,'11.6'));
  for (const input of d.querySelectorAll('[data-fix]')) {
    input.checked=false;input.dispatchEvent(new w.Event('change',{bubbles:true}));
  }
  check('switching off all corrections restores shipped units',()=>assert.equal(d.getElementById('corrected-demand').textContent,'20.0'));
  const mode=d.getElementById('inventory-mode');
  mode.value='before';mode.dispatchEvent(new w.Event('change',{bubbles:true}));
  await waitFor(()=>d.getElementById('quantity-status').textContent.startsWith('Scenario calculated'),'before-order calculation');
  check('before-order scenario calls the Python engine',()=>assert.ok(d.getElementById('quantity-output').textContent.includes('60 units')));
  const slider=d.getElementById('co'); slider.focus();slider.value='30';slider.dispatchEvent(new w.Event('input',{bubbles:true}));
  await waitFor(()=>d.getElementById('quantity-status').textContent.startsWith('Scenario calculated'),'slider calculation');
  check('slider remains focused and quantity really changes',()=> {
    assert.equal(d.activeElement,slider);
    assert.ok(!d.getElementById('quantity-output').textContent.includes('60 units'));
    assert.ok(parseFloat(d.getElementById('service-value').textContent)<50);
  });
  d.getElementById('reset-economics').click();
  await waitFor(()=>d.getElementById('quantity-status').textContent.startsWith('Scenario calculated'),'reset calculation');
  check('reset restores engine economics',()=>assert.ok(d.getElementById('quantity-output').textContent.includes('60 units')));
  const ratio=d.getElementById('band-ratio');
  for (const [value,action] of [[80,'scale'],[81,'hold'],[100,'hold'],[101,'reduce'],[150,'reduce'],[151,'pause']]) {
    ratio.value=value;ratio.dispatchEvent(new w.Event('input',{bubbles:true}));
    check('CPA band boundary '+value+'%',()=>assert.ok(d.getElementById('band-result').textContent.includes(action)));
  }
  const selected=d.getElementById('verdict-product');
  const mug=[...selected.options].find(o=>o.textContent.includes('Mug'));
  selected.value=mug.value;selected.dispatchEvent(new w.Event('change',{bubbles:true}));
  check('verdict switches to measured site diagnosis',()=>assert.ok(d.getElementById('verdict-output').textContent.includes('FIX_SITE')));
  const candle=[...selected.options].find(o=>o.textContent.includes('Candle'));
  selected.value=candle.value;selected.dispatchEvent(new w.Event('change',{bubbles:true}));
  check('kill displays the human-approval boundary',()=>assert.ok(d.getElementById('verdict-output').textContent.includes('human approval')));
  const channels=d.getElementById('channel-product');
  channels.value='p_yoghurt';channels.dispatchEvent(new w.Event('change',{bubbles:true}));
  check('unfunded product explains absent channel allocation',()=>assert.ok(d.getElementById('channel-output').textContent.includes('No channel allocation')));
  const amount=d.getElementById('budget-amount');
  amount.value='5000';d.getElementById('apply-budget').click();
  await waitFor(()=>!d.getElementById('budget-summary').textContent.startsWith('Recalculating'),'budget recalculation');
  check('budget recalculates through the real allocator',()=>assert.ok(d.getElementById('budget-summary').textContent.includes('€500.00 exploration')));
  amount.value='-1';d.getElementById('apply-budget').click();
  check('invalid budgets are handled visibly',()=>assert.ok(d.getElementById('budget-summary').textContent.includes('Enter a budget')));
  const broken = new JSDOM(html,{url:base+'/explain',runScripts:'outside-only'});
  broken.window.AbortController=AbortController;
  broken.window.fetch=()=>Promise.reject(new Error('offline'));
  broken.window.eval(script);
  await waitFor(()=>broken.window.document.getElementById('retry'),'error message');
  check('network failure offers retry instead of endless loading',()=>assert.ok(broken.window.document.querySelector('[role="alert"]')));
  broken.window.fetch=(url,options)=>fetch(base+url,options);
  broken.window.document.getElementById('retry').click();
  await waitFor(()=>broken.window.document.getElementById('corrected-demand'),'error recovery');
  check('retry recovers the full view',()=>assert.ok(broken.window.document.getElementById('marketing')));
  dom.window.close();broken.window.close();
  console.log(checks+' interaction checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
