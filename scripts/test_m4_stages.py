"""Orchestration and provenance regressions; no formal data generation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from m4_analysis import aggregate_dialogues
from m4_experiment_plan import make_plan, validate_plan, STAGES
from m4_protocol import digest, write_new
import run_m4_stages as runner
import test_m4_temporal as temporal_fixture


class StageTests(unittest.TestCase):
    def test_changed_source_requires_new_process_before_archiving(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'runner.py'
            source.write_text('version_1', encoding='utf-8')
            with patch.object(runner, 'EXECUTION_HASHES', {source: digest(source)}):
                runner._assert_code_unchanged()
                source.write_text('version_2', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Source changed'):
                    runner._assert_code_unchanged()

    def test_all_presets_are_development_only_and_single_factor(self):
        for stage in STAGES:
            plan = make_plan(stage, 'smoke')
            validate_plan(plan)
            self.assertFalse(plan['formal'])
            self.assertTrue(plan['fixture'])
            self.assertEqual(plan['dialogue_seeds']['stable'], [130000, 130001])
            for v in plan['variants'][1:]:
                self.assertEqual(len(v['config']) + len(v['adapter']), 1)

    def test_formal_seeds_and_custom_grid_rejected_before_run_directory(self):
        for change in ['seed', 'formal', 'grid']:
            plan = make_plan('E2', 'smoke')
            if change == 'seed': plan['dialogue_seeds']['stable'][0] = 930000
            if change == 'formal': plan['formal'] = True
            if change == 'grid': plan['variants'][1]['adapter']['feature_mode'] = 'full'
            with patch.object(runner, '_run_directory') as directory, self.assertRaises(ValueError):
                runner.run_experiment(plan, 'must_not_exist')
            directory.assert_not_called()

    def test_variant_contrast_sign_and_lambda_scope(self):
        fixture = temporal_fixture.TemporalTests(); fixture.setUp()
        default = aggregate_dialogues(fixture.replay)
        variant = default.copy()
        variant['cost'] = variant.cost + 10
        variant['utility'] = variant.utility - 10 / 1024
        tables = runner._variant_effects({'default': default, 'constant_features': variant}, make_plan('E2', 'smoke'))
        utility = tables['variant_effects'].query("metric == 'utility'")
        np.testing.assert_allclose(utility.effect, 10 / 1024)
        self.assertTrue(utility.direction.eq('default_minus_variant').all())
        tables = runner._variant_effects({'default': default, 'lambda_100': variant}, make_plan('E4', 'smoke'))
        self.assertNotIn('utility', tables['variant_effects'].metric.tolist())

    def test_rescoring_preserves_behavior_and_accuracy(self):
        fixture = temporal_fixture.TemporalTests(); fixture.setUp()
        table = runner._fixed_trajectory_scores(fixture.replay, make_plan('E4', 'smoke'))
        self.assertEqual(set(table.scoring_lambda), {.25, .5, 1.})
        for _, group in table.groupby(['scenario', 'seed', 'method']):
            self.assertEqual(group.y.nunique(), 1)
            self.assertEqual(group.cost.nunique(), 1)
            np.testing.assert_allclose(group.utility, group.y - group.scoring_lambda * group.cost / 512)

    def test_alias_variant_missing_stratum_remains_missing(self):
        fixture = temporal_fixture.TemporalTests(); fixture.setUp()
        default = aggregate_dialogues(fixture.replay)
        default['question_alias'] = True
        default.loc[default.seed == 100, ['y', 'cost', 'utility', 'coverage', 'outdated']] = np.nan
        changed = default.copy()
        changed['cost'] += 10
        changed['utility'] -= 10 / 1024
        tables = runner._variant_effects({'default': default, 'without_normalize_aliases': changed},
                                         make_plan('E5b', 'smoke'), ('question_alias',))
        effects = tables['variant_effects'].query("scenario == 'stable' and metric == 'utility'")
        self.assertTrue(effects.n.eq(1).all())
        self.assertTrue(effects.n_total.eq(2).all())
        self.assertTrue(effects.low.isna().all())
        np.testing.assert_allclose(effects.effect, 10 / 1024)
        missing = tables['variant_dialogue_differences'].query('seed == 100')
        self.assertTrue(missing.difference.isna().all())
        self.assertFalse(missing.observed.any())

    def test_source_hash_and_entire_missing_dialogue_rejected(self):
        fixture = temporal_fixture.TemporalTests(); fixture.setUp()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); table_dir = root / 'tables'; table_dir.mkdir()
            outcomes = table_dir / 'evaluation_outcomes.csv'
            replay = table_dir / 'replay.csv'
            fixture.outcomes.to_csv(outcomes, index=False)
            fixture.replay.to_csv(replay, index=False)
            manifest = dict(mode='development', status='computed_pending_review', config=fixture.cfg,
                seeds={'stable': [100, 101], 'abrupt': [200, 201]},
                files={'tables/evaluation_outcomes.csv': digest(outcomes), 'tables/replay.csv': digest(replay)})
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            runner._verified_analysis_source(root)
            # Honest hashes alone cannot excuse deleting one whole independent unit.
            fixture.outcomes[fixture.outcomes.seed != 100].to_csv(outcomes, index=False)
            fixture.replay[fixture.replay.seed != 100].to_csv(replay, index=False)
            manifest['files'] = {k: digest(root / k) for k in manifest['files']}
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'four-arm grid'):
                runner._verified_analysis_source(root)
            outcomes.write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash verification'):
                runner._verified_analysis_source(root)

    def test_failed_attempt_retained_and_run_id_not_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'team_workspace').mkdir()
            registry = root / 'team_workspace/formal_runs.json'; registry.write_text('[]')
            plan = make_plan('E1', 'smoke')
            with patch.object(runner, 'ROOT', root), patch.object(runner, '_snapshot'), \
                    patch.object(runner, '_source_inputs', side_effect=ValueError('injected source failure')):
                with self.assertRaisesRegex(ValueError, 'injected'):
                    runner.run_experiment(plan, 'retained_failure')
                path = root / 'outputs/development/retained_failure'
                self.assertTrue((path / 'failure.json').is_file())
                self.assertEqual(json.loads((path / 'manifest.json').read_text())['status'], 'failed')
                with self.assertRaises(FileExistsError):
                    runner.run_experiment(plan, 'retained_failure')
                self.assertEqual(registry.read_text(), '[]')


if __name__ == '__main__':
    unittest.main()
