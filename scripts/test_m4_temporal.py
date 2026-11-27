"""Hand-computable temporal and hindsight-oracle analysis fixtures."""
import unittest

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, SCENARIOS
from m4_temporal import oracle_analysis, temporal_analysis


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(T=4, algorithm_seeds=[17, 37], **{'lambda': .5},
                        cost_reference=512, n_bootstrap=80, bootstrap_seed=2026)
        self.baselines = dict.fromkeys(SCENARIOS, 'recent_short')
        rows, replay = [], []
        for scenario, seeds in [('stable', [100, 101]), ('abrupt', [200, 201])]:
            for seed in seeds:
                for t in range(4):
                    for arm in ARMS:
                        y = int(arm in ('tfidf', 'resolved_tfidf'))
                        rows.append(dict(scenario=scenario, seed=seed, t=t, arm=arm,
                            question='What is its current dataset?',
                            qtype='historical' if seed % 2 and t >= 2 else 'recent',
                            state='B' if scenario == 'abrupt' and t >= 2 else 'A',
                            y=y, cost=128., utility=y-.125, coverage=y, outdated=0))
                for method in METHODS:
                    for alg in [17, 37]:
                        for t in range(4):
                            if method in ARMS:
                                arm = method
                            elif method == 'LaplaceCTS':
                                arm = 'recent_short' if alg == 17 and t < 2 else 'resolved_tfidf'
                            elif method == 'TS':
                                arm = 'recent_short'
                            else:
                                arm = 'resolved_tfidf'
                            y = int(arm in ('tfidf', 'resolved_tfidf'))
                            replay.append(dict(scenario=scenario, seed=seed, t=t, method=method,
                                alg_seed=alg, arm=arm, y=y, cost=128., utility=y-.125,
                                coverage=y, outdated=0))
        self.outcomes = pd.DataFrame(rows)
        self.replay = pd.DataFrame(replay)

    def analyze(self, **kwargs):
        return temporal_analysis(self.replay, self.outcomes, self.baselines, self.cfg, **kwargs)

    def test_hand_computed_stage_and_post_pre_effect(self):
        tables = self.analyze(window_size=2)
        phase = tables['phase_episode_metrics']
        cts = phase[phase.method == 'LaplaceCTS']
        np.testing.assert_allclose(cts[cts.phase == 'pre'].utility, .375)
        np.testing.assert_allclose(cts[cts.phase == 'post'].utility, .875)
        change = tables['post_pre_effects']
        utility = change[(change.comparison == 'cts_vs_fixed') & (change.metric == 'utility')]
        np.testing.assert_allclose(utility[['effect', 'low', 'high']], .5)
        self.assertTrue(utility.n.eq(2).all())
        self.assertTrue(utility.n_questions.eq(8).all())
        self.assertFalse(utility.simultaneous.any())

    def test_missing_query_is_not_zero_and_counts_are_dialogues(self):
        tables = self.analyze()
        query = tables['query_episode_metrics']
        absent = query[(query.seed == 100) & (query.qtype == 'historical')]
        self.assertEqual(len(absent), len(METHODS))
        self.assertTrue(absent.y.isna().all())
        self.assertTrue(absent.n_questions.eq(0).all())
        summary = tables['query_summary']
        historical = summary[(summary.scenario == 'stable') & (summary.qtype == 'historical')]
        self.assertTrue(historical.n.eq(1).all())
        self.assertTrue(historical.n_total.eq(2).all())
        effects = tables['query_effects']
        historical = effects[(effects.scenario == 'stable') & (effects.qtype == 'historical')]
        self.assertTrue(historical.low.isna().all())
        self.assertTrue(historical.status.eq('insufficient_dialogues').all())

    def test_cumulative_curve_seed_averaging_and_partial_window(self):
        tables = self.analyze(window_size=3)
        curves = tables['cumulative_dialogue_differences']
        example = curves[(curves.seed == 100) & (curves.comparison == 'cts_vs_fixed')]
        np.testing.assert_allclose(example.cumulative_delta_utility, [.5, 1., 2., 3.])
        windows = tables['window_episode_metrics']
        self.assertTrue(windows[windows.window == 1].n_questions.eq(1).all())
        self.assertTrue(windows[windows.window == 1].end_t.eq(3).all())
        summary = tables['cumulative_effects']
        self.assertTrue(summary.interval_scope.eq('pointwise').all())
        self.assertTrue(summary.n.eq(2).all())

    def test_arm_shares_preserve_missing_and_zero(self):
        shares = self.analyze()['arm_choice_by_query']
        absent = shares[(shares.seed == 100) & (shares.qtype == 'historical')]
        self.assertTrue(absent.share.isna().all())
        fixed = shares[(shares.method == 'recent_short') & shares.observed]
        np.testing.assert_allclose(fixed[fixed.arm == 'recent_short'].share, 1)
        np.testing.assert_allclose(fixed[fixed.arm != 'recent_short'].share, 0)
        sums = shares[shares.observed].groupby(['scenario', 'seed', 'method', 'qtype']).share.sum()
        np.testing.assert_allclose(sums, 1)

    def test_oracle_gaps_match_hand_calculation(self):
        tables = oracle_analysis(self.replay, self.outcomes, self.cfg)
        cts = tables['oracle_dialogue_curves']
        example = cts[(cts.seed == 100) & (cts.method == 'LaplaceCTS')]
        np.testing.assert_allclose(example.cumulative_oracle_gap, [.5, 1., 1., 1.])
        episode = tables['oracle_episode_metrics']
        np.testing.assert_allclose(episode[episode.method == 'LaplaceCTS'].mean_oracle_gap, .25)
        np.testing.assert_allclose(episode[episode.method == 'resolved_tfidf'].cumulative_oracle_gap, 0)
        self.assertTrue(tables['oracle_trajectory_gaps'].oracle_gap.ge(0).all())
        self.assertTrue(tables['oracle_cumulative_summary'].n.eq(2).all())

    def test_permuted_input_is_invariant(self):
        reference = self.analyze(window_size=2)
        actual = temporal_analysis(self.replay.sample(frac=1, random_state=1),
            self.outcomes.sample(frac=1, random_state=2), self.baselines, self.cfg, window_size=2)
        for name in reference:
            pd.testing.assert_frame_equal(reference[name], actual[name], obj=name)

    def test_incomplete_or_misaligned_inputs_rejected(self):
        with self.assertRaises(ValueError):
            temporal_analysis(self.replay.iloc[1:], self.outcomes, self.baselines, self.cfg)
        broken = self.outcomes.copy()
        broken.loc[0, 'qtype'] = 'historical'
        with self.assertRaisesRegex(ValueError, 'query type'):
            temporal_analysis(self.replay, broken, self.baselines, self.cfg)
        broken = self.replay.copy()
        broken['qtype'] = 'historical'
        with self.assertRaisesRegex(ValueError, 'metadata'):
            temporal_analysis(broken, self.outcomes, self.baselines, self.cfg)
        with self.assertRaises(ValueError):
            oracle_analysis(self.replay, self.outcomes.iloc[1:], self.cfg)

    def test_invalid_window_and_demand_state_rejected(self):
        for value in [0, -1, True, 1.5]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.analyze(window_size=value)
        broken = self.outcomes.copy()
        broken.loc[(broken.scenario == 'abrupt') & (broken.t == 2), 'state'] = 'A'
        with self.assertRaisesRegex(ValueError, 'state'):
            temporal_analysis(self.replay, broken, self.baselines, self.cfg)


if __name__ == '__main__':
    unittest.main()
