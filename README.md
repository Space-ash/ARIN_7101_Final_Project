# ARIN7101 · 小组研究任务工作本
**[Release Notebook](ARIN7101_Context_Bandit_Release_Notebook.ipynb) 是任务脚手架，项目代码与结果评估由成员自行完成。** 研究函数均为待实现接口；第0节已完整实现环境检查、统一目录初始化与通用保存工具；M1–M5仍为研究骨架，不产生研究数据、统计或图，初始化不代表任务完成。

目标：受控合成长对话中的贝叶斯上下文选择，研究正确性与输入成本取舍。无需真实LLM、外部数据或API密钥。

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
- scripts：清输出、结构检查和第0节环境/路径测试工具，没有实验执行器或研究实现。
- reference：原始可行性完整本，以及应要求保留的修改前完整release（ARIN7101_Context_Bandit_Release_v1_Complete_Reference.ipynb）；当前工作本不导入或执行。借鉴须注明来源和自己的理解/验证，复制运行不是个人贡献。
- outputs/<mode>/<run_id>：第0节初始化data/tables/audit/config/figures/reports分区和环境记录，研究文件由成员实现后生成，Git忽略。详见[输出契约](docs/OUTPUT_CONTRACT.md)。

当前不附带上一版自动demo的结果、图表和源码快照。M4自行编写集成入口，M5自行实现制图与评估。

## 提交检查
    python scripts/clean_notebook.py
    python scripts/validate_release.py

环境和路径工具的测试（在临时目录执行，不修改团队记录）：

    python scripts/test_setup.py

检查只验证格式、语法、任务分区、空输出，并报告待实现函数数量，**不证明算法正确或实验通过**。初始骨架可加 --expect-scaffold；成员开始实现后无需该选项通过。

成员分支只改本人cell/说明；公共接口变化写team_workspace/interface_decisions.md并通知下游，M4顺序合并。Git提交源码和人工证据；完整run另行共享，登记commit/地址/校验和。

[变更说明](docs/RELEASE_NOTES.md) · [本次验证范围](docs/VALIDATION.md)。研究实现、成员验收、正式结果和最终汇报均待小组完成。
