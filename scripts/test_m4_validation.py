"""E0 source-truth and online/table-state checks on tiny known-seed fixtures."""
from copy import deepcopy
from pathlib import Path
import unittest

from m4_validation import validate_pipeline
from m4_variants import evaluate_episodes, load_namespace, replay_all

NOTEBOOK = Path(__file__).resolve().parents[1] / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb'


class PipelineValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ns = load_namespace(NOTEBOOK)
        cls.cfg = deepcopy(ns['PROTOCOL_DRAFT'])
        cls.cfg.update(T=6, refit_every=2, n_bootstrap=20)
        cls.episodes = [ns['generate_episode'](seed, scenario, cls.cfg)
            for scenario, seeds in [('stable', [130000, 130001]), ('abrupt', [130100, 130101])]
            for seed in seeds]
        cls.outcomes = evaluate_episodes(ns, cls.episodes, cls.cfg)
        cls.replay, _ = replay_all(ns, cls.outcomes, cls.cfg)

    def setUp(self):
        self.ns = load_namespace(NOTEBOOK)

    def test_complete_prefix_execution_and_exact_scope(self):
        report = validate_pipeline(self.ns, self.episodes, self.outcomes, self.replay, self.cfg)
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['formal_generated'])
        self.assertEqual(report['four_arm_reconstruction']['rows'], 4*6*4)
        self.assertEqual(report['four_arm_reconstruction']['dialogues'], 4)
        check = report['online_table_equivalence']
        self.assertEqual({(r['scenario'], r['seed']) for r in check['dialogues']},
                         {('stable', 130000), ('abrupt', 130100)})
        self.assertEqual(check['question_method_seed_steps'], 2*6*7*2)
        self.assertEqual(check['state_comparisons'], 2*7*2*(1+2*6))
        self.assertEqual(len(report['method_checks']), 2)

    def test_fabricated_cost_and_consistent_replay_still_rejected(self):
        outcomes = self.outcomes.copy()
        outcomes.loc[outcomes.arm == 'recent_short', 'cost'] += 10
        outcomes['utility'] = outcomes.y-self.cfg['lambda']*outcomes.cost/self.cfg['cost_reference']
        replay, _ = replay_all(self.ns, outcomes, self.cfg)
        with self.assertRaisesRegex(ValueError, 'Reconstructed outcome differs'):
            validate_pipeline(self.ns, self.episodes, outcomes, replay, self.cfg)

    def test_fabricated_feedback_and_consistent_replay_still_rejected(self):
        outcomes = self.outcomes.copy()
        outcomes.loc[outcomes.arm == 'recent_short', 'y'] = 1-outcomes.loc[outcomes.arm == 'recent_short', 'y']
        outcomes['utility'] = outcomes.y-self.cfg['lambda']*outcomes.cost/self.cfg['cost_reference']
        replay, _ = replay_all(self.ns, outcomes, self.cfg)
        with self.assertRaisesRegex(ValueError, 'Reconstructed outcome differs'):
            validate_pipeline(self.ns, self.episodes, outcomes, replay, self.cfg)

    def test_hidden_future_public_view_rejected(self):
        original = self.ns['public_view']
        def leaking(episode, probe):
            view = original(episode, probe)
            view['history'] = episode['history']
            return view
        self.ns['public_view'] = leaking
        with self.assertRaisesRegex(ValueError, 'future or hidden'):
            validate_pipeline(self.ns, self.episodes, self.outcomes, self.replay, self.cfg)

    def test_divergent_internal_state_rejected_before_trajectory_diverges(self):
        original = self.ns['Selector']
        class DivergentSelector(original):
            created = 0
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.diverge = DivergentSelector.created % 2 == 1
                DivergentSelector.created += 1
            def update(self, *args, **kwargs):
                super().update(*args, **kwargs)
                if self.diverge:
                    self.mean[0, 0] += .1
        self.ns['Selector'] = DivergentSelector
        with self.assertRaisesRegex(ValueError, 'Selector state mismatch'):
            validate_pipeline(self.ns, self.episodes, self.outcomes, self.replay, self.cfg)

    def test_missing_episode_and_truth_tampering_rejected(self):
        with self.assertRaisesRegex(ValueError, 'dialogue grid'):
            validate_pipeline(self.ns, self.episodes[:-1], self.outcomes, self.replay, self.cfg)
        episodes = deepcopy(self.episodes)
        episodes[0]['probes'][0]['gold'] = 'WRONG'
        with self.assertRaisesRegex(ValueError, 'truth audit'):
            validate_pipeline(self.ns, episodes, self.outcomes, self.replay, self.cfg)

    def test_timings_are_not_claimed_as_reproducible(self):
        outcomes = self.outcomes.copy()
        outcomes['construction_ms'] = 9876.5
        report = validate_pipeline(self.ns, self.episodes, outcomes, self.replay, self.cfg)
        self.assertEqual(report['four_arm_reconstruction']['excluded_fields'], ['construction_ms'])


if __name__ == '__main__':
    unittest.main()
