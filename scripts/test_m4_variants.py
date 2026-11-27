"""Small development-fixture checks for isolated experimental adapters."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from m4_variants import (load_namespace, configure_namespace, evaluate_episodes,
                         replay_all, validate_config)
from test_member_handoff import load


NOTEBOOK = Path(__file__).resolve().parents[1] / "ARIN7101_Context_Bandit_Release_Notebook.ipynb"


class VariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = load_namespace(NOTEBOOK)
        cls.cfg = deepcopy(cls.ns["PROTOCOL_DRAFT"])
        cls.cfg.update(T=12, n_bootstrap=20)
        cls.episodes = [cls.ns["generate_episode"](seed, scenario, cls.cfg)
                        for seed, scenario in [(130000, "stable"), (130100, "abrupt")]]
        cls.outcomes = evaluate_episodes(cls.ns, cls.episodes, cls.cfg)

    def test_default_matches_notebook(self):
        original_m2 = load(NOTEBOOK, "m2")
        expected = pd.concat([original_m2["evaluate_episode"](e, self.cfg)
                              for e in self.episodes], ignore_index=True)
        pd.testing.assert_frame_equal(self.outcomes.drop(columns="construction_ms"),
                                      expected.drop(columns="construction_ms"))
        original_m3 = load(NOTEBOOK, "m3")
        actual, diagnostics = replay_all(self.ns, self.outcomes, self.cfg)
        expected = pd.concat([original_m3["replay_episode"](g, m, a, self.cfg)
                              for _, g in self.outcomes.groupby(["scenario", "seed"])
                              for m in self.ns["METHODS"] for a in self.cfg["algorithm_seeds"]],
                             ignore_index=True)
        pd.testing.assert_frame_equal(actual, expected)
        self.assertEqual(int(diagnostics.selected_count.sum()), len(actual))
        cts = diagnostics[diagnostics.method == "LaplaceCTS"]
        np.testing.assert_array_equal(cts.refit_count, cts.selected_count // 5)

    def test_constant_only_changes_cts_not_reader_or_router(self):
        constant = configure_namespace(self.ns, {"feature_mode": "constant"})
        question = "What is its current data source?"
        full_router = self.ns["Selector"]("RuleRouter", 17, self.cfg)
        constant_router = constant["Selector"]("RuleRouter", 17, self.cfg)
        self.assertEqual(full_router.choose(question, [20] * 4), 0)
        self.assertEqual(constant_router.choose(question, [20] * 4), 0)
        cts = constant["Selector"]("LaplaceCTS", 17, self.cfg)
        cts.update(0, 1, question)
        np.testing.assert_array_equal(cts.features[0][0], [1, 1, 0])
        full = self.ns["Selector"]("LaplaceCTS", 17, self.cfg)
        full.update(0, 1, question)
        np.testing.assert_array_equal(full.features[0][0], [1, 0, 1])
        context = [{"id": 0, "text": "Focus is project P1."},
                   {"id": 1, "text": "For project P1: the data source is V10."}]
        self.assertEqual(constant["rule_reader"](question, context), "V10")
        self.assertEqual(self.ns["_variant_options"]["feature_mode"], "full")

    def test_only_resolved_arm_changes(self):
        altered = configure_namespace(self.ns, {"resolved_top_k": 1, "preserve_focus": False})
        observed = evaluate_episodes(altered, self.episodes, self.cfg)
        selected = self.outcomes.arm != "resolved_tfidf"
        pd.testing.assert_frame_equal(self.outcomes.loc[selected].drop(columns="construction_ms"),
                                      observed.loc[selected].drop(columns="construction_ms"))
        self.assertFalse(self.outcomes.loc[~selected, ["y", "cost", "coverage"]].equals(
                         observed.loc[~selected, ["y", "cost", "coverage"]]))

    def test_retrieval_switches_have_the_intended_scope(self):
        view = {"question": "What is its current data source?", "history": [
            {"id": 0, "text": "Focus is project P1."},
            {"id": 1, "text": "For project P1: the data source is V10."}]}
        unresolved = configure_namespace(self.ns, {"resolve_pronouns": False})
        rank = unresolved["m2_rank_tfidf"](view, resolved=True)
        self.assertEqual(rank["query"].iloc[0], "its dataset")
        literal = configure_namespace(self.ns, {"normalize_aliases": False})
        rank = literal["m2_rank_tfidf"](view, resolved=True)
        self.assertEqual(rank["query"].iloc[0], "P1 data source")
        self.assertIn("data source", " ".join(rank.document))
        self.assertEqual(literal["rule_reader"](view["question"], view["history"]), "V10")
        for changed in (unresolved, literal):
            pd.testing.assert_frame_equal(changed["m2_rank_tfidf"](view, resolved=False),
                                          self.ns["m2_rank_tfidf"](view, resolved=False))

    def test_focus_switch_changes_packing_not_rank(self):
        view = {"question": "What is its current dataset?", "history": [
            {"id": 0, "text": "Focus is project P1."},
            {"id": 1, "text": "For project P1: the dataset is V10."}]}
        with_focus = configure_namespace(self.ns, {"resolved_top_k": 1})
        without_focus = configure_namespace(self.ns, {"resolved_top_k": 1, "preserve_focus": False})
        pd.testing.assert_frame_equal(with_focus["m2_rank_tfidf"](view, resolved=True),
                                      without_focus["m2_rank_tfidf"](view, resolved=True))
        self.assertEqual([m["id"] for m in with_focus["select_context"](view, "resolved_tfidf", self.cfg)], [0, 1])
        self.assertEqual([m["id"] for m in without_focus["select_context"](view, "resolved_tfidf", self.cfg)], [1])

    def test_no_normalization_preserves_every_alias_in_query_and_index(self):
        literal = configure_namespace(self.ns, {"normalize_aliases": False})
        for canonical, alias in self.ns["M2_ALIASES"].items():
            with self.subTest(alias=alias):
                view = {"question": f"What is its current {alias}?", "history": [
                    {"id": 0, "text": "Focus is project P1."},
                    {"id": 1, "text": f"For project P1: the {alias} is V10."}]}
                ranked = literal["m2_rank_tfidf"](view, resolved=True)
                self.assertEqual(set(ranked["query"]), {f"P1 {alias}"})
                self.assertEqual(ranked.set_index("id").loc[1, "document"], view["history"][1]["text"])
                normalized = self.ns["m2_rank_tfidf"](view, resolved=True)
                self.assertEqual(set(normalized["query"]), {f"P1 {canonical}"})
                self.assertEqual(literal["rule_reader"](view["question"], view["history"]), "V10")

    def test_no_coreference_preserves_explicit_project_priority(self):
        unresolved = configure_namespace(self.ns, {"resolve_pronouns": False})
        view = {"question": "What is P2 current dataset?", "history": [
            {"id": 0, "text": "Focus is project P1."},
            {"id": 1, "text": "For project P2: the dataset is V10."}]}
        pd.testing.assert_frame_equal(unresolved["m2_rank_tfidf"](view, resolved=True),
                                      self.ns["m2_rank_tfidf"](view, resolved=True))

    def test_constant_selected_feedback_isolation(self):
        constant = configure_namespace(self.ns, {"feature_mode": "constant"})
        frame = self.outcomes[self.outcomes.scenario == "abrupt"].copy()
        before = constant["replay_episode"](frame, "LaplaceCTS", 17, self.cfg)
        selected = dict(zip(before.t, before.arm))
        mask = frame.apply(lambda row: row.arm != selected[row.t], axis=1)
        frame.loc[mask, "y"] = 1 - frame.loc[mask, "y"]
        frame["utility"] = frame.y - self.cfg["lambda"] * frame.cost / self.cfg["cost_reference"]
        pd.testing.assert_frame_equal(before, constant["replay_episode"](frame, "LaplaceCTS", 17, self.cfg))

    def test_refit_is_per_arm_and_precision_changes_prior(self):
        cfg = deepcopy(self.cfg)
        cfg.update(refit_every=2, prior_precision=10)
        selector = self.ns["Selector"]("LaplaceCTS", 17, cfg)
        np.testing.assert_allclose(selector.covariance[0], np.eye(3) / 10)
        selector.update(0, 1, "What is its current dataset?")
        selector.update(1, 1, "What is P1 current dataset?")
        np.testing.assert_array_equal(selector.refit_counts, [0, 0, 0, 0])
        selector.update(0, 0, "What is P1 current dataset?")
        np.testing.assert_array_equal(selector.refit_counts, [1, 0, 0, 0])
        self.assertEqual(self.cfg["refit_every"], 5)

    def test_environment_override_is_explicit_and_isolated(self):
        cfg = dict(deepcopy(self.cfg), n_projects=3, alias_probability=1,
                   update_probability=0.5, initial_conflict_fraction=0)
        validate_config(cfg)
        episode = self.ns["generate_episode"](130000, "stable", cfg)
        self.assertTrue(self.ns["audit_truth"](episode)["passed"])
        self.assertNotEqual(episode, self.episodes[0])
        self.assertEqual(self.ns["generate_episode"](130000, "stable", self.cfg), self.episodes[0])

    def test_invalid_config_and_adapter_fail_early(self):
        for updates in ({"T": True}, {"prior_precision": 0}, {"lambda": float("nan")},
                        {"algorithm_seeds": [17, 17]}, {"alias_probability": 2},
                        {"refit_every": 0}, {"n_projects": 1}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_config(dict(deepcopy(self.cfg), **updates))
        for adapter in ({"unknown": 1}, {"resolved_top_k": True},
                        {"normalize_aliases": 0}, {"feature_mode": "none"}):
            with self.subTest(adapter=adapter), self.assertRaises(ValueError):
                configure_namespace(self.ns, adapter)


if __name__ == "__main__":
    unittest.main()
