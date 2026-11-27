"""Run E0-E7 development experiments or analyze an existing archive; never run formal data."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import json
from importlib.metadata import version
from pathlib import Path
import platform
import shutil
import sys

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, METRICS, aggregate_dialogues, validate_outcomes, validate_replay
from m4_experiment_plan import ROOT, NOTEBOOK, STAGES, make_plan, validate_plan
from m4_protocol import canonical_hash, digest, write_new
from m4_temporal import temporal_analysis, oracle_analysis
from m4_variants import load_namespace, configure_namespace, evaluate_episodes, replay_all
from run_m4_experiment1 import verified_archive, compatible_source, read_episodes
from run_m4_formal import build_analysis_artifacts

SOURCE_FILES = ['m4_experiment_plan.py', 'run_m4_stages.py', 'm4_variants.py', 'm4_temporal.py', 'm4_subgroups.py',
                'm4_statistics.py', 'm4_validation.py', 'm4_analysis.py', 'm4_protocol.py',
                'run_m4_formal.py', 'run_m4_experiment1.py', 'test_member_handoff.py']
EXECUTION_HASHES = {p: digest(p) for p in [NOTEBOOK, *(ROOT / 'scripts' / name for name in SOURCE_FILES)]}


def _assert_code_unchanged():
    if any(digest(path) != expected for path, expected in EXECUTION_HASHES.items()):
        raise ValueError('Source changed after runner import; restart with one consistent code version')


def _resolve(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _run_directory(run_id):
    if not isinstance(run_id, str) or not run_id.replace('_', '').replace('-', '').isalnum():
        raise ValueError('run-id must contain only letters, digits, underscores and hyphens')
    path = ROOT / 'outputs/development' / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _tables(directory, tables):
    directory.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        if not isinstance(table, pd.DataFrame):
            raise TypeError('Expected table: ' + name)
        if Path(name).name != name:
            raise ValueError('Unsafe table name')
        table.to_csv(directory / (name + '.csv'), index=False, mode='x')


def _snapshot(run):
    _assert_code_unchanged()
    destination = run / 'config/code'
    destination.mkdir(parents=True)
    shutil.copyfile(NOTEBOOK, destination / NOTEBOOK.name)
    for name in SOURCE_FILES:
        shutil.copyfile(ROOT / 'scripts' / name, destination / name)
    write_new(run / 'config/environment.json', dict(python=platform.python_version(),
        packages={name: version(name) for name in ['numpy', 'pandas', 'scipy', 'scikit-learn']}))


def _manifest(run, metadata, status):
    files = {p.relative_to(run).as_posix(): digest(p) for p in sorted(run.rglob('*'))
             if p.is_file() and p.name != 'manifest.json'}
    write_new(run / 'manifest.json', dict(metadata, status=status, mode='development',
        formal_generated=False, created_utc=datetime.now(timezone.utc).isoformat(), files=files))


def _save_episodes(path, episodes):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = '\n'.join(json.dumps(e, ensure_ascii=False, allow_nan=False) for e in episodes) + '\n'
    path.write_bytes(gzip.compress(content.encode('utf-8'), mtime=0))


def _source_inputs(plan, ns):
    cfg = plan['config']
    if plan['fixture']:
        episodes = [ns['generate_episode'](seed, scenario, cfg)
                    for scenario, seeds in plan['dialogue_seeds'].items() for seed in seeds]
        outcomes = evaluate_episodes(ns, episodes, cfg)
        return episodes, outcomes, None, dict(kind='smoke_fixture', already_viewed_seed_ranges=True,
            note='Short regenerated fixtures on existing development seed IDs; not independent research results')
    source = _resolve(plan['source_run'])
    manifest = verified_archive(source)
    if manifest['mode'] != 'development' or manifest['config'] != cfg:
        raise ValueError('Experiments require the unchanged complete development source/config')
    compatible_source(source, manifest, NOTEBOOK)
    episodes, seeds, _, _ = read_episodes(source, 'development', cfg, ns)
    if seeds != plan['dialogue_seeds']:
        # Ordering in an archive is immaterial, identities are not.
        if {s: sorted(v) for s, v in seeds.items()} != plan['dialogue_seeds']:
            raise ValueError('Development seed identities differ from the plan')
    outcomes = pd.read_csv(source / 'tables/development_outcomes.csv')
    replay = pd.read_csv(source / 'tables/development_replay.csv')
    validate_outcomes(outcomes, cfg, plan['dialogue_seeds'])
    validate_replay(replay, outcomes, cfg)
    metadata = pd.DataFrame([dict(scenario=e['scenario'], seed=e['seed'], t=p['t'],
        question=p['question'], qtype=p['qtype'], state=p['state']) for e in episodes for p in e['probes']])
    keys = ['scenario', 'seed', 't']
    observed = outcomes[list(metadata.columns)].drop_duplicates()
    pd.testing.assert_frame_equal(observed.sort_values(keys).reset_index(drop=True),
                                   metadata.sort_values(keys).reset_index(drop=True))
    return episodes, outcomes, replay, dict(kind='verified_development_archive', path=str(source),
        manifest_sha256=digest(source / 'manifest.json'), already_viewed=True,
        outcomes_sha256=digest(source / 'tables/development_outcomes.csv'))


def _assert_default(replay, original):
    if original is not None:
        keys = ['scenario', 'seed', 't', 'method', 'alg_seed']
        pd.testing.assert_frame_equal(replay.sort_values(keys).reset_index(drop=True),
            original.sort_values(keys).reset_index(drop=True), check_exact=False, rtol=0, atol=1e-12)


def _seed_spread(replay):
    per_seed = replay.groupby(['scenario', 'seed', 'method', 'alg_seed'])[METRICS].mean().reset_index()
    parts = []
    for keys, group in per_seed.groupby(['scenario', 'seed', 'method']):
        for metric in METRICS:
            parts.append(dict(zip(['scenario', 'seed', 'method'], keys), metric=metric,
                algorithm_seed_count=len(group), mean=group[metric].mean(),
                std=group[metric].std(ddof=1), minimum=group[metric].min(), maximum=group[metric].max()))
    return {'algorithm_seed_metrics': per_seed, 'algorithm_seed_spread': pd.DataFrame(parts)}


def _variant_effects(metrics, plan, group_columns=()):
    """Pair common seed draws; for lambda variants exclude cross-preference utility."""
    reference = metrics['default']
    effects, differences = [], []
    rng = np.random.default_rng(plan['config']['bootstrap_seed'])
    selected_metrics = ['y', 'cost', 'coverage', 'outdated'] if plan['stage'] == 'E4' else METRICS
    for variant, table in metrics.items():
        if variant == 'default':
            continue
        keys = ['scenario', 'seed', 'method', *group_columns]
        combined = table.merge(reference, on=keys, suffixes=('_variant', '_default'), validate='one_to_one')
        if len(combined) != len(reference) or len(table) != len(reference):
            raise ValueError('Variant dialogue pairing differs')
        sign = -1 if plan['stage'] == 'E2' or variant.startswith('without_') else 1
        direction = 'default_minus_variant' if sign == -1 else 'variant_minus_default'
        group_keys = ['scenario', 'method', *group_columns]
        for key, group in combined.groupby(group_keys, sort=True):
            group = group.sort_values('seed')
            labels = dict(zip(group_keys, key))
            bootstrap_draws = {}
            for metric in selected_metrics:
                valid = group[[metric + '_variant', metric + '_default']].notna().all(axis=1)
                observed = group.loc[valid]
                delta = sign * (observed[metric + '_variant'].to_numpy() - observed[metric + '_default'].to_numpy())
                low = high = np.nan
                if len(delta) >= 2:
                    paired_seeds = tuple(observed.seed)
                    if paired_seeds not in bootstrap_draws:
                        bootstrap_draws[paired_seeds] = rng.integers(0, len(delta), size=(plan['config']['n_bootstrap'], len(delta)))
                    indices = bootstrap_draws[paired_seeds]
                    low, high = np.quantile(delta[indices].mean(axis=1), [0.025, 0.975])
                effects.append(dict(labels, variant=variant, metric=metric,
                    direction=direction, n=len(delta), n_total=len(group),
                    effect=float(delta.mean()) if len(delta) else np.nan, low=float(low), high=float(high),
                    status='ok' if len(delta) >= 2 else 'insufficient_dialogues',
                    interpretation='exploratory paired dialogue CI',
                    pairing='common_seed_environment_draws' if plan['stage'].startswith('E7') else 'same_dialogue'))
                full_delta = sign * (group[metric + '_variant'] - group[metric + '_default'])
                differences.extend(dict(labels, variant=variant, seed=int(seed), metric=metric,
                    direction=direction, difference=float(value), observed=bool(seen))
                    for seed, value, seen in zip(group.seed, full_delta, valid))
    return {'variant_effects': pd.DataFrame(effects), 'variant_dialogue_differences': pd.DataFrame(differences)}


def _fixed_trajectory_scores(replay, plan):
    tables = []
    for weight in (0.25, 0.5, 1.0):
        scored = replay.copy()
        scored['utility'] = scored.y - weight * scored.cost / plan['config']['cost_reference']
        metrics = aggregate_dialogues(scored)
        metrics['scoring_lambda'] = weight
        metrics['decision_lambda'] = plan['config']['lambda']
        metrics['interpretation'] = 'same saved actions rescored; not reoptimized policies'
        tables.append(metrics)
    return pd.concat(tables, ignore_index=True)


def run_experiment(plan, run_id):
    validate_plan(plan)
    registry = ROOT / 'team_workspace/formal_runs.json'
    registry_before = digest(registry)
    run = _run_directory(run_id)
    metadata = dict(run_id=run_id, experiment=plan['stage'], fixture=plan['fixture'],
                    plan_sha256=canonical_hash(plan), config=plan['config'], seeds=plan['dialogue_seeds'])
    try:
        write_new(run / 'config/experiment_plan.json', plan)
        _snapshot(run)
        ns = load_namespace(NOTEBOOK)
        episodes, base_outcomes, old_replay, provenance = _source_inputs(plan, ns)
        baselines = ns['choose_fixed_baselines'](base_outcomes)
        metadata.update(baselines=baselines, source=provenance)
        write_new(run / 'audit/source.json', provenance)
        if provenance.get('path'):
            shutil.copyfile(Path(provenance['path']) / 'manifest.json', run / 'config/source_manifest.json')
        _save_episodes(run / 'data/default_dialogues.jsonl.gz', episodes)
        metrics = {}
        alias_metrics = {}
        default_replay = None
        variant_records = []
        for variant in plan['variants']:
            name = variant['id']
            print(f"{plan['stage']}/{name}: {plan['profile']}", flush=True)
            cfg = deepcopy(plan['config'])
            cfg.update(deepcopy(variant['config']))
            current_ns = configure_namespace(ns, variant['adapter'])
            current_episodes = episodes
            if variant['rebuild'] == 'environment':
                current_episodes = [current_ns['generate_episode'](seed, scenario, cfg)
                    for scenario, seeds in plan['dialogue_seeds'].items() for seed in seeds]
                _save_episodes(run / 'data' / (name + '_dialogues.jsonl.gz'), current_episodes)
            outcomes = (evaluate_episodes(current_ns, current_episodes, cfg)
                        if variant['rebuild'] != 'none' else base_outcomes.copy())
            outcomes['utility'] = outcomes.y - cfg['lambda'] * outcomes.cost / cfg['cost_reference']
            validate_outcomes(outcomes, cfg, plan['dialogue_seeds'])
            if variant['rebuild'] == 'arms':
                columns = [c for c in base_outcomes if c != 'construction_ms']
                mask = outcomes.arm != 'resolved_tfidf'
                pd.testing.assert_frame_equal(outcomes.loc[mask, columns].reset_index(drop=True),
                    base_outcomes.loc[base_outcomes.arm != 'resolved_tfidf', columns].reset_index(drop=True))
            replay, diagnostics = replay_all(current_ns, outcomes, cfg)
            diagnostics['selected_share'] = diagnostics.selected_count / cfg['T']
            if name == 'default':
                _assert_default(replay, old_replay)
                default_replay = replay
            artifacts = build_analysis_artifacts(current_ns, outcomes, replay, baselines, cfg, plan['dialogue_seeds'])
            folder = run / 'variants' / name
            table_map = {Path(k).stem: v for k, v in artifacts.items() if isinstance(v, pd.DataFrame)}
            table_map['selector_diagnostics'] = diagnostics
            table_map.update(_seed_spread(replay))
            metrics[name] = table_map['episode_metrics']
            # The original E1 analysis is reused for every configuration, always as exploratory here.
            _tables(folder / 'tables', table_map)
            write_new(folder / 'config.json', dict(config=cfg, adapter=variant['adapter'],
                baseline_rule=plan['baseline_rule'], baselines=baselines, rebuild=variant['rebuild'],
                inference='exploratory development/fixture only'))
            truth = [current_ns['audit_truth'](e) for e in current_episodes]
            if not all(v['passed'] for v in truth):
                raise ValueError('Independent truth audit failed')
            write_new(folder / 'truth_checks.json', truth)
            if plan['stage'] in ('E2', 'E3', 'E4', 'E6', 'E6a', 'E6b') or plan['stage'].startswith('E5'):
                _tables(folder / 'temporal', temporal_analysis(replay, outcomes, baselines, cfg, plan['window_size']))
            if plan['stage'].startswith('E5'):
                from m4_subgroups import alias_analysis
                aliases = alias_analysis(current_ns, current_episodes, outcomes, replay, cfg, baselines)
                alias_metrics[name] = aliases['alias_query_episode_metrics']
                _tables(folder / 'aliases', aliases)
            if plan['stage'] == 'E0':
                from m4_validation import validate_pipeline
                write_new(folder / 'pipeline_validation.json', validate_pipeline(current_ns, current_episodes, outcomes, replay, cfg))
            if plan['stage'] == 'A':
                from m4_statistics import statistical_analysis
                _tables(folder / 'statistics', statistical_analysis(metrics[name], baselines, cfg, plan['statistics']))
                _tables(folder / 'oracle', oracle_analysis(replay, outcomes, cfg))
            variant_records.append(dict(variant=name, dialogues=len(current_episodes), outcomes=len(outcomes),
                replay=len(replay), algorithm_seeds=cfg['algorithm_seeds'], status='computed_pending_review'))
        if len(metrics) > 1:
            _tables(run / 'tables', _variant_effects(metrics, plan))
        if len(alias_metrics) > 1:
            grouped = _variant_effects(alias_metrics, plan, ('question_alias', 'evidence_alias', 'qtype'))
            _tables(run / 'tables', {'alias_' + name: table for name, table in grouped.items()})
        if plan['stage'] == 'E4':
            _tables(run / 'tables', {'fixed_trajectory_rescoring': _fixed_trajectory_scores(default_replay, plan)})
        write_new(run / 'audit/variant_status.json', variant_records)
        if digest(registry) != registry_before:
            raise ValueError('Formal registry changed; investigate concurrent modification')
        _assert_code_unchanged()
        report = ('# M4 ' + plan['stage'] + '\n\nStatus: computed_pending_review.\n\n'
            + ('Smoke fixture only; no research effect estimate.\n\n' if plan['fixture'] else 'Exploratory previously viewed development data.\n\n')
            + 'Fixed references are selected once on default development data and retained for all variants. '
            + 'Independent units are dialogues; algorithm seeds are averaged within dialogue. '
            + 'All results including negative/uncertain effects are retained. No formal data or approvals were generated.\n\n'
            + 'Environment variants share predetermined seed draws, not necessarily identical histories. '
            + 'Cross-lambda utility is not compared; each lambda has its own within-configuration effects.\n')
        (run / 'report.md').write_text(report, encoding='utf-8')
        _manifest(run, dict(metadata, variants=variant_records), 'computed_pending_review')
        return run
    except BaseException as exc:
        write_new(run / 'failure.json', dict(type=type(exc).__name__, message=str(exc), formal_generated=False,
            traceback_policy='exception propagated; keep run directory and completed variant artifacts'))
        _manifest(run, metadata, 'failed')
        raise


def _verified_analysis_source(path, variant='default'):
    """Read-only E1/stage archive analysis; formal source must be reviewed separately."""
    root = _resolve(path)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('mode') not in ('development', 'demo', 'formal'):
        raise ValueError('Unknown source mode')
    if manifest.get('status') not in ('computed_pending_review', 'exploratory_complete_pending_review'):
        raise ValueError('Only complete computed archives can be analyzed')
    if not manifest.get('files'):
        raise ValueError('Missing source hashes')
    for name, expected in manifest['files'].items():
        target = (root / name).resolve()
        if not target.is_relative_to(root) or digest(target) != expected:
            raise ValueError('Source file escaped archive or failed hash verification: ' + name)
    if manifest.get('experiment') in STAGES and (root / 'variants').exists():
        if not variant.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Unsafe variant name')
        folder = root / 'variants' / variant
        config_path = folder / 'config.json'
        if config_path.relative_to(root).as_posix() not in manifest['files']:
            raise ValueError('Variant configuration is not bound')
        cfg = json.loads(config_path.read_text(encoding='utf-8'))['config']
    else:
        folder, cfg = root, manifest['config']
    paths = {name: folder / 'tables' / (name + '.csv') for name in ['evaluation_outcomes', 'replay']}
    if any(p.relative_to(root).as_posix() not in manifest['files'] for p in paths.values()):
        raise ValueError('Manifest must bind both consumed tables')
    outcomes, replay = (pd.read_csv(paths[name]) for name in ['evaluation_outcomes', 'replay'])
    declared = manifest.get('seeds', {})
    if set(declared) == {'stable', 'abrupt'}:
        expected = declared
    else:
        declared_flat = declared.get('evaluation', declared.get('dialogue'))
        if not isinstance(declared_flat, list) or len(declared_flat) != len(set(declared_flat)):
            raise ValueError('Source must declare distinct dialogue seed identities')
        if set(outcomes.seed) != set(declared_flat):
            raise ValueError('Source tables omit or add declared dialogues')
        expected = {s: sorted(map(int, outcomes.loc[outcomes.scenario == s, 'seed'].unique()))
                    for s in ('stable', 'abrupt')}
        size_field = {'formal': 'n_formal_per_scenario', 'demo': 'n_demo_per_scenario',
                      'development': 'n_dev_per_scenario'}[manifest['mode']]
        if any(len(v) != cfg[size_field] for v in expected.values()):
            raise ValueError('Source scenario counts differ from design')
    validate_outcomes(outcomes, cfg, expected)
    validate_replay(replay, outcomes, cfg)
    return root, manifest, cfg, outcomes, replay


def analyze_archive(source, run_id, analysis, variant='default', options=None):
    """E3 or A analyses on a hashed archive, including future already-computed formal data."""
    if analysis not in ('E3', 'A'):
        raise ValueError('analysis must be E3 or A')
    root, source_manifest, cfg, outcomes, replay = _verified_analysis_source(source, variant)
    baselines = source_manifest['baselines']
    metrics = aggregate_dialogues(replay)
    if analysis == 'A' and options is None:
        raise ValueError('A analyses require an explicit options JSON, including ROPE priors when selected')
    run = _run_directory(run_id)
    meta = dict(experiment=analysis, operation='analysis_only', source_run=str(root),
        source_manifest_sha256=digest(root / 'manifest.json'), source_mode=source_manifest.get('mode'),
        fixture=source_manifest.get('fixture', False), config=cfg, baselines=baselines,
        variant=variant, creates_dialogues=False, inference='supplementary exploratory analysis')
    try:
        write_new(run / 'config/analysis_plan.json', dict(meta, statistics=options))
        _snapshot(run)
        shutil.copyfile(root / 'manifest.json', run / 'config/source_manifest.json')
        if analysis == 'E3':
            tables = temporal_analysis(replay, outcomes, baselines, cfg)
        else:
            from m4_statistics import statistical_analysis
            tables = statistical_analysis(metrics, baselines, cfg, options)
            tables.update(oracle_analysis(replay, outcomes, cfg))
        _tables(run / 'tables', tables)
        _assert_code_unchanged()
        _manifest(run, meta, 'computed_pending_review')
        return run
    except BaseException as exc:
        write_new(run / 'failure.json', dict(type=type(exc).__name__, message=str(exc)))
        _manifest(run, meta, 'failed')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run'):
        command = sub.add_parser(name)
        command.add_argument('--stage', choices=STAGES)
        command.add_argument('--profile', choices=['smoke', 'development'], default='development')
        command.add_argument('--source-run')
        if name == 'plan':
            command.add_argument('--output', type=Path, required=True)
        else:
            command.add_argument('--plan', type=Path)
            command.add_argument('--run-id', required=True)
    analysis = sub.add_parser('analyze')
    analysis.add_argument('--source-run', required=True)
    analysis.add_argument('--analysis', choices=['E3', 'A'], required=True)
    analysis.add_argument('--variant', default='default')
    analysis.add_argument('--options', type=Path)
    analysis.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if args.command == 'analyze':
        options = json.loads(args.options.read_text(encoding='utf-8')) if args.options else None
        print(analyze_archive(args.source_run, args.run_id, args.analysis, args.variant, options))
        return
    if args.command == 'run' and args.plan:
        if args.stage or args.source_run or args.profile != 'development':
            parser.error('--plan cannot be combined with stage/profile/source overrides')
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
    else:
        if not args.stage:
            parser.error('--stage is required without --plan')
        plan = make_plan(args.stage, args.profile, args.source_run)
    if args.command == 'plan':
        write_new(args.output, plan)
        print(args.output)
    else:
        print(run_experiment(plan, args.run_id))


if __name__ == '__main__':
    main()
