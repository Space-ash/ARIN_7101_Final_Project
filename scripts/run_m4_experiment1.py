"""Rerun E1 on verified, previously viewed development/demo data; no formal generation."""
import argparse
import gzip
import json
import platform
import subprocess
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from m4_analysis import (ARMS, METHODS, SCENARIOS, METRICS, aggregate_dialogues,
                         paired_comparisons, validate_outcomes, validate_replay)
from m4_protocol import digest, write_new
from test_member_handoff import ROOT, load


def verified_archive(root):
    root = root.resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('mode') not in ('development', 'demo') or manifest.get('fixture', False):
        raise ValueError('E1 accepts full-size development/demo archives only')
    if not manifest.get('files'):
        raise ValueError('Missing source archive file hashes')
    required = {'config/notebook_snapshot.ipynb', 'config/loader_snapshot.py'}
    if manifest['mode'] == 'development':
        required.update({'data/development_dialogues.jsonl.gz',
                         'tables/development_outcomes.csv', 'tables/development_replay.csv'})
    else:
        required.update({'data/evaluation_dialogues.jsonl.gz',
                         'tables/evaluation_outcomes.csv', 'tables/replay.csv'})
    if not required.issubset(manifest['files']):
        raise ValueError('Source manifest does not bind all consumed input files')
    for relative, expected in manifest['files'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path == root or digest(path) != expected:
            raise ValueError('Unsafe path or archive hash mismatch: ' + relative)
    return manifest


def compatible_source(source, manifest, notebook):
    snapshot = source / 'config/notebook_snapshot.ipynb'
    if digest(snapshot) != manifest['code_sha256']:
        raise ValueError('Source notebook hash does not match manifest')
    def selected(path):
        cells = json.loads(path.read_text(encoding='utf-8'))['cells']
        return {c['id']: ''.join(c['source']) for c in cells if c['cell_type'] == 'code'
                and (c.get('id') == 'shared-protocol-draft' or c.get('id', '').startswith(('m1-', 'm2-', 'm3-')))}
    before, current = selected(snapshot), selected(notebook)
    if before != current:
        raise ValueError('M1/M2/M3 or shared protocol changed; regenerate source outcomes')
    if digest(source / 'config/loader_snapshot.py') != digest(ROOT / 'scripts/test_member_handoff.py'):
        raise ValueError('Notebook loader differs from source run')
    return sorted(current)


def read_episodes(source, mode, cfg, ns):
    filename = 'development_dialogues.jsonl.gz' if mode == 'development' else 'evaluation_dialogues.jsonl.gz'
    with gzip.open(source / 'data' / filename, 'rt', encoding='utf-8') as stream:
        episodes = [json.loads(line) for line in stream if line.strip()]
    expected_seeds = {sc: [] for sc in SCENARIOS}
    checks = []
    for episode in episodes:
        scenario, seed = episode['scenario'], episode['seed']
        if scenario not in expected_seeds or episode != ns['generate_episode'](seed, scenario, cfg):
            raise ValueError('Archived dialogue does not reproduce with current generator')
        expected_seeds[scenario].append(seed)
        check = ns['audit_truth'](episode)
        if not check['passed']:
            raise ValueError('Independent truth audit failed')
        checks.append(check)
    count = cfg['n_dev_per_scenario'] if mode == 'development' else cfg['n_demo_per_scenario']
    if any(len(seeds) != count for seeds in expected_seeds.values()):
        raise ValueError('Source dialogue count differs from configuration')
    return episodes, expected_seeds, checks, filename


def markdown_table(frame):
    def cell(value):
        return f'{value:.6f}' if isinstance(value, float) else str(value)
    lines = ['| ' + ' | '.join(frame.columns) + ' |',
             '| ' + ' | '.join('---' for _ in frame.columns) + ' |']
    lines.extend('| ' + ' | '.join(cell(v) for v in row) + ' |'
                 for row in frame.itertuples(index=False, name=None))
    return '\n'.join(lines)


def records(frame):
    return json.loads(frame.to_json(orient='records', double_precision=15))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--source-run', type=Path,
                        default=ROOT / 'outputs/demo/m4_stage2_verified_20261123')
    parser.add_argument('--development-run', type=Path,
                        default=ROOT / 'outputs/development/m4_default_benchmark_20261123')
    args = parser.parse_args()
    if not args.run_id.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Invalid run ID')
    source, development = args.source_run.resolve(), args.development_run.resolve()
    manifest, dev_manifest = verified_archive(source), verified_archive(development)
    if dev_manifest['mode'] != 'development':
        raise ValueError('Fixed baseline must come from development data')
    mode, cfg = manifest['mode'], manifest['config']
    notebook = ROOT / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb'
    checked_cells = compatible_source(source, manifest, notebook)
    compatible_source(development, dev_manifest, notebook)
    ns = load(notebook, 'm2')
    ns.update(load(notebook, 'm3'))
    cells = json.loads(notebook.read_text(encoding='utf-8'))['cells']
    exec(''.join(next(c['source'] for c in cells if c.get('id') == 'm4-experiment-skeleton')), ns)
    if cfg != dev_manifest['config'] or cfg != ns['PROTOCOL_DRAFT'] or cfg['T'] != 300:
        raise ValueError('Source/current/development configurations differ')
    run = ROOT / 'outputs' / mode / args.run_id
    evidence_path = ROOT / 'deliverables' / ('M4_E1_' + args.run_id + '.json')
    if evidence_path.exists():
        raise FileExistsError(evidence_path)
    run.mkdir(parents=True, exist_ok=False)
    try:
        write_new(run / 'config/experiment_plan.json', dict(
            experiment='E1', mode=mode, already_viewed=True, formal=False,
            source_run=str(source), source_manifest_sha256=digest(source / 'manifest.json'),
            development_run=str(development), development_manifest_sha256=digest(development / 'manifest.json'),
            config=cfg, primary='CTS minus development-selected fixed arm, one utility contrast per scenario',
            supplementary=['CTS minus TS', 'CTS minus RuleRouter', 'accuracy/cost decomposition'],
            interpretation='Exploratory verification on previously viewed data; no confirmatory inference'))
        episodes, seeds, truth, data_name = read_episodes(source, mode, cfg, ns)
        dev_episodes, dev_seeds, dev_truth, _ = read_episodes(development, 'development', cfg, ns)
        source_seed_list = manifest['seeds']['dialogue' if mode == 'development' else 'evaluation']
        if sorted(source_seed_list) != sorted(e['seed'] for e in episodes):
            raise ValueError('Source manifest seed list differs from archived dialogues')
        if sorted(dev_manifest['seeds']['dialogue']) != sorted(e['seed'] for e in dev_episodes):
            raise ValueError('Development manifest seed list differs from archived dialogues')
        if mode == 'demo' and set(source_seed_list) & set(dev_manifest['seeds']['dialogue']):
            raise ValueError('Development/demo dialogue overlap')
        dev_out = pd.read_csv(development / 'tables/development_outcomes.csv')
        out_name = 'development_outcomes.csv' if mode == 'development' else 'evaluation_outcomes.csv'
        outcomes = pd.read_csv(source / 'tables' / out_name)
        validate_outcomes(dev_out, cfg, dev_seeds)
        validate_outcomes(outcomes, cfg, seeds)
        metadata = pd.DataFrame([dict(scenario=e['scenario'], seed=e['seed'], t=p['t'],
            question=p['question'], qtype=p['qtype'], state=p['state']) for e in episodes for p in e['probes']])
        observed = outcomes[['scenario', 'seed', 't', 'question', 'qtype', 'state']].drop_duplicates()
        sort = ['scenario', 'seed', 't']
        pd.testing.assert_frame_equal(observed.sort_values(sort).reset_index(drop=True),
                                      metadata.sort_values(sort).reset_index(drop=True))
        baselines = ns['choose_fixed_baselines'](dev_out)
        if baselines != dev_manifest['baselines'] or baselines != manifest['baselines']:
            raise ValueError('Baseline does not reproduce from development source')
        replay_parts = []
        for (scenario, seed), group in outcomes.groupby(['scenario', 'seed'], sort=True):
            for method in METHODS:
                for alg in cfg['algorithm_seeds']:
                    replay_parts.append(ns['replay_episode'](group, method, alg, cfg))
            print(f'Replayed {scenario}/{seed}: seven methods, two algorithm seeds.', flush=True)
        replay = pd.concat(replay_parts, ignore_index=True)
        validate_replay(replay, outcomes, cfg)
        old_name = 'development_replay.csv' if mode == 'development' else 'replay.csv'
        old_replay = pd.read_csv(source / 'tables' / old_name)
        keys = ['scenario', 'seed', 't', 'method', 'alg_seed']
        pd.testing.assert_frame_equal(replay.sort_values(keys).reset_index(drop=True),
            old_replay.sort_values(keys).reset_index(drop=True), check_exact=False, rtol=0, atol=1e-12)
        metrics = aggregate_dialogues(replay)
        pd.testing.assert_frame_equal(metrics, ns['aggregate_dialogues'](replay))
        primary, secondary = ns['paired_effects'](metrics, baselines, cfg)
        differences, direct = paired_comparisons(metrics, baselines, cfg)
        summary = metrics.groupby(['scenario', 'method'])[METRICS].mean().reset_index()
        decomposition = differences.groupby(['scenario', 'comparison', 'reference'])[
            ['delta_' + m for m in METRICS]].mean().reset_index()
        tables = dict(evaluation_outcomes=outcomes, development_outcomes=dev_out,
            replay=replay, episode_metrics=metrics, method_summary=summary,
            primary_effects=primary, secondary_effects=secondary,
            paired_dialogue_differences=differences, direct_comparisons=direct,
            effect_decomposition=decomposition)
        for name, table in tables.items():
            path = run / 'tables' / (name + '.csv')
            path.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(path, index=False, mode='x')
        provenance = dict(source_manifest_sha256=digest(source / 'manifest.json'),
            development_manifest_sha256=digest(development / 'manifest.json'),
            compatible_code_cells=checked_cells, source_hashes_verified=True,
            current_generator_reproduced=True, current_replay_matches_archived=True,
            fixed_baseline_selected_on_development=True, formal_generated=False,
            selected_feedback_and_complete_grids='passed')
        write_new(run / 'audit/input_validation.json', provenance)
        write_new(run / 'audit/truth_checks.json', dict(evaluation=truth, development=dev_truth))
        write_new(run / 'config/environment.json', dict(python=platform.python_version(),
            packages={k: version(k) for k in ['numpy', 'pandas', 'scipy', 'scikit-learn']}))
        write_new(run / 'config/development_plan.json', dict(config=cfg, baselines=baselines, frozen=False))
        copies = {
            'config/notebook_snapshot.ipynb': notebook,
            'config/runner_snapshot.py': Path(__file__),
            'config/analysis_snapshot.py': ROOT / 'scripts/m4_analysis.py',
            'config/loader_snapshot.py': ROOT / 'scripts/test_member_handoff.py',
            'config/protocol_helpers_snapshot.py': ROOT / 'scripts/m4_protocol.py',
            'config/source_manifest.json': source / 'manifest.json',
            'config/development_manifest.json': development / 'manifest.json',
            'config/source_notebook_snapshot.ipynb': source / 'config/notebook_snapshot.ipynb',
            'config/development_notebook_snapshot.ipynb': development / 'config/notebook_snapshot.ipynb',
            'config/source_outcomes.csv': source / 'tables' / out_name,
            'config/source_development_outcomes.csv': development / 'tables/development_outcomes.csv',
            'data/' + data_name: source / 'data' / data_name,
        }
        if mode == 'demo':
            copies['data/development_dialogues.jsonl.gz'] = development / 'data/development_dialogues.jsonl.gz'
        for relative, original in copies.items():
            target = run / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(original.read_bytes())
        utility = direct[direct.metric == 'utility'][['scenario', 'reference', 'n', 'effect', 'low', 'high']]
        report = '\n\n'.join([
            '# M4 E1：七方法总体评估与直接配对比较',
            f'数据阶段：{mode}。使用已看过的序列，重新执行当前 M3；不是正式实验。',
            f'规模：{len(episodes)}条对话，每条300题；算法种子17/37；独立n为每场景{len(seeds["stable"])}。',
            '固定基线仅由开发数据选择：' + json.dumps(baselines, ensure_ascii=False),
            '开发数据与demo不合并。开发集内选择和比较共用数据；demo也已看过，所有区间仅用于探索和流程验证。',
            '## 七方法均值', markdown_table(summary),
            '## 原主比较（沿用原函数与两场景97.5%区间）', markdown_table(primary),
            '## 新增直接比较（95%探索区间，无多重比较校正）', markdown_table(utility),
            '## 配对效应分解', markdown_table(decomposition),
            'ΔU = Δaccuracy − 0.5 × Δcost / 512。五指标共用对话重采样索引；各指标区间端点不可直接相减。成本为正则长度代理。',
            '本轮没有生成新的对话种子或formal数据。正式30条/场景仍待联合审查、统计复核、种子披露与团队批准。',
            '出处及逐文件哈希见manifest；源码、输入表及来源manifest均随本次归档保留。']) + '\n'
        (run / 'reports').mkdir()
        (run / 'reports/E1_report.md').write_text(report, encoding='utf-8')
        files = {p.relative_to(run).as_posix(): digest(p) for p in sorted(run.rglob('*')) if p.is_file()}
        result = dict(experiment='E1', mode=mode, run_id=args.run_id,
            status='exploratory_complete_pending_review', formal_generated=False, already_viewed=True,
            config=cfg, baselines=baselines, provenance=provenance,
            seeds=dict(development=dev_manifest['seeds']['dialogue'], evaluation=source_seed_list,
                       algorithm=cfg['algorithm_seeds']),
            counts=dict(dialogues=len(episodes), questions=len(episodes) * cfg['T'],
                        outcomes=len(outcomes), replay=len(replay), episode_metrics=len(metrics)),
            created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
            code_sha256=digest(notebook),
            base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            working_tree_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
            files=files)
        write_new(run / 'manifest.json', result)
        for relative, expected in files.items():
            if digest(run / relative) != expected:
                raise ValueError('Output archive hash mismatch: ' + relative)
        write_new(evidence_path, dict(experiment='E1', mode=mode, status=result['status'],
            formal_generated=False, already_viewed=True, run=str(run),
            manifest_sha256=digest(run / 'manifest.json'), config=cfg, baselines=baselines,
            provenance=provenance, counts=result['counts'],
            tables={name: records(tables[name]) for name in ['method_summary', 'primary_effects',
                    'secondary_effects', 'direct_comparisons', 'effect_decomposition']}))
        print(utility.to_string(index=False))
        print('Archive:', run)
        print('Review evidence:', evidence_path)
    except BaseException as exc:
        try:
            write_new(run / 'failure.json', dict(type=type(exc).__name__, message=str(exc)))
        except Exception as record_error:
            exc.add_note('Could not persist E1 failure record: ' + str(record_error))
        raise


if __name__ == '__main__':
    main()
