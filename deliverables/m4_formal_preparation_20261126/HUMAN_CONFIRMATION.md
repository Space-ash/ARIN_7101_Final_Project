# 60条正式实验：人工确认清单

当前为待确认冻结草案，未冻结、未生成正式对话、未写入正式尝试登记。机器检查结果见readiness.json；批准对象哈希见approval_request.json。

## 已准备好的方案

- stable种子：930000–930029；abrupt：930100–930129，各30条、每条300题。
- 七方法，算法种子17/37；λ=0.5、C0=512、候选上限8、预算128/512/256/256、prior_precision=1、refit_every=5。
- 固定基线stable→recent_short、abrupt→resolved_tfidf，只用开发数据选择。
- 两场景CTS−固定臂为主比较，2,000次配对对话bootstrap、seed2026，95%及97.5%区间。CTS−TS、CTS−RuleRouter和其它指标为探索性95%区间。
- 实际意义阈值草案为效用0.02：若成本相同，相当于正确率提高2个百分点；若正确率相同，相当于每题减少20.48个长度代理单位。需要团队在看正式结果前接受；不保证当前样本量有足够功效。
- 预计18,000题、72,000行四臂结果、252,000行回放、420行对话指标；所有失败、负向及不确定结果保留。E2–E5不在本次E1正式执行范围。
- seed_inventory.json仅覆盖可见仓库/归档。不存在仓库碰撞不等于已确认所有成员未用过这些种子。

## 1. M1/M2：关闭十题联合判定

编辑本目录audit_review.csv。以下姓名和意见来自既有审查记录，不是本次自动署名。本人确认意见后逐题给出pass/fail；未解决题保留pending或fail及原因，不能为通过检查批量填pass。

| seed/t（t从0计） | 已记录M1 | 已记录M2 | 当前判定 |
|---|---|---|---|
| 130000/0 | Liu Zhuoyang | He Junchen | pending |
| 130000/2 | Liu Zhuoyang | He Junchen | pending |
| 130000/12 | Liu Zhuoyang | He Junchen | pending |
| 130001/1 | Liu Zhuoyang | He Junchen | pending |
| 130100/99 | Liu Zhuoyang | He Junchen | pending |
| 130100/149 | Liu Zhuoyang | He Junchen | pending |
| 130100/150 | Liu Zhuoyang | He Junchen | pending |
| 130100/151 | Liu Zhuoyang | He Junchen | pending |
| 130101/149 | Liu Zhuoyang | He Junchen | pending |
| 130101/299 | Liu Zhuoyang | He Junchen | pending |

参考材料：M1_review.md、audit_examples.json、development_outcomes.csv。双方审查的是公开历史边界、gold/最新证据/旧值，以及四臂上下文、回答、成本和评分。

## 2. M3：确认统计方案

可用statistics_review.template.json逐项记录，另存statistics_review.json；它是辅助工作表，最终有效确认记录在approvals.json。必须确认：独立单位是对话；先题目再算法种子平均；基线开发选择；原两个主比较及95%/97.5%区间；新增直接比较为探索；准确率/成本分解；区间跨0不是等效；效用0.02阈值；保留失败和负结果。技术回归和demo回读记录见technical_checks及validation_tables。

确认后在最终approvals.json中据实填写m3_statistics_reviewed=true。该标志不能仅因为机器测试通过就设置。

## 3. 全体成员：披露未共享的种子

每人核对seed_inventory.json，可填写seed_disclosure.template.json并另存seed_disclosure.json作为辅助工作表：姓名、日期、confirmed_complete，以及additional_dialogue_seeds。最终有效披露在approvals.json各成员记录中的seeds_disclosed与additional_dialogue_seeds；无补充也需明确确认并保留空列表。包括本地开发、demo、调参、失败和历史运行；算法种子和bootstrap种子另记，不能混入对话清单。

有补充时运行下方refresh，合并到plan.used_seeds。若与候选冲突必须更换候选并重新出版本；本脚本会拒绝冲突，不会偷偷试跑后换种子。全员完成后才能据实设置all_used_seeds_disclosed=true。

## 4. M1–M5：批准准确版本

先完成前两项材料修改及种子补充，再执行refresh。它只更新待签哈希和未签模板，不生成任何人的批准。检查plan.json、code/、七项evidence及approval_request.json后，将approvals.template.json复制为approvals.json，由各成员填写members.Mx的真实name、ISO date、approved=true、seeds_disclosed=true及additional_dialogue_seeds。程序检查披露的额外种子已全部纳入绑定的plan.used_seeds；遗漏刷新或候选冲突不能通过。M1/M2已有的审查姓名不会自动填进批准记录。

任何配置、代码、审查表或上游证据改动都会使旧批准失效。有真实approvals.json时refresh拒绝覆盖，应保留旧版本并另建新版本。审批是可追溯的人工声明，不是数字身份认证。

## 完成材料后的命令

以下检查和refresh都不会生成正式对话：

```powershell
python scripts/prepare_m4_formal.py refresh --package deliverables/m4_formal_preparation_20261126
python scripts/prepare_m4_formal.py preflight --package deliverables/m4_formal_preparation_20261126
```

只有真实确认齐备、preflight显示ready_for_freeze后，才执行冻结。以下命令已准备但本轮没有执行：

```powershell
python scripts/run_m4_formal.py freeze --plan deliverables/m4_formal_preparation_20261126/plan.json --evidence deliverables/m4_formal_preparation_20261126/evidence.json --destination outputs/frozen/m4_e1_20261126_v1
python scripts/run_m4_formal.py run --frozen outputs/frozen/m4_e1_20261126_v1 --run-id m4_e1_formal_20261126_v1
```

冻结及正式run目录均不可复用。开始前登记started，计算后仍为computed_pending_review，随后由M3/M5核验。不要手动补写已发生之外的正式登记。

## Fork PR 发布版核验

本目录在最新主分支上重新生成：保留上游导出完整性检查，执行源码统一为 LF，并在 `.gitattributes` 中保护本目录证据原始字节。此前工作区清点保存在 prior_workspace_seed_inventory.json（125 个来源）；本次隔离发布工作区清点为 62 个来源，保守排除仍为 154 个 seed。两次清点均不能替代成员私有运行披露。批准对象应以本目录最新 approval_request.json 为准。

干净克隆可直接运行 preflight 核验本包；重新 prepare 需要另行取得说明中的原始 development/demo 归档。完整 demo 回归测试也需要 outputs 中的共享归档，缺少时会跳过相关 5 项。正式对话未生成、真实审批未写入。
