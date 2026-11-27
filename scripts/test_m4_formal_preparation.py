"""Unsigned preparation checks in isolated synthetic workspace fixtures.

No formal generator, real review material, or real attempt registry is used.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import prepare_m4_formal as preparer
import test_m4_protocol as protocol_fixture
from m4_protocol import digest
from test_member_handoff import ROOT


class PreparationTests(unittest.TestCase):
    def setUp(self):
        # Keep synthetic data on the ordinary workspace volume. Some managed
        # Windows temporary mounts cannot support atomic registry replacements.
        temporary_root = ROOT / 'outputs/test_tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        original_temporary_directory = tempfile.TemporaryDirectory
        self.fixture = protocol_fixture.ProtocolTests('test_machine_readiness_is_not_human_approval')
        self.addCleanup(self.fixture.doCleanups)
        with patch.object(protocol_fixture.tempfile, 'TemporaryDirectory',
                          side_effect=lambda: original_temporary_directory(
                              dir=temporary_root, prefix='m4_preparation_fixture_')):
            self.fixture.setUp()
        self.root = self.fixture.root
        # ProtocolTests creates deliberately SYNTHETIC signatures. Remove that
        # isolated test file before exercising the unsigned preparation path.
        self.fixture.evidence['approvals'].unlink()
        self.package = self.root / 'package'
        self.package.mkdir()
        self.plan = self.fixture.plan
        self.plan['expected_counts'] = dict(dialogues=60, questions=18000,
            outcomes=72000, replay=252000, episode_metrics=420)
        self.put('plan.json', self.plan)
        mapping = {name: path.name for name, path in self.fixture.evidence.items()}
        for name, source in self.fixture.evidence.items():
            if name != 'approvals':
                shutil.copyfile(source, self.package / mapping[name])
        self.put('evidence.json', mapping)
        review_path = self.package / mapping['audit_review']
        review = pd.read_csv(review_path)
        review.verdict = 'pending'
        review.to_csv(review_path, index=False)
        (self.package / 'code').mkdir()
        for name, source in self.fixture.codes.items():
            shutil.copyfile(source, self.package / 'code' / name)
        self.put('code_snapshot_hashes.json',
                 {name: digest(path) for name, path in self.fixture.codes.items()})
        (self.root / 'team_workspace').mkdir()
        self.registry = self.root / 'team_workspace/formal_runs.json'
        self.registry.write_text('[]\n', encoding='utf-8')
        code_patch = patch.object(preparer, 'code_paths', return_value=self.fixture.codes)
        root_patch = patch.object(preparer, 'ROOT', self.root)
        code_patch.start()
        root_patch.start()
        self.addCleanup(code_patch.stop)
        self.addCleanup(root_patch.stop)
        self.put('approval_request.json', preparer.approval_bindings(self.package))

    def put(self, name, data):
        (self.package / name).write_text(json.dumps(data), encoding='utf-8')

    def get(self, name):
        return json.loads((self.package / name).read_text(encoding='utf-8'))

    def test_refresh_only_creates_unsigned_template(self):
        result = preparer.refresh(self.package)
        template = self.get('approvals.template.json')
        self.assertEqual(set(template['members']), set(preparer.MEMBERS))
        for entry in template['members'].values():
            self.assertIs(entry['approved'], False)
            self.assertEqual(entry['name'], '')
            self.assertEqual(entry['date'], '')
        self.assertIs(template['m3_statistics_reviewed'], False)
        self.assertIs(template['all_used_seeds_disclosed'], False)
        self.assertFalse((self.package / 'approvals.json').exists())
        self.assertFalse(result['approved_for_execution'])
        self.assertEqual(json.loads(self.registry.read_text()), [])
        with self.assertRaisesRegex(ValueError, 'does not write human approvals'):
            preparer.put_json(self.package / 'approvals.json', template)

    def test_refresh_preserves_existing_approval_file(self):
        path = self.package / 'approvals.json'
        existing = b'{"SYNTHETIC_EXISTING_REVIEW": "must not overwrite"}'
        path.write_bytes(existing)
        with self.assertRaisesRegex(ValueError, 'Real approvals already exist'):
            preparer.refresh(self.package)
        self.assertEqual(path.read_bytes(), existing)
        self.assertFalse((self.package / 'approvals.template.json').exists())

    def test_disclosed_candidate_collision_is_rejected_before_plan_rewrite(self):
        candidate = self.plan['evaluation_seeds']['stable'][0]
        self.put('seed_disclosure.json', dict(members={
            'M1': dict(additional_dialogue_seeds=[candidate])}))
        before = (self.package / 'plan.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'collides with candidates'):
            preparer.refresh(self.package)
        self.assertEqual((self.package / 'plan.json').read_bytes(), before)
        self.assertFalse((self.package / 'approvals.json').exists())

    def test_technical_preflight_does_not_imply_human_approval(self):
        result = preparer.preflight(self.package)
        self.assertTrue(result['technical_checks_passed'])
        self.assertEqual(result['technical_errors'], [])
        self.assertEqual(result['status'], 'prepared_pending_human_confirmation')
        for field in ['approved_for_execution', 'formal_generated', 'frozen']:
            self.assertIs(result[field], False)
        self.assertTrue(any(row['owner'] == 'M1/M2' for row in result['human_missing']))
        self.assertTrue(any(row['owner'] == 'M3' for row in result['human_missing']))
        self.assertEqual(len(result['human_missing'][0]['pending_rows']), 10)
        self.assertFalse((self.package / 'approvals.json').exists())

    def test_noncolliding_disclosure_rebinds_but_does_not_approve(self):
        before = self.get('approval_request.json')['plan_sha256']
        self.put('seed_disclosure.json', dict(members={
            'M2': dict(additional_dialogue_seeds=[700001, 700002])}))
        result = preparer.refresh(self.package)
        self.assertEqual(self.get('plan.json')['used_seeds'], [700001, 700002])
        self.assertNotEqual(self.get('approval_request.json')['plan_sha256'], before)
        self.assertTrue(result['technical_checks_passed'])
        self.assertFalse(result['approved_for_execution'])
        self.assertFalse((self.package / 'approvals.json').exists())

    def test_preflight_detects_new_registered_seed_collision(self):
        candidate = self.plan['evaluation_seeds']['abrupt'][0]
        self.registry.write_text(json.dumps([
            dict(run_id='SYNTHETIC_ATTEMPT', status='started', evaluation_seeds=[candidate])]),
            encoding='utf-8')
        result = preparer.preflight(self.package)
        self.assertFalse(result['technical_checks_passed'])
        self.assertIn('formal attempt registry', result['technical_errors'][0])
        self.assertFalse(result['approved_for_execution'])


if __name__ == '__main__':
    unittest.main()
