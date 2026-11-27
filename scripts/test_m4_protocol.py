"""Full-schema synthetic fixtures; never touch real approvals or formal records."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from m4_protocol import *


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        cfg=dict(T=300,n_formal_per_scenario=30,n_dev_per_scenario=1,n_demo_per_scenario=6,
                 algorithm_seeds=[17,37],bootstrap_seed=2026,n_bootstrap=2000,refit_every=5,
                 budgets=dict(zip(ARMS,[128,512,256,256])),cost_reference=512,prior_precision=1,
                 p_recent_stable=.9,p_recent_abrupt_before=.9,p_recent_abrupt_after=.1,
                 update_probability=.25,initial_conflict_fraction=.25)
        cfg['lambda']=.5
        self.plan=dict(config=cfg,analysis_spec=analysis_specification(),evaluation_seeds=dict(stable=list(range(800000,800030)),abrupt=list(range(800100,800130))),used_seeds=[],baselines=dict(stable=ARMS[0],abrupt=ARMS[0]))
        self.codes={k:self.root/k for k in ['notebook','runner','protocol','loader','analysis']}
        for p in self.codes.values():p.write_text('synthetic source')
        names=['truth_checks','strategy_checks','method_checks','development_outcomes','audit_review','development_provenance','approvals']
        self.evidence={k:self.root/(k+'.json') for k in names}
        data=pd.DataFrame([dict(scenario=sc,seed=seed,t=t,arm=a,y=1,cost=10,utility=1-.5*10/512,coverage=1,outdated=0)
            for sc,seed in [('stable',130000),('abrupt',130100)] for t in range(300) for a in ARMS])
        data.to_csv(self.evidence['development_outcomes'],index=False)
        pd.DataFrame([dict(seed=130000,t=t,m1_reviewer='SYNTHETIC',m2_reviewer='SYNTHETIC',verdict='pass',m1_notes='fixture',m2_notes='fixture') for t in range(10)]).to_csv(self.evidence['audit_review'],index=False)
        binding=dict(config_sha256=canonical_hash(cfg),notebook_sha256=digest(self.codes['notebook']),development_sha256=digest(self.evidence['development_outcomes']))
        self.put('development_provenance',binding)
        self.put('truth_checks',dict(binding,status='passed',payload=[dict(scenario=sc,seed=seed,passed=True,question_count=300,errors=[]) for sc,seed in [('stable',130000),('abrupt',130100)]]))
        self.put('strategy_checks',dict(binding,status='passed',payload=dict(fixture_checks=[dict(result='pass')],development_checks=dict.fromkeys(['unique_keys_four_arms_and_matching_metadata','cost_count_and_utility_consistency','m1_independent_truth_audit','audit_coverage_and_reconstruction_match_outcomes'],'pass'),row_counts=dict(outcomes=2400))))
        self.put('method_checks',dict(binding,status='passed',payload=dict(beta_posterior=[3,2],reset_and_unchosen_reward_flip='passed',algorithm_seeds=[17,37],refit_every_selected_feedbacks=5,methods=list(ARMS)+['TS','LaplaceCTS','RuleRouter'],map_gradient_norm=1e-7,gradient_fd_max_error=1e-10,hessian_fd_max_error=1e-10,covariance_min_eigenvalue=.3,source=dict(scenario='abrupt',seed=130100),replay_rows=4200)))
        self.sign()

    def put(self,name,value):self.evidence[name].write_text(json.dumps(value))
    def get(self,name):return json.loads(self.evidence[name].read_text())
    def sign(self):
        self.put('approvals',dict(plan_sha256=canonical_hash(self.plan),code_sha256={k:digest(v) for k,v in self.codes.items()},evidence_sha256={k:digest(v) for k,v in self.evidence.items() if k!='approvals'},members={k:dict(name='SYNTHETIC',date='2026-11-25',approved=True,seeds_disclosed=True,additional_dialogue_seeds=[]) for k in ['M1','M2','M3','M4','M5']},m3_statistics_reviewed=True,all_used_seeds_disclosed=True))
    def validate(self):return validate_plan(self.plan,self.evidence,self.codes)

    def test_valid_freeze_and_tamper(self):
        dest=self.root/'frozen';freeze(self.plan,self.evidence,self.codes,dest);verify_frozen(dest)
        with self.assertRaises(FileExistsError):freeze(self.plan,self.evidence,self.codes,dest)
        (dest/'code/notebook').write_text('changed')
        with self.assertRaises(ValueError):verify_frozen(dest)

    def test_analysis_is_bound_and_spec_is_fixed(self):
        (self.root/'analysis').write_text('changed analysis')
        with self.assertRaisesRegex(ValueError,'code hashes'):self.validate()
        self.sign()
        self.plan['analysis_spec']['primary']['family_size']=1
        self.sign()
        with self.assertRaisesRegex(ValueError,'Analysis specification'):self.validate()

    def test_machine_readiness_is_not_human_approval(self):
        review=pd.read_csv(self.evidence['audit_review']);review.verdict='pending'
        review.to_csv(self.evidence['audit_review'],index=False)
        self.evidence['approvals'].unlink()
        result=validate_machine_plan(self.plan,self.evidence,self.codes)
        self.assertEqual(result['technical_checks'],'passed')
        self.assertFalse(result['formal_generated'])
        with self.assertRaisesRegex(ValueError,'pending'):self.validate()

    def test_individual_seed_disclosure_cannot_bypass_bound_plan(self):
        approvals=self.get('approvals')
        approvals['members']['M2']['additional_dialogue_seeds']=[800000]
        self.put('approvals',approvals)
        with self.assertRaisesRegex(ValueError,'absent from bound plan'):self.validate()
        self.plan['used_seeds']=[800000]
        self.sign()
        with self.assertRaisesRegex(ValueError,'overlap'):self.validate()

    def test_config_missing_invalid(self):
        original=dict(self.plan['config'])
        for key,value in [('budgets',None),('lambda',float('nan')),('n_bootstrap',0),('refit_every',True),('bootstrap_seed',-1)]:
            with self.subTest(key=key):
                self.plan['config']=dict(original)
                if value is None:self.plan['config'].pop(key)
                else:self.plan['config'][key]=value
                with self.assertRaises(ValueError):self.validate()

    def test_failed_and_empty_payloads(self):
        for name in ['truth_checks','strategy_checks','method_checks']:
            original=self.get(name)
            for payload in [None,{},dict(passed=False)]:
                with self.subTest(name=name,payload=payload):
                    self.put(name,dict(original,payload=payload));self.sign()
                    with self.assertRaises(ValueError):self.validate()
            self.put(name,original)
        self.sign()

    def test_failed_status_and_internal_checks(self):
        for name in ['truth_checks','strategy_checks','method_checks']:
            original=self.get(name)
            self.put(name,dict(original,status='failed'));self.sign()
            with self.assertRaisesRegex(ValueError,'Failed/unbound'):self.validate()
            self.put(name,original)
        truth=self.get('truth_checks');truth['payload'][0]['passed']=False
        self.put('truth_checks',truth);self.sign()
        with self.assertRaisesRegex(ValueError,'Truth audit failed'):self.validate()

    def test_incomplete_grid_even_with_updated_hashes(self):
        p=self.evidence['development_outcomes'];pd.read_csv(p).iloc[1:].to_csv(p,index=False)
        for name in ['development_provenance','truth_checks','strategy_checks','method_checks']:
            value=self.get(name);value['development_sha256']=digest(p);self.put(name,value)
        self.sign()
        with self.assertRaisesRegex(ValueError,'Incomplete development grid'):self.validate()

    def test_identity_and_date(self):
        for value in [None,'','   ',123]:
            for field in ['name','date']:
                self.sign();a=self.get('approvals');a['members']['M1'][field]=value;self.put('approvals',a)
                with self.assertRaises(ValueError):self.validate()
        self.sign();a=self.get('approvals');a['members']['M1']['date']='not-a-date';self.put('approvals',a)
        with self.assertRaises(ValueError):self.validate()

    def test_development_config_mismatch(self):
        self.plan['config']['lambda']=1.;self.sign()
        with self.assertRaisesRegex(ValueError,'binding mismatch'):self.validate()
        for name in ['development_provenance','truth_checks','strategy_checks','method_checks']:
            a=self.get(name);a['config_sha256']=canonical_hash(self.plan['config']);self.put(name,a)
        self.sign()
        with self.assertRaisesRegex(ValueError,'utility/config mismatch'):self.validate()

    def test_review_coverage(self):
        p=self.evidence['audit_review'];d=pd.read_csv(p);d.seed=999;d.to_csv(p,index=False);self.sign()
        with self.assertRaisesRegex(ValueError,'outside development'):self.validate()

    def test_failure_report_error_still_registers(self):
        registry=self.root/'registry.json';register_event(registry,dict(run_id='a',status='started',evaluation_seeds=[800000]))
        original=RuntimeError('original compute failure')
        # Existing report must not prevent registry persistence.
        (self.root/'failure.json').write_text('{}')
        errors=record_failure(self.root,registry,'a',[800000],original)
        self.assertTrue(errors);self.assertEqual(json.loads(registry.read_text())[-1]['status'],'failed')
        self.assertIn('failure report:',original.__notes__[0])
        with self.assertRaises(ValueError):register_event(registry,dict(run_id='b',status='started',evaluation_seeds=[800000]))

    def test_both_persistence_failures_preserve_original(self):
        original=RuntimeError('original')
        with patch('m4_protocol.write_new',side_effect=OSError('disk')),patch('m4_protocol.register_event',side_effect=OSError('registry')):
            errors=record_failure(self.root,self.root/'r.json','a',[],original)
        self.assertEqual(len(errors),2);self.assertEqual(str(original),'original')


if __name__=='__main__':unittest.main()
