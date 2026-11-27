# ARIN7101 · 小组研究任务工作本
**[Release Notebook](ARIN7101_Context_Bandit_Release_Notebook.ipynb) 是任务脚手架，项目代码与结果评估由成员自行完成。** 第0节提供环境检查、统一目录初始化与通用保存工具。M3开发回放和核查见[交接记录](deliverables/M3_notes.md)。

目标：受控合成长对话中的贝叶斯上下文选择，研究正确性与输入成本取舍。无需真实LLM、外部数据或API密钥。

当前进度见 [2026-11-26 项目进度报告](project_progress_11.26.md)：M1–M3 核心实现和开发验证已完成；M4 已完成各阶段完整开发计算、E1 demo分析及60条正式实验准备，尚待人工确认、冻结和正式运行；M5 接口及最终汇报待交付。[成员进度表](team_workspace/team_progress.csv) · [正式实验人工确认清单](deliverables/m4_formal_preparation_20261126/HUMAN_CONFIRMATION.md)

## 从哪里开始
1. 读notebook共同范围与本人的M1–M5任务区间，在team_workspace/team_progress.csv认领。
2. 在deliverables/Mx_notes.md写自己的理解、实现计划与测试设计，用自建微型案例开始编码。
3. 按[协作流程](docs/TEAM_WORKFLOW.md)交付代码、测试、解释与证据，由接收人复核。
4. 上游未完成时使用标为fixture的小输入独立工作；M4集成、冻结后才运行正式数据。

Python 3.11/3.12，建立环境：
    python -m venv .venv

PowerShell激活：.\.venv\Scripts\Activate.ps1；macOS/Linux：source .venv/bin/activate。也可直接用环境里的Python。随后执行：

    python -m pip install -r requirements.txt
    python -m ipykernel install --user --name arin7101 --display-name "Python 3 (ARIN7101)"
    python -m jupyter lab

打开release并选择该环境内核，依次运行“0 · 环境配置及路径约定”的两个代码单元。它会检查/补装requirements依赖（安装后须重启内核）、建立outputs的三个模式分区及本次run的六个目录，保存config/environment.json，并显示所有路径。默认MODE=development、RUN_ID=local_setup；实际实验换明确RUN_ID。重复初始化不覆盖文件，formal目录不允许复用。公共save_json/save_csv提供统一编码与防覆盖。之后成员再完成自己的研究接口与测试，未实现接口仍会报NotImplementedError。

## 责任区间
| 成员 | 自己实现与研究 | 接收人 |
|---|---|---|
| M1 / m1-* | 生成器、公开信息、真值核查与诊断 | M2/M4 |
| M2 / m2-* | 四策略、回答器、成本、评价、反例 | M1/M3/M4 |
| M3 / m3-* | TS/CTS、特征、后验核查、回放 | M4 |
| M4 / m4-* | 开发选择、冻结、调度、统计、归档 | M3复核/M5 |
| M5 / m5-* | 读取校验、可视化编码、解释、汇报 | 全组 |

研究目标和接口界定边界；实现、测试案例、实验评估与结论不提供答案。各模块有步骤、输入输出、研究问题和验收方向。

## 目录与产物
- 根目录release：唯一工作本，提交Git前清输出。
- docs：协作、输出契约、脚手架检查范围；docs/proposal保留原计划背景，旧流程以当前文档为准。
- team_workspace：人工进度、接口决策、正式尝试登记。
- deliverables：个人研究记录、slides、提交清单；视频用链接。
- scripts：清输出、结构/接口测试，以及 M4 开发探索、E1 分析、正式准备和冻结/运行工具；用法见 [M4 工作流](docs/M4_FORMAL_WORKFLOW.md)。
- reference：原始可行性完整本，以及应要求保留的修改前完整release（ARIN7101_Context_Bandit_Release_v1_Complete_Reference.ipynb）；当前工作本不导入或执行。借鉴须注明来源和自己的理解/验证，复制运行不是个人贡献。
- outputs/<mode>/<run_id>：第0节初始化data/tables/audit/config/figures/reports分区和环境记录，研究文件由成员实现后生成，Git忽略。详见[输出契约](docs/OUTPUT_CONTRACT.md)。

当前 M4 已有开发/demo 结果和正式准备包；完整运行数据位于被 Git 忽略的 outputs 目录，需另行共享归档。M5 制图与独立评估仍待实现。

## 提交检查
    python scripts/clean_notebook.py
    python scripts/validate_release.py

环境和路径工具的测试（在临时目录执行，不修改团队记录）：

    python scripts/test_setup.py

检查只验证格式、语法、任务分区、空输出，并报告待实现函数数量，**不证明算法正确或实验通过**。初始骨架可加 --expect-scaffold；成员开始实现后无需该选项通过。

成员分支只改本人cell/说明；公共接口变化写team_workspace/interface_decisions.md并通知下游，M4顺序合并。Git提交源码和人工证据；完整run另行共享，登记commit/地址/校验和。

[变更说明](docs/RELEASE_NOTES.md) · [历史脚手架验证范围](docs/VALIDATION.md) · [当前进度与验证证据](project_progress_11.26.md)。成员最终验收、正式结果和最终汇报仍待小组完成。

## M1–M3 接入自检（试用）

运行 `python scripts/test_member_handoff.py --member all`，或指定 `m1`、`m2`、`m3`。说明与限制见 [接入自检手册](docs/MEMBER_SMOKE_TESTS.md)。通过仅代表小型接口检查，不代替研究验证和人工验收。

## 研究方法调研

见 [调研文档库](docs/research/README.md)，包括 TS/CTS 效果、成本与统计不确定性的数学测评方法。

具体实验测什么、控制什么、如何解释结果，见 [实验设计与数学评估说明](docs/EXPERIMENT_DESIGN.md)。

分阶段代码入口、短对话检查、完整开发实验与已有归档分析命令，见 [实验代码运行说明](docs/EXPERIMENT_EXECUTION.md)。新入口不启动正式实验。

完整开发实验E0–E7（含预算）及A1–A7的计算与归档已完成，见[逐项结果与解释](docs/EXPERIMENT_RESULTS_DEVELOPMENT_20261126.md)。每场景3条已见开发对话，结果待研究审阅；60条正式实验仍未启动。
