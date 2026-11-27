"""Exercise formal E1 table preparation on existing demo data only.

These tests never call the generator, formal CLI, registry, or freeze function.
"""
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from run_m4_formal import build_analysis_artifacts, code_paths
from test_member_handoff import ROOT


class FormalAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'outputs/demo/m4_stage2_verified_20261123'
        if not cls.source.exists():
            raise unittest.SkipTest('Existing complete demo archive is required; no data is generated')
        manifest = json.loads((cls.source / 'manifest.json').read_text(encoding='utf-8'))
        cls.cfg = manifest['config']
        cls.baselines = manifest['baselines']
        cls.outcomes = pd.read_csv(cls.source / 'tables/evaluation_outcomes.csv')
        cls.replay = pd.read_csv(cls.source / 'tables/replay.csv')
        cls.expected = {
            'stable': list(range(730000, 730006)),
            'abrupt': list(range(730100, 730106)),
        }
        cls.ns = dict(np=np, pd=pd)
        notebook = json.loads((ROOT / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb').read_text(encoding='utf-8'))
        for cell_id in ['shared-protocol-draft', 'm4-experiment-skeleton']:
            source = ''.join(next(c['source'] for c in notebook['cells'] if c.get('id') == cell_id))
            exec(compile(source, cell_id, 'exec'), cls.ns)
        cls.artifacts = build_analysis_artifacts(
            cls.ns, cls.outcomes, cls.replay, cls.baselines, cls.cfg, cls.expected)

    def test_primary_and_secondary_exactly_reproduce_existing_demo(self):
        for name in ['primary_effects', 'secondary_effects', 'episode_metrics', 'method_summary']:
            expected = pd.read_csv(self.source / 'tables' / (name + '.csv'))
            pd.testing.assert_frame_equal(self.artifacts['tables/' + name + '.csv'], expected,
                                          check_exact=False, rtol=0, atol=1e-12)

    def test_direct_comparisons_and_dialogue_counts(self):
        direct = self.artifacts['tables/direct_comparisons.csv']
        self.assertEqual(len(direct), 20)
        self.assertTrue(direct.n.eq(6).all())
        self.assertTrue(direct[['family_low', 'family_high']].isna().all().all())
        expected_utility = {
            ('stable', 'cts_vs_ts'): 0.08177951388888889,
            ('stable', 'cts_vs_router'): -0.030801595052083314,
            ('abrupt', 'cts_vs_ts'): 0.1342277018229167,
            ('abrupt', 'cts_vs_router'): -0.027950575086805523,
        }
        for row in direct[direct.metric == 'utility'].itertuples(index=False):
            self.assertAlmostEqual(row.effect, expected_utility[(row.scenario, row.comparison)], places=12)
        differences = self.artifacts['tables/paired_dialogue_differences.csv']
        self.assertEqual(len(differences), 12 * 3)
        np.testing.assert_allclose(differences.delta_utility,
                                   differences.delta_y - differences.delta_cost / 1024,
                                   rtol=0, atol=1e-12)

    def test_entire_missing_dialogue_rejected_against_approved_seeds(self):
        seed = self.expected['stable'][0]
        with self.assertRaisesRegex(ValueError, 'four-arm grid'):
            build_analysis_artifacts(self.ns, self.outcomes[self.outcomes.seed != seed],
                self.replay[self.replay.seed != seed], self.baselines, self.cfg, self.expected)

    def test_entire_missing_method_or_algorithm_seed_rejected(self):
        for altered in [self.replay[self.replay.method != 'RuleRouter'],
                        self.replay[self.replay.alg_seed != 37]]:
            with self.subTest(rows=len(altered)), self.assertRaisesRegex(ValueError, 'replay grid'):
                build_analysis_artifacts(self.ns, self.outcomes, altered,
                                         self.baselines, self.cfg, self.expected)

    def test_analysis_is_frozen_and_report_preserves_inference_boundaries(self):
        self.assertEqual(code_paths()['analysis'], ROOT / 'scripts/m4_analysis.py')
        self.assertEqual(set(code_paths()), {'notebook', 'runner', 'protocol', 'loader', 'analysis'})
        report = self.artifacts['reports/M4_handoff.md']
        for text in ['computed_pending_review', '97.5%', 'exploratory 95%',
                     'stable: n=6', 'abrupt: n=6', '0.081780', '-0.030802']:
            self.assertIn(text, report)


if __name__ == '__main__':
    unittest.main()
