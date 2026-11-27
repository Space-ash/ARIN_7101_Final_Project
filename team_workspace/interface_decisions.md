# 接口与研究设计决策
影响下游的改动逐条追加并保留历史；正式结果后的改动说明修正/探索和已看情况。

| 日期 | 提出人 | 问题/候选方案 | 选择与理由 | 影响的接口/文件 | 接收人确认 | 阶段/数据是否已看 |
|---|---|---|---|---|---|---|
| 2026-11-23 | M2（用户确认） | 两检索臂共用前 8、9 或 12 个候选，正文预算各 256 | 保留 8。9 和 12 均修复 130100/99，但增加完整成本，原始检索平均效用下降，abrupt 最佳臂效用在 8 时最高。 | 主本 `f3e82d3` 的 `select_context`；沿用 `m2_development_20261119` 的全表、交接和已有回放。8/9/12 各复算 7,200 行，最佳固定臂映射一致。[对照与交付材料](../deliverables/M2_notes.md) | 待 M4 本人核对并填写姓名、日期和验收结果 | 已看六条开发对话；未运行正式实验 |

初始定位：release-2只给任务与接口，成员自行实现、测试与解释。

| 2026-11-23 | M4（实现草案） | 冻结需要绑定完整计划与证据 | freeze_protocol 的 cfg 改为含 config/baselines/evaluation_seeds/used_seeds 的计划对象；正式结果状态为 computed_pending_review | m4-*、scripts/run_m4_formal.py、docs/M4_FORMAL_WORKFLOW.md | 待 M3/M5 及全组确认 | 开发阶段；仅已看 demo，未运行正式数据 |

| 2026-11-25 | M4（自动技术核对） | 核对M2保留8的开发证据和交付一致性 | 7,200行全表、36行候选对话指标及差值与M4独立运行一致；支持保留8，基线映射不变 | scripts/verify_m4_m2_acceptance.py；deliverables/M4_M2_acceptance_20261125.json | 技术核对通过；本人签收及团队批准仍待完成，不代签 | 已看开发/demo；未运行正式实验 |

| 2026-11-26 | M4（用户授权补充计划并推进E1，Codex协助） | Methods需要七方法效果、特征贡献、题型变化及成本取舍的可区分证据 | 按E1–E5推进。E1保留两场景CTS−开发固定臂主比较及95%/97.5%区间，新增CTS−TS、CTS−RuleRouter探索性95%配对区间和五指标分解；development/demo分别分析，不重选demo基线。后续特征消融、阶段曲线与λ重放独立记录 | docs/M4_FORMAL_WORKFLOW.md；scripts/m4_analysis.py；scripts/run_m4_experiment1.py；deliverables/M4_notes.md | 用户已授权计划及E1推进；M3统计复核和正式冻结所需真实团队批准另行记录，未代签 | 已完成6条development及12条demo的回放核验和新分析；复用四臂表，未生成60条正式数据；两个run均为exploratory_complete_pending_review |

| 2026-11-26 | M4（用户授权准备60种子、冻结方案及人工清单，Codex协助） | 将E1新增分析纳入准确版本批准，并准备未碰撞候选和可填写材料 | 候选stable930000–930029、abrupt930100–930129；可见材料保守排除154种子且无扫描错误/碰撞。plan.analysis_spec为必需，code绑定新增analysis共五项；每人最终批准需seeds_disclosed及additional_dialogue_seeds，额外种子必须纳入plan.used_seeds。复用原7,200行全臂表并重核开发证据；0.02阈值待本人确认 | scripts/m4_protocol.py；scripts/run_m4_formal.py；scripts/prepare_m4_formal.py；deliverables/m4_formal_preparation_20261126；[人工清单](../deliverables/m4_formal_preparation_20261126/HUMAN_CONFIRMATION.md) | 机器准备与47项测试通过；十题联合判定、M3统计复核、成员未共享种子披露及准确版本批准待本人完成。未签模板全false、无approvals.json | 只准备60候选及冻结草案，未生成正式对话、未冻结；正式登记仍为空 |
