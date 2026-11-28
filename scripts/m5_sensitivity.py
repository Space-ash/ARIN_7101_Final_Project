"""E2/E4 adapters for the published M4 development summary schema.

No raw-trajectory or bootstrap verification is claimed by this module.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

SCENARIOS = ("stable", "abrupt")
METHODS = ("recent_short", "recent_long", "tfidf", "resolved_tfidf", "TS", "LaplaceCTS", "RuleRouter")
METRICS = ("y", "cost", "utility", "coverage", "outdated")
ARMS = METHODS[:4]
VARIANTS = {"E2": ("default", "constant_features"), "E4": ("default", "lambda_025", "lambda_100")}
LAMBDAS = {"default": .5, "lambda_025": .25, "lambda_100": 1.}
FIGURE_IDS = ("E2_effects", "E2_selection", "E4_tradeoff", "E4_effects")
SOURCE_FILES = ("plans/E2.json", "plans/E4.json", "variant_effects.csv",
                "variant_dialogue_differences.csv", "selector_diagnostics.csv", "algorithm_seed_spread.csv")
METRIC_STYLE = {"utility": ("Utility", 1, "utility units"), "y": ("Accuracy", 100, "percentage points"),
                "cost": ("Complete input length", 1, "proxy input units"),
                "coverage": ("Latest-evidence coverage", 100, "percentage points"),
                "outdated": ("Outdated-answer rate", 100, "percentage points")}
SCENE_COLORS = {"stable": "#2166AC", "abrupt": "#C66B20"}
ARM_COLORS = ("#2166AC", "#7AA8CC", "#C66B20", "#6D8374")
COMPARISONS = ("cts_vs_fixed", "cts_vs_ts", "cts_vs_router")
REF_COLORS = ("#2166AC", "#C66B20", "#64748B")


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _close(actual, expected, message):
    _require(np.allclose(actual, expected, atol=1e-9, rtol=0), message)


def _grid(f, keys, expected, name):
    _require(set(keys).issubset(f) and not f[keys].isna().any().any(), name+": missing key")
    _require(not f.duplicated(keys).any(), name+": duplicate key")
    _require(set(f[keys].itertuples(index=False, name=None)) == set(expected), name+": incomplete/unexpected grid")


def _finite(f, cols, name):
    _require(set(cols).issubset(f) and np.isfinite(f[list(cols)].to_numpy(dtype=float)).all(), name+": nonfinite/missing value")


def _intervals(f, n, name):
    _finite(f, ["effect", "low", "high", "n"], name)
    _require(f.n.eq(n).all(), name+": dialogue count mismatch")
    _require((f.low <= f.effect+1e-12).all() and (f.high >= f.effect-1e-12).all(), name+": invalid interval")


def load(tables, plans, verification, cfg, seeds, overview, baselines):
    """Check designs, paired effects, dialogue means and complete selection counts."""
    n, T, alg = cfg["n_dev_per_scenario"], cfg["T"], cfg["algorithm_seeds"]
    e1_run = next(r for r in verification["runs"] if r["stage"] == "E1")
    output = {}
    for stage, variants in VARIANTS.items():
        plan = plans[stage]
        _require(plan.get("stage") == stage and plan.get("profile") == "development"
                 and plan.get("formal") is False and plan.get("fixture") is False, stage+": mixed mode")
        _require(plan.get("config") == cfg and plan.get("dialogue_seeds") == seeds, stage+": mixed configuration/seeds")
        expected = [{"id": "default", "config": {}, "adapter": {}, "rebuild": "none"}]
        if stage == "E2":
            expected.append({"id": "constant_features", "config": {}, "adapter": {"feature_mode": "constant"}, "rebuild": "none"})
        else:
            expected += [{"id": v, "config": {"lambda": LAMBDAS[v]}, "adapter": {}, "rebuild": "none"} for v in variants[1:]]
        _require(plan.get("variants") == expected and plan.get("statistics", {}).get("confidence") == .95
                 and plan.get("baseline_rule") == "default_development_selected_fixed_arm_retained_for_all_variants", stage+": variant design mismatch")
        runs = [r for r in verification["runs"] if r.get("stage") == stage]
        _require(len(runs) == 1, stage+": ambiguous source")
        run = runs[0]
        _require(run.get("fixture") is False and run.get("formal_generated") is False
                 and run.get("source", {}).get("manifest_sha256") == e1_run["source"]["manifest_sha256"]
                 and run.get("source", {}).get("outcomes_sha256") == e1_run["source"]["outcomes_sha256"], stage+": source identity mismatch")
        rv = run.get("variants", [])
        _require(len(rv) == len(variants) and {v["variant"] for v in rv} == set(variants)
                 and all(v["dialogues"] == 2*n and v["algorithm_seeds"] == alg for v in rv), stage+": execution design mismatch")
        select = lambda name: tables[name].loc[tables[name].stage.eq(stage)].copy()
        mm = select("method_metrics.csv")
        _grid(mm, ["scenario", "variant", "method"], itertools.product(SCENARIOS, variants, METHODS), stage+" methods")
        _finite(mm, [*METRICS, "n", "algorithm_seed_count", "lambda"], stage)
        _require(mm.n.eq(n).all() and mm.algorithm_seed_count.eq(len(alg)).all(), stage+": sample count mismatch")
        _require(mm[["y", "coverage", "outdated"]].ge(0).all().all()
                 and mm[["y", "coverage", "outdated"]].le(1).all().all() and mm.cost.ge(0).all(), stage+": metric range")
        expected_lambda = mm.variant.map(LAMBDAS) if stage == "E4" else np.full(len(mm), cfg["lambda"])
        _close(mm["lambda"], expected_lambda, stage+": lambda mismatch")
        _close(mm.utility, mm.y-mm["lambda"]*mm.cost/cfg["cost_reference"], stage+": utility mismatch")
        means = mm.set_index(["scenario", "variant", "method"])
        defaults = mm.loc[mm.variant.eq("default")].set_index(["scenario", "method"])
        _close(defaults.loc[overview.set_index(["scenario", "method"]).index, list(METRICS)], overview[list(METRICS)], stage+": default/E1 mismatch")

        spread = select("algorithm_seed_spread.csv")
        expected_grid = ((s,v,d,m,k) for s in SCENARIOS for v in variants for d in seeds[s] for m in METHODS for k in METRICS)
        _grid(spread, ["scenario", "variant", "seed", "method", "metric"], expected_grid, stage+" dialogue means")
        _finite(spread, ["mean", "std", "minimum", "maximum", "algorithm_seed_count"], stage+" dialogue means")
        _require(spread.algorithm_seed_count.eq(len(alg)).all() and spread["std"].ge(0).all()
                 and (spread.minimum <= spread["mean"]+1e-12).all()
                 and (spread.maximum >= spread["mean"]-1e-12).all(), stage+": algorithm seed summary mismatch")
        for (s,v,m,k), group in spread.groupby(["scenario", "variant", "method", "metric"]):
            _close(group["mean"].mean(), means.loc[(s,v,m),k], stage+": dialogue/method mean mismatch")
        dm = spread.set_index(["scenario", "variant", "seed", "method", "metric"])["mean"]
        metrics = METRICS if stage == "E2" else tuple(k for k in METRICS if k != "utility")
        direction = "default_minus_variant" if stage == "E2" else "variant_minus_default"
        sign = 1 if stage == "E2" else -1
        effects, pairs = select("variant_effects.csv"), select("variant_dialogue_differences.csv")
        keys = ["scenario", "variant", "method", "metric"]
        _grid(effects, keys, itertools.product(SCENARIOS, variants[1:], METHODS, metrics), stage+" variant effects")
        _grid(pairs, [*keys, "seed"], ((s,v,m,k,d) for s in SCENARIOS for v in variants[1:] for m in METHODS for k in metrics for d in seeds[s]), stage+" paired dialogues")
        _intervals(effects, n, stage+" variant effects")
        _finite(pairs, ["difference"], stage+" paired dialogues")
        _require(effects.direction.eq(direction).all() and pairs.direction.eq(direction).all(), stage+": effect direction mismatch")
        _require(effects.n_total.eq(n).all() and effects.status.eq("ok").all()
                 and effects.pairing.eq("same_dialogue").all() and pairs.observed.eq(True).all(), stage+": missing paired observations")
        for r in pairs.itertuples():
            expected_difference = sign*(dm.loc[(r.scenario,"default",r.seed,r.method,r.metric)]-dm.loc[(r.scenario,r.variant,r.seed,r.method,r.metric)])
            _close(r.difference, expected_difference, stage+": paired dialogue difference mismatch")
        paired_means = pairs.groupby(keys).difference.mean()
        for r in effects.itertuples():
            _close(r.effect, paired_means.loc[(r.scenario,r.variant,r.method,r.metric)], stage+": paired mean mismatch")
        if stage == "E2":
            _close(pairs.loc[~pairs.method.eq("LaplaceCTS"), "difference"], 0, "E2: non-CTS changed")
        else:
            _close(pairs.loc[pairs.method.isin([*ARMS,"RuleRouter"]), "difference"], 0, "E4: fixed-policy accuracy/cost changed")

        diag = select("selector_diagnostics.csv")
        dk = ["scenario", "variant", "seed", "method", "alg_seed", "arm"]
        _grid(diag, dk, ((s,v,d,m,a,arm) for s in SCENARIOS for v in variants for d in seeds[s] for m in METHODS for a in alg for arm in ARMS), stage+" arm selections")
        _finite(diag, ["selected_count", "selected_share"], stage+" arm selections")
        _require(diag.selected_count.between(0,T).all() and (diag.selected_count % 1).eq(0).all(), stage+": invalid selection count")
        _close(diag.selected_share, diag.selected_count/T, stage+": selection share/count mismatch")
        _close(diag.groupby(dk[:-1]).selected_count.sum(), T, stage+": incomplete trajectory selections")
        expected_mode = diag.variant.map(lambda v: "constant" if v == "constant_features" else "full")
        _require(diag.feature_mode.eq(expected_mode).all(), stage+": feature mode mismatch")
        output[stage] = dict(metrics=mm, effects=effects, pairs=pairs, diagnostics=diag, dialogue_means=spread)

    # E4 within-lambda comparisons are distinct from cross-lambda metric changes.
    primary = tables["primary_effects.csv"].query("stage == 'E4'").copy()
    direct = tables["direct_comparisons.csv"].query("stage == 'E4'").copy()
    _grid(primary, ["scenario", "variant", "method"], itertools.product(SCENARIOS, VARIANTS["E4"], ["LaplaceCTS"]), "E4 primary")
    _grid(direct, ["scenario", "variant", "comparison", "metric"], itertools.product(SCENARIOS, VARIANTS["E4"], COMPARISONS[1:], METRICS), "E4 direct")
    means = output["E4"]["metrics"].set_index(["scenario", "variant", "method"])
    for frame in [primary, direct]:
        _intervals(frame, n, "E4 within-lambda effects")
        for r in frame.itertuples():
            is_primary = hasattr(r, "baseline")
            ref = r.baseline if is_primary else r.reference
            expected_ref = baselines[r.scenario] if is_primary else ("TS" if r.comparison == "cts_vs_ts" else "RuleRouter")
            _require(ref == expected_ref, "E4: reference mismatch")
            metric = "utility" if is_primary else r.metric
            _close(r.effect, means.loc[(r.scenario,r.variant,"LaplaceCTS"),metric]-means.loc[(r.scenario,r.variant,ref),metric], "E4: within-lambda effect mismatch")
    within = pd.concat([primary.rename(columns={"baseline":"reference"}).assign(comparison="cts_vs_fixed",metric="utility"), direct.query("metric == 'utility'")], ignore_index=True).drop(columns="method")
    within["lambda"] = within.variant.map(LAMBDAS)
    output["E4"]["within_lambda"] = within
    return output


def figure_tables(results):
    data = results["sensitivity"]
    e2 = data["E2"]["effects"].query("method == 'LaplaceCTS'").copy()
    # Display scaling is explicit; raw effects and intervals stay in original units.
    e2["display_scale"] = e2.metric.map(lambda k: METRIC_STYLE[k][1])
    e2["display_unit"] = e2.metric.map(lambda k: METRIC_STYLE[k][2])
    for col in ("effect", "low", "high"):
        e2["display_"+col] = e2[col]*e2.display_scale
    diag = data["E2"]["diagnostics"].query("method == 'LaplaceCTS'")
    dialogue_shares = diag.groupby(["scenario","variant","seed","arm"], as_index=False).selected_share.mean()
    selection = dialogue_shares.groupby(["scenario","variant","arm"], as_index=False).selected_share.mean()
    selection["n"] = results["config"]["n_dev_per_scenario"]
    selection["algorithm_seed_count"] = len(results["config"]["algorithm_seeds"])
    selection["scope"] = "all_question_types_combined"
    selection["selected_percent"] = 100*selection.selected_share
    trade = data["E4"]["metrics"].copy()
    trade = trade.loc[trade.method.isin(["LaplaceCTS","TS","RuleRouter"]) | trade.apply(lambda r:r.method==results["baselines"][r.scenario],axis=1)].copy()
    trade["accuracy_percent"] = 100*trade.y
    return {"E2_effects":e2, "E2_selection":selection, "E4_tradeoff":trade, "E4_effects":data["E4"]["within_lambda"].copy()}


def build_figures(results, cfg, tables, canvas, footer, axes):
    figures = {}
    fig = canvas("E2  What changes with query features?", cfg, figsize=(13.33,8.5))
    axs = fig.subplots(2,3)
    fig.subplots_adjust(left=.09,right=.97,top=.77,bottom=.22,wspace=.46,hspace=.8)
    effect_data = tables["E2_effects"].set_index(["scenario","metric"])
    for ax, metric in zip(axs.flat, METRIC_STYLE):
        title, scale, unit = METRIC_STYLE[metric]
        for y,s in enumerate(SCENARIOS):
            r = effect_data.loc[(s,metric)]
            ax.errorbar(r.display_effect,1-y,xerr=[[r.display_effect-r.display_low],[r.display_high-r.display_effect]],fmt="o",capsize=4,color=SCENE_COLORS[s],ms=7,lw=2)
            ax.text(r.display_effect,1-y+.20,f"{r.display_effect:+.3f}",ha="center",fontsize=9,color=SCENE_COLORS[s])
        ax.axvline(0,color="#8793A1",ls="--",lw=1)
        ax.set_yticks([1,0],SCENARIOS); ax.set_ylim(-.5,1.65)
        ax.set_title(title,loc="left",fontsize=12,weight="bold",pad=10)
        ax.set_xlabel(unit,fontsize=10); axes(ax)
    axs[1,2].axis("off")
    axs[1,2].text(0,.9,"Full features − constant features\n\nSame CTS model dimension\nSame dialogues and algorithm seeds\n\nHigher input cost and outdated-answer\nrate are trade-offs, not improvements.",va="top",fontsize=11,linespacing=1.65,color="#334155")
    footer(fig,"Points: paired dialogue means; bars: published exploratory 95% intervals. Each metric has its own horizontal scale.\nAccuracy, coverage and outdated-answer differences use percentage points. Utility and input length retain their own units.\nOnly CTS changes in this ablation; all six other methods have zero paired changes in the published tables.")
    figures["E2_effects"] = fig

    fig = canvas("E2  Overall CTS arm selection",cfg)
    axs = fig.subplots(1,2)
    fig.subplots_adjust(left=.11,right=.97,top=.75,bottom=.28,wspace=.35)
    for ax,s in zip(axs,SCENARIOS):
        f=tables["E2_selection"].query("scenario == @s").set_index(["variant","arm"])
        left=np.zeros(2)
        for arm,color in zip(ARMS,ARM_COLORS):
            vals=np.array([f.loc[(v,arm),"selected_percent"] for v in VARIANTS["E2"]])
            ax.barh([1,0],vals,left=left,height=.46,color=color,label=arm,edgecolor="white")
            for y,l,w in zip([1,0],left,vals):
                if w >= 8: ax.text(l+w/2,y,f"{w:.1f}%",ha="center",va="center",fontsize=10,color="white")
            left+=vals
        ax.set_yticks([1,0],["Full","Constant"]); ax.set_ylim(-.6,1.6); ax.set_xlim(0,100)
        ax.set_xlabel("Share of all decisions (%)"); ax.set_title(s,loc="left",weight="bold",pad=18); axes(ax)
    fig.legend(*axs[0].get_legend_handles_labels(),loc="upper center",bbox_to_anchor=(.52,.85),ncol=4,frameon=False,fontsize=10)
    footer(fig,"Shares first average algorithm seeds within dialogue, then weight the three dialogues equally. All questions are pooled.\nSmall segments remain in the chart; exact values for every arm are in the companion CSV. No uncertainty intervals are shown.\nThese overall shares cannot establish how arm choices differ between recent and historical questions; that requires raw trajectories.")
    figures["E2_selection"] = fig

    fig=canvas("E4  Accuracy and input cost across reward weights",cfg)
    axs=fig.subplots(1,2)
    fig.subplots_adjust(left=.08,right=.97,top=.76,bottom=.27,wspace=.30)
    styles=[("LaplaceCTS","#2166AC","o"),("TS","#C66B20","s"),("RuleRouter","#64748B","D")]
    for ax,s in zip(axs,SCENARIOS):
        f=tables["E4_tradeoff"].query("scenario == @s")
        for method,color,marker in styles+[(results["baselines"][s],"#6D8374","^")]:
            d=f.loc[f.method.eq(method)].sort_values("lambda")
            if method in ["LaplaceCTS","TS"]:
                ax.plot(d.cost,d.accuracy_percent,color=color,marker=marker,lw=1.5,ms=7,label=method)
                for _,r in d.iterrows():
                    # Label crowded CTS points above/below the line in lambda order.
                    offset={.25:(8,10),.5:(6,-18),1.:(-27,10)}[r["lambda"]]
                    ax.annotate(f'λ={r["lambda"]:g}',(r.cost,r.accuracy_percent),xytext=offset,textcoords="offset points",fontsize=8.5,color=color)
            else:
                r=d.iloc[0]
                ax.plot([r.cost],[r.accuracy_percent],color=color,marker=marker,ms=8,linestyle="none",label="Fixed reference" if method==results["baselines"][s] else method)
        ax.set_title(s+"; fixed = "+results["baselines"][s],loc="left",fontsize=11.5,pad=18)
        ax.set_xlabel("Mean complete input length (proxy units)"); ax.set_ylabel("Accuracy (%)")
        ax.margins(x=.25,y=.25); axes(ax)
    fig.legend(*axs[0].get_legend_handles_labels(),loc="upper center",bbox_to_anchor=(.52,.85),ncol=4,frameon=False,fontsize=10)
    footer(fig,"λ = 0.25, 0.5, 1.0; each point is a dialogue-weighted mean. Lines connect tested settings, not a fitted Pareto frontier.\nFour focal methods are shown; all seven methods are retained in E4_method_metrics_support.csv. Panel axes use separate scales.\nFixed-reference and RuleRouter accuracy/cost coincide across λ. Cost is a prompt-length proxy, not money or runtime; no intervals are shown here.")
    figures["E4_tradeoff"]=fig

    fig=canvas("E4  Compare methods at the same reward weight",cfg)
    axs=fig.subplots(1,2,sharey=True)
    fig.subplots_adjust(left=.09,right=.97,top=.76,bottom=.26,wspace=.23)
    for ax,s in zip(axs,SCENARIOS):
        for c,color,label,offset in zip(COMPARISONS,REF_COLORS,["Fixed reference","TS","RuleRouter"],[-.08,0,.08]):
            d=tables["E4_effects"].query("scenario == @s and comparison == @c").sort_values("lambda")
            ax.errorbar(np.arange(3)+offset,d.effect,yerr=np.vstack([d.effect-d.low,d.high-d.effect]),color=color,marker="o",capsize=4,lw=1.5,label=label)
        ax.axhline(0,color="#8793A1",ls="--",lw=1)
        ax.set_xticks(range(3),["0.25","0.5","1.0"]); ax.set_xlim(-.4,2.4)
        ax.set_title(s,loc="left",weight="bold",pad=15); ax.set_xlabel("Reward cost weight λ")
        ax.set_ylabel("Mean utility difference (CTS − reference)"); axes(ax)
    fig.legend(*axs[0].get_legend_handles_labels(),loc="upper center",bbox_to_anchor=(.52,.85),ncol=3,frameon=False,fontsize=10)
    footer(fig,"Bars: published exploratory 95% paired dialogue intervals. Comparisons are within each λ; negative RuleRouter effects remain visible.\nChanging λ changes the utility definition. Cross-λ heights describe sensitivity of relative advantages, not a common objective for choosing λ.\nFixed references selected at the default setting are retained: recent_short in stable, resolved_tfidf in abrupt.")
    figures["E4_effects"]=fig
    return figures


def interpretations(results):
    """Evidence-first Chinese prose; numbers are drawn from verified tables."""
    data=results["sensitivity"]
    effects=data["E2"]["effects"].query("method == 'LaplaceCTS'").set_index(["scenario","metric"])
    e4=data["E4"]["metrics"].query("method == 'LaplaceCTS'").sort_values(["scenario","lambda"])
    lines=["# M5：E2 / E4 开发结果图表说明","","当前结果供用户与组员复核；正式实验尚未运行。","",
           "## 数据与分析范围","",f'来源为 `{Path(results["source_dir"]).name}`，实验执行版本为 `{results["execution_commit"]}`。每场景有 3 条独立开发对话，每条 300 题。两个算法种子先在对话内平均，变体沿用相同的对话种子。重复使用默认配置不增加独立样本数。',"",
           f'本次核对了全部 {results["verified_files"]} 个发布文件的哈希，并用已发布的对话均值表核对总体均值和配对差值。选臂比例依据诊断表中的计数检查。区间沿用 M4 发布的探索性 95% 区间，未重新计算 bootstrap。完整原始归档尚未交接，本次也未独立复算逐题轨迹。',"",
           "## E2：完整特征与常量特征的比较","",
           '消融将 CTS 的查询特征替换为常量，模型维度、对话和算法种子保持不变。差值统一按“完整特征减常量特征”计算，其余六种方法的配对变化均为零。五项指标分别使用独立横轴，其中准确率、覆盖率和旧值率的差值以百分点表示。',"",
           "| 场景 | 指标 | 配对均值差 | 95% 区间 | 单位 |","|---|---|---:|---|---|"]
    names={"utility":"效用","y":"准确率","cost":"完整输入长度","coverage":"最新证据覆盖率","outdated":"旧值回答率"}
    for s in SCENARIOS:
        for metric,(_,scale,unit) in METRIC_STYLE.items():
            r=effects.loc[(s,metric)]
            lines.append(f'| {s} | {names[metric]} | {scale*r.effect:+.6f} | [{scale*r.low:+.6f}, {scale*r.high:+.6f}] | {"百分点" if scale==100 else ("代理单位" if metric=="cost" else "效用")} |')
    lines += ["",'数据见[特征消融效应表](../tables/figure_E2_effects.csv)，[对话配对差值](../tables/E2_dialogue_differences_support.csv)保留三个独立对话各自的结果。在两个场景中，完整特征均对应更高的效用、准确率和最新证据覆盖率，也带来更长的输入和更高的旧值回答率。按当前 λ=0.5 的效用定义，准确率增益超过了额外的成本惩罚。',"",
              '总体选臂图比较两种特征设置下的策略选择比例。计算时先对同一对话内的算法种子取平均，再对三条对话等权平均。[选臂比例表](../tables/figure_E2_selection.csv)列出全部四个策略，[计数明细](../tables/E2_selection_counts_support.csv)保留逐对话、逐算法种子的选臂次数。这些比例合并了所有题型，未区分近期题与历史题各自的条件选臂比例；该分层分析仍需完整原始轨迹。',"",
              '在当前合成环境和开发样本中，完整查询特征对应较高的准确率和效用。这些特征来自结构化查询模板，现有结果尚不能说明其在真实自由文本中的识别能力，也不能推广为 CTS 在所有环境下都优于非上下文方法。',"",
              "## E4：成本权重与准确率、输入长度的取舍","",
              'E4 使用 λ=0.25、0.5、1.0 三个设置，效用定义为 accuracy−λ×cost/512。准确率与成本图展示 CTS、TS、RuleRouter 和预选固定参照；全部四条固定策略的结果均保留在[七方法指标表](../tables/E4_method_metrics_support.csv)中。图中的连线连接已测试的设置，未拟合最优前沿。',"",
              "| 场景 | λ | CTS 准确率（%） | 完整输入长度 | 效用 |","|---|---:|---:|---:|---:|"]
    for _,r in e4.iterrows():
        lines.append(f'| {r.scenario} | {r["lambda"]:g} | {100*r.y:.6f} | {r.cost:.6f} | {r.utility:.6f} |')
    for s in SCENARIOS:
        d=e4.query("scenario == @s").set_index("lambda")
        limitation = '这些结果反映了当前样本中准确率与输入长度的取舍，其在其他环境中的表现仍需验证。' if s == 'stable' else '本组开发数据中的输入长度和准确率对成本权重呈现不同响应。这种响应能否推广到其他环境，仍需更多样本验证。'
        lines += ["",f'{s} 中，λ 从 0.25 增至 1.0 时，CTS 的平均输入长度由 {d.loc[.25,"cost"]:.6f} 降至 {d.loc[1.,"cost"]:.6f}，准确率由 {100*d.loc[.25,"y"]:.6f}% 变为 {100*d.loc[1.,"y"]:.6f}%。{limitation}']
    lines += ["",'图中各点表示对话均值，未显示区间。[跨 λ 的配对指标变化表](../tables/E4_variant_effects_support.csv)列出相对默认 λ=0.5 的准确率、输入长度、覆盖率和旧值率差异，并提供对应区间。该表按“变体减默认”计算，与 E2 的差值方向不同。输入长度采用完整提示的代理计数，不能直接换算为实际 API 费用或运行时间。',"",
              "## E4：同一 λ 下的方法比较","",
              '配对效用图在同一 λ 下比较 CTS 与固定参照、TS、RuleRouter。固定参照沿用默认开发设置选定的策略。在两个场景和三个 λ 设置下，CTS 相对 RuleRouter 的平均效用差均为负，相对固定参照和 TS 则均为正。具体数值和 95% 区间见[同 λ 配对效应表](../tables/figure_E4_effects.csv)。CTS 因而未在全部参照比较中取得更高效用。',"",
              'λ 改变时，效用的评价标准随之改变，不同 λ 的绝对效用不能直接用于确定最优权重。图中各设置的效应大小描述了方法间相对优势对成本权重的敏感性。实际应用中的权重选择还取决于对准确率与资源开销的偏好。',"",
              "## 解释边界与后续","",
              'E2 和 E4 均使用已查看过的开发数据，每场景只有三条独立对话，属于探索性分析。多个指标和 λ 设置的区间未作统一多重比较校正。即使某个区间不跨零，也不能替代独立正式实验。图中保留成本增加、旧值率上升和相对 RuleRouter 的负向结果。',"",
              '本报告可用于 M5 开发版图表说明、报告草稿和组内讨论。取得完整轨迹后，还需补充 E2 按题型的选臂分析，并依据团队实际批准的实验范围更新正式结果。代码和文字由 Codex 协助生成，报告按 academic-humanizer 的证据与措辞要求润色。用户及相关组员仍需理解、复核并确认最终汇报内容。',""]
    return "\n".join(lines)


def export_support(results, target):
    data=results["sensitivity"]
    frames={"E2_method_metrics_support":data["E2"]["metrics"],
            "E2_dialogue_differences_support":data["E2"]["pairs"],
            "E2_selection_counts_support":data["E2"]["diagnostics"].query("method == 'LaplaceCTS'"),
            "E4_method_metrics_support":data["E4"]["metrics"],
            "E4_variant_effects_support":data["E4"]["effects"],
            "E4_dialogue_differences_support":data["E4"]["pairs"]}
    for name,frame in frames.items():
        frame.to_csv(target/f"tables/{name}.csv",index=False,encoding="utf-8",lineterminator="\n")
    (target/"reports/E2_E4_interpretations.md").write_text(interpretations(results),encoding="utf-8",newline="\n")
    (target/"config/code/m5_sensitivity.py").write_bytes(Path(__file__).read_bytes())
    (target/"reports/report_edit_notes.md").write_bytes((Path(__file__).resolve().parents[1]/"docs/M5_E2_E4_REPORT_REVIEW.md").read_bytes())
    for stage in VARIANTS:
        (target/f"config/{stage}_plan.json").write_bytes((Path(results["source_dir"])/f"plans/{stage}.json").read_bytes())
