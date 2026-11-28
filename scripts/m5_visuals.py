"""M5 E1-E4 figures from a verified published development evidence package.

This reader deliberately supports the published-summary schema only. It does
not certify missing raw trajectories, accept formal/demo runs, or run M4 code.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

if __package__:
    from . import m5_sensitivity as sensitivity
else:
    import m5_sensitivity as sensitivity

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("stable", "abrupt")
METHODS = ("recent_short", "recent_long", "tfidf", "resolved_tfidf", "TS", "LaplaceCTS", "RuleRouter")
METRICS = ("y", "cost", "utility", "coverage", "outdated")
COMPARISONS = ("cts_vs_fixed", "cts_vs_ts", "cts_vs_router")
LABELS = {"cts_vs_fixed": "Fixed reference", "cts_vs_ts": "TS", "cts_vs_router": "RuleRouter"}
COLORS = {"cts_vs_fixed": "#2166AC", "cts_vs_ts": "#C66B20", "cts_vs_router": "#64748B"}
BASE_FIGURE_IDS = ("E1_overview", "E1_effects", "E3_temporal", "E3_groups")
FIGURE_IDS = ("E1_overview", "E1_effects", "E2_effects", "E2_selection", "E3_temporal", "E3_groups", "E4_tradeoff", "E4_effects")
SOURCE_FILES = (
    "method_metrics.csv", "primary_effects.csv", "direct_comparisons.csv",
    "temporal/cumulative_effects.csv", "temporal/phase_summary.csv",
    "temporal/query_summary.csv", "temporal/phase_effects.csv",
    "temporal/query_effects.csv", "temporal/post_pre_effects.csv",
    "plans/E1.json", "plans/E3.json", "verification.json",
) + sensitivity.SOURCE_FILES


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe_child(root, name):
    relative = Path(name)
    path = (root / relative).resolve()
    _require(not relative.is_absolute() and path != root and path.is_relative_to(root),
             "Unsafe manifest path: " + str(name))
    return path


def _grid(frame, keys, expected, name):
    _require(set(keys).issubset(frame.columns), name + ": missing key columns")
    _require(not frame[keys].isna().any().any(), name + ": missing key")
    _require(not frame.duplicated(keys).any(), name + ": duplicate key")
    _require(set(frame[keys].itertuples(index=False, name=None)) == set(expected), name + ": incomplete/unexpected grid")


def _finite(frame, columns, name):
    _require(set(columns).issubset(frame.columns), name + ": missing metric columns")
    _require(np.isfinite(frame[list(columns)].to_numpy(dtype=float)).all(), name + ": nonfinite value")


def _close(actual, expected, message):
    _require(np.allclose(actual, expected, rtol=0, atol=1e-9), message)


def _intervals(frame, n, name):
    _finite(frame, ["n", "effect", "low", "high"], name)
    _require(frame.n.eq(n).all(), name + ": dialogue count mismatch")
    _require((frame.low <= frame.effect + 1e-12).all() and (frame.effect <= frame.high + 1e-12).all(),
             name + ": invalid interval")


def load_verified_run(run_dir):
    """Read the supported summary package; verify all hashes and E1-E4 consistency.

    Missing groups are rejected for this fully observed E1/E3 release, rather
    than silently plotted as zero. Future raw-run schemas need a new adapter.
    """
    source = Path(run_dir).resolve()
    manifest_path = source / "artifact_manifest.json"
    _require(manifest_path.is_file(), "Expected published development artifact_manifest.json; raw/demo/formal runs are not supported")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(manifest.get("schema_version") == "m4-development-evidence-manifest-v1"
             and manifest.get("formal_generated") is False, "Unsupported source mode/schema")
    files = manifest.get("files", {})
    _require(isinstance(files, dict) and set(SOURCE_FILES).issubset(files), "Source files not bound by manifest")
    for name, digest in files.items():
        path = _safe_child(source, name)
        _require(path.is_file(), "Missing source file: " + name)
        _require(isinstance(digest, str) and _hash(path) == digest, "Source hash mismatch: " + name)
    read_json = lambda name: json.loads((source / name).read_text(encoding="utf-8"))
    plan, temporal_plan, verification = (read_json(n) for n in ("plans/E1.json", "plans/E3.json", "verification.json"))
    cfg = plan["config"]
    n, T = cfg["n_dev_per_scenario"], cfg["T"]
    _require(isinstance(n, int) and not isinstance(n, bool) and n >= 2 and isinstance(T, int)
             and not isinstance(T, bool) and T > 1 and T % 2 == 0, "Invalid dialogue design")
    _require(plan.get("stage") == "E1" and plan.get("profile") == "development"
             and plan.get("formal") is False and plan.get("fixture") is False, "Mixed source mode")
    _require(temporal_plan.get("source_mode") == "development" and temporal_plan.get("fixture") is False
             and temporal_plan.get("variant") == "default" and temporal_plan.get("config") == cfg, "Mixed E1/E3 configuration")
    _require(verification.get("formal_generated") is False
             and verification.get("execution_commit") == manifest.get("execution_commit")
             and verification.get("n_per_scenario") == n and verification.get("questions_per_dialogue") == T,
             "Source verification/configuration mismatch")
    _require(verification.get("independent_unit") == "dialogue", "Unsupported independent unit")
    e1_runs = [r for r in verification.get("runs", []) if r.get("stage") == "E1"]
    e3_runs = [r for r in verification.get("runs", []) if r.get("stage") == "E3"]
    _require(len(e1_runs) == len(e3_runs) == 1, "Missing/ambiguous E1/E3 source run")
    _require(temporal_plan.get("source_manifest_sha256") == e1_runs[0].get("manifest_sha256")
             == e3_runs[0].get("source", {}).get("manifest_sha256"), "Mixed E1/E3 source identity")
    _require(all(r.get("fixture") is False and r.get("formal_generated") is False for r in [*e1_runs, *e3_runs]),
             "Mixed execution mode")
    seeds = plan.get("dialogue_seeds", {})
    _require(set(seeds) == set(SCENARIOS) and all(len(seeds[s]) == n for s in SCENARIOS)
             and len(set(itertools.chain.from_iterable(seeds.values()))) == 2*n
             and verification.get("dialogue_seeds") == seeds, "Dialogue identities mismatch")
    baselines = temporal_plan.get("baselines", {})
    _require(set(baselines) == set(SCENARIOS) and all(b in METHODS[:4] for b in baselines.values()), "Invalid fixed references")

    tables = {name: pd.read_csv(source / name) for name in SOURCE_FILES if name.endswith(".csv")}
    def default(name):
        f = tables[name]
        _require({"stage", "variant"}.issubset(f), name + ": no stage/variant")
        return f.loc[f.stage.eq("E1") & f.variant.eq("default")].copy()
    overview, primary, direct = (default(name) for name in ("method_metrics.csv", "primary_effects.csv", "direct_comparisons.csv"))
    _grid(overview, ["scenario", "method"], itertools.product(SCENARIOS, METHODS), "overview")
    _finite(overview, [*METRICS, "n", "algorithm_seed_count", "lambda"], "overview")
    _require(overview.n.eq(n).all() and overview.algorithm_seed_count.eq(len(cfg["algorithm_seeds"])).all(), "Overview sample counts mismatch")
    _require(overview["lambda"].eq(cfg["lambda"]).all(), "Overview lambda mismatch")
    _require(overview[["y", "coverage", "outdated"]].ge(0).all().all()
             and overview[["y", "coverage", "outdated"]].le(1).all().all()
             and overview.cost.ge(0).all(), "Invalid metric range")
    _close(overview.utility, overview.y - cfg["lambda"]*overview.cost/cfg["cost_reference"], "Utility decomposition mismatch")
    means = overview.set_index(["scenario", "method"])
    _grid(primary, ["scenario", "method"], itertools.product(SCENARIOS, ["LaplaceCTS"]), "primary")
    _intervals(primary, n, "primary")
    _finite(primary, ["family_low", "family_high"], "primary")
    _require((primary.family_low <= primary.low+1e-12).all()
             and (primary.family_high >= primary.high-1e-12).all(), "Invalid 97.5% interval")
    _grid(direct, ["scenario", "comparison", "metric"],
          itertools.product(SCENARIOS, COMPARISONS[1:], METRICS), "direct")
    _intervals(direct, n, "direct")
    references = {(s, c): baselines[s] if c == "cts_vs_fixed" else ("TS" if c == "cts_vs_ts" else "RuleRouter")
                  for s in SCENARIOS for c in COMPARISONS}
    for r in primary.itertuples():
        _require(r.baseline == baselines[r.scenario], "Primary baseline mismatch")
        _close(r.effect, means.loc[(r.scenario, "LaplaceCTS"), "utility"] - means.loc[(r.scenario, r.baseline), "utility"], "Primary effect mismatch")
    for r in direct.itertuples():
        _require(r.reference == references[(r.scenario, r.comparison)], "Direct reference mismatch")
        _close(r.effect, means.loc[(r.scenario, "LaplaceCTS"), r.metric] - means.loc[(r.scenario, r.reference), r.metric], "Direct effect mismatch")
    effects = pd.concat([primary.rename(columns={"baseline": "reference"}).assign(comparison="cts_vs_fixed", metric="utility"),
                         direct.loc[direct.metric.eq("utility")]], ignore_index=True)
    effects = effects.drop(columns=["method"], errors="ignore")
    eindex = effects.set_index(["scenario", "comparison"])
    cumulative = tables["temporal/cumulative_effects.csv"]
    _grid(cumulative, ["scenario", "comparison", "t"], itertools.product(SCENARIOS, COMPARISONS, range(T)), "cumulative")
    _intervals(cumulative, n, "cumulative")
    _require(cumulative.interval_scope.eq("pointwise").all()
             and cumulative.simultaneous.eq(False).all() and cumulative.confidence.eq(.95).all(), "Cumulative interval semantics mismatch")
    for (s, c), group in cumulative.groupby(["scenario", "comparison"]):
        _require(group.reference.eq(references[(s, c)]).all(), "Cumulative reference mismatch")
        _close(group.loc[group.t.eq(T-1), "effect"].iloc[0]/T, eindex.loc[(s, c), "effect"], "Cumulative endpoint/E1 mismatch")
    grouped = []
    for dimension, levels, stem in [("phase", ["pre", "post"], "phase"), ("qtype", ["recent", "historical"], "query")]:
        summary = tables[f"temporal/{stem}_summary.csv"]
        effects_table = tables[f"temporal/{stem}_effects.csv"]
        _grid(summary, ["scenario", "method", dimension], itertools.product(SCENARIOS, METHODS, levels), stem+" summary")
        _finite(summary, [*METRICS, "n", "n_total", "n_missing", "n_questions"], stem+" summary")
        _require(summary.n.eq(n).all() and summary.n_total.eq(n).all() and summary.n_missing.eq(0).all(), "Missing dialogue subgroup; this release requires complete groups")
        _close(summary.utility, summary.y-cfg["lambda"]*summary.cost/cfg["cost_reference"], stem+" utility mismatch")
        for (_, _), group in summary.groupby(["scenario", "method"]):
            _require(group.n_questions.sum() == n*T and (group.n_questions > 0).all(), "Subgroup question counts mismatch")
            if dimension == "phase":
                _require(group.n_questions.eq(n*T//2).all(), "Phase question counts mismatch")
        sm = summary.set_index(["scenario", "method", dimension])
        _grid(effects_table, ["scenario", "comparison", dimension, "metric"],
              itertools.product(SCENARIOS, COMPARISONS, levels, METRICS), stem+" effects")
        _intervals(effects_table, n, stem+" effects")
        _require(effects_table.n_total.eq(n).all() and effects_table.n_missing.eq(0).all()
                 and effects_table.confidence.eq(.95).all() and effects_table.simultaneous.eq(False).all(), stem+" semantics mismatch")
        for _, r in effects_table.iterrows():
            ref = references[(r.scenario, r.comparison)]
            _require(r.reference == ref, stem+" reference mismatch")
            _close(r.effect, sm.loc[(r.scenario, "LaplaceCTS", r[dimension]), r.metric]
                   - sm.loc[(r.scenario, ref, r[dimension]), r.metric], stem+" effect mismatch")
            _require(r.n_questions == sm.loc[(r.scenario, "LaplaceCTS", r[dimension]), "n_questions"], stem+" question count mismatch")
        grouped.append(effects_table.loc[effects_table.metric.eq("utility")].rename(columns={dimension:"group"}).assign(dimension=dimension))
    groups = pd.concat(grouped, ignore_index=True)
    post_pre = tables["temporal/post_pre_effects.csv"]
    _grid(post_pre, ["scenario", "comparison", "metric"], itertools.product(SCENARIOS, COMPARISONS, METRICS), "post-pre")
    _intervals(post_pre, n, "post-pre")
    phase = tables["temporal/phase_effects.csv"].set_index(["scenario", "comparison", "phase", "metric"])
    for r in post_pre.itertuples():
        _require(r.reference == references[(r.scenario, r.comparison)] and r.n_total == n
                 and r.n_missing == 0 and r.n_questions == n*T and r.confidence == .95
                 and r.simultaneous is False, "Post-pre metadata mismatch")
        _close(r.effect, phase.loc[(r.scenario, r.comparison, "post", r.metric), "effect"]
               - phase.loc[(r.scenario, r.comparison, "pre", r.metric), "effect"], "Post-pre mismatch")
        if r.metric == "utility":
            _close((phase.loc[(r.scenario, r.comparison, "post", r.metric), "effect"]
                    + phase.loc[(r.scenario, r.comparison, "pre", r.metric), "effect"])/2,
                   eindex.loc[(r.scenario, r.comparison), "effect"], "Phase/full E1 mismatch")
    sensitivity_data = sensitivity.load(tables, {s:read_json(f"plans/{s}.json") for s in ("E2","E4")},
                                        verification, cfg, seeds, overview, baselines)
    return dict(source_dir=str(source), manifest_sha256=_hash(manifest_path), config=deepcopy(cfg),
                mode="development", source_kind="published_summary", execution_commit=manifest["execution_commit"],
                verified_files=len(files), source_files=deepcopy(files), baselines=baselines,
                overview=overview, effects=effects, cumulative=cumulative, groups=groups,
                post_pre=post_pre, sensitivity=sensitivity_data, raw_trajectories_verified=False)


def _figure_tables(results):
    tables = dict(zip(BASE_FIGURE_IDS, [results["overview"].copy(), results["effects"].copy(),
                                 results["cumulative"].copy(), results["groups"].copy()]))
    tables["E3_temporal"]["completed_questions"] = tables["E3_temporal"].t+1
    tables.update(sensitivity.figure_tables(results))
    for table in tables.values():
        table.reset_index(drop=True, inplace=True)
        table["source_mode"] = results["mode"]
        table["source_manifest_sha256"] = results["manifest_sha256"]
        table["execution_commit"] = results["execution_commit"]
    return tables


def _canvas(title, cfg, figsize=(13.33, 7.5)):
    fig = plt.figure(figsize=figsize, facecolor="white")
    fig.text(.04, .94, title, fontsize=20, weight="bold", color="#172B43")
    fig.text(.04, .892, f'DEVELOPMENT / EXPLORATORY    n={cfg["n_dev_per_scenario"]} dialogues per scenario; '
             f'{cfg["T"]} questions/dialogue; {len(cfg["algorithm_seeds"])} algorithm seeds averaged within dialogue',
             fontsize=10, color="#58677A")
    return fig


def _footer(fig, text):
    fig.text(.04, .065, text, fontsize=9.2, color="#526173", linespacing=1.65)


def _axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#CCD5E0")
    ax.grid(axis="x", color="#E5EBF2", lw=.7)
    ax.set_axisbelow(True)


def build_figures(results, cfg):
    """Return eight Matplotlib figures and their exact source-value CSV tables."""
    _require(cfg == results["config"], "Plot configuration differs from verified source")
    tables = _figure_tables(results)
    figures = {}
    with plt.rc_context({"font.family":"DejaVu Sans", "font.size":11, "svg.fonttype":"path", "axes.labelcolor":"#334155"}):
        fig = _canvas("E1  Seven methods: accuracy, cost and utility", cfg)
        for j, scenario in enumerate(SCENARIOS):
            ax = fig.add_axes([.04 + j*.48, .22, .44, .58])
            ax.axis("off")
            ax.set_title(scenario, fontsize=15, weight="bold", loc="left", pad=16)
            data = results["overview"].set_index(["scenario", "method"])
            content = []
            for method in METHODS:
                r = data.loc[(scenario, method)]
                content.append([method, f"{100*r.y:.2f}", f"{r.cost:.2f}", f"{r.utility:.4f}",
                                f"{100*r.coverage:.2f}", f"{100*r.outdated:.2f}"])
            table = ax.table(cellText=content, colLabels=["Method", "Acc.\n(%)", "Input\nunits", "Utility", "Latest\n(%)", "Old\n(%)"],
                             colWidths=[.30,.14,.15,.14,.14,.13], cellLoc="right", bbox=[0,0,1,1])
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            for (row, col), cell in table.get_celld().items():
                cell.set_edgecolor("white")
                if row == 0:
                    cell.set_facecolor("#213C58"); cell.set_text_props(color="white", weight="bold", ha="center")
                else:
                    cell.set_facecolor("#E7F0FA" if METHODS[row-1] == "LaplaceCTS" else ("#F7EBDD" if METHODS[row-1] == "RuleRouter" else ("#F2F5F8" if row%2 else "white")))
                    if col == 0: cell.set_text_props(ha="left")
        _footer(fig, f'Utility = accuracy (0-1 scale) - {cfg["lambda"]:g} × input units / {cfg["cost_reference"]:g}. Input units count the complete prompt, not API tokens or fees.\nLatest = latest-evidence coverage; Old = outdated-answer rate. Values are equally weighted dialogue means; no intervals in this overview.')
        figures["E1_overview"] = fig

        fig = _canvas("E1  CTS relative to three references", cfg)
        axs = fig.subplots(1, 2, sharex=True)
        fig.subplots_adjust(left=.15, right=.97, top=.78, bottom=.25, wspace=.5)
        for ax, scenario in zip(axs, SCENARIOS):
            data = results["effects"].set_index(["scenario", "comparison"])
            for k, comparison in enumerate(COMPARISONS):
                r = data.loc[(scenario, comparison)]
                color = COLORS[comparison]
                if comparison == "cts_vs_fixed":
                    ax.hlines(2-k, r.family_low, r.family_high, color=color, lw=1, alpha=.6)
                ax.errorbar(r.effect, 2-k, xerr=[[r.effect-r.low], [r.high-r.effect]], fmt="o", color=color, capsize=5, lw=2, ms=7)
                ax.text(r.effect, 2-k+.19, f"{r.effect:+.4f}", ha="center", fontsize=10, color=color)
            ax.set_yticks([2,1,0], [results["baselines"][scenario], "TS", "RuleRouter"])
            ax.set_ylim(-.5,2.6); ax.set_xlim(-.065,.21)
            ax.axvline(0, color="#7A8797", ls="--", lw=1)
            ax.set_title(scenario, loc="left", fontsize=15, weight="bold", pad=15)
            ax.set_xlabel("Mean utility difference (CTS - reference)", fontsize=10, labelpad=12)
            _axes(ax)
        _footer(fig, 'Points: paired dialogue mean differences. Thick lines: exploratory 95% bootstrap intervals.\nFixed-reference 97.5% intervals are also drawn; their endpoints overlap the 95% intervals in this small development sample.\nPositive values favor CTS. Negative RuleRouter comparisons are retained. These are not confirmatory test results.')
        figures["E1_effects"] = fig

        fig = _canvas("E3  How paired utility differences accumulate", cfg)
        axs = fig.subplots(1, 2)
        fig.subplots_adjust(left=.075, right=.97, top=.77, bottom=.25, wspace=.25)
        for ax, scenario in zip(axs, SCENARIOS):
            for comparison in COMPARISONS:
                data = results["cumulative"].query("scenario == @scenario and comparison == @comparison").sort_values("t")
                x = data.t.to_numpy()+1
                ax.plot(x, data.effect, color=COLORS[comparison], lw=1.7, label=LABELS[comparison])
                ax.fill_between(x, data.low, data.high, color=COLORS[comparison], alpha=.12, linewidth=0)
            ax.axhline(0, color="#7A8797", lw=1)
            ax.axvline(cfg["T"]//2, color="#7A8797", ls="--", lw=1)
            ax.text(.52,.96, "Second half" if scenario=="stable" else f'Switch after Q{cfg["T"]//2}', transform=ax.transAxes, va="top", fontsize=10)
            ax.set_xlim(0,cfg["T"]); ax.set_xlabel("Completed questions")
            ax.set_ylabel("Cumulative utility difference")
            ax.set_title(scenario+"; fixed = "+results["baselines"][scenario], loc="left", fontsize=11.5, pad=12)
            _axes(ax)
        fig.legend(*axs[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(.52,.855), ncol=3, frameon=False, fontsize=10)
        _footer(fig, 'Every curve is CTS minus its stated reference. Shading: exploratory 95% pointwise paired intervals, not simultaneous bands.\nEach panel has its own vertical scale. Algorithm seeds are averaged within each dialogue.\nThe stable panel provides a same-time comparison; cumulative differences are not theoretical regret or causal switch effects.')
        figures["E3_temporal"] = fig

        fig = _canvas("E3  Phase and question-type comparisons", cfg, figsize=(13.33,9))
        axs = fig.subplots(2, 2, sharex="col")
        fig.subplots_adjust(left=.135, right=.97, top=.79, bottom=.21, hspace=.62, wspace=.38)
        for i, scenario in enumerate(SCENARIOS):
            for j, (dimension, levels, names) in enumerate([("phase", ["pre","post"], [f'Q1-{cfg["T"]//2}',f'Q{cfg["T"]//2+1}-{cfg["T"]}']),
                                                           ("qtype", ["recent","historical"], ["Recent","Historical"])]):
                ax = axs[i,j]
                subset = results["groups"].query("scenario == @scenario and dimension == @dimension")
                counts=[]
                for group, name, offset, color, marker in zip(levels, names, [.14,-.14], ["#2166AC","#C66B20"], ["o","s"]):
                    selected = subset.loc[subset.group.eq(group)].set_index("comparison")
                    counts.append(int(selected.iloc[0].n_questions))
                    for k, comparison in enumerate(COMPARISONS):
                        r = selected.loc[comparison]
                        ax.errorbar(r.effect, 2-k+offset, xerr=[[r.effect-r.low],[r.high-r.effect]], fmt=marker,
                                    ms=5, capsize=3, color=color, label=name if k==0 else None)
                ax.set_title(f'{scenario}: {"phase" if dimension=="phase" else "question type"}', loc="left", fontsize=12, weight="bold", pad=26)
                ax.text(0,1.035, f'{names[0]} / {names[1]}: {counts[0]} / {counts[1]} questions; n={cfg["n_dev_per_scenario"]} each',
                        transform=ax.transAxes, fontsize=8.5, color="#64748B")
                ax.set_yticks([2,1,0], ["Fixed reference", "TS", "RuleRouter"])
                ax.set_ylim(-.5,2.5); ax.axvline(0, color="#7A8797", ls="--", lw=1)
                ax.set_xlabel("Mean utility difference (CTS - reference)", fontsize=9.5)
                ax.legend(frameon=False, fontsize=8.5, loc="lower right", ncol=2)
                _axes(ax)
        _footer(fig, 'Intervals: exploratory 95% paired dialogue intervals within each group; no subgroup multiplicity correction.\nFixed reference: recent_short in stable, resolved_tfidf in abrupt. Question counts describe composition, not independent sample size.\nSubgroup means weight dialogues equally. Aggregate question proportions cannot be used to reconstruct the overall effect exactly.')
        figures["E3_groups"] = fig
        figures.update(sensitivity.build_figures(results, cfg, tables, _canvas, _footer, _axes))
    return figures, tables


def _interpretations(results):
    effects = results["effects"].set_index(["scenario","comparison"])
    groups = results["groups"].set_index(["scenario","dimension","group","comparison"])
    pp = results["post_pre"].query("metric == 'utility'").set_index(["scenario","comparison"])
    def effect(s,c):
        r=effects.loc[(s,c)]
        return f'{r.effect:+.6f}（95% 区间 [{r.low:+.6f}, {r.high:+.6f}]）'
    lines = ["# M5：E1 / E3 开发结果图表说明", "", "本报告基于开发结果，待用户与组员复核。正式实验尚未运行。", "",
             "## 数据来源与核验范围", "", f'数据来自 `{Path(results["source_dir"]).name}`，对应的实验执行代码版本为 `{results["execution_commit"]}`。',
             f'本次独立核验了发布清单中 {results["verified_files"]} 个文件的 SHA-256，并检查了方法组合、样本数、配置和效用公式。核对还覆盖配对均值、累计曲线终点及前后阶段结果的一致性。', "",
             '每场景包含 3 条独立开发对话，每条对话有 300 题。两个算法种子的结果先在同一对话内平均，再进行对话间比较。区间沿用 M4 已发布的结果，未重新选择统计方法或重采样。', "",
             '完整原始轨迹尚未交接，本次未独立重算逐题选择或 bootstrap 区间，也未验证全部原始对话。哈希一致仅说明文件与发布清单相符。', "",
             "## 图 1：E1 总体指标表", "", '总体指标表比较七种方法在准确率、输入长度和效用上的取舍。',
             '两个场景分栏展示，均保留七种方法和五项指标。百分比、代理长度与效用按各自单位列出，以免混用不同量纲。', "",
             '在两个开发场景中，RuleRouter 的平均效用均高于 CTS；CTS 则高于预选固定参照和 TS。',
             '相对固定参照，stable 中 CTS 的准确率增益抵消了额外输入成本。abrupt 中 CTS 的准确率略低，但输入成本下降，使其平均效用仍高于固定参照。具体数值见[总体指标表](../tables/figure_E1_overview.csv)。', "",
             '完整输入长度采用代理计数，无法直接换算为真实 API 费用或推理时延。证据覆盖率衡量最新证据是否入选，也应与回答准确率分别解释。', "",
             "## 图 2：E1 配对效应", "", '配对效应图展示 CTS 相对各参照的效应方向和不确定性。',
             '点表示对话配对效用差的均值，粗横线表示 95% 区间。固定参照比较同时保留 97.5% 区间；在本次小样本中，这两个区间的端点重合。', ""]
    for s in SCENARIOS:
        lines.append(f'- {s}：CTS−固定参照为 {effect(s,"cts_vs_fixed")}。CTS−TS 为 {effect(s,"cts_vs_ts")}。CTS−RuleRouter 为 {effect(s,"cts_vs_router")}。')
    lines += ['', '上述数值见[配对效应表](../tables/figure_E1_effects.csv)。这些比较使用已经查看过的开发数据，属于探索性分析。区间不跨零不足以构成正式确认，也不支持 CTS 全面优于所有方法的结论。', '',
              '## 图 3：E3 累计过程', '', '累计曲线展示 CTS 相对不同参照的效用差如何随对话推进而变化。',
              '各场景分别绘制固定参照、TS 和 RuleRouter 三条对照曲线。阴影表示逐点 95% 区间，两个面板使用独立的纵轴刻度。', "",
              'abrupt 后半段，CTS 相对 TS 的累计优势增幅大于其相对固定参照的增幅；相对 RuleRouter 的累计差仍为负。不同参照下的变化见[累计效用差表](../tables/figure_E3_temporal.csv)，相对 TS 的改善不能推广到全部参照。',
              'stable 同期也呈现随时间改善的表现，与学习进展相符。这些变化可能同时反映学习状态、历史长度和题型构成的影响，现有结果无法单独识别切换的因果效应。', '',
              '## 图 4：E3 阶段与题型', '', '阶段与题型分析用于检查总体平均是否掩盖了组间差异。',
              '分析分别按前后阶段、近期与历史题分组，并在各组内使用相同参照计算配对效应。图中保留负值和跨零区间；题数描述样本构成，独立样本数仍按对话计算。', ""]
    for c in ['cts_vs_fixed','cts_vs_ts']:
        r=pp.loc[('abrupt',c)]
        reference = '固定参照' if c == 'cts_vs_fixed' else ' TS '
        lines.append(f'- abrupt 中，相对{reference}的“后半段减前半段”效应变化为 {r.effect:+.6f}，95% 区间为 [{r.low:+.6f}, {r.high:+.6f}]。')
    lines += [f'- stable 相对固定短窗：历史题效用差 {groups.loc[("stable","qtype","historical","cts_vs_fixed"),"effect"]:+.6f}，近期题 {groups.loc[("stable","qtype","recent","cts_vs_fixed"),"effect"]:+.6f}。',
              f'- abrupt 相对固定消解检索：历史题效用差 {groups.loc[("abrupt","qtype","historical","cts_vs_fixed"),"effect"]:+.6f}，近期题 {groups.loc[("abrupt","qtype","recent","cts_vs_fixed"),"effect"]:+.6f}。',
              '', '对应结果见[阶段与题型效应表](../tables/figure_E3_groups.csv)及[前后阶段变化表](../tables/E3_post_pre_support.csv)。各子组先按对话汇总，因而不能直接按总体题数比例加权子组均值来重建总体效应。子组区间未作统一的多重比较校正。', '',
              '## 交付与后续', '', '每张图均提供 PNG、SVG 及保留原始精度的 CSV。CSV 中记录源清单哈希与实验执行代码版本，figure_manifest.json 记录来源、制图代码和全部输出文件的哈希。', "",
              '当前实现支持已发布的 development 汇总包。取得完整 demo/formal 原始归档后，还需接入相应读取流程，完成逐题重算并生成正式版图表。', "",
              '研究判断和汇报措辞仍需用户及相关组员复核。代码和报告初稿由 Codex 协助生成；姓名、验收和批准均未代填。', '']
    return '\n'.join(lines)


def export_visual_evidence(figures, figure_tables, source_run, render_id):
    """Recheck source, forbid overwrites, export exact tables/figures and hashes."""
    _require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", render_id)), "Invalid render_id")
    results = load_verified_run(source_run)
    _require(set(figures) == set(figure_tables) == set(FIGURE_IDS), "Expected eight matching figures/tables")
    expected = _figure_tables(results)
    for key in FIGURE_IDS:
        pd.testing.assert_frame_equal(figure_tables[key], expected[key], check_exact=True)
    target = ROOT / "outputs/development" / render_id
    _require(not target.resolve().is_relative_to(Path(source_run).resolve()), "Output must not be inside source")
    target.mkdir(parents=True, exist_ok=False)
    for sub in ["figures", "tables", "reports", "config/code"]:
        (target/sub).mkdir(parents=True)
    for key in FIGURE_IDS:
        for ext in ["png", "svg"]:
            figures[key].savefig(target/f"figures/{key}.{ext}", dpi=180, facecolor="white")
        figure_tables[key].to_csv(target/f"tables/figure_{key}.csv", index=False, encoding="utf-8", lineterminator="\n")
    results["post_pre"].to_csv(target/"tables/E3_post_pre_support.csv", index=False, encoding="utf-8", lineterminator="\n")
    (target/"reports/figure_interpretations.md").write_text(_interpretations(results), encoding="utf-8", newline="\n")
    sensitivity.export_support(results, target)
    (target/"config/code/m5_visuals.py").write_bytes(Path(__file__).read_bytes())
    (target/"config/source_manifest.json").write_bytes((Path(source_run)/"artifact_manifest.json").read_bytes())
    (target/"config/plot_config.json").write_text(json.dumps(results["config"], indent=2), encoding="utf-8")
    captions = {
        "E1_overview": "总体指标：保留七种方法，分别查看准确率、完整输入长度和效用。",
        "E1_effects": "CTS 的效用高于预选固定参照和 TS，低于 RuleRouter。误差线为开发数据上的探索性区间。",
        "E2_effects": "完整特征减常量特征：准确率和效用提高，同时输入长度和旧值回答率也增加。五项指标分别使用各自单位。",
        "E2_selection": "CTS 的总体选臂比例。合并所有题型；按近期题、历史题拆分的分析仍需完整原始轨迹。",
        "E3_temporal": "三种参照下的累计效用差。abrupt 后半段相对 TS 的优势增幅大于相对固定参照的增幅，相对 RuleRouter 的累计差仍为负。",
        "E3_groups": "分别查看前后阶段、近期与历史题。图中的题数用于说明构成，独立样本仍是对话。",
        "E4_tradeoff": "三个成本权重下准确率与输入长度的取舍。展示四种重点方法，完整七方法数据另有支持表。",
        "E4_effects": "同一 λ 下的配对效用比较。改变 λ 会改变效用定义，不能用跨 λ 的绝对效用直接选出最优权重。",
    }
    cards = ''.join(f'<section><h2>{key}</h2><p>{captions[key]}</p><img src="figures/{key}.png" alt="{key}"><p><a href="figures/{key}.svg">SVG 矢量图</a> · <a href="tables/figure_{key}.csv">对应数据表</a></p></section>' for key in FIGURE_IDS)
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 E1/E3 开发图表</title><style>body{font:16px/1.65 system-ui;margin:40px auto;max-width:1100px;padding:0 24px;color:#20344a;background:#f4f7fb}section{background:white;padding:24px;margin:24px 0;border-radius:8px}img{width:100%;height:auto}a{color:#2166ac}h1,h2{line-height:1.3}</style><h1>M5：E1 / E3 开发图表</h1><p>每场景 3 条开发对话；正式实验未运行。已核验发布汇总文件，尚未独立复算原始轨迹。</p><p><a href="reports/figure_interpretations.md">逐图解释与局限</a> · <a href="reports/figure_manifest.json">来源和文件清单</a></p>'+cards+'</html>'
    html = html.replace("E1/E3", "E1–E4").replace("E1 / E3", "E1–E4").replace("逐图解释与局限</a>", 'E1/E3 解释</a> · <a href="reports/E2_E4_interpretations.md">E2/E4 解释</a>')
    (target/"index.html").write_text(html, encoding="utf-8")
    files = {p.relative_to(target).as_posix(): _hash(p) for p in sorted(target.rglob("*")) if p.is_file()}
    manifest = dict(schema_version="m5-development-figures-v1", status="development_figures_pending_review",
                    created_utc=datetime.now(timezone.utc).isoformat(), render_id=render_id,
                    source_mode="development", source_kind="published_summary", source_directory=str(Path(source_run).resolve()),
                    source_manifest_sha256=results["manifest_sha256"], source_execution_commit=results["execution_commit"],
                    source_file_count_verified=results["verified_files"], raw_trajectories_verified=False,
                    stages=["E1", "E2", "E3", "E4"], figure_ids=list(FIGURE_IDS),
                    code_files={name: _hash(target/"config/code"/name) for name in ("m5_visuals.py", "m5_sensitivity.py")},
                    config=results["config"], code_sha256=_hash(__file__),
                    environment=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, matplotlib=matplotlib.__version__),
                    files=files)
    (target/"reports/figure_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--render-id", required=True)
    args = parser.parse_args()
    results = load_verified_run(args.source_run)
    figures, tables = build_figures(results, results["config"])
    try:
        output = export_visual_evidence(figures, tables, args.source_run, args.render_id)
    finally:
        for fig in figures.values(): plt.close(fig)
    print(json.dumps(dict(output=str(output), figures=len(figures), verified_source_files=results["verified_files"],
                          mode="development", raw_trajectories_verified=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
