"""Hand-computable alias subgroups; all data are explicitly synthetic fixtures."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, SCENARIOS
from m4_subgroups import alias_analysis
from m4_variants import load_namespace


NOTEBOOK = Path(__file__).resolve().parents[1] / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb'


class AliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = load_namespace(NOTEBOOK)

    def setUp(self):
        self.cfg = dict(T=4, algorithm_seeds=[17, 37], **{'lambda': .5},
                        cost_reference=512, n_bootstrap=40, bootstrap_seed=2026)
        self.baselines = dict.fromkeys(SCENARIOS, 'recent_short')

    def fixture(self, attribute='dataset', canonical_only_seed=None):
        alias = self.ns['M1_ATTRIBUTE_ALIASES'][attribute]
        episodes, outcomes, replay = [], [], []
        for scenario, seeds in [('stable', [100, 101]), ('abrupt', [200, 201])]:
            for seed in seeds:
                surface_alias = attribute if seed == canonical_only_seed else alias
                episode = dict(scenario=scenario, seed=seed, history=[
                    dict(id=0, text='Focus is project P1.'),
                    dict(id=1, text=f'For project P1: the {attribute} is V10.'),
                    dict(id=2, text=f'For project P1: the {surface_alias} is V11.')], probes=[])
                for t in range(4):
                    question = f'What is its current {surface_alias if t % 2 else attribute}?'
                    state = 'B' if scenario == 'abrupt' and t >= 2 else 'A'
                    episode['probes'].append(dict(t=t, question=question, qtype='recent', state=state,
                        end=2 if t < 2 else 3, evidence=1 if t < 2 else 2,
                        gold='V10' if t < 2 else 'V11', old_values=[] if t < 2 else ['V10']))
                    for arm in ARMS:
                        y = int(arm in ('tfidf', 'resolved_tfidf'))
                        outcomes.append(dict(scenario=scenario, seed=seed, t=t, arm=arm,
                            question=question, qtype='recent', state=state, y=y, cost=128.,
                            utility=y-.125, coverage=y, outdated=1-y))
                    for method in METHODS:
                        for alg in self.cfg['algorithm_seeds']:
                            if method in ARMS:
                                arm = method
                            elif method == 'LaplaceCTS':
                                arm = 'recent_short' if alg == 17 else 'resolved_tfidf'
                            elif method == 'TS':
                                arm = 'recent_short'
                            else:
                                arm = 'resolved_tfidf'
                            y = int(arm in ('tfidf', 'resolved_tfidf'))
                            replay.append(dict(scenario=scenario, seed=seed, t=t, method=method,
                                alg_seed=alg, arm=arm, y=y, cost=128., utility=y-.125,
                                coverage=y, outdated=1-y))
                episodes.append(episode)
        return episodes, pd.DataFrame(outcomes), pd.DataFrame(replay)

    def analyze(self, fixture=None):
        episodes, outcomes, replay = fixture or self.fixture()
        return alias_analysis(self.ns, episodes, outcomes, replay, self.cfg, self.baselines)

    def test_hand_calculated_means_intervals_and_seed_averaging(self):
        tables = self.analyze()
        metadata = tables['alias_question_metadata']
        self.assertEqual(metadata.loc[metadata.seed == 100, ['question_alias', 'evidence_alias']].values.tolist(),
                         [[False, False], [True, False], [False, True], [True, True]])
        cts = tables['alias_episode_metrics'].query("method == 'LaplaceCTS'")
        np.testing.assert_allclose(cts.y, .5)
        np.testing.assert_allclose(cts.utility, .375)
        self.assertTrue(cts.n_questions.eq(1).all())
        effects = tables['alias_effects'].query("comparison == 'cts_vs_fixed' and metric == 'utility'")
        np.testing.assert_allclose(effects[['effect', 'low', 'high']], .5)
        self.assertTrue(effects.n.eq(2).all())
        self.assertTrue(effects.n_questions.eq(2).all())
        self.assertFalse(effects.simultaneous.any())
        costs = tables['alias_effects'].query("comparison == 'cts_vs_fixed' and metric == 'cost'")
        np.testing.assert_allclose(costs.effect, 0)

    def test_missing_alias_and_query_groups_are_not_zeros(self):
        tables = self.analyze(self.fixture(canonical_only_seed=101))
        grouped = tables['alias_episode_metrics']
        absent = grouped[(grouped.seed == 101) & (grouped.question_alias | grouped.evidence_alias)]
        self.assertTrue(absent.y.isna().all())
        self.assertTrue(absent.n_questions.eq(0).all())
        effects = tables['alias_effects']
        partial = effects[(effects.scenario == 'stable') & (effects.question_alias | effects.evidence_alias)]
        self.assertTrue(partial.n.eq(1).all())
        self.assertTrue(partial.n_total.eq(2).all())
        self.assertTrue(partial.low.isna().all())
        self.assertTrue(partial.status.eq('insufficient_dialogues').all())
        query = tables['alias_query_episode_metrics'].query("qtype == 'historical'")
        self.assertTrue(query.y.isna().all())
        self.assertTrue(query.n_questions.eq(0).all())

    def test_all_attribute_aliases_are_parsed_as_whole_terms(self):
        for attribute, alias in self.ns['M1_ATTRIBUTE_ALIASES'].items():
            with self.subTest(attribute=attribute):
                table = self.analyze(self.fixture(attribute=attribute))['alias_question_metadata']
                self.assertEqual(set(table.attribute), {attribute})
                self.assertEqual(set(table.loc[table.question_alias, 'question_attribute_surface']), {alias})
                self.assertEqual(set(table.loc[table.evidence_alias, 'evidence_attribute_surface']), {alias})

    def test_future_history_and_unrelated_metadata_have_no_effect(self):
        episodes, outcomes, replay = self.fixture()
        expected = self.analyze((episodes, outcomes, replay))
        altered = deepcopy(episodes)
        for episode in altered:
            episode['unrelated_note'] = 'data source coding language due date'
            episode['history'].extend([
                dict(id=3, text='Focus is project P2.'),
                dict(id=4, text='For project P1: the data source is V99.')])
        original_outcomes, original_replay = outcomes.copy(deep=True), replay.copy(deep=True)
        actual = self.analyze((altered, outcomes, replay))
        for name in expected:
            pd.testing.assert_frame_equal(expected[name], actual[name], obj=name)
        pd.testing.assert_frame_equal(outcomes, original_outcomes)
        pd.testing.assert_frame_equal(replay, original_replay)

    def test_arm_shares_and_paired_references(self):
        tables = self.analyze()
        shares = tables['arm_choice_by_alias'].query("method == 'LaplaceCTS'")
        for arm in ARMS:
            np.testing.assert_allclose(shares.loc[shares.arm == arm, 'share'],
                                       .5 if arm in ('recent_short', 'resolved_tfidf') else 0)
        historical = tables['arm_choice_by_alias_query'].query("qtype == 'historical'")
        self.assertTrue(historical.share.isna().all())
        router = tables['alias_effects'].query("comparison == 'cts_vs_router' and metric == 'utility'")
        np.testing.assert_allclose(router.effect, -.5)

    def test_metadata_mismatch_or_future_evidence_rejected(self):
        episodes, outcomes, replay = self.fixture()
        changed = deepcopy(episodes)
        changed[0]['probes'][0]['evidence'] = 2
        with self.assertRaisesRegex(ValueError, 'latest evidence'):
            self.analyze((changed, outcomes, replay))
        changed = deepcopy(episodes)
        changed[0]['probes'][0]['question'] = 'What is its current data source?'
        with self.assertRaisesRegex(ValueError, 'metadata differs'):
            self.analyze((changed, outcomes, replay))

    def test_order_invariance(self):
        episodes, outcomes, replay = self.fixture()
        expected = self.analyze((episodes, outcomes, replay))
        actual = self.analyze((list(reversed(episodes)), outcomes.sample(frac=1, random_state=1),
                               replay.sample(frac=1, random_state=2)))
        for name in expected:
            pd.testing.assert_frame_equal(expected[name], actual[name], obj=name)


if __name__ == '__main__':
    unittest.main()
