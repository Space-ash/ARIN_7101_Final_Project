# M1 研究、实现与交接记录

姓名：刘卓扬

阶段：待复核（实现、development 数据及十题证据复核已完成；本人确认、M1/M2 联合判定和 M2/M4 接收未完成）



## 1. 数据机制选择与理由

- 沿用共同设计：每条 episode 有 6 个项目、4 种属性、300 道题；`stable` 的近期题概率为 0.9；`abrupt` 在 `t=150` 从 0.9 切换到 0.1；每轮事实更新概率为 0.25；初始项目-属性组合以 0.25 概率包含两个不同版本。
- 每轮按 focus、事实、短干扰的顺序追加消息，再生成问题。近期题用 `its` 指向 focus；历史题明确写出非 focus 项目名。事实中使用 `dataset/data source`、`language/coding language`、`metric/evaluation measure`、`deadline/due date` 表达。
- 使用 episode 局部 NumPy RNG；事实值由 seed 和 episode 内序号构造。更新产生新值，复述保持值不变。`evidence` 始终指向截至当前题最后一次陈述，因此复述也会改变 evidence ID；`old_values` 保存此前不同的值。
- 参数是生成概率，不强制有限样本比例等于设定概率。这个选择保留了抽样波动，也避免通过配额让每段对话看起来过于整齐。

## 2. 生成/公开视图/独立核查的实现

- 在 notebook `m1-generation-skeleton` 实现 `generate_episode`、`public_view`、`audit_truth` 和 `export_development_data`。`public_view` 仅返回 `question/history`，历史严格截断为 `history[:end]`。
- `audit_truth` 逐题重新解析公开文本中的 focus、事实、属性同义表达和显式项目名，再重建当前值、证据 ID 和旧值。审计不以 episode 内保存的 `gold` 作为推导来源；保存值只用于最后比对。
- 输出字段说明、可见性、生成机制和统计单位写入 `audit/data_dictionary.json`；逐题核查记录写入 `audit/truth_checks.json`；按场景和状态汇总问题、旧值、历史长度、证据距离、更新和 alias 使用情况写入 `tables/development_data_profile.csv`。
- M1 测试区提供临时 fixture 导出检查。独立运行开发导出时，在共享路径单元设置新的 development `RUN_ID`，然后将 `M1_EXPORT_DEVELOPMENT` 改为 `True`；默认 `local_setup` 不会导出研究数据。

## 3. 自己设计的测试与失败案例

在 Python 3.12 环境执行 M1 单元后，以下检查通过：

- 相同 seed/配置完全复现；不同 seed 得到不同 episode；message ID 与 `t` 从 0 连续。
- `abrupt` 在小型 `T=8` fixture 的 `t=4` 切换；正式 `T=300` 的边界为 `t=150`。`stable` 始终为 A。
- 变更当前题之后的未来消息不改变 `public_view`；返回对象不含评估器字段。
- fixture 覆盖 `its`、显式项目名、属性别名、版本更新，以及同值复述后 evidence 前移。
- 故意篡改 fixture 的 `gold`、旧 `evidence`、未来 `evidence` 和 `old_values` 后，审计器能报告不一致或时间越界。
- fixture JSONL gzip 导出后可读回；重复导出被拒绝；fixture 使用临时目录，不混入 development 数据。

这些是围绕接口性质编写的自动检查，不替代 M1 成员本人解释代码，也不证明上下文策略或研究假设正确。测试来源为 notebook `m1-checks-workspace`。

## 4. 开发诊断与10题审查

运行 `outputs/development/m1_development_20261109`，共 6 条 episode、1,800 道题；独立真值审计覆盖全部 1,800 题并通过。观测比例是本次抽样结果，不是硬编码目标：

| scenario/state | questions | recent fraction | historical fraction | has-old-value fraction | mean evidence lag (messages) |
|---|---:|---:|---:|---:|---:|
| stable/A | 900 | 0.890 | 0.110 | 0.771 | 7.197 |
| abrupt/A | 450 | 0.893 | 0.107 | 0.649 | 8.691 |
| abrupt/B | 450 | 0.102 | 0.898 | 0.898 | 72.362 |

所有汇总组覆盖 6 个目标项目和 4 种属性。abrupt 后半段历史题比例及其旧值暴露较高，且平均 evidence 距离增加；这些是数据机制诊断，不能据此推断哪种策略会胜出。

2026-11-23 已取得 `team_workspace/m2_handoff/audit_examples.json` 的十题材料，并从每题公开前缀逐条追踪目标、当前值、最新证据与旧值，十题真值字段均一致。四十条策略的上下文、回答、正文预算、完整成本、评分与归档行也核对一致；已知旧值回答和缺 focus 的失败案例得到复现，未发现本轮需要修改生成器或评分代码的问题。

逐题证据和评分摘要见 [M1 十题复核记录](M1_review_20261123.md)。协作表 `team_workspace/m2_handoff/audit_review.csv` 的十条 `m1_notes` 已补充，`m1_reviewer` 已填写为 `Liu Zhuoyang`，联合 `verdict` 仍为 `pending`。与 M2 逐题核对后再填写最终判定；技术检查不替代人工签收。

## 5. 证据 run 与 M2/M4 接收

- Development run：原始 run 现归档于 `deliverables/m1_development_20261109/`。
- 已归档：`data/development_dialogues.jsonl.gz`、`audit/data_dictionary.json`、`audit/truth_checks.json`、`tables/development_data_profile.csv` 和 `config/environment.json`。
- Seeds：stable `130000-130002`；abrupt `130100-130102`。开发和审计均使用 Python 3.12.0，虚拟环境解释器为 `C:\Users\86158\Desktop\project\.venv\Scripts\python.exe`。
- JSONL gzip 逐条读回后与生成的 episode 完全一致；独立审计状态为 `passed`。完整原始 run 已复制到 Git 跟踪的 `deliverables/m1_development_20261109/`，供组员读取。`config/environment.json` 记录环境初始化；生成规模和审计通过状态以对话文件及 `audit/truth_checks.json` 为准。
- M1 代码已合入当前主工作本，M2 已使用同一生成器重生成开发数据。原 M1 run 现已归档在当前 v2 仓库的 `deliverables/m1_development_20261109/`；M2/M4 尚待记录读回、seed、题数、审计结果和前缀重建的接收核验。十题联合判定也待 M1/M2 双方完成。

### 提供给 M5 背景页的机制实例

以下实例均来自 seed `130000` 的原始 run，可从 `data/development_dialogues.jsonl.gz` 按 episode seed 和题目 `t` 复核。每轮历史按 focus、事实、短干扰的顺序追加；近期题用 `its` 指向当前 focus，历史题则明确点名其他项目。`recent_short` 只保留最近三条消息。

- 近期题 `t=0` 问 “What is its current deadline?”，公开前缀到 `end=37`。消息 34 指向 P2，消息 35 给出截止日期 `V130000000012`，消息 36 是干扰。M2 审查材料中的 `recent_short` 选中 `[34, 35, 36]` 并答对。近期题容易被短窗命中，是因为生成器把当前 focus 和与之相关的事实放在问题前的最近消息中。
- 历史题 `t=2` 问 “What is P4 current coding language?”，答案为 `V130000000022`，最新证据是消息 21。该题公开前缀到 `end=43`，最近三条消息 40–42 只谈 P3 和干扰，因此 `recent_short` 返回 `UNKNOWN`；检索臂可从更早历史找回 P4 的语言事实。它展示了明确指向旧项目的问题会超出短窗。
- 同值复述见近期题 `t=8` “What is its current due date?”。截至 `end=61`，最新证据为消息 59，内容是 P2 的 deadline `V130000000012`；较早的消息 35 已陈述完全相同的值。若某策略只选入消息 35 而漏掉 59，仍可能答出正确值，但按 M1 的定义没有覆盖最新证据。答案正确性检查值是否正确，coverage 检查最新支持消息是否入选，两项指标因此可以分离。这个例子说明指标机制，不声称某个 M2 策略在该题实际只选了消息 35。

这三例已整理为 M5 背景页候选材料；M5 实际接收及采用情况待其确认。它们说明生成机制与开发接口，不代表正式实验结论。M2 开发表也记录了整体上存在答对但未覆盖最新证据、以及覆盖最新证据却答错的行，详见 `deliverables/M2_notes.md`。

### 接收与本人确认状态

- M2/M4 接收：完整原始 run 已在仓库归档。接收人仍需实际读回六条对话，核对 stable seeds `130000–130002`、abrupt seeds `130100–130102`、每条 300 题、审计 `passed`，并从一个指定前缀独立重建答案后，在接收记录中填写姓名、日期与结果。目前尚无该项接收确认。
- M1 本人确认

## 6. 局限、引用与本人贡献

- 本项目采用程序生成的英文模板对话，答案可以通过规则从公开历史中恢复。数据覆盖指代、属性别名、版本更新和同值复述等情况，对真实自然语言表达、多轮理解及实际 LLM 行为的覆盖仍有限。
- 近期题比例、事实更新概率、干扰文本和即时反馈均由生成机制设定，具体分布随 seed 波动。当前六条开发对话用于接口联调、数据诊断和开发选择，正式结论仍需依据冻结后的实验结果。
- 实现依据项目共同设计、主工作本中的共享协议及 `docs/OUTPUT_CONTRACT.md`。旧 reference notebook 用于了解历史背景和核对接口语义。正式报告中的课程材料页码及文献引用仍需逐项核实。
- 本人负责 M1 的合成对话、公开视图、真值核查和开发数据交付。具体工作包括落实 `stable` 与 `abrupt` 两种场景，处理近期题与历史题、事实更新、同值复述和属性别名，并通过 `public_view` 按题目边界截断历史。
- 本人负责 `generate_episode`、`public_view`、`audit_truth` 和 `export_development_data` 的实现与验证，围绕 seed 复现、消息编号、场景切换、未来信息隔离、真值篡改检测和导出读回等情况整理检查与失败案例。
- 本人完成开发数据的整理与归档，保留 `m1_development_20261109` 的六条对话、1,800 道题、数据字典、真值审计和分布概况，并将完整原始 run 放入 `deliverables/m1_development_20261109/`，供 M2/M4 核对来源和读取。
- 本人整理十题真值及四十条策略记录的复核材料，记录目标项目、当前值、最新证据、旧值、上下文和评分之间的对应关系，并补充审查意见及逐题证据说明。十题最终联合判定仍待与 M2 完成。
- 本人补充近期题、历史题和同值复述三个具体实例，解释短窗容易覆盖近期事实的原因，以及回答正确性与最新证据覆盖率可以分离的机制，整理为 M5 背景页材料。M2/M4 数据验收与 M5 材料接收仍待实际确认。
