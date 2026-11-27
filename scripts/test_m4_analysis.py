"""Hand-computable E1 fixtures; no real runs, approvals, or registry writes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from m4_analysis import (
    ARMS,
    METHODS,
    METRICS,
    SCENARIOS,
    aggregate_dialogues,
    paired_comparisons,
    validate_outcomes,
    validate_replay,
)
from run_m4_experiment1 import verified_archive


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "T": 2,
            "algorithm_seeds": [17, 37],
            "lambda": 0.5,
            "cost_reference": 512,
            "n_bootstrap": 2000,
            "bootstrap_seed": 2026,
        }
        self.seeds = {"stable": [100, 101], "abrupt": [200, 201]}
        self.baselines = {"stable": "recent_short", "abrupt": "resolved_tfidf"}
        # Costs are complete-input proxies. Binary feedback is fixed by arm.
        arm_values = {
            "recent_short": (0, 64, 0, 0),
            "recent_long": (1, 512, 1, 0),
            "tfidf": (0, 256, 0, 1),
            "resolved_tfidf": (1, 192, 1, 0),
        }
        outcomes = []
        replay = []
        for scenario in SCENARIOS:
            for seed in self.seeds[scenario]:
                for t in range(self.cfg["T"]):
                    for arm in ARMS:
                        y, cost, coverage, outdated = arm_values[arm]
                        outcomes.append({
                            "scenario": scenario, "seed": seed, "t": t, "arm": arm,
                            "question": "What is P1 current dataset?",
                            "qtype": "historical",
                            "state": "B" if scenario == "abrupt" and t == 1 else "A",
                            "construction_ms": 0.01,
                            "y": y, "cost": cost, "utility": y - cost / 1024,
                            "coverage": coverage, "outdated": outdated,
                        })
                for method in METHODS:
                    for alg_seed in self.cfg["algorithm_seeds"]:
                        for t in range(self.cfg["T"]):
                            if method in ARMS:
                                arm = method
                            elif method == "TS":
                                arm = "recent_short"
                            elif method == "RuleRouter":
                                arm = "resolved_tfidf"
                            else:
                                arm = "recent_short" if alg_seed == 17 and t == 0 else "resolved_tfidf"
                            y, cost, coverage, outdated = arm_values[arm]
                            replay.append({
                                "scenario": scenario, "seed": seed, "t": t,
                                "method": method, "alg_seed": alg_seed, "arm": arm,
                                "y": y, "cost": cost, "utility": y - cost / 1024,
                                "coverage": coverage, "outdated": outdated,
                            })
        self.outcomes = pd.DataFrame(outcomes)
        self.replay = pd.DataFrame(replay)

    def metrics(self):
        return aggregate_dialogues(self.replay)

    def test_complete_fixture_and_dialogue_unit(self):
        validate_outcomes(self.outcomes, self.cfg, self.seeds)
        validate_replay(self.replay, self.outcomes, self.cfg)
        metrics = self.metrics()
        self.assertEqual(len(metrics), 4 * len(METHODS))
        cts = metrics[metrics.method == "LaplaceCTS"]
        np.testing.assert_allclose(cts.y, 0.75)
        np.testing.assert_allclose(cts.cost, 160)
        np.testing.assert_allclose(cts.utility, 0.59375)
        differences, effects = paired_comparisons(metrics, self.baselines, self.cfg)
        self.assertEqual(len(differences), 4 * 3)
        self.assertEqual(len(effects), 2 * 2 * len(METRICS))
        self.assertTrue(effects.n.eq(2).all())  # Not four algorithm runs or eight questions.
        self.assertTrue(effects[["family_low", "family_high"]].isna().all().all())

    def test_hand_calculated_positive_and_negative_effects(self):
        _, effects = paired_comparisons(self.metrics(), self.baselines, self.cfg)
        for comparison, expected in [("cts_vs_ts", 0.65625), ("cts_vs_router", -0.21875)]:
            selected = effects[(effects.comparison == comparison) & (effects.metric == "utility")]
            self.assertEqual(len(selected), 2)
            for field in ["effect", "low", "high"]:
                np.testing.assert_allclose(selected[field], expected, rtol=0, atol=1e-12)

    def test_zero_effect_and_row_order_invariance(self):
        metrics = self.metrics()
        # Make TS equal CTS in every paired dialogue; other methods remain unchanged.
        for scenario, seed in metrics[["scenario", "seed"]].drop_duplicates().itertuples(index=False):
            group = (metrics.scenario == scenario) & (metrics.seed == seed)
            values = metrics.loc[group & (metrics.method == "LaplaceCTS"), METRICS].iloc[0]
            metrics.loc[group & (metrics.method == "TS"), METRICS] = values.to_numpy()
        expected = paired_comparisons(metrics, self.baselines, self.cfg)
        actual = paired_comparisons(metrics.sample(frac=1, random_state=9), self.baselines, self.cfg)
        for left, right in zip(expected, actual):
            pd.testing.assert_frame_equal(left, right)
        effects = expected[1]
        zero = effects[effects.comparison == "cts_vs_ts"]
        np.testing.assert_allclose(zero[["effect", "low", "high"]], 0, atol=1e-12)

    def test_difference_decomposition_and_shared_bootstrap_draw(self):
        metrics = self.metrics()
        # A dialogue-specific cost perturbation gives a nondegenerate paired sample.
        changed = (metrics.method == "LaplaceCTS") & metrics.seed.isin([101, 201])
        metrics.loc[changed, "cost"] += 64
        metrics["utility"] = metrics.y - metrics.cost / 1024
        differences, effects = paired_comparisons(
            metrics, self.baselines, dict(self.cfg, n_bootstrap=1)
        )
        np.testing.assert_allclose(
            differences.delta_utility,
            differences.delta_y - differences.delta_cost / 1024,
            rtol=0, atol=1e-12,
        )
        # With one bootstrap draw, every endpoint is that draw's mean. Its five
        # metrics must obey the utility identity; endpoints generally cannot be
        # subtracted this way for a multi-draw percentile interval.
        for _, group in effects.groupby(["scenario", "comparison"]):
            wide = group.set_index("metric")
            for field in ["low", "high"]:
                self.assertAlmostEqual(
                    wide.loc["utility", field],
                    wide.loc["y", field] - wide.loc["cost", field] / 1024,
                    places=12,
                )

    def test_missing_full_outcome_groups_rejected(self):
        mutations = {
            "arm": self.outcomes[self.outcomes.arm != "tfidf"],
            "last_question": self.outcomes[self.outcomes.t != 1],
            "dialogue": self.outcomes[self.outcomes.seed != 101],
            "scenario": self.outcomes[self.outcomes.scenario != "abrupt"],
        }
        for name, frame in mutations.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_outcomes(frame, self.cfg, self.seeds)

    def test_empty_scenario_seed_group_rejected(self):
        with self.assertRaises(ValueError):
            validate_outcomes(
                self.outcomes[self.outcomes.scenario == "stable"], self.cfg,
                {"stable": [100, 101], "abrupt": []},
            )

    def test_duplicate_algorithm_seed_config_rejected(self):
        with self.assertRaises(ValueError):
            validate_replay(
                self.replay, self.outcomes,
                dict(self.cfg, algorithm_seeds=[17, 37, 37]),
            )

    def test_boolean_bootstrap_seed_rejected(self):
        with self.assertRaises(ValueError):
            paired_comparisons(
                self.metrics(), self.baselines, dict(self.cfg, bootstrap_seed=True)
            )

    def test_bad_outcome_values_rejected(self):
        duplicate = pd.concat([self.outcomes, self.outcomes.iloc[[0]]], ignore_index=True)
        nonfinite = self.outcomes.copy()
        nonfinite["cost"] = nonfinite.cost.astype(float)
        nonfinite.loc[0, "cost"] = np.inf
        wrong_utility = self.outcomes.copy()
        wrong_utility.loc[0, "utility"] += 0.1
        for name, frame in [("duplicate", duplicate), ("nonfinite", nonfinite), ("utility", wrong_utility)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_outcomes(frame, self.cfg, self.seeds)

    def test_missing_full_replay_groups_rejected(self):
        mutations = {
            "method": self.replay[self.replay.method != "RuleRouter"],
            "algorithm_seed": self.replay[self.replay.alg_seed != 37],
            "last_question": self.replay[self.replay.t != 1],
            "dialogue": self.replay[self.replay.seed != 101],
        }
        for name, frame in mutations.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_replay(frame, self.outcomes, self.cfg)

    def test_bad_replay_values_and_selected_feedback_rejected(self):
        duplicate = pd.concat([self.replay, self.replay.iloc[[0]]], ignore_index=True)
        nonfinite = self.replay.copy()
        nonfinite.loc[0, "utility"] = np.nan
        # Keep the utility formula internally correct while changing the actual
        # chosen-arm feedback: this needs a join against the outcome table.
        wrong_feedback = self.replay.copy()
        wrong_feedback.loc[0, "y"] = 1
        wrong_feedback.loc[0, "utility"] = 1 - wrong_feedback.loc[0, "cost"] / 1024
        for name, frame in [("duplicate", duplicate), ("nonfinite", nonfinite), ("feedback", wrong_feedback)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_replay(frame, self.outcomes, self.cfg)

    def test_incomplete_pair_duplicate_or_nonfinite_metrics_rejected(self):
        metrics = self.metrics()
        incomplete = metrics[~((metrics.seed == 101) & (metrics.method == "TS"))]
        duplicate = pd.concat([metrics, metrics.iloc[[0]]], ignore_index=True)
        nonfinite = metrics.copy()
        nonfinite.loc[0, "utility"] = np.inf
        for name, frame in [("missing_pair", incomplete), ("duplicate", duplicate), ("nonfinite", nonfinite)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                paired_comparisons(frame, self.baselines, self.cfg)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m4_e1_archive_fixture_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, mode):
        """Only the hash verifier is under test, not notebook/CSV parsing."""
        root = self.root / mode
        root.mkdir()
        required = ["config/notebook_snapshot.ipynb", "config/loader_snapshot.py"]
        if mode == "development":
            required.extend([
                "data/development_dialogues.jsonl.gz",
                "tables/development_outcomes.csv", "tables/development_replay.csv",
            ])
        else:
            required.extend([
                "data/evaluation_dialogues.jsonl.gz",
                "tables/evaluation_outcomes.csv", "tables/replay.csv",
            ])
        files = {}
        for relative in required:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = ("SYNTHETIC hash-verifier fixture: " + relative).encode()
            path.write_bytes(content)
            files[relative] = hashlib.sha256(content).hexdigest()
        manifest = {"mode": mode, "fixture": False, "files": files}
        self.write_manifest(root, manifest)
        return root, manifest

    @staticmethod
    def write_manifest(root, manifest):
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_valid_development_and_demo_hashes(self):
        for mode in ["development", "demo"]:
            with self.subTest(mode=mode):
                root, manifest = self.archive(mode)
                self.assertEqual(verified_archive(root), manifest)

    def test_every_consumed_file_requires_a_manifest_entry(self):
        for mode in ["development", "demo"]:
            root, original = self.archive(mode)
            for omitted in original["files"]:
                with self.subTest(mode=mode, omitted=omitted):
                    changed = dict(original, files={
                        key: value for key, value in original["files"].items()
                        if key != omitted
                    })
                    self.write_manifest(root, changed)
                    with self.assertRaises(ValueError):
                        verified_archive(root)

    def test_changed_file_content_rejected(self):
        for mode in ["development", "demo"]:
            with self.subTest(mode=mode):
                root, _ = self.archive(mode)
                (root / "config/loader_snapshot.py").write_bytes(b"changed after archival")
                with self.assertRaises(ValueError):
                    verified_archive(root)

    def test_formal_source_rejected(self):
        root, manifest = self.archive("demo")
        self.write_manifest(root, dict(manifest, mode="formal"))
        with self.assertRaises(ValueError):
            verified_archive(root)

    def test_fixture_source_rejected(self):
        for mode in ["development", "demo"]:
            with self.subTest(mode=mode):
                root, manifest = self.archive(mode)
                self.write_manifest(root, dict(manifest, fixture=True))
                with self.assertRaises(ValueError):
                    verified_archive(root)


if __name__ == "__main__":
    unittest.main()
