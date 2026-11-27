"""Prepare an unsigned E1 formal package; never generate formal dialogues."""
import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from m4_protocol import (analysis_specification, canonical_hash, digest, write_new,
                         validate_evidence, validate_machine_plan, validate_plan)
from m4_seed_inventory import collect_seed_inventory
from run_m4_formal import code_paths, build_analysis_artifacts
from test_member_handoff import ROOT, load

MEMBERS = ['M1', 'M2', 'M3', 'M4', 'M5']
EVIDENCE_NAMES = ['audit_review', 'truth_checks', 'strategy_checks', 'method_checks',
                  'development_outcomes', 'development_provenance', 'approvals']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def put_json(path, value):
    """Replace generated draft/readiness files, never human approval records."""
    if Path(path).name == 'approvals.json':
        raise ValueError('This preparer does not write human approvals')
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def evidence_paths(package):
    return {key: (package / relative).resolve() for key, relative in read_json(package / 'evidence.json').items()}


def approval_bindings(package):
    plan = read_json(package / 'plan.json')
    evidence = evidence_paths(package)
    return dict(plan_sha256=canonical_hash(plan),
                code_sha256={key: digest(path) for key, path in code_paths().items()},
                evidence_sha256={key: digest(path) for key, path in evidence.items() if key != 'approvals'})


def write_manifest(package):
    files = {p.relative_to(package).as_posix(): digest(p) for p in sorted(package.rglob('*'))
             if p.is_file() and p.name != 'package_manifest.json'}
    put_json(package / 'package_manifest.json', dict(status='prepared_not_frozen',
        formal_generated=False, human_approval_generated=False, files=files))


def preflight(package):
    plan, evidence = read_json(package / 'plan.json'), evidence_paths(package)
    technical_errors = []
    try:
        validate_machine_plan(plan, evidence, code_paths())
        snapshots = read_json(package / 'code_snapshot_hashes.json')
        for name, path in code_paths().items():
            if digest(path) != snapshots[name] or digest(package / 'code' / name) != snapshots[name]:
                raise ValueError('Prepared code snapshot differs: ' + name)
        if approval_bindings(package) != read_json(package / 'approval_request.json'):
            raise ValueError('Approval request is stale; refresh after evidence/plan edits')
        registry = read_json(ROOT / 'team_workspace/formal_runs.json')
        used = {s for event in registry for s in event.get('evaluation_seeds', [])}
        candidates = {s for group in plan['evaluation_seeds'].values() for s in group}
        if used & candidates:
            raise ValueError('Candidate seeds now appear in formal attempt registry')
        disclosure = package / 'seed_disclosure.json'
        if disclosure.exists():
            entries = read_json(disclosure).get('members', {})
            for member, entry in entries.items():
                additional = entry.get('additional_dialogue_seeds', [])
                if not isinstance(additional, list) or any(type(s) is not int or s < 0 for s in additional):
                    raise ValueError('Invalid disclosure worksheet: ' + member)
                if not set(additional).issubset(plan['used_seeds']):
                    raise ValueError('Disclosure worksheet has unbound seeds; refresh before approval')
                if evidence['approvals'].exists():
                    signed = read_json(evidence['approvals']).get('members', {}).get(member, {})
                    if set(additional) != set(signed.get('additional_dialogue_seeds', [])):
                        raise ValueError('Worksheet differs from signed member disclosure: ' + member)
    except Exception as exc:
        technical_errors.append(str(exc))
    review = pd.read_csv(evidence['audit_review'], keep_default_na=False)
    pending = review.loc[review.verdict.ne('pass'), ['seed', 't', 'verdict']].to_dict('records')
    missing = []
    if pending:
        missing.append(dict(owner='M1/M2', file='audit_review.csv',
            requirement='Confirm existing reviewer notes and complete ten joint verdicts; do not batch-approve unresolved rows',
            pending_rows=pending))
    approval = read_json(evidence['approvals']) if evidence['approvals'].exists() else {}
    if approval.get('m3_statistics_reviewed') is not True:
        missing.append(dict(owner='M3', file='approvals.json', field='m3_statistics_reviewed',
                            requirement='Review aggregation, primary family and supplemental intervals'))
    if approval.get('all_used_seeds_disclosed') is not True:
        missing.append(dict(owner='M1-M5', file='approvals.json', field='all_used_seeds_disclosed',
                            requirement='Disclose unshared local/history/failed-run dialogue seeds or confirm no additions'))
    for member in MEMBERS:
        entry = approval.get('members', {}).get(member, {})
        if entry.get('approved') is not True or not entry.get('name') or not entry.get('date'):
            missing.append(dict(owner=member, file='approvals.json', field='members.' + member,
                                requirement='Real name, ISO date and approval of the exact bound package'))
        if entry.get('seeds_disclosed') is not True:
            missing.append(dict(owner=member, file='approvals.json', field='members.' + member + '.seeds_disclosed',
                                requirement='Individual complete disclosure, including additional_dialogue_seeds or an empty list'))
    if not evidence['approvals'].exists():
        missing.append(dict(owner='M1-M5', file='approvals.json', requirement='No signed approval file exists; template is unsigned'))
    approved = False
    validation_message = None
    if not technical_errors:
        try:
            validate_plan(plan, evidence, code_paths())
            approved = True
        except Exception as exc:
            validation_message = str(exc)
    result = dict(status='ready_for_freeze' if approved else 'prepared_pending_human_confirmation',
        technical_checks_passed=not technical_errors, technical_errors=technical_errors,
        formal_generated=False, frozen=False, approved_for_execution=approved,
        evaluation_seeds=plan['evaluation_seeds'], expected_counts=plan['expected_counts'],
        human_missing=missing, full_protocol_validation=validation_message)
    put_json(package / 'readiness.json', result)
    write_manifest(package)
    return result


def refresh(package):
    """Rebind edited draft inputs before any real member signs."""
    if (package / 'approvals.json').exists():
        raise ValueError('Real approvals already exist; preserve them and prepare a new version before rebinding')
    plan = read_json(package / 'plan.json')
    disclosure = package / 'seed_disclosure.json'
    if disclosure.exists():
        additional = []
        for entry in read_json(disclosure).get('members', {}).values():
            values = entry.get('additional_dialogue_seeds', [])
            if not isinstance(values, list) or any(type(v) is not int or v < 0 for v in values):
                raise ValueError('Additional dialogue seeds must be nonnegative integers')
            additional.extend(values)
        plan['used_seeds'] = sorted(set(plan['used_seeds']) | set(additional))
        if set(additional) & {s for group in plan['evaluation_seeds'].values() for s in group}:
            raise ValueError('New disclosure collides with candidates; choose a new package/version before approval')
        put_json(package / 'plan.json', plan)
    validate_machine_plan(plan, evidence_paths(package), code_paths())
    bindings = approval_bindings(package)
    put_json(package / 'approval_request.json', bindings)
    entries = read_json(disclosure).get('members', {}) if disclosure.exists() else {}
    put_json(package / 'approvals.template.json', dict(bindings,
        members={member: dict(name='', date='', approved=False, seeds_disclosed=False,
            additional_dialogue_seeds=entries.get(member, {}).get('additional_dialogue_seeds', [])) for member in MEMBERS},
        m3_statistics_reviewed=False, all_used_seeds_disclosed=False))
    return preflight(package)


def verify_source(source):
    manifest = read_json(source / 'manifest.json')
    for name, expected in manifest['files'].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or digest(path) != expected:
            raise ValueError('Source evidence hash mismatch: ' + name)
    required = {'notebook_snapshot.ipynb', 'development_outcomes.csv', 'plan_draft.json',
                'audit_review.csv', 'M1_review.md', 'development_provenance.json',
                'truth_checks.json', 'strategy_checks.json', 'method_checks.json'}
    if not required.issubset(manifest['files']):
        raise ValueError('Source manifest does not bind required evidence')
    def source_cells(path):
        return {c['id']: ''.join(c['source']) for c in read_json(path)['cells']
                if c['cell_type'] == 'code' and (c.get('id') == 'shared-protocol-draft'
                    or c.get('id', '').startswith(('m1-', 'm2-', 'm3-')))}
    before, after = source_cells(source / 'notebook_snapshot.ipynb'), source_cells(code_paths()['notebook'])
    if before != after:
        raise ValueError('M1-M3/shared source changed; regenerate upstream evidence instead of rebinding')
    return sorted(after)


def human_instructions(package, plan):
    review = pd.read_csv(package / 'audit_review.csv', keep_default_na=False)
    rows = '\n'.join(f"| {row.seed}/{row.t} | {row.m1_reviewer} | {row.m2_reviewer} | {row.verdict} |"
                     for row in review.itertuples())
    relative = package.relative_to(ROOT).as_posix()
    return f'''# 60条正式实验：人工确认清单

当前为待确认冻结草案，未冻结、未生成正式对话、未写入正式尝试登记。机器检查结果见readiness.json；批准对象哈希见approval_request.json。

## 已准备好的方案

- stable种子：{plan['evaluation_seeds']['stable'][0]}–{plan['evaluation_seeds']['stable'][-1]}；abrupt：{plan['evaluation_seeds']['abrupt'][0]}–{plan['evaluation_seeds']['abrupt'][-1]}，各30条、每条300题。
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
{rows}

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
python scripts/prepare_m4_formal.py refresh --package {relative}
python scripts/prepare_m4_formal.py preflight --package {relative}
```

只有真实确认齐备、preflight显示ready_for_freeze后，才执行冻结。以下命令已准备但本轮没有执行：

```powershell
python scripts/run_m4_formal.py freeze --plan {relative}/plan.json --evidence {relative}/evidence.json --destination outputs/frozen/m4_e1_20261126_v1
python scripts/run_m4_formal.py run --frozen outputs/frozen/m4_e1_20261126_v1 --run-id m4_e1_formal_20261126_v1
```

冻结及正式run目录均不可复用。开始前登记started，计算后仍为computed_pending_review，随后由M3/M5核验。不要手动补写已发生之外的正式登记。
'''


def prepare(package, source):
    checked_cells = verify_source(source)
    inventory = collect_seed_inventory(ROOT)
    if inventory['collisions'] or inventory.get('scan_errors'):
        raise ValueError('Resolve candidate collisions or inventory scan errors first')
    package.mkdir(parents=True, exist_ok=False)
    registry_before = digest(ROOT / 'team_workspace/formal_runs.json')
    try:
        for folder in ['code', 'source_evidence', 'validation_tables', 'technical_sources']:
            (package / folder).mkdir()
        for name in ['manifest.json', 'notebook_snapshot.ipynb', 'development_provenance.json',
                     'truth_checks.json', 'strategy_checks.json', 'method_checks.json']:
            shutil.copyfile(source / name, package / 'source_evidence' / name)
        for name in ['development_outcomes.csv', 'audit_review.csv', 'M1_review.md']:
            shutil.copyfile(source / name, package / name)
        shutil.copyfile(ROOT / 'team_workspace/m2_handoff/audit_examples.json', package / 'audit_examples.json')
        notebook = code_paths()['notebook']
        ns = load(notebook, 'm2')
        ns.update(load(notebook, 'm3'))
        cfg = dict(ns['PROTOCOL_DRAFT'])
        original_cfg = read_json(source / 'plan_draft.json')['config']
        if cfg != original_cfg:
            raise ValueError('Original/current protocol differs before formal metadata is assigned')
        cfg['formal_seed'] = inventory['candidate_seeds']['stable'][0]
        nb = read_json(notebook)
        ns['display'] = lambda *args: None
        for cell in nb['cells']:
            if cell.get('id') in ['m2-checks-workspace', 'm2-isolation-and-version-checks', 'm4-experiment-skeleton']:
                exec(''.join(cell['source']), ns)
        outcomes = pd.read_csv(package / 'development_outcomes.csv')
        episodes = [ns['generate_episode'](int(seed), scenario, cfg)
                    for scenario, seed in outcomes[['scenario', 'seed']].drop_duplicates().itertuples(index=False)]
        truth = [ns['audit_truth'](episode) for episode in episodes]
        if not all(check['passed'] for check in truth):
            raise ValueError('Development truth audit failed')
        ns['m2_validate_development_outcomes'](episodes, outcomes, cfg)
        examples = ns['m2_build_audit_examples'](episodes, outcomes, cfg, ns['M2_DEVELOPMENT_AUDIT_KEYS'])
        if examples != read_json(package / 'audit_examples.json')['questions']:
            raise ValueError('Rebuilt forty audit arms differ from original evidence')
        print('Six existing development dialogues and forty audit arms revalidated.', flush=True)
        method, method_replay = ns['run_m3_method_checks'](outcomes[outcomes.seed == 130100].copy(), cfg)
        method['source'] = dict(seed=130100, scenario='abrupt', rows=1200)
        method_replay.to_csv(package / 'validation_tables/method_check_replay.csv', index=False)
        binding = dict(config_sha256=canonical_hash(cfg), notebook_sha256=digest(notebook),
                       development_sha256=digest(package / 'development_outcomes.csv'))
        provenance = dict(binding, mode='revalidated_existing_development',
            original_manifest_sha256=digest(source / 'manifest.json'),
            original_notebook_sha256=digest(source / 'notebook_snapshot.ipynb'),
            original_config_sha256=canonical_hash(original_cfg),
            compatible_code_cells=checked_cells,
            metadata_only_config_change=dict(formal_seed=dict(before=None, after=cfg['formal_seed'])),
            reused='Full four-arm outcomes and construction_ms; no full TF-IDF recomputation',
            rerun='Six existing development truth audits, M2 fixtures/full-table validation/40-arm reconstruction, M3 checks')
        write_new(package / 'development_provenance.json', provenance)
        strategy = dict(fixture_checks=ns['M2_CHECKS'], development_checks=dict.fromkeys([
            'unique_keys_four_arms_and_matching_metadata', 'cost_count_and_utility_consistency',
            'm1_independent_truth_audit', 'audit_coverage_and_reconstruction_match_outcomes'], 'pass'),
            row_counts=dict(outcomes=len(outcomes)))
        for name, payload in [('truth_checks', truth), ('strategy_checks', strategy), ('method_checks', method)]:
            write_new(package / (name + '.json'), dict(binding, status='passed', payload=payload))
        plan = dict(config=cfg, baselines=ns['choose_fixed_baselines'](outcomes),
            evaluation_seeds=inventory['candidate_seeds'], used_seeds=inventory['known_used_seeds'],
            seed_inventory=inventory, analysis_spec=analysis_specification(),
            expected_counts=dict(dialogues=60, questions=18000, outcomes=72000, replay=252000, episode_metrics=420),
            seed_status='reserved_candidates_not_generated_pending_full_team_disclosure',
            formal_seed_semantics='legacy stable base; evaluation_seeds lists are authoritative')
        write_new(package / 'plan.json', plan)
        write_new(package / 'seed_inventory.json', inventory)
        evidence = {name: name + ('.csv' if name in ['audit_review', 'development_outcomes'] else '.json')
                    for name in EVIDENCE_NAMES}
        write_new(package / 'evidence.json', evidence)
        validate_evidence(plan, evidence_paths(package), code_paths())
        # Exercise the real formal analysis builder on already-viewed demo tables.
        demo = ROOT / 'outputs/demo/m4_e1_demo_20261126'
        demo_manifest = read_json(demo / 'manifest.json')
        for name, expected in demo_manifest['files'].items():
            if digest(demo / name) != expected:
                raise ValueError('Demo validation source hash mismatch')
        demo_out = pd.read_csv(demo / 'tables/evaluation_outcomes.csv')
        demo_replay = pd.read_csv(demo / 'tables/replay.csv')
        expected_demo = {sc: sorted(map(int, demo_out.loc[demo_out.scenario == sc, 'seed'].unique()))
                         for sc in ['stable', 'abrupt']}
        artifacts = build_analysis_artifacts(ns, demo_out, demo_replay, plan['baselines'], cfg, expected_demo)
        for name, frame in artifacts.items():
            if isinstance(frame, pd.DataFrame) and name not in ['tables/evaluation_outcomes.csv', 'tables/replay.csv']:
                frame.to_csv(package / 'validation_tables' / Path(name).name, index=False)
        for name in ['primary_effects', 'secondary_effects']:
            pd.testing.assert_frame_equal(artifacts['tables/' + name + '.csv'],
                pd.read_csv(demo / 'tables' / (name + '.csv')), check_exact=False, rtol=0, atol=1e-12)
        write_new(package / 'technical_checks.json', dict(status='passed', formal_generated=False,
            development_rows=len(outcomes), truth_questions=sum(x['question_count'] for x in truth),
            fixture_count=len(ns['M2_CHECKS']), rebuilt_audit_arms=40, method_replay_rows=len(method_replay),
            formal_analysis_test_source=str(demo), formal_analysis_demo_dialogues=12,
            old_primary_secondary_reproduced=True, code_compatibility_cells=len(checked_cells),
            original_source_manifest_sha256=digest(source / 'manifest.json')))
        for name, path in code_paths().items():
            shutil.copyfile(path, package / 'code' / name)
        for name in ['prepare_m4_formal.py', 'm4_seed_inventory.py']:
            shutil.copyfile(ROOT / 'scripts' / name, package / 'technical_sources' / name)
        write_new(package / 'code_snapshot_hashes.json', {name: digest(path) for name, path in code_paths().items()})
        write_new(package / 'seed_disclosure.template.json', dict(
            instructions='Each member confirms visible inventory and adds unshared dialogue seeds; empty additions require an explicit complete confirmation.',
            members={name: dict(name='', date='', confirmed_complete=False, additional_dialogue_seeds=[], notes='') for name in MEMBERS}))
        checks = ['dialogue_unit_and_seed_averaging', 'development_only_baseline', 'two_primary_comparisons_95_and_975',
                  'direct_comparisons_exploratory_95', 'accuracy_cost_decomposition', 'practical_threshold_002',
                  'failures_negative_results_and_no_equivalence_from_nonsignificance']
        write_new(package / 'statistics_review.template.json', dict(member='M3', name='', date='',
            checks={name: False for name in checks}, confirmed=False, notes=''))
        (package / 'HUMAN_CONFIRMATION.md').write_text(human_instructions(package, plan), encoding='utf-8')
        result = refresh(package)
        if digest(ROOT / 'team_workspace/formal_runs.json') != registry_before:
            raise ValueError('Formal registry changed during preparation')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('Unsigned preparation:', package)
    except BaseException as exc:
        put_json(package / 'preparation_failure.json', dict(type=type(exc).__name__, message=str(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('prepare')
    create.add_argument('--destination', type=Path, default=ROOT / 'deliverables/m4_formal_preparation_20261126')
    create.add_argument('--source-evidence', type=Path, default=ROOT / 'outputs/development/m4_evidence_20261126_v2')
    for name in ['preflight', 'refresh']:
        sub.add_parser(name).add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.destination.resolve(), args.source_evidence.resolve())
    else:
        package = args.package.resolve()
        result = preflight(package) if args.command == 'preflight' else refresh(package)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
