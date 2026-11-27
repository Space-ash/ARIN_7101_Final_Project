# 分阶段实验代码与运行说明

日期：2026-11-26。研究问题与控制条件见 [实验设计](EXPERIMENT_DESIGN.md)。本入口用于开发实验和已有结果的补充分析，**不生成 60 条正式对话，不执行 freeze/run，不写真实审批或正式尝试登记**。正式 E1 仍通过原 [M4 正式流程](M4_FORMAL_WORKFLOW.md)管理。

## 1. 代码与阶段对应

统一入口为 [run_m4_stages.py](../scripts/run_m4_stages.py)，预设计划位于 [m4_experiment_plan.py](../scripts/m4_experiment_plan.py)。

| 阶段参数 | 已实现内容 | 核心代码 |
|---|---|---|
| `E0` | 独立真值、真实四臂重建、现有接口/数值检查；逐轮在线与存储表驱动的动作、反馈、后验/缓存/RNG 状态对照 | `m4_validation.py` |
| `E1` | 原七方法及主次效应、CTS–TS/Router 直接比较、效用分解 | 原 `run_m4_formal.build_analysis_artifacts` 纯分析函数 |
| `E2` | 完整特征与同模型常量特征；仅改变 CTS，保留 reader/Router 输入；阶段/题型与选臂分析 | `m4_variants.py`、`m4_temporal.py` |
| `E3` | 前后半程、题型、25题窗、post−pre、累计差及逐点区间，缺组显式标记 | `m4_temporal.py` |
| `E4` | λ=0.25/0.5/1.0 重新回放；另存默认动作换评分结果；不比较跨 λ 的效用差 | `m4_experiment_plan.py`、统一入口 |
| `E5a` | 只改 resolved_tfidf 的候选数 8/9/12 | `m4_variants.py` |
| `E5b` | 分别移除指代消解、别名归一化、focus 优先保留，保留回答器 | `m4_variants.py`、`m4_subgroups.py` |
| `E5c` | 算法 seed 从17/37扩展为17/37/53/71/89，输出对话内随机性 | 统一入口、适配器 |
| `E5d` | 可选单臂正文预算128/256/512 | 预设、适配器 |
| `E6a` / `E6b` | 先验精度0.1/1/10，或每臂重拟合间隔1/5/10；记录选择和拟合次数 | 预设、适配器 |
| `E7a`–`E7e` | 分别改变后段近期题概率、更新概率、初始化冲突、别名概率、项目数，重新生成并审计 | 预设、原生成器 |
| `A` | A1–A6 配对 bootstrap/t/符号/秩/ROPE/多方法比较，另附 A7 事后 oracle 差距 | `m4_statistics.py`、`m4_temporal.py` |

`E5` 合并执行 E5a/E5b/E5c，共7个配置（默认只算一次）；预算实验用 `E5d` 单独选择。`E6` 包含两个单因素网格，共5个配置；`E7` 包含5个环境单因素网格，共11个配置，不做笛卡尔积。所有变体均保留结果。

## 2. 先生成计划，再选择运行规模

下列命令均在仓库根目录执行。run ID 和输出文件不得复用；已存在时会拒绝覆盖。

```powershell
# 只写计划，不读取结果、不生成对话。
python scripts/run_m4_stages.py plan --stage E2 --profile smoke --output outputs/e2_smoke_plan.json

# 按该版本化计划运行短对话检查。
python scripts/run_m4_stages.py run --plan outputs/e2_smoke_plan.json --run-id e2_smoke_check_01

# 也可直接选择预设。
python scripts/run_m4_stages.py run --stage E5b --profile smoke --run-id e5b_smoke_check_01
```

`smoke` 使用已有开发种子 stable 130000/130001、abrupt 130100/130101，每条12题、bootstrap 200次。短对话在这些已用 seed 上重新生成，不是新独立研究数据；所有归档明确 `fixture=true`。ROPE/BCa 等在极小样本或常差时可能退化，输出状态说明，不强行给有效区间。

`development` 使用原有6条完整开发对话，每条300题，来源默认是 `outputs/development/m4_default_benchmark_20261123`。该目录须完整共享，包含 manifest、原工作本/加载器、对话与全臂/回放表；本入口核对全部来源哈希、M1–M3/共同配置、对话身份及默认轨迹。没有来源时会报错，不会静默改用 fixture 或新数据。

```powershell
python scripts/run_m4_stages.py plan --stage E4 --profile development --output outputs/e4_development_plan.json
python scripts/run_m4_stages.py run --plan outputs/e4_development_plan.json --run-id e4_development_01
```

可用 `--source-run` 指定同配置的完整原始 development 归档。demo 和 formal 不作为参数探索入口。正式候选 930000/930100 两段不会传入生成器。

计划目前采用严格的版本化预设：手工改种子、网格或字段后运行会拒绝。要研究其他网格，应修改预设、增加相应验证并生成新版本计划；不能通过改 JSON 绕过数据范围限制。A 类补充分析的 options 文件则支持显式选择方法、先验和重采样参数。

## 3. 对已有归档只做分析

E3/A 可读取带完整 manifest 的 E1 或本阶段归档，不重放、不生成对话。也可读取未来已计算完成的 formal 归档，输出始终另存为探索性补充分析，不改变原主结果与正式状态。

```powershell
python scripts/run_m4_stages.py analyze --analysis E3 --source-run outputs/demo/m4_e1_demo_20261126 --run-id e3_existing_demo_01

python scripts/run_m4_stages.py analyze --analysis A --source-run outputs/demo/m4_e1_demo_20261126 --options configs/m4_statistics_exploratory.json --run-id statistics_existing_demo_01

# 对阶段归档的某个变体做分析，需与源目录实际变体名一致。
python scripts/run_m4_stages.py analyze --analysis E3 --source-run outputs/development/e2_smoke_check_01 --variant constant_features --run-id e3_constant_fixture_01
```

输入文件必须被 manifest 绑定；整个对话缺失、算法 seed/方法缺失、重复记录、错误效用或哈希不符都会被拒绝。分析归档记录源 manifest 哈希、源模式和 fixture 标志。

[统计选项](../configs/m4_statistics_exploratory.json)列明全部候选。ROPE 使用独立评价模型：μ~Normal(0,0.1²)，σ²~InverseGamma(shape=2, scale=0.01)，δ=0.02；它是可运行的探索性候选，不是团队已批准的正式先验。数值积分记录收敛状态；采用 A5 必须显式给出四项参数。先验敏感性应使用另一个明确 options 文件和新 run ID。

Friedman 及21对事后比较分别在每个场景计算，Holm 只控制对应场景的21对探索比较，不声称控制跨两场景42对的同一比较族。学习器内部先验与这套差值评价先验不同。

## 4. 输出、解释与失败处理

统一写入 `outputs/development/<run_id>/`，由 Git 忽略：

- `config/experiment_plan.json` 或 `analysis_plan.json`：预设、数据范围、配置和先验；`config/code/` 保存本次实际代码快照及环境版本。
- `audit/source.json`、源 manifest 副本与对话 gzip：来源及默认数据；E7 另保存每个环境变体的对话。
- `variants/<id>/config.json`、`truth_checks.json`：变体改变项、固定基线与独立真值检查。
- `variants/<id>/tables/`：完整四臂表、回放、对话指标、主次/直接比较、效用分解、选择/拟合诊断及算法 seed 波动。
- `variants/<id>/temporal/`：阶段、题型、窗口、累计差与选臂比例。E5 另有 `aliases/` 的问题/证据别名标记、子组与配对结果。
- `tables/variant_effects.csv` 和 `variant_dialogue_differences.csv`：变体相对默认的配对比较。E2 与移除组件使用“默认−消融”；其他参数用“变体−默认”，文件显式记录方向。
- `fixed_trajectory_rescoring.csv`：E4 固定轨迹换评分；它不代表新 λ 下重新选择的策略。
- `statistics/` 与 `oracle/`：可选数学分析。仅 `analyze` 时这些表位于顶层 `tables/`。
- `manifest.json`：所有文件哈希、运行范围、`computed_pending_review` 或 `failed`。失败保留已完成变体及 `failure.json`，不自动删行、换 seed 或覆盖重跑。

各变体内的“primary_effects”沿用 E1 表结构，但此入口所有输出都是开发/fixture 探索结果，不自动成为新增正式主检验。固定基线仅由默认开发表选定，λ、检索或环境变化时仍保留同一参照，避免变体内重新挑选有利基线。

`selector_diagnostics` 的 `trajectory_seconds` 在四个臂记录中重复，汇总时每条 `(scenario, seed, method, alg_seed)` 只取一次；`refit_seconds` 按臂记录，可求和。耗时是本机诊断，不计入效用，也不代表真实 LLM 时延。

E7 在不同设置中预先共用 seed，允许作配对的环境设置比较；生成器分支不同可能改变后续随机数消耗，不能解释成严格固定事实历史的纯需求干预。缺题型/别名子组保留 NaN 与0题；不足两条有效对话时不计算区间。

## 5. 验证范围

```powershell
python -m unittest discover -s scripts -p 'test_m4*.py'
python scripts/validate_release.py
```

新增测试覆盖默认等价、特征/组件隔离、每臂拟合计数、真实四臂与在线状态对账、阶段手算、缺组、oracle 差距、统计退化与先验积分、来源缺失/篡改、正式种子拒绝和失败目录保留。Windows 临时卷若不支持原子替换，可将 `TEMP`、`TMP` 指向工作区的 `outputs/test_tmp` 后重试。

本次101项测试通过（原有47项及新增54项），工作本结构检查通过。E0–E7、可选预算及A类分析共35个短对话配置完成端到端检查；另用完整6条开发对话验证默认回放一致，并对现有12条demo完成E3/A只读分析。归档位置、源码哈希、样本量和实际状态见 [验证记录](../deliverables/M4_stage_code_verification_20261126.json)。同一批fixture被多次重放不增加独立对话数。

发布记录基于 PR #7 的提交 `4cdbc377`，包含继承的 LF 源码和上游导出网格校验；35个配置、完整开发回放以及demo分析均在本发布分支重新验证。此前[原工作区验证](../deliverables/M4_stage_workspace_verification_20261126.json)按原字节单独保存，其源码哈希及“42项准备包文件”描述的是当时的工作区，不能用于校验当前继承的44项发布准备包。两个版本的来源和验证范围分别记录。

此前短对话验证只说明代码能够按设计运行。本轮已另行完成E0/E2/E4–E7（含E5d）的32个完整开发配置，核验复用1个已有完整E1配置，另对其进行E3/A只读分析；结果均待研究审阅，不能替代正式推断。完整 demo 的五项已有回归依赖单独共享的 `outputs` 归档，干净克隆缺少时会跳过。当前正式准备包和正式登记不因新增代码而更新或获得批准。

## 6. 完整开发实验记录（2026-11-26）

执行代码为PR #8提交`afc8015`。33个配置执行记录含1个已有E1复用，共26种不同参数设置；E3和A为两项只读分析。每场景3条、每条300题，所有归档均为`fixture=false`、`formal_generated=false`。完整结果、每项实验的解释和实际run ID见[结果文档](EXPERIMENT_RESULTS_DEVELOPMENT_20261126.md)，配置与哈希见[验证记录](../deliverables/M4_full_development_20261126/verification.json)。

E7在10种非默认生成设置下重新生成的开发对话继续使用6个既有开发seed；它们不等于60条独立正式样本。运行前后核验正式准备包、绑定源码和空登记均未改动，未写批准或冻结。既有101项代码测试与35个短配置记录保留为此前代码验证；本轮记录的是完整开发计算、来源校验和结果独立重算，不声称重新运行了该测试套件。
