# 项目进度审查报告｜2026 年 11 月 23 日 | f3e82d3

## A. 项目整体状态

**项目已达到开发联调阶段，尚未达到正式实验或最终提交阶段。** M1 的生成器、M2 的四臂评价、M3 的贝叶斯回放，以及 M4 的对话级统计函数已经能传递真实格式的数据。M2 有可回读的完整开发产物，M3 在其中一条开发对话上的回放也能复现。当前关键路径是 **M1/M2 完成十题人工审查 → M4 完成集成、冻结和归档 → 正式运行 → M3 复核统计、M5 核验并展示结果**。目前没有依据判断 LaplaceCTS 在正式评估中是否优于固定策略。

### 实际验证到了哪一步

| 本次只读检查 | 实际观察 | 可以支持的判断 |
|---|---|---|
| 主工作本结构与接口测试 | `validate_release.py` 通过，共 49 个单元，源码语法、分区和清输出检查通过。`test_member_handoff.py --member all --verbose` 的 M1、M2、M3 全部通过 | 三个上游模块已接入当前主本；测试覆盖小型接口案例 |
| M2 已落盘的开发评价 | 读回 7,200 行、1,800 个 `(seed,t)`，每题四臂齐全，`(seed,t,arm)` 无重复。全表效用均符合 `y − 0.5 × cost / 512`。单对话交接 CSV 与全表对应的 1,200 行完全一致；汇总表有 24 行 | M2 已实际执行六条开发对话的评价，有逐行结果可交付 |
| M3 使用 M2 真实开发表 | 用主本 `run_m3_method_checks` 在 `abrupt/130100` 上重放 7 种方法、2 个算法 seed，得到 4,200 行。五项指标逐行匹配所选臂；打乱输入和翻转未选奖励的检查通过。M4 可将其聚合为 7 行对话指标 | M2→M3→M4 的单对话接口已实测接通；这一规模不能估计两个场景的正式效应 |
| M4 统计及跨模块检查 | 本次重跑 M4 手算 fixture 通过。另在内存串行调用 M1→M2→M3→M4，用两场景各两条、每条 8 题的小样例得到 128 行四臂评价、448 行回放、28 行对话指标和主次表各 2 行 | 统计函数能消费上游输出。串接由审查时手工调用，项目自身的运行入口仍缺失 |
| 正式实验与展示 | `formal_runs.json` 为 `[]`，当前 `outputs/demo` 和 `outputs/formal` 未见结果文件；未找到正式 manifest、正式效应表、最终图表、slides 或视频链接 | 工作区内没有可验收的正式实验或最终汇报。团队是否另有未共享材料，待验证 |

审查以本地 `main` 的 `f3e82d3` 为准，与本地记录的 `origin/main` 一致。开始和结束时 Git 工作区均干净。本次只读现有产物，并在内存运行上述检查；未执行整本初始化、完整开发表重算、demo 或 formal，未安装依赖、写入项目文件或改变 Git 状态。[主工作本](./ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [结构检查](./scripts/validate_release.py) · [接口测试及其断言](./scripts/test_member_handoff.py) · [正式运行登记](./team_workspace/formal_runs.json)

### 哪些文档仍有效

- **任务范围**以根目录 Release Notebook 的 `member-m1` 至 `member-m5`、当前分工、协作流程和输出契约为准。`docs/proposal` 保留研究目标与汇报计划；两份 `reference` 完整本属于历史实现，`deliverables/M3_presentation.ipynb` 属于 M3 的独立展示材料。它们都不能证明当前主本已跑完整流程。[项目说明](./README.md) · [协作流程](./docs/TEAM_WORKFLOW.md) · [输出契约](./docs/OUTPUT_CONTRACT.md) · [参考本说明](./reference/README.md)
- **进度板落后于代码。** `team_progress.csv` 仍把 M3 标为 `todo`，M1 的下一步仍是“等待 M2 输出策略审计”。实际 M2 十题包已存在，M3 已并入主本且真实表回放通过。M4 笔记中的“尚未提交”和部分“待集成”也属于合并前状态。Git 可见 M1 合并 `0babf8d`、M2 合并 `c29fba4`、M3 合并 `a7db089`、M4 合并 `a6c3a48`，以及随后修正 M2 自检加载方式的 `f3e82d3`。代码合并与接收人签收仍需分别记录。[进度板](./team_workspace/team_progress.csv) · [M3 记录](./deliverables/M3_notes.md) · [M4 记录](./deliverables/M4_notes.md)
- **旧验证报告有明确日期。** `docs/VALIDATION.md` 的“29 个单元、23 个占位接口”描述的是 11 月 5 日脚手架。本次检查当前主本只剩 **6 个明确占位接口，M4、M5 各 3 个**。研究方法调研中的敏感性分析和额外统计方法仍属候选，不应全部追加为最低交付要求。[历史验证记录](./docs/VALIDATION.md) · [研究调研说明](./docs/research/README.md)

## B. M1–M5 任务进度总表

优先级按**尚待执行的最高优先任务**标记。P0 阻塞后续阶段，P1 是核心交付，P2 是解释、记录或可选优化。“待验证”单独标在证据不足的事项上。按项目自己的 `done` 标准，还需要本人解释、测试证据和接收人复核，五人的整项职责目前均未达到这个标准。

| 成员 | 原定职责 | 已完成工作 | 剩余工作 | 当前状态 | 优先级 |
|---|---|---|---|---|---|
| M1 | 合成对话、公开视图、真值审计、开发数据与诊断 | 两场景生成、版本更新与复述、前缀隔离、独立重建真值、导出函数均有实现；小型生成与审计可运行；M2 已消费同一生成器 | 原始 M1 开发归档待取得和核验；十题 M1 栏全部空白；M2/M4 接收与数据偏向解释待收尾 | **基本完成** | **P0** |
| M2 | 四种上下文策略、共享回答器、预算与完整输入成本、逐臂评价和反例 | 四臂与评价链已实现；六条开发数据、单对话交接表、十题材料、边界案例及 ZIP 实物存在；M3 可直接消费 | 与 M1 逐题定案；统一审查表版本；与 M4 确认检索截断和全表来源，完成接收 | **基本完成** | **P0** |
| M3 | TS、LaplaceCTS、规则参照、后验核查、回放；交付 M4 并复核统计 | 主本有学习器及推导；单对话 4,200 行回放可复现；数值、第五次反馈重拟合、重置、反馈隔离检查通过 | 原 `m3_abrupt_130100` 归档本地待验证；M4 接收；复核 M4 对话级聚合及未来正式效应 | **基本完成** | **P0** 冻结证据；**P1** 正式复核 |
| M4 | 开发选基线、demo 调度、冻结、正式实验、统计与归档 | `choose_fixed_baselines`、`aggregate_dialogues`、`paired_effects` 已实现，手算与异常 fixture 通过，可读取真实开发表和回放 | 三个核心入口仍抛异常；未见全规模 demo、冻结快照、正式登记、完整结果表、manifest 和交接报告 | **进行中** | **P0** |
| M5 | 独立读档校验、可视化、逐图解释、slides、视频、提交 | 主本已有任务说明、选题菜单和输出约定；未发现可计为成员实现的读取器、图表或汇报初稿 | 三个接口全部待实现；fixture 测试、图表对应表、解读、slides、视频和全组复核均未见交付 | **未开始**（按工作区证据） | **P1**，可立即并行 |

## C. 各成员下一步任务清单

### M1｜先完成十题独立追踪

实现证据集中在主本 `m1-generation-skeleton` 的 `generate_episode`、`public_view`、`audit_truth`、`export_development_data`。`audit_truth` 会重新解析可见历史，推导对象、当前值、证据位置和旧值后再与保存字段比较。M1 笔记记载原 run 有 6 条对话、1,800 题；本机未找到该 run。M2 以相同 seed 重新生成数据并留下检查记录，可佐证生成器可用，原归档逐文件一致性仍待验证。[主工作本](./ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [M1 交接记录](./deliverables/M1_notes.md) · [M2 开发检查记录](./team_workspace/m2_handoff/strategy_checks.json)

- [ ] **P0｜逐题填写 M1 审查。** 直接使用现有 `audit_examples.json`，按 `(seed,t)` 从公开前缀追踪 focus、目标属性、最新陈述、旧值和证据 ID。验收为十行都有 M1 本人意见，与 M2 对应意见逐项核对；发现失败则保留案例、定位原因并复核。输入已经就绪。[十题材料](./team_workspace/m2_handoff/audit_examples.json) · [协作审查表](./team_workspace/m2_handoff/audit_review.csv)
- [ ] **P0｜向 M4 补齐开发数据来源。** 提供 `m1_development_20261109` 的对话 gzip、字典、`truth_checks.json`、`development_data_profile.csv` 和可核对的归档位置。若原包不可得，以新 run 明确标记重生成，保留原记录。验收为 M2/M4 能读回六条对话，核对 seed、题数和审计结果，并从一个具体前缀重建答案。
- [ ] **P1｜补上数据机制解释与接收记录。** 用一题近期、一题历史及一次同值复述，说明为何短窗容易命中近期题、为何答对与选中最新证据可能分离。将实例交 M5 用于背景页，并由本人确认贡献与 AI 辅助说明。[M1 交接记录](./deliverables/M1_notes.md)

### M2｜固定审查版本，关闭策略决策

主本 `select_context`、`rule_reader`、`evaluate_episode` 已形成可运行链。预算限制所选消息正文，效用使用包含共同指令、格式、上下文和问题的完整成本。现有开发 ZIP 的 SHA-256 与笔记公布值一致；本地既有完整 `development_outcomes.csv`，也有已提交 Git 的精简交接材料。M4 可立即开始接收。[M2 交接记录](./deliverables/M2_notes.md) · [完整开发表](./outputs/development/m2_development_20261119/tables/development_outcomes.csv) · [M3 单对话输入](./team_workspace/m2_handoff/m3_handoff_abrupt_130100.csv)

- [ ] **P0｜与 M1 完成十题联合判定，并指定冻结来源。** Git 协作表十行均有 M2 姓名和意见，M1 姓名、意见均空，十行 `verdict` 均为 `pending`。ZIP 内是更早的空 reviewer 版本；本地 run 的松散 CSV 又带有列名填充空格。请保留历史包，以 Git 协作表完成复核，由 M4 对最终版本校验准确列名、实质非空意见、逐题判定及哈希。直接读取 ZIP 或对空格只做非空检查，都会给冻结带来错误证据。[协作审查表](./team_workspace/m2_handoff/audit_review.csv) · [run 内松散审查表](./outputs/development/m2_development_20261119/audit/audit_review.csv)
- [ ] **P0｜与 M4 关闭检索候选数决策。** 对照 `seed=130100,t=99` 核实最新证据排第 9、当前 `head(8)` 漏选的案例。若继续比较笔记提出的 8/9/12，使用相同六条开发对话、同预算，报告对话级效用差、成本与旧值率；若保留 8，记录理由与接收人即可。验收为冻结前只有一套明确配置。若更改策略，重新生成受影响的评价、回放及基线选择。[M2 反例记录](./deliverables/M2_notes.md) · [接口决策表](./team_workspace/interface_decisions.md)
- [ ] **P1｜完成 M4 全表交接。** 提供 run ID、ZIP 校验和、源码快照、四臂顺序及成本公式；由 M4 读回 7,200 行，复核每题四臂、唯一键、效用，以及抽查题与十题包的一致性。把接收人和实际检查写回交接记录。M3 单对话接口无须重新设计。

### M3｜交付可核验的回放包，并承担统计复核

主本 `Selector.choose` 只接收问题和按固定臂序排列的成本，`update` 接收所选臂反馈，每次 `replay_episode` 新建学习器。本次在 M2 单对话上复现 Beta(3,2)、MAP 梯度范数约 `7.37×10⁻⁷`、梯度/Hessian 有限差分最大误差分别约 `5.04×10⁻¹¹`、`1.89×10⁻¹¹`。这些数值支持方法实现与笔记一致，原笔记所指的导出文件仍需交付。[主工作本](./ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [M3 推导与开发记录](./deliverables/M3_notes.md)

- [ ] **P0｜向 M4 提供 `method_checks.json` 和 `development_replay.csv`。** 提供原包，或从受控单对话 CSV 用 `export_m3_development` 在新 run 导出。验收为记录输入 SHA-256，M4 可独立读出 300 题 × 7 方法 × 2 seed 的 4,200 行，按键回连所选臂，五项指标一致。将进度板从已过时的 `todo` 更新为真实复核阶段。
- [ ] **P1｜先复核统计代码，正式表生成后再复核结果。** 现在可用 M4 手算样例验证先按题平均、再按算法 seed 平均、最后按同一对话做配对差。正式运行后检查两场景各 `n=30`、开发基线映射、主次比较方向、95% 与主比较 97.5% 区间，并把复核意见交 M4/M5。[M4 统计设计与手算案例](./deliverables/M4_notes.md)
- [ ] **P1｜完成方法解释与本人确认。** 在 M3 记录和演示材料中说明模板下“显式项目 ID”和 `its` 特征的相关性、高斯先验对拟合的作用、每五次反馈重拟合的滞后，以及 TS/CTS 同时改变了模型和特征，比较不能单独识别特征贡献。验收为方法页与实际 `Selector` 实现、引用及贡献记录一致。[M3 记录](./deliverables/M3_notes.md) · [已有方法展示本](./deliverables/M3_presentation.ipynb)

### M4｜优先实现项目自身的运行入口

三个统计函数已具备实际用途。本次把当前 7,200 行开发表送入 `choose_fixed_baselines`，得到 **stable → `recent_short`，abrupt → `resolved_tfidf`**。这是按当前输入和代码重算出的**开发候选基线**。`formal_seed` 仍为 `None`，`freeze_protocol`、`run_evaluation`、`export_run` 均直接抛出 `NotImplementedError`，团队尚未冻结这一选择。[主工作本](./ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [M4 交接记录](./deliverables/M4_notes.md)

- [ ] **P0｜实现 `run_evaluation` 并完成 demo。** 按场景和 seed 调 M1，逐对话调 M2，然后按方法和算法 seed 调 M3；最后调用已实现的聚合函数。先用六条现有开发对话检查来源和接口，再以独立 demo seed 跑每场景 6 条。验收为单一入口在新 run 中产生能互相回连的对话、四臂表、回放和统计表，失败时可定位到场景、对话及方法。
- [ ] **P0｜实现 `freeze_protocol`。** 核对 M1 原始或明确重生成的证据、M1/M2 十题最终审查、M3 方法检查和全组配置确认。锁定基线、预算、候选数、效用、方法、重拟合频率、样本量、算法与 bootstrap seed；排除开发、fixture、demo、历史参考和已看 seed。保存 `frozen_config.json`、清输出源码快照、`review_snapshot.json` 和对应哈希。验收为缺签、证据版本错误或 seed 冲突时无法进入正式运行。[协作流程](./docs/TEAM_WORKFLOW.md) · [输出契约](./docs/OUTPUT_CONTRACT.md)
- [ ] **P0｜实现 `export_run`、完整性检查与尝试登记。** 按冻结配置检查完整预期集合。现有 `aggregate_dialogues` 能发现局部缺轨迹，但如果所有对话都少同一个方法、同一算法 seed 或最后一题，仅靠已出现的行可能发现不了。验收为故意去掉整组后导出被拒；每次正式尝试和失败均保留，`manifest.json` 记录源代码、配置、环境、审查来源及文件哈希，完整通过后才标完成。[正式运行登记](./team_workspace/formal_runs.json) · [输出契约](./docs/OUTPUT_CONTRACT.md)
- [ ] **P1｜正式运行并交接。** 按当前草案应有 60 条独立对话、18,000 题、72,000 行四臂评价。若沿用开发回放中七种方法各跑两个算法 seed 的口径，应有 252,000 行回放、420 行对话指标；最终以冻结配置核验。导出两场景主次效应、方法汇总、`M4_handoff.md` 和完整 manifest。M3 复核统计，M5 在新内核读取同一归档。正式结论允许负向或不确定。

### M5｜立即用 fixture 开工，正式解释等归档

`m5-visualization-skeleton` 的 `load_verified_run`、`build_figures`、`export_visual_evidence` 均为占位函数，`m5-checks-workspace` 只有 TODO，`M5_notes.md` 各节待填。当前依赖 M4 的是**正式数据和最终解读**；读取器、图表代码、叙事骨架和异常测试现在即可推进。[主工作本](./ARIN7101_Context_Bandit_Release_Notebook.ipynb) · [M5 研究记录](./deliverables/M5_notes.md)

- [ ] **P1｜与 M4 对齐契约并实现 `load_verified_run`。** 显式传入 run 路径，用标记清楚的 fixture 验证 mode、配置、manifest 哈希、表键和样本规模；分别模拟缺文件、改 CSV 和混用 run。验收为正确包可在新内核读取，三个反例均明确失败。与 M4 约定次比较 `family_low/high` 为空的读取方式。[输出契约](./docs/OUTPUT_CONTRACT.md)
- [ ] **P1｜实现制图与逐图对账。** 先用 fixture 做主效应区间、准确率/成本/效用取舍、选臂或突变前后行为等项目既定问题；由负责该指标的成员核对。验收为每图都有对应 `figure_<id>.csv`，可从源表复算，负值、单位、区间和数据阶段标识正确。图数按当前工作本允许协商，无须为复刻旧计划而重复展示。
- [ ] **P1｜接收正式包后完成汇报。** 用确认过的 formal run 生成最终图、`figure_manifest.json` 和 `figure_interpretations.md`，逐图注明数据、观察、局限与复核人。现在可同步建立 slides 骨架并核对课程原始要求；旧计划目标为约 15–16 页、15–20 分钟、五人讲述并在本人部分出镜。最终 slides PDF、视频链接、访问权限、引用、个人贡献和 AI 辅助说明由全组复核。目前课程原始要求及外部视频状态**待验证**。[原计划](./docs/proposal/ARIN7101_Context_Bandit_Project_Plan_Formal.tex) · [提交清单](./deliverables/SUBMISSION_CHECKLIST.md)

## D. 项目集成与风险

| 优先级 | 风险与影响 | 解决责任及通过条件 |
|---|---|---|
| **P0** | **冻结证据存在多个版本。** M1 原 run 与 M3 原 run 本地缺失；M2 十题表有协作版、松散 run 版、ZIP 初始版，且人工判定未完成。只验“文件存在”可能接受错误版本 | M1/M2/M3 给出各自证据来源，M4 冻结具体文件、哈希和接收记录。Git 里的审查进展与只读历史包分别保存 |
| **P0** | **局部函数能接上，正式入口仍断开。** 手工小样例跑通不能覆盖完整调度、失败留档、配置冻结和正式规模核验 | M4 打通 demo，在完整预期集合上验证，再开放 formal；M3 用同一输出独立核查 |
| **P0** | **配置选择会使下游结果失效。** 当前候选数写在 `select_context` 的 `head(8)`；若开发后期改为 9 或 12，旧开发表、基线和回放不再对应同一策略 | M2/M4 在冻结前明确取舍，在目前仍是空模板的 `interface_decisions.md` 记录代码版本、影响、接收人及哪些产物已重算 |
| **P1** | **结果解释容易高估外推性。** M1 的近期题直接询问刚出现的事实，模板特征又能区分需求；成本是正则输入长度代理。题、方法和算法 seed 共享对话，不能扩充独立样本数 | M1/M2 给出具体例子；M3/M4 按对话配对；M5 分清开发诊断、正式效应和适用范围 |
| **P1** | **工作量集中在 M4、M5。** M4 同时承担调度、冻结、正式运行和归档；M5 尚无实现，若等 formal 后才动工，展示会成为第二条关键路径 | M1/M2 自行关闭审查与来源问题，M3提前复核统计，M5 现在用 fixture 实现独立读取与制图。M4 保持运行和统计产物的唯一负责人 |

**职责交叉有明确用途。** M1 追踪真值，M2 查验四臂上下文与评分；M3 验证学习器并交叉复核 M4 统计，M4 对运行与归档负责；M5 独立验证归档并制图。未发现主要模块无人负责。当前遗漏集中在**接收人签收、版本决策和证据归档**。`team_progress.csv` 的姓名列也尚未填写，现有提交记录不足以替代个人贡献确认。[团队进度板](./team_workspace/team_progress.csv) · [接口决策记录](./team_workspace/interface_decisions.md)

## E. 推荐执行顺序

| 顺序 | 可直接分配的工作 | 进入下一阶段的条件 |
|---|---|---|
| **1．立即并行** | **M1** 逐题追踪并找回开发包；**M2** 固定审查协作版、交付全表并整理候选数决策；**M3** 交回放与数值核查包；**M4** 写调度和完整性检查；**M5** 写 fixture 读取器、图表与 slides 骨架 | M4 拿到版本可识别的上游输入，M5 与 M4 对齐表结构 |
| **2．开发验收及 demo** | M1/M2 完成人工审查；M4 运行两场景 demo；M3 核查轨迹与统计；M5 从 demo 归档独立读表绘图 | 十题问题已关闭，demo 预期规模完整，文件可校验，主要模块接收有记录 |
| **3．冻结后正式运行** | 全组确认配置与未用 seed；M4 保存快照、登记尝试、运行两场景各 30 条，导出主次结果与 manifest | 同一 formal run 可追溯、可回读，两场景各有 30 个独立对话配对，M3 完成统计复核 |
| **4．最终提交** | M5 从已核验的正式包导图并统筹试讲；M1–M4 分别复核本人负责的案例、方法和结论；全组核对课程要求及提交链接 | 图、表、解释均能追到源 run；slides PDF、视频、贡献说明与提交清单齐备 |

**最低可交付线**是十题真实双人审查、可复核的方法证据、通过 demo 的集成入口、预先冻结且登记的 60 条正式对话、经复核的对话级效应表、可独立验证的归档，以及由该归档生成的最终汇报。额外敏感性分析和更多图型可以后排；显著或正向的实验结果不是交付条件。