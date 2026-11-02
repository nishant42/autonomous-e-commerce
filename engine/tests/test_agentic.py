"""Regression tests for the interview's actual agent and execution boundaries.

Uses an isolated seeded database and a scripted model protocol, never a paid
provider, a live shop write, or the user's demo database.
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import bus, db, gateway, harness, model
from db import seed
from agents import marketing_agentic, reorder_agentic, verdict_agentic, tools
from engines import allocator, demand, explanation, quantity, verdict_evidence


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = sqlite3.connect(':memory:', isolation_level=None)
        cls.baseline.row_factory = sqlite3.Row
        cls.baseline.executescript(Path(db.SCHEMA).read_text())
        seed.run(cls.baseline)

    def setUp(self):
        self.conn = sqlite3.connect(':memory:', isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.baseline.backup(self.conn)
        self.providers = patch.object(model, 'available', return_value=False)
        self.providers.start()
        self.model_view = patch.object(allocator, 'model_view', return_value={})
        self.model_view.start()

    def tearDown(self):
        self.model_view.stop()
        self.providers.stop()
        self.conn.close()

    def scripted(self, tool, args, answer):
        def loop(task, spec, executor, **kwargs):
            value, eid = executor(tool, args)
            chosen = answer(value) if callable(answer) else answer
            trace = [{'tool':tool, 'args':args, 'result':value, 'evidence_id':eid, 'ok':True}]
            kwargs['on_event']('tool_call', trace[0])
            return {'answer':chosen, 'trace':trace, 'totals':{'steps':2,'tokens_in':100,'tokens_out':20}, 'parsed':True}
        return loop

    def run_model(self, fn, payload, tool, args, answer):
        with patch.object(model, 'available', return_value=True), patch.object(model, 'agent_loop',
                side_effect=self.scripted(tool,args,answer)):
            return fn(self.conn,payload)

    def test_required_tools_are_granted(self):
        for config, specs in [('marketing_allocator',marketing_agentic.TOOL_SPEC),('product_verdict',verdict_agentic.TOOL_SPEC)]:
            granted = harness.load_config(config)['reads']
            self.assertTrue(all(s['name'] in granted for s in specs))

    def test_reorder_fallback_has_evidence_and_is_idempotent(self):
        payload = {'variants':['v_black'],'period':'same'}
        first = reorder_agentic.handle(self.conn,payload)[0]
        second = reorder_agentic.handle(self.conn,payload)[0]
        self.assertGreater(first['decision']['quantity'],0)
        self.assertNotEqual(first['ledger']['status'],'rejected')
        self.assertTrue(json.loads(first['ledger']['evidence']))
        # An existing purchase reduces the next requirement rather than doubling it.
        self.assertEqual(second['decision']['quantity'],0)
        self.assertEqual(db.scalar(self.conn,"SELECT COUNT(*) FROM ledger WHERE intent='propose_reorder'"),1)

    def test_reorder_accepts_computed_option_only(self):
        rows = self.run_model(reorder_agentic.handle,{'variants':['v_black']},'compute_quantities',{'variant_id':'v_black'},
             lambda value: {'action':'order','option':'recommended','quantity':value['options']['recommended']['quantity'],'why':'The computed option covers demand.'})
        self.assertEqual(rows[0]['decision']['source'],'agent')
        run = db.one(self.conn,'SELECT * FROM agent_run ORDER BY rowid DESC LIMIT 1')
        self.assertEqual(run['tokens'],120)

    def test_reorder_rejects_invented_quantity(self):
        rows = self.run_model(reorder_agentic.handle,{'variants':['v_black']},'compute_quantities',{'variant_id':'v_black'},
                              {'action':'order','option':'recommended','quantity':9999,'why':'Order more.'})
        self.assertNotEqual(rows[0]['decision']['source'],'agent')
        self.assertNotEqual(rows[0]['decision']['quantity'],9999)

    def test_model_cannot_skip_required_evidence(self):
        with patch.object(model,'available',return_value=True), patch.object(model,'agent_loop',return_value={
                'answer':{'action':'scale','why':'Looks profitable.'},'trace':[], 'totals':{}}):
            row = marketing_agentic.handle(self.conn,{'product_id':'p_towel','cells':['google_pmax']})[0]
        self.assertEqual(row['decision']['source'],'rules')

    def test_model_cannot_read_another_product(self):
        cfg = harness.load_config('product_verdict')
        h = harness.Harness(self.conn,'product_verdict',cfg)
        h.register('margin_table',tools.margin_table)
        with patch.object(model,'available',return_value=True), patch.object(model,'agent_loop',
                side_effect=self.scripted('margin_table',{'product_id':'p_lamp'}, {'why':'Read another product.'})):
            out, _ = h.investigate('test',verdict_agentic.TOOL_SPEC,{'product_id':['p_towel']},['margin_table'])
        self.assertIsNone(out)
        self.assertEqual(db.scalar(self.conn,'SELECT COUNT(*) FROM evidence'),0)

    def test_model_unsupported_number_falls_back(self):
        row = self.run_model(marketing_agentic.handle,{'product_id':'p_towel','cells':['google_pmax']},
               'band_options',{'cell_id':'google_pmax'}, {'action':'hold','why':'It needs 987654321 orders.'})[0]
        self.assertEqual(row['decision']['source'],'rules')

    def test_marketing_valid_judgment_and_trace(self):
        row = self.run_model(marketing_agentic.handle,{'product_id':'p_towel','cells':['google_pmax']},
               'band_options',{'cell_id':'google_pmax'}, {'action':'hold','why':'Keep measuring this ad.'})[0]
        self.assertEqual(row['decision']['source'],'agent')
        self.assertTrue(row['tool_calls'])

    def test_marketing_cannot_scale_during_cooldown(self):
        self.conn.execute("INSERT INTO cooldown VALUES (?,?)",('budget:google_pmax',db.now()))
        row = self.run_model(marketing_agentic.handle,{'product_id':'p_towel','cells':['google_pmax']},
               'band_options',{'cell_id':'google_pmax'}, {'action':'scale','why':'Increase spending.'})[0]
        self.assertEqual(row['decision']['action'],'hold')
        self.assertEqual(list(row['options']),['hold'])
        self.assertIsNone(row['ledger'])

    def test_marketing_cannot_scale_without_exposure(self):
        self.conn.execute("UPDATE ad_metrics SET orders=0,spend=1 WHERE cell_id='google_pmax'")
        row = self.run_model(marketing_agentic.handle,{'product_id':'p_towel','cells':['google_pmax']},
               'band_options',{'cell_id':'google_pmax'}, {'action':'scale','why':'Increase spending.'})[0]
        self.assertEqual(row['decision']['action'],'hold')
        self.assertEqual(list(row['options']),['hold'])

    def test_fallback_verdict_distinguishes_site_and_product(self):
        rows = verdict_agentic.handle(self.conn,{'products':['p_mug','p_candle']})
        self.assertEqual(rows[0]['decision']['verdict'],'FIX_SITE')
        self.assertEqual(rows[1]['decision']['verdict'],'KILL')
        self.assertEqual(rows[1]['ledger']['status'],'pending_human')
        self.assertTrue(all(json.loads(r['ledger']['evidence']) for r in rows))

    def test_invalid_confidence_is_rejected(self):
        for value in ('nonsense',float('nan'),float('inf'),-1,2,True):
            with self.subTest(value=value):
                row = self.run_model(verdict_agentic.handle,{'products':['p_mug'],'period':str(value)},
                      'evidence_pack',{'product_id':'p_mug'}, {'verdict':'FIX_SITE','confidence':value,'why':'Repair checkout.','first_fix':'none'})[0]
                self.assertEqual(row['decision']['source'],'engine default')

    def test_valid_verdict_and_kill_always_waits(self):
        row = self.run_model(verdict_agentic.handle,{'products':['p_candle']},'evidence_pack',{'product_id':'p_candle'},
             {'verdict':'KILL','confidence':.8,'why':'Refund evidence indicates product trouble.','first_fix':'none'})[0]
        self.assertEqual(row['decision']['source'],'agent')
        self.assertEqual(row['ledger']['status'],'pending_human')

    def test_insufficient_exposure_cannot_be_killed(self):
        self.conn.execute("DELETE FROM funnel_daily WHERE product_id='p_mug'")
        self.conn.execute("DELETE FROM sales_fact WHERE variant_id IN (SELECT id FROM variant WHERE product_id='p_mug')")
        row = self.run_model(verdict_agentic.handle,{'products':['p_mug']},'evidence_pack',{'product_id':'p_mug'},
             {'verdict':'KILL','confidence':.8,'why':'Stop this product.','first_fix':'none'})[0]
        self.assertEqual(row['decision']['verdict'],'CONTINUE_TEST')

    def test_submedian_service_level_changes_quantile(self):
        low = demand.over_horizon({'net_ros':10,'dispersion':1},7,.43)
        self.assertLess(low['z'],0)
        self.assertLess(low['quantile'],low['mu'])

    def test_explanation_matches_engine_and_is_read_only(self):
        before = self.conn.total_changes
        data = explanation.snapshot(self.conn)
        black = data['variants']['v_black']
        self.assertEqual(black['before_order']['qty'],60)
        w = data['variants']['v_white']['reconstruction']
        factors = w['correction_factors']
        calculated = w['spike_capped_units']/w['available_days']*w['period_days']*math.prod(factors.values())
        self.assertAlmostEqual(calculated,w['net_demand_period'],delta=.05)
        self.assertEqual(self.conn.total_changes,before)

    def test_quantity_preview_uses_economics_and_inventory(self):
        before = self.conn.total_changes
        high = explanation.quantity_preview(self.conn,{'cu':50,'co':1,'inventory':'before'})
        low = explanation.quantity_preview(self.conn,{'cu':1,'co':30,'inventory':'before'})
        self.assertGreater(high['qty'],low['qty'])
        self.assertEqual(self.conn.total_changes,before)
        for value in (float('nan'),float('inf'),-1,0):
            with self.assertRaises(ValueError): explanation.quantity_preview(self.conn,{'cu':value,'co':1})

    def test_gateway_uses_database_cooldown(self):
        self.conn.execute('INSERT INTO cooldown VALUES (?,?)',('budget:google_pmax',db.now()))
        row = gateway.propose(self.conn,'marketing_allocator','propose_budget_change',
                {'cell_id':'google_pmax','from_eur':100.0,'to_eur':110.0},harness.load_config('policy'),
                ctx={'hours_since_change':999})
        self.assertEqual(row['status'],'rejected')
        self.assertIn('cooldown',row['reason'])

    def test_ledger_and_outbox_are_atomic(self):
        with patch.object(bus,'emit',side_effect=RuntimeError('outbox unavailable')):
            with self.assertRaises(RuntimeError):
                gateway.propose(self.conn,'product_verdict','publish_verdict',
                    {'product_id':'p_mug','verdict':'FIX_SITE','confidence':.8},harness.load_config('policy'))
        self.assertEqual(db.scalar(self.conn,'SELECT COUNT(*) FROM ledger'),0)

    def test_queue_retries_stop_on_fifth_attempt(self):
        with patch.dict(bus.HANDLERS, {'test.fail':lambda c,p: (_ for _ in ()).throw(RuntimeError('fail'))}):
            bus.publish(self.conn,'test.fail',{},'test')
            for _ in range(bus.MAX_ATTEMPTS):
                self.conn.execute("UPDATE work_queue SET run_after='2000-01-01'")
                bus.run_worker(self.conn,max_jobs=1,verbose=False)
        row = db.one(self.conn,"SELECT * FROM work_queue WHERE topic='test.fail'")
        self.assertEqual(row['status'],'dead')
        self.assertEqual(row['attempts'],bus.MAX_ATTEMPTS)

    def test_queue_skips_busy_session_and_claims_unrelated_work(self):
        for key in ('busy','busy','free'): bus.publish(self.conn,'test',{},key)
        first = bus._claim(self.conn,'worker1')
        self.assertEqual(first['session_key'],'busy')
        second = bus._claim(self.conn,'worker2')
        self.assertEqual(second['session_key'],'free')
        self.assertIsNone(bus._claim(self.conn,'worker3'))

    def test_token_threshold_stops_further_calls(self):
        with patch.object(model,'complete',return_value=(json.dumps({'call':{'tool':'read','args':{}}}), {'tokens_in':100,'tokens_out':10})) as complete:
            result = model.agent_loop('test',[{'name':'read'}],lambda n,a: ({},'ev'),max_steps=6,max_tokens=50)
        self.assertEqual(complete.call_count,1)
        self.assertFalse(result['parsed'])

    def test_cli_error_payload_is_not_a_model_answer(self):
        response = type('Result', (), {'returncode':0,'stdout':json.dumps({
            'is_error':True,'result':'subscription limit reached'}),'stderr':''})()
        with patch.object(model.subprocess,'run',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'subscription limit'):
                model._call_cli('test','model','claude')

    def test_agent_loop_repairs_an_answer_that_skips_required_read(self):
        replies = [json.dumps({'answer':{'action':'hold'}}),
                   json.dumps({'call':{'tool':'read','args':{}}}),
                   json.dumps({'answer':{'action':'hold','why':'Evidence supports holding.'}})]
        with patch.object(model,'complete',side_effect=[(text,{}) for text in replies]):
            result = model.agent_loop('test',[{'name':'read'}],lambda n,a: ({'action':'hold'},'ev'),
                                      max_steps=3,required_calls=[{'tool':'read','args':{}}])
        self.assertTrue(result['parsed'])
        self.assertEqual(result['totals']['steps'],3)
        self.assertEqual(result['trace'][0]['evidence_id'],'ev')

    def test_shop_order_refresh_does_not_duplicate_sales(self):
        from adapters import medusa
        self.conn.execute("INSERT INTO ext_map VALUES ('v_black','medusa','product','variant','item','sku')")
        order = {'id':'order','created_at':db.now()[:19],'items':[
            {'id':'line','variant_id':'variant','quantity':2,'unit_price':39}]}
        with patch.object(medusa,'_paged',return_value=iter([[order]])):
            medusa.pull_orders(self.conn)
        first = db.scalar(self.conn,"SELECT SUM(units) FROM sales_fact WHERE channel='medusa'")
        with patch.object(medusa,'_paged',return_value=iter([[order]])):
            medusa.pull_orders(self.conn)
        self.assertEqual(db.scalar(self.conn,"SELECT SUM(units) FROM sales_fact WHERE channel='medusa'"),first)
        with patch.object(medusa,'_paged',side_effect=RuntimeError('shop disconnected')):
            with self.assertRaises(RuntimeError): medusa.pull_orders(self.conn)
        self.assertEqual(db.scalar(self.conn,"SELECT SUM(units) FROM sales_fact WHERE channel='medusa'"),first)


if __name__ == '__main__':
    unittest.main(verbosity=2)
