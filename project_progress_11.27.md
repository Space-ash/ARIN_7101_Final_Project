# 项目进度报告｜2026 年 11 月 27 日

**M4 已交付 E0–E7 全阶段开发结果、A1–A7 补充分析、12 条 demo 的 E1 分析和 60 条正式对话的未签署准备包。** 正式运行登记仍为空。冻结前还需 M1/M2 逐题定案、M3 确认统计方案，以及五名成员披露已用对话种子并批准同一版本。M5 可以同时开始读档、校验和制图。[准备包状态](deliverables/m4_formal_preparation_20261126/readiness.json) · [正式登记](team_workspace/formal_runs.json)

## 相比 11 月 26 日的变化

上一版主线报告验证到小规模 demo。本轮从 `0472e32` 起按依赖顺序审查并合并三项交付，实验代码与结果对应的执行版本为 `afc8015`。[11 月 26 日主线报告](https://github.com/Space-ash/ARIN_7101_Final_Project/blob/0472e32/project_progress_11.26.md)

| 合并项 | 新增交付 | 本轮复核 |
|---|---|---|
| [#7 · E1 与正式准备](https://github.com/Space-ash/ARIN_7101_Final_Project/pull/7) | E1 增加 CTS 与 TS、RuleRouter 的对话级配对比较和效用分解。正式准备包绑定配置、候选种子、源码和开发证据。 | 准备包清单的 44 个文件逐一通过 SHA-256 核验；合并版本的技术预检通过，状态仍为待人工确认。 |
| [#8 · 分阶段实验代码](https://github.com/Space-ash/ARIN_7101_Final_Project/pull/8) | 可按版本化计划执行 E0–E7，并分析时间变化、参数敏感性和不同方法的表现。 | 本机实际运行的 96 项 M4 测试通过。另有一个依赖完整 demo 归档的测试类被跳过，含 5 项用例。主本 49 个单元的结构检查和 M1–M3 接口检查通过。 |
| [#9 · 完整开发结果](https://github.com/Space-ash/ARIN_7101_Final_Project/pull/9) | 发布结果表、运行计划及来源记录。33 次配置评估涵盖 26 种不同设置，其中 32 次新执行、1 次复用。 | 46 个开发证据文件、证据清单及结果文档哈希匹配。用 E1 七方法的平均效用独立复算两个场景各三项比较，均与发布表一致。 |

**开发结果的解释范围。** 每个场景使用 3 条已见开发对话，每条 300 题。默认 E1 中，stable 和 abrupt 的 CTS 平均效用分别高于各自开发固定臂 0.050314、0.053373，高于 TS 0.065150、0.160645，低于 RuleRouter 0.031801、0.034321。扩大参数网格和重复算法种子会增加轨迹行数，独立样本数仍是每场景 3 条。这些比较供方法解释与冻结前复核使用。[开发结果报告](docs/EXPERIMENT_RESULTS_DEVELOPMENT_20261126.md) · [结果底表](deliverables/M4_full_development_20261126)

## M1–M5 的进度和下一次交付

| 成员 | 当前进度 | 下一步与验收人 |
|---|---|---|
| **M1 · 待复核** | 已交付两场景生成器、真值核查和十题公开前缀追踪。准备包含六条开发对话、1,800 题的真值核查证据。[真值检查](deliverables/m4_formal_preparation_20261126/truth_checks.json) | 本人确认十题的目标、最新证据和旧值，与 M2 逐题写入联合判定；有分歧的题记录原因并复核。向 M4 确认开发数据来源及对应版本。 |
| **M2 · 待复核** | 六条对话共 7,200 行四臂评价，40 条抽查策略记录已有重建证据。比较过 8、9、12 个检索候选，当前保留 8。准备包与协作表的审查 CSV 哈希一致，十行都有双方意见，判定均为 `pending`。[审查表](deliverables/m4_formal_preparation_20261126/audit_review.csv) · [接口决策](team_workspace/interface_decisions.md) | 与 M1 关闭十题判定，向 M3/M4 确认回放所用全表及策略配置；和 M4 核对最终审查表已绑定到待批准备包。 |
| **M3 · 待复核** | 七方法回放已接入开发和 demo。准备包已含方法数值与反馈隔离检查，E1 已有按对话配对的差值表。[方法检查](deliverables/m4_formal_preparation_20261126/method_checks.json) · [E1 验证表](deliverables/m4_formal_preparation_20261126/validation_tables) | 复核算法种子先在对话内平均、两场景主比较的 95% 与 97.5% 区间、探索性直接比较及准确率与成本分解，向 M4 提交统计复核意见。正式运行后再核对同一归档的效应表。 |
| **M4 · 开发结果已交付，正式实验待冻结** | 已交付全部开发结果与 E1 正式准备包。正式方案预留每场景 30 条对话，预计 18,000 题、72,000 行四臂评价和 252,000 行回放。[正式计划](deliverables/m4_formal_preparation_20261126/plan.json) | 向 M3/M5 共享完整原始归档及校验和，收齐十题判定、统计复核与五人种子披露。复查冲突并刷新版本绑定，取得全组批准后冻结、登记、运行，再向 M3/M5 交付同一正式归档。[人工确认清单](deliverables/m4_formal_preparation_20261126/HUMAN_CONFIRMATION.md) |
| **M5 · 待实现** | 主本的 `load_verified_run`、`build_figures`、`export_visual_evidence` 仍为占位，提交清单中的最终 slides、视频与签收待填。[主工作本](ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [提交清单](deliverables/SUBMISSION_CHECKLIST.md) | 先用小规模 demo 实现独立读取与哈希、表键、样本数校验，再用 M4 共享的完整 demo 对账。每张图附对应数据表和解释；正式包验收后生成最终图表、slides 和视频，交全组复核。 |

**归档交接仍待完成。** GitHub 已有可审阅的开发结果表和完整 demo 的 E1 摘要；本机缺少完整 demo 原始目录和全阶段开发 ZIP。此次核验覆盖仓库中的文件，未重跑全部开发实验，也未独立回读原始 ZIP 中的逐题轨迹。接收方可按发布记录中的 SHA-256 核对另行共享的文件。[E1 demo 摘要](deliverables/M4_E1_m4_e1_demo_20261126.json) · [原始开发包记录](deliverables/M4_full_development_20261126/raw_archive.json)
