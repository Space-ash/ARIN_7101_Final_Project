# M4 正式运行管理（待团队验收）

## 分工与参数候选
M2/M3 的模块正确性测试由本人负责。M4 负责同输入、同种子、同评价口径的实验编排与对话级比较，不代写算法、不代签审查。

| 模块 | 已有候选/默认 | 责任与状态 |
|---|---|---|
| M1 | 近期题概率、更新/初始冲突比例等默认配置 | M1解释机制；当前无确认的候选网格 |
| M2 | 检索候选数8/9/12 | M2提出；需由M2使策略参数可配置并验证，再交M4统一比较 |
| M3 | prior_precision=1、refit_every=5，算法seed 17/37 | 默认，不代表已选定多个实验组合；候选由M3提出并解释 |
| M4 | λ=0.25/0.5/1.0；bootstrap 2000/10000 | 探索建议未执行未冻结。λ改变行为需重放；bootstrap只改变统计计算精度 |

不必穷举参数笛卡尔积。优先验证具体问题，例如M2的候选截断；固定其他条件比较8/9/12，报告每条对话及各场景的效用、准确率、成本、旧值率。若发现参数间交互再做小规模联合比较。全部选择使用开发数据；正式结果只评价冻结方案。M5可先用demo做排版，不必等待所有参数探索结束。

## 输入准备
scripts/run_m4_formal.py 提供 freeze/run 两个命令，当前只支持每场景30条、每条300题设计。

plan.json 是完整计划对象，字段包括：
- config：完整 PROTOCOL_DRAFT 配置（lambda、cost_reference、algorithm_seeds、bootstrap等）。
- baselines：stable/abrupt各自开发固定臂。
- evaluation_seeds：stable/abrupt各30个不重复整数。
- used_seeds：全组披露的所有已用对话seed，除代码内已知禁用范围外也要登记。
- analysis_spec：必需，须与 `m4_protocol.analysis_specification()` 的E1定义一致；绑定对话级聚合、两个CTS−开发固定臂主比较、95%/97.5%区间、探索性直接比较、五指标、失败处理及实际意义阈值草案0.02。最终批准前由成员确认其研究含义。
- 准备包另保存seed_inventory、expected_counts和seed_status；evaluation_seeds列表是最终种子依据，config.formal_seed只保留stable基准的兼容元数据语义。

evidence.json 是证据名到路径的映射，路径相对此文件：audit_review、truth_checks、strategy_checks、method_checks、development_outcomes、development_provenance、approvals。正式freeze需提供这七项真实产物，不用占位空对象。准备阶段可保留尚不存在的approvals.json路径，并另外提供全false的未签模板；模板不能作为正式批准文件使用。

development_provenance 是 JSON 对象，包含 config_sha256（canonical_hash(plan['config'])）、notebook_sha256（生成或实际重核所用工作本的文件 SHA256）和 development_sha256（开发全臂 CSV 的文件 SHA256）。必须记录真实生成或明确重核的来源，不能只给旧结果重新贴上当前哈希。若保留原全臂表并用当前代码重核，须同时保留原始manifest/工作本/配置哈希、相容代码单元、配置差异、重新执行的检查及未重算范围；本次准备包以 `revalidated_existing_development` 明确标识。

truth_checks、strategy_checks、method_checks 使用同一信封格式：包含上述三个哈希、status="passed" 和 payload（原始检查结果）。程序检查 payload 内部结果，外层 passed 不足以通过。truth_checks 必须覆盖全部开发对话且每条300题、无错误；strategy_checks 必须包含通过的 fixture_checks、四项 development_checks 和匹配的 outcomes 行数；method_checks 必须包含 Beta 后验 [3,2]、反馈隔离检查、七种方法、匹配的算法种子/refit、开发对话来源及回放行数，且梯度范数≤1e-3、梯度/Hessian 有限差分误差≤1e-5、协方差最小特征值>0。字段名见 scripts/m4_protocol.py 的 validate_evidence。

开发 CSV 必须覆盖每场景配置数量的对话、每条完整300题×4臂；程序复算 utility = y - lambda * cost / cost_reference 和固定基线，检查缺失值、重复记录及开发/正式种子分离。人工抽查的十题必须属于该开发表。

旧版裸检查文件不能直接用于新版 freeze。应以最终配置和工作本重新生成或核验开发产物，保留原始来源后整理为上述格式，再取得团队批准；不得把失败或未运行检查包装为 passed。整个工作本哈希参与绑定，因此工作本变更后也需要重新核验。哈希绑定和内容检查不能证明文件声明真实，仍需人工审查来源。

配置在冻结前检查完整字段、类型、有限值与取值范围。批准者 name/date 必须为非空字符串，date 必须能解析为 ISO 日期或日期时间，null 不再视作有效签署。

计算失败时，failure.json 和失败登记独立尝试写入；任一写入失败会作为附注保留在原始异常上，两者都失败也不会替换计算异常。磁盘故障仍可能使持久化失败，需要人工调查 started 状态，已登记的种子继续禁止重用。

approvals 文件需包含：plan_sha256（m4_protocol.canonical_hash(plan)）、code_sha256（notebook/runner/protocol/loader/analysis五项实际文件SHA256）、evidence_sha256（除approvals自身外所有证据SHA256）；members对象的M1–M5各有name/date/approved/seeds_disclosed/additional_dialogue_seeds。每人需据实确认seeds_disclosed=true；additional_dialogue_seeds必须是互异的非负整数列表，无新增时明确保留空列表。程序核验这些额外种子已全部纳入绑定的plan.used_seeds，候选与used冲突会被拒绝。另有m3_statistics_reviewed和all_used_seeds_disclosed两个真实确认值。程序不会生成签名。批准记录是人工声明，不是数字签名系统，仍需团队审查真实性。

代码绑定文件：根工作本、scripts/run_m4_formal.py、scripts/m4_protocol.py、scripts/test_member_handoff.py、scripts/m4_analysis.py，共五项。配置、analysis_spec、代码或审计证据变化后旧批准失效。

```powershell
python scripts/run_m4_formal.py freeze --plan plan.json --evidence evidence.json --destination outputs/frozen/approved_v1
python scripts/run_m4_formal.py run --frozen outputs/frozen/approved_v1 --run-id formal_unique_id
```

freeze复制证据和源码并拒绝覆盖。run再次核对批准、快照与当前代码；从批准的开发全臂表复算基线；检查开发/正式seed分离。在生成任何正式对话前向team_workspace/formal_runs.json追加started事件，然后运行60条对话。完成状态为computed_pending_review，仍待M3/M5验收，不自动标complete。

失败追加failed事件，保留已使用seed和目录；重复run ID或已尝试seed会被拒绝。注册采用锁文件和原子替换，异常进程退出留下的锁/.new文件须人工调查，不自动删除或覆盖。不得并行启动共享同一登记文件的正式任务。冻结后不能依据已看结果调参并伪称原主检验。

## 验证与限制
python scripts/test_m4_protocol.py 在临时目录使用明确的SYNTHETIC签名测试，绝不写实际审查表；覆盖绑定、篡改、重用seed、重复run、未签审查和失败历史保留。当前仅有生命周期组件测试和先前demo计算链验证，尚未执行真人批准的完整正式运行。上游证据由批准者确认含义，不能只靠文件哈希推断研究通过。

当前没有真实审批文件，formal_runs.json保持原状态。正式数据不可在团队确认前生成。

发布版可直接对 `deliverables/m4_formal_preparation_20261126` 运行 `preflight`。该目录由 `.gitattributes` 保留证据原始字节；当前执行源码使用 LF，防止 Git 换行转换破坏源码/证据绑定。本次 fork PR 在最新 main 上重新核验开发证据和 demo 分析，保留上游导出完整性检查；没有生成真实批准或正式对话。完整 demo 回归测试需要另行共享的 `outputs/demo/m4_stage2_verified_20261123`，缺少时相关五项会跳过。

## 追加：候选数开发探索入口

```powershell
python scripts/explore_m4_candidates.py --run-id your_unique_candidate_run
```

该脚本在内存中对M2的select_context只替换head(8)为head(k)，不修改M2工作本；若源代码不再精确匹配，则停止要求重新审核。比较同时应用于两个检索臂，k=8/9/12，预算保持256，focus锚点和打包规则不变。方法回放使用相同算法seed，但行为分叉后的随机过程不保证逐次抽样完全对齐。
先验证k=8与默认基准一致，且固定短/长窗不受变体影响，再比较同一方法相对k=8的对话级效用、正确率、成本与旧值变化。保存三个变体的全部四臂与回放结果，不只保留最佳者。不把适配器变成正式协议；若选定新候选数，应请M2正式参数化并独立测试，再冻结。

## 2026-11-26 补充实验计划：E1–E5

本计划依据仓库根目录的 [Methods 中文原稿](../ARIN7101_Methods_CN.md) 补充评估，用户已授权推进 E1。它规定接下来的实验问题和分析顺序；结果是否产生、验证是否通过及正式批准状态分别记录在 [M4 研究记录](../deliverables/M4_notes.md)，不能用本计划代替实际证据。

### 共同比较口径

- 主目标仍为各场景 LaplaceCTS（下称 CTS）相对开发集预选固定臂的对话平均效用差。保留 stable、abrupt 两个主比较，主参数为 λ=0.5、C0=512、T=300、算法种子17/37，四策略预算128/512/256/256、检索候选上限8、prior_precision=1、refit_every=5。
- 每种方法使用同一条对话和四臂结果；每条新对话重置学习器。先在算法种子内平均题目，再在同一对话内等权平均算法种子，最后跨独立对话配对。300题和两个算法种子均不增加独立样本数。
- 两个主比较保留 percentile 配对 bootstrap：2,000次、seed=2026，报告95%区间及各97.5%的两场景校正区间。新增 CTS−TS、CTS−RuleRouter 及其余补充分析只报告探索性95%区间，不套用原来的两比较校正；如需升级为确认性结论，须在正式数据生成前另行定义比较族。
- 同时报准确率、完整输入长度代理成本、效用、最新证据覆盖率和旧值回答率，并核验 ΔU=Δaccuracy−λ×Δcost/512。覆盖不等于正确，输入长度不是真实API费用或时延。区间跨0不证明等效，bootstrap区间也不提供严格有限样本覆盖保证。
- development（每场景3条）和 demo（每场景6条）均为已看数据；本次分别分析，不合并成新的独立测试集。正式评估仍为每场景30条未看对话，基线仅从开发数据选择并冻结。30条是设计规模，不是已验证的功效保证。

### 实验矩阵与验收

| 编号与优先级 | 问题及比较 | 控制条件与数据 | 必交输出和通过条件 | 计划时状态 |
|---|---|---|---|---|
| **E1 · 开发/demo已执行** | 七方法总体表现；CTS是否优于开发固定臂、TS及RuleRouter；效用收益来自正确率还是成本 | 默认配置不变。开发基线为stable→recent_short、abrupt→resolved_tfidf；从已用development/demo序列执行重放核验，两个数据阶段分开；正式阶段另用冻结后的30条/场景 | 七方法五指标汇总；每条对话的三个CTS配对差；效应区间及准确率/成本分解；完整轨迹、配置/源码/输入哈希、失败记录。主比较与补充比较标签准确，差值可回连源表，保留负结果 | 6条development、12条demo已重放并生成直接对比；状态为exploratory_complete_pending_review。60条正式实验未执行 |
| **E2 · 强烈建议** | CTS收益是否来自问题特征，而非仅来自模型族变化 | 完整CTS对比同一logistic–Laplace实现的常量特征版本；仅学习器把所有问题映射为[1,1,0]，保留原问题供回答器及RuleRouter使用；维度、先验、成本规则、更新频率、对话及算法种子不变 | 配对效用/准确率/成本差和按题型选臂比例；验证常量版本不区分问题类型、所选反馈隔离及后验更新仍正确。两个原特征均与常量特征等范数，减少先验预测尺度混杂 | 仅计划，未实现或运行 |
| **E3 · 必做补充分析** | 突变前后表现如何，变化来自题型比例还是题型内表现 | 同一E1轨迹；固定第1–150/151–300题，另按近期/历史题分层；预先固定25题不重叠时间窗及累计配对效用差；stable同期曲线作描述参照。阶段内不重选固定臂 | 阶段/题型指标、选臂比例、每组对话数及题数、累计差曲线底表；全程指标保持主结果。缺某题型的组注明缺失和样本数，不当作零；逐点区间不能解释为整条曲线的同时置信带 | 开发阶段已有半程、题型和选臂统计；正式输出接入及时间曲线待完成 |
| **E4 · 建议** | 排名与成本取舍是否依赖λ=0.5 | λ=0.25/0.5/1.0；其他条件固定，使用已登记开发对话，每个λ重新回放。若比较各λ下的开发最优固定臂，须分别从开发数据选定并标明，不能从正式结果重选 | 每个λ的完整轨迹、五指标和选臂比例，报告所有λ。验证λ=0.5复现E1；区分“重新选择动作”和“固定轨迹换评分” | 仅计划，未执行；主λ仍为0.5 |
| **E5 · 可选** | 检索组件及算法随机性是否影响结论 | 优先只改变resolved_tfidf候选上限8/9/12，保持tfidf=8；或分别关闭指代消解、同义词归一化、focus保留。算法种子扩展须提前列清单；不默认穷举所有组合 | 单因素配置、全臂结果、重新回放、旧值/成本/效用分解及全部变体结果；改变检索后不能复用旧结果表。增加算法种子仅用于随机性诊断，不增加独立对话n | 两检索臂同时8/9/12已有开发探索；单臂/组件消融及种子扩展未执行 |

E2 的 TS−CTS 比较仍可保留，但不能替代同模型消融。E3 的 abrupt 改变的是提问需求比例，事实生成和回答规则不主动改变；历史增长仍可能影响题型内难度。没有遗忘机制的本实现不能据此宣称解决一般条件奖励漂移。

### E1 本轮执行边界与后续正式交付

本轮实现入口为 `scripts/run_m4_experiment1.py`，公共分析放在 `scripts/m4_analysis.py`。已核对原始development/demo来源的全部manifest文件哈希、M1–M3与共享协议代码一致性，使用当前生成器同seed复现对话并独立核验真值，重新执行七方法回放，与原归档逐行一致。四臂结果复用原表；本轮没有重新构造TF–IDF候选或测量构造耗时。新结果保存输入哈希、代码快照、统计表和完整回放。

已完成归档为 `outputs/development/m4_e1_development_20261126`（6条对话、7,200行四臂、25,200行回放、42行对话指标）和 `outputs/demo/m4_e1_demo_20261126`（12条对话、14,400行四臂、50,400行回放、84行对话指标）。两份manifest均标为 `exploratory_complete_pending_review`、`already_viewed=true`、`formal_generated=false`。数值与解释见M4记录第15节，精简交接证据分别为 `deliverables/M4_E1_m4_e1_development_20261126.json` 和 `deliverables/M4_E1_m4_e1_demo_20261126.json`。

可用新run ID复跑；默认输入为原始完整demo归档，开发阶段须显式指定原始基准。入口不接受E1输出目录作为下一次输入，两者归档schema不同。

```powershell
python scripts/run_m4_experiment1.py --run-id m4_e1_demo_repeat_20261126
python scripts/run_m4_experiment1.py --run-id m4_e1_development_repeat_20261126 --source-run outputs/development/m4_default_benchmark_20261123
```

每次执行需使用尚不存在的run ID；以上示例不代表已执行的额外尝试。

E1分析代码及比较定义现已接入正式入口和待签绑定范围；正式运行前仍需确认代码版本并补齐真实审查、M3统计复核、完整已用种子披露和团队批准，再执行冻结。正式规模预计60条对话、18,000题、72,000行四臂结果；沿用七方法各两个算法种子的记录口径时为252,000行回放、420行对话指标。新增补充表须与同一formal run关联，不混用开发结果。

计划本身不改变十题联合判定，不生成审批签名。E1的开发/demo运行完成只能标为相应阶段完成，不能替代独立正式评估。回放可信性还应通过同序列、同随机数流的逐轮执行对照，核对动作、已选反馈和后验状态；已有未选反馈翻转、数值和重置测试继续保留。

## 2026-11-26：60条候选种子与冻结准备包

按用户要求完成的准备包为 [m4_formal_preparation_20261126](../deliverables/m4_formal_preparation_20261126/HUMAN_CONFIRMATION.md)，完整逐项人工材料、填写顺序和最终freeze/run命令见该目录的 [HUMAN_CONFIRMATION.md](../deliverables/m4_formal_preparation_20261126/HUMAN_CONFIRMATION.md)。当前是待确认草案：技术检查通过，`frozen=false`、`approved_for_execution=false`、`formal_generated=false`。60条正式对话尚未生成。

候选种子为stable 930000–930029、abrupt 930100–930129，各30条且互异。仓库与可见归档的清点保守排除154个对话种子，scan_errors和碰撞均为0。该检查只覆盖可见材料，不能证明成员未共享的本地、失败、调参或历史运行没有使用候选种子；必须取得每人的完整披露。

准备包已具备plan.json、evidence.json、approval_request.json、五项代码快照、原始来源、重新核验的开发证据、技术检查及逐项人工清单。最终package_manifest中的42个文件哈希全部通过；remote_readback.json记录主线仍为0472e32、审查表Git blob与远端一致，test_verification.json记录47项测试。`approvals.template.json`按用户要求预备，姓名/日期为空、批准和披露标志均为false；`approvals.json`尚不存在。`seed_disclosure.template.json`与`statistics_review.template.json`是辅助工作表，真正供协议核验的确认位于最终approvals.json，不能仅填写辅助表就宣称批准齐备。

机器可完成的部分已经执行：20个M1–M3/共享源码单元与原证据一致，7,200行开发全臂表保持字节不变；重新核验六条开发对话的1,800题真值、7项策略fixture、40条抽查臂，并重新执行4,200行方法检查回放。正式分析构造器在已看过的12条demo上验证，原主次效应复现。完整四臂检索和construction_ms沿用原产物，保留源哈希与重核说明。

| 待本人完成 | 材料与最终有效字段 |
|---|---|
| M1/M2十题联合审查 | 确认包内audit_review.csv既有意见，逐题填写真实pass/fail；十题目前均pending，不能批量代填 |
| M3统计复核 | 确认主次比较、聚合、区间、失败处理及0.02阈值；最终填写approvals.json的m3_statistics_reviewed |
| M1–M5种子披露 | 每位成员的seeds_disclosed及additional_dialogue_seeds；新增种子先经refresh纳入plan.used_seeds，候选冲突则另选候选并重新出版本 |
| M1–M5准确版本批准 | 真实name/ISO date/approved，绑定最终plan、五项代码和六项非批准证据哈希；全员披露后才能确认all_used_seeds_disclosed |

0.02是待确认的效用实际意义阈值：成本相同时相当于正确率提高2个百分点，正确率相同时相当于每题减少20.48个长度代理单位。它不代表已验证的功效或必然可检测效应；不能看过正式结果后再调整。

修改联合审查或补充种子后，可执行以下命令刷新待签哈希并检查缺项；两者均不生成正式对话：

```powershell
python scripts/prepare_m4_formal.py refresh --package deliverables/m4_formal_preparation_20261126
python scripts/prepare_m4_formal.py preflight --package deliverables/m4_formal_preparation_20261126
```

refresh只更新待签材料，不生成批准；已有真实approvals.json时拒绝覆盖，需保留旧版本并另建版本。只有真实材料完整且preflight为ready_for_freeze后，才按人工清单中的命令冻结与运行。准备过程不修改真实审查判定或正式登记；`formal_runs.json`仍为`[]`。本次47项测试通过；协议测试首次在沙箱虚拟临时卷的os.replace触发WinError 650，在工作区outputs/test_tmp重跑通过，属于测试环境文件替换问题，不是算法失败或正式运行失败。
