"""Read-only source checks and isolated mutation tests for M5 development figures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import m5_visuals as m5

SOURCE = m5.ROOT / "deliverables/M4_full_development_20261126"


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m5_test_")
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/"source"
        shutil.copytree(SOURCE, self.source)

    def rebind(self, name):
        path = self.source/"artifact_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["files"][name] = hashlib.sha256((self.source/name).read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def edit_json(self, name, mutate, rebind=True):
        path = self.source/name
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        if rebind: self.rebind(name)

    def edit_csv(self, name, mutate):
        path = self.source/name
        frame = mutate(pd.read_csv(path))
        frame.to_csv(path, index=False)
        self.rebind(name)

    def rejects(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            m5.load_verified_run(self.source)

    def test_published_package_has_expected_scope(self):
        result = m5.load_verified_run(self.source)
        self.assertEqual(result["verified_files"], 46)
        self.assertFalse(result["raw_trajectories_verified"])
        self.assertEqual(result["mode"], "development")
        self.assertEqual(len(result["overview"]), 14)
        self.assertEqual(len(result["effects"]), 6)
        self.assertEqual(len(result["cumulative"]), 1800)
        self.assertEqual(len(result["sensitivity"]["E2"]["pairs"]), 210)
        self.assertEqual(len(result["sensitivity"]["E4"]["pairs"]), 336)

    def test_changed_file_rejected(self):
        with (self.source/"method_metrics.csv").open("a") as f: f.write("\n")
        self.rejects("hash mismatch")

    def test_missing_file_rejected(self):
        (self.source/"temporal/query_effects.csv").unlink()
        self.rejects("Missing source file")

    def test_unbound_file_rejected(self):
        self.edit_json("artifact_manifest.json", lambda d: d["files"].pop("primary_effects.csv"), rebind=False)
        self.rejects("not bound")

    def test_outside_path_rejected(self):
        self.edit_json("artifact_manifest.json", lambda d: d["files"].update({"../external":"0"*64}), rebind=False)
        self.rejects("Unsafe manifest path")

    def test_formal_mode_rejected(self):
        self.edit_json("artifact_manifest.json", lambda d: d.update(formal_generated=True), rebind=False)
        self.rejects("mode/schema")

    def test_different_e3_configuration_rejected(self):
        self.edit_json("plans/E3.json", lambda d: d["config"].update({"lambda":1.}))
        self.rejects("configuration")

    def test_different_e3_source_rejected(self):
        self.edit_json("plans/E3.json", lambda d: d.update(source_manifest_sha256="0"*64))
        self.rejects("source identity")

    def test_duplicate_key_even_with_new_hash_rejected(self):
        def duplicate(f):
            return pd.concat([f,f.loc[f.stage.eq("E1") & f.variant.eq("default")].iloc[[0]]], ignore_index=True)
        self.edit_csv("method_metrics.csv", duplicate)
        self.rejects("duplicate key")

    def test_wrong_utility_even_with_new_hash_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E1") & f.method.eq("TS"), "utility"] += .1
            return f
        self.edit_csv("method_metrics.csv", change)
        self.rejects("Utility decomposition")

    def test_missing_question_type_rejected(self):
        self.edit_csv("temporal/query_effects.csv", lambda f:f.iloc[1:])
        self.rejects("grid")

    def test_wrong_n_not_inferred_from_questions(self):
        def change(f):
            f.loc[0,"n"] = 450
            return f
        self.edit_csv("temporal/phase_effects.csv", change)
        self.rejects("dialogue count")

    def test_changed_trajectory_endpoint_rejected(self):
        def change(f):
            f.loc[f.t.eq(299), ["effect","low","high"]] += 1
            return f
        self.edit_csv("temporal/cumulative_effects.csv", change)
        self.rejects("endpoint/E1")

    def test_incorrect_question_count_rejected(self):
        def change(f):
            f.loc[0,"n_questions"] -= 1
            return f
        self.edit_csv("temporal/query_summary.csv", change)
        self.rejects("question counts")

    def test_e2_reversed_effect_direction_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E2"),"direction"] = "variant_minus_default"
            return f
        self.edit_csv("variant_effects.csv",change)
        self.rejects("E2: effect direction")

    def test_e2_missing_paired_dialogue_rejected(self):
        self.edit_csv("variant_dialogue_differences.csv",lambda f:f.drop(f.index[f.stage.eq("E2")][0]))
        self.rejects("E2 paired dialogues.*grid")

    def test_e2_wrong_paired_value_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E2") & f.method.eq("LaplaceCTS"),"difference"] *= -1
            return f
        self.edit_csv("variant_dialogue_differences.csv",change)
        self.rejects("paired dialogue difference")

    def test_e2_feature_mode_mismatch_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E2") & f.variant.eq("constant_features"),"feature_mode"] = "full"
            return f
        self.edit_csv("selector_diagnostics.csv",change)
        self.rejects("feature mode")

    def test_missing_algorithm_seed_in_selections_rejected(self):
        self.edit_csv("selector_diagnostics.csv",lambda f:f.loc[~(f.stage.eq("E2") & f.alg_seed.eq(37))])
        self.rejects("arm selections.*grid")

    def test_wrong_selection_denominator_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E2"),"selected_share"] /= 2
            return f
        self.edit_csv("selector_diagnostics.csv",change)
        self.rejects("share/count")

    def test_e4_wrong_lambda_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E4") & f.variant.eq("lambda_025"),"lambda"] = .5
            return f
        self.edit_csv("method_metrics.csv",change)
        self.rejects("E4: lambda mismatch")

    def test_e4_mixed_configuration_rejected(self):
        self.edit_json("plans/E4.json",lambda d:d["config"].update(cost_reference=1024))
        self.rejects("E4: mixed configuration")

    def test_e4_cross_lambda_utility_rejected(self):
        def change(f):
            f.loc[f.stage.eq("E4") & f.metric.eq("coverage"),"metric"] = "utility"
            return f
        self.edit_csv("variant_effects.csv",change)
        self.rejects("E4 variant effects.*grid")

    def test_wrong_dialogue_mean_rejected(self):
        def change(f):
            mask=f.stage.eq("E4") & f.method.eq("LaplaceCTS") & f.metric.eq("y")
            f.loc[mask,["mean","minimum","maximum"]] += .01
            return f
        self.edit_csv("algorithm_seed_spread.csv",change)
        self.rejects("dialogue/method mean")


class FigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results=m5.load_verified_run(SOURCE)
        cls.figures,cls.tables=m5.build_figures(cls.results, cls.results["config"])

    @classmethod
    def tearDownClass(cls):
        for fig in cls.figures.values(): plt.close(fig)

    def test_plot_configuration_mismatch_rejected(self):
        cfg=deepcopy(self.results["config"]); cfg["lambda"]=1.
        with self.assertRaisesRegex(ValueError,"configuration"):
            m5.build_figures(self.results,cfg)

    def test_plotted_effects_and_curves_match_tables(self):
        effect_table=self.tables["E1_effects"].set_index(["scenario","comparison"])
        for ax,s in zip(self.figures["E1_effects"].axes,m5.SCENARIOS):
            # The three marker lines are the plotted estimates, independent of caps.
            points=[line.get_xdata()[0] for line in ax.lines if line.get_marker()=="o"]
            np.testing.assert_allclose(points,[effect_table.loc[(s,c),"effect"] for c in m5.COMPARISONS])
        curve_table=self.tables["E3_temporal"]
        for ax,s in zip(self.figures["E3_temporal"].axes,m5.SCENARIOS):
            for line,c in zip(ax.lines[:3],m5.COMPARISONS):
                expected=curve_table.query("scenario == @s and comparison == @c").sort_values("t")
                np.testing.assert_array_equal(line.get_xdata(),expected.completed_questions)
                np.testing.assert_array_equal(line.get_ydata(),expected.effect)

    def test_export_hashes_exact_tables_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="m5_export_") as tmp, patch.object(m5,"ROOT",Path(tmp)):
            output=m5.export_visual_evidence(self.figures,self.tables,SOURCE,"test_export")
            manifest=json.loads((output/"reports/figure_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["raw_trajectories_verified"])
            self.assertTrue((output/"reports/E2_E4_interpretations.md").is_file())
            self.assertTrue((output/"config/code/m5_sensitivity.py").is_file())
            for name,digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),digest)
            for name,table in self.tables.items():
                saved=pd.read_csv(output/f"tables/figure_{name}.csv")
                pd.testing.assert_frame_equal(saved,table,check_exact=False,atol=1e-12,rtol=0)
            with self.assertRaises(FileExistsError):
                m5.export_visual_evidence(self.figures,self.tables,SOURCE,"test_export")
            bad=deepcopy(self.tables); bad["E1_effects"].loc[0,"effect"] += 1
            with self.assertRaises(AssertionError):
                m5.export_visual_evidence(self.figures,bad,SOURCE,"altered")
            self.assertFalse((Path(tmp)/"outputs/development/altered").exists())
            with self.assertRaisesRegex(ValueError,"render_id"):
                m5.export_visual_evidence(self.figures,self.tables,SOURCE,"../escape")

    def test_e2_plot_units_and_selection_totals(self):
        effects=self.tables["E2_effects"].set_index(["scenario","metric"])
        for ax,metric in zip(self.figures["E2_effects"].axes,m5.sensitivity.METRIC_STYLE):
            points=[line.get_xdata()[0] for line in ax.lines if line.get_marker()=="o"]
            scale=100 if metric in ("y","coverage","outdated") else 1
            np.testing.assert_allclose(points,[effects.loc[(s,metric),"effect"]*scale for s in m5.SCENARIOS])
        table=self.tables["E2_selection"]
        np.testing.assert_allclose(table.groupby(["scenario","variant"]).selected_share.sum(),1)
        for ax,s in zip(self.figures["E2_selection"].axes,m5.SCENARIOS):
            expected=table.query("scenario == @s").set_index(["variant","arm"])
            for bars,arm in zip(ax.containers,m5.sensitivity.ARMS):
                np.testing.assert_allclose([b.get_width() for b in bars],[expected.loc[(v,arm),"selected_percent"] for v in m5.sensitivity.VARIANTS["E2"]])

    def test_e4_plotted_points_and_effects_match_tables(self):
        for ax,s in zip(self.figures["E4_tradeoff"].axes,m5.SCENARIOS):
            for line,method in zip(ax.lines[:2],["LaplaceCTS","TS"]):
                d=self.tables["E4_tradeoff"].query("scenario == @s and method == @method").sort_values("lambda")
                np.testing.assert_array_equal(line.get_xdata(),d.cost)
                np.testing.assert_array_equal(line.get_ydata(),100*d.y)
        for ax,s in zip(self.figures["E4_effects"].axes,m5.SCENARIOS):
            points=[line for line in ax.lines if line.get_marker()=="o"]
            for line,c in zip(points,m5.COMPARISONS):
                d=self.tables["E4_effects"].query("scenario == @s and comparison == @c").sort_values("lambda")
                np.testing.assert_array_equal(line.get_ydata(),d.effect)


if __name__ == "__main__":
    unittest.main(verbosity=2)
