# M5：E1–E4 开发图表

当前交付是已发布开发汇总表的可复现图表。来源为 `deliverables/M4_full_development_20261126`，每场景 3 条已见开发对话。正式实验未运行，完整原始轨迹尚未交接。

## 运行

使用项目 Python 环境和 `requirements.txt` 中的依赖，在仓库根目录执行：

```powershell
python scripts/m5_visuals.py --source-run deliverables/M4_full_development_20261126 --render-id m5_e1_e4_20261128_v3
```

`--source-run` 必须明确指定。输出在 `outputs/development/<render-id>/`；已存在的目录会拒绝覆盖，重绘使用新的 ID。打开 `index.html` 可浏览八张图和对应 CSV。E1/E3 中文解释在 `reports/figure_interpretations.md`，E2/E4 解释在 `reports/E2_E4_interpretations.md`。

当前统一交付为 `m5_e1_e4_20261128_v3`。E2/E4 四图及六份支持表在 v2 接入；v3 按用户要求再次使用 academic-humanizer 润色 E2/E4 报告，数值、公式、引用、全部图像与 CSV 保持不变。原 E1/E3 报告保留。E2/E4 润色记录见生成目录的 `reports/report_edit_notes.md`；重新运行时请使用未占用的 ID。

| 文件 ID | 研究问题 | 表行数 |
|---|---|---|
| E1_overview | 七方法的准确率、完整输入长度、效用、最新证据覆盖率、旧值率 | 14 |
| E1_effects | CTS 相对固定策略、TS、RuleRouter 的配对效用差 | 6 |
| E2_effects | 完整特征减常量特征的五指标配对变化；独立单位仍是对话 | 10 |
| E2_selection | CTS 两种特征设置下的总体四臂比例；未按题型拆分 | 16 |
| E3_temporal | 上述三种差异怎样随对话进展累积 | 1,800 |
| E3_groups | 前后阶段及近期/历史题的差异 | 24 |
| E4_tradeoff | 三个 λ 下 CTS、TS、RuleRouter、固定参照的准确率和输入成本 | 24 |
| E4_effects | 同一 λ 下 CTS 对三种参照的效用差 | 18 |

每图导出 PNG、SVG、原精度 CSV。图表使用英文标签以方便课程展示，解释和交接说明使用中文。CSV 保留原始 0–1 数值；E2/E4 的百分比和百分点显示值在单独列中明确命名，未覆盖原值。完整输入长度仍是代理单位。

E4 取舍图聚焦四种方法，支持表 `E4_method_metrics_support.csv` 保留全部七方法和三个 λ。固定参照与 RuleRouter 的准确率、成本在三个 λ 下相同，图中重合为一点。E4 的跨设置配对支持表方向为“变体减默认”，只比较准确率、成本、覆盖率、旧值率，排除跨 λ 的效用差。

## 三个接口

```python
from scripts.m5_visuals import load_verified_run, build_figures, export_visual_evidence

source = "deliverables/M4_full_development_20261126"
results = load_verified_run(source)
figures, figure_tables = build_figures(results, results["config"])
output = export_visual_evidence(figures, figure_tables, source, "m5_review_new_id")
```

三个接口在 `scripts/m5_visuals.py` 中，E2/E4 的读取、绘图和报告实现于 `scripts/m5_sensitivity.py`。当前 release 工作本已绑定到 M4 的正式准备包，本次没有修改该工作本；其中的三个占位函数仍保留。后续统一接入工作本时，需要由 M4 按原流程刷新相关版本绑定，不能把旧准备包当作修改后代码的批准材料。

## 已执行的核验

- 读取发布清单并核对全部 46 个文件的 SHA-256；拒绝缺失文件、越界路径和未被清单绑定的必需文件。
- 明确识别开发汇总包，核对 E1–E4 的配置、对话 seed、来源 manifest 和执行版本。拒绝混入 demo/formal/fixture。
- 核对 E1 默认设置下两场景 × 七方法，不把其他阶段重复的默认行重复汇总。
- 核对对话数、算法种子数、五项指标和效用公式。独立样本是对话，不是题数、算法种子或重采样次数。
- 从方法汇总表核对配对效应均值；从阶段/题型汇总核对分组效应；核对累计终点除以 300 等于 E1 平均效应，以及前后段与总体相符。
- E2/E4 默认行与 E1 对齐。从算法种子汇总表独立汇总对话均值，核对全部 546 条跨变体对话配对差及 182 个效应均值，区分 E2/E4 相反的差值方向。
- 核对两阶段共 1,680 行选臂诊断的完整网格，每个对话和算法种子有四臂、计数和为 300、比例与计数一致。E2 图只展示 CTS 总体比例。
- 直接绘制 M4 已发布的区间，不重新选择检验或重算 bootstrap。读取不完整子组时明确报错，不填零。
- 导出前重新验证来源，并检查导出数据与核验后的数据完全一致。生成的清单包含制图代码、环境版本、配置、来源哈希和所有图表文件哈希。

测试入口：

```powershell
python scripts/test_m5_visuals.py
python scripts/validate_release.py
```

29 项测试涵盖变更、缺失、模式混用、配置混用、来源混用、重复键、错误样本数、错误效用、累计终点、差值方向、配对缺失、错误特征模式、算法种子缺失、比例分母、λ 标签，以及图中点/线/柱形与 CSV 一致性和拒绝覆盖。

## 解释边界和剩余交付

当前读取器只支持 `m4-development-evidence-manifest-v1` 发布汇总包。清单匹配不代表已独立复核原始实验；完整 demo/formal 归档需要另行接入其 schema 并校验逐题网格。尚未重算原始轨迹、bootstrap 区间或新增独立样本。

E1 的 RuleRouter 负向比较完整保留。E3 的逐点区间不是同时置信带；固定策略累计差不是理论 regret；前后变化不能单独解释为环境切换的因果效应。子组平均先按对话汇总，不能用总体题数比例直接重建总体平均。

E2 的完整特征提高准确率、效用和覆盖率，同时提高成本和旧值率；不能将其描述为所有指标都改善。E4 的比较应在同一 λ 内解读，跨 λ 的绝对效用不能直接用于选择最优权重。E2 按题型的选臂分析仍缺原始轨迹，未生成此项结果。

下一步由用户复核逐图解释，和 M4/M3 核对统计口径；拿到完整原始归档后补充验收，再更新正式图表和 slides。最终展示、视频、姓名与人工签收仍待完成。

`outputs/` 被 Git 忽略。提交脚本与说明不会同时上传图表，应另行共享生成目录或 ZIP；不要修改 M4 的原始目录。
