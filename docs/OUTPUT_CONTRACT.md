# 输出与接口契约（导出、校验及统计代码待成员实现）
当前没有完成run。本页规定交接格式，不提供答案实现。

## 路径
统一outputs/<mode>/<run_id>/，mode为development/demo/formal；子目录data/tables/audit/config/figures/reports。第0节提供init_run创建六个目录和config/environment.json；artifact_path统一取路径；save_json/save_csv统一UTF-8并拒绝覆盖。专用序列化、研究计算和manifest生成仍由成员实现。development/demo同环境可重复初始化，formal只允许新目录；失败记录保留。默认outputs/development/local_setup仅用于首次配置。M5读取明确SOURCE_RUN，不初始化或改写M4的上游目录。

开发可各自run，交接注明上游run。M4集成时核对协议一致，不混拼不同配置的表。fixtures标为测试，不归入真实结果。

## 输入与表
episode含seed(int)、scenario、history、probes。message含id(0起连续)/text；probe含t(0起)、question、end(历史截断)、gold、evidence(最新证据id)、old_values(list)、qtype(recent/historical)、state(A/B)。

public_view只有question/history；select_context返回预算内且id唯一升序的消息。choose(q,costs)返回ARMS索引；update(k,y,q)仅更新已选反馈。新对话重置学习器。

四臂评价列：seed,scenario,t,arm,question,y,cost,utility,coverage,outdated,construction_ms,qtype,state。唯一键seed/t/arm。
回放列：seed,scenario,t,method,alg_seed,arm,y,cost,utility,coverage,outdated。唯一键seed/t/method/alg_seed。
对话指标列：scenario,seed,method,y,cost,utility,coverage,outdated。唯一键scenario/seed/method。
效应列：scenario,method,baseline,n,effect,low,high,family_low,family_high。n是对话数；low/high为95%，family_*为两主比较97.5%；次比较属探索。

y为0/1；C包含共同指令、上下文、问题；U=y−0.5C/512；coverage为最新证据入选；outdated为回答过期值。指标实现与区别由成员研究/验证。

## 文件清单
| 负责人 | 相对run根目录的文件 | 用途 |
|---|---|---|
| 公共设施 | config/environment.json | 第0节自动记录Python/依赖/内核路径；仅初始化状态 |
| M1 | data/development_dialogues.jsonl.gz | 一行一episode，M2输入 |
| M1 | audit/data_dictionary.json、audit/truth_checks.json、tables/development_data_profile.csv | 字段、独立核查、分布 |
| M2 | tables/development_outcomes.csv、tables/strategy_by_query.csv | 回放输入和开发选择 |
| M2/M1 | audit/audit_examples.json、audit/audit_review.csv、audit/strategy_checks.json | 10题完整证据、人工双签、策略检查 |
| M3 | audit/method_checks.json、tables/development_replay.csv | 数值/反馈核查与联调 |
| M4 | config/frozen_config.json、config/notebook_snapshot.ipynb、audit/review_snapshot.json | 测试前保存配置、无输出源码和人工证据 |
| M4 | data/evaluation_dialogues.jsonl.gz、tables/evaluation_outcomes.csv、tables/replay.csv | 同run数据与回放 |
| M4 | tables/episode_metrics.csv、tables/primary_effects.csv、tables/secondary_effects.csv、tables/method_summary.csv | 聚合、主次区间、完整对照 |
| M4 | reports/M4_handoff.md、manifest.json | 实际判断与完整性/来源 |
| M5 | figures/<figure_id>.png/.svg、tables/figure_<figure_id>.csv | 自己设计的图和对应表 |
| M5 | reports/figure_interpretations.md、reports/figure_manifest.json | 逐图判断与来源 |

审计CSV最低列：seed,t,m1_reviewer,m2_reviewer,verdict,m1_notes,m2_notes。起始pending，真实审查后pass/fail，不能自动署名。

M4实现manifest生成：mode/run_id/config/code_sha256、各类seeds、包版本、规模、status、files(相对路径→SHA256)、审查来源。manifest不能将自己纳入自校验哈希，仅实际完整验收后标complete。

M5自己实现校验，拒绝缺文件、改表、模式混用、样本不一致；figure_manifest记录上游manifest哈希、图表代码版本、图/表清单。M5不改M4表或manifest，重绘用新figure_id或render子目录并记录实际提交版本。

team_workspace和deliverables为人工协作/研究记录，进入Git；run另行共享，提供完整目录、commit、链接和校验和。旧参考实现或输出不能充当本组已完成证据。
