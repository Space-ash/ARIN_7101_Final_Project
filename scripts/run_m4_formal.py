"""Freeze approved inputs or run a new registered formal attempt."""
import argparse
import gzip
import json
import platform
import sys
from pathlib import Path
from importlib.metadata import version
from m4_protocol import freeze, verify_frozen, register_event, digest, write_new, record_failure
from m4_analysis import METRICS, paired_comparisons, validate_outcomes, validate_replay
from test_member_handoff import ROOT, load
sys.path.insert(0, str(ROOT))


def code_paths():
    return dict(notebook=ROOT/'ARIN7101_Context_Bandit_Release_Notebook.ipynb',
                runner=Path(__file__), protocol=ROOT/'scripts/m4_protocol.py',
                loader=ROOT/'scripts/test_member_handoff.py',
                analysis=ROOT/'scripts/m4_analysis.py')


def _markdown_table(frame):
    def cell(value):
        return f'{value:.6f}' if isinstance(value, float) else str(value)
    lines = ['| ' + ' | '.join(frame.columns) + ' |',
             '| ' + ' | '.join('---' for _ in frame.columns) + ' |']
    lines.extend('| ' + ' | '.join(cell(value) for value in row) + ' |'
                 for row in frame.itertuples(index=False, name=None))
    return '\n'.join(lines)


def build_analysis_artifacts(ns, outcomes, replay, baselines, cfg, expected_seeds):
    """Build E1 tables without generating data, approving, or writing files.

    expected_seeds comes from the approved plan in a formal run; neither missing
    dialogues nor globally missing methods/seeds may be inferred away from data.
    The original notebook function retains its primary-bootstrap RNG sequence.
    """
    validate_outcomes(outcomes, cfg, expected_seeds)
    validate_replay(replay, outcomes, cfg)
    metrics = ns['aggregate_dialogues'](replay)
    primary, secondary = ns['paired_effects'](metrics, baselines, cfg)
    differences, direct = paired_comparisons(metrics, baselines, cfg)
    summary = metrics.groupby(['scenario', 'method'])[METRICS].mean().reset_index()
    decomposition = differences.groupby(['scenario', 'comparison', 'reference'])[
        ['delta_' + metric for metric in METRICS]].mean().reset_index()
    direct_utility = direct[direct.metric == 'utility'][
        ['scenario', 'reference', 'n', 'effect', 'low', 'high']]
    sample_counts = ', '.join(f'{scenario}: n={len(seeds)}'
                              for scenario, seeds in expected_seeds.items())
    report = '\n\n'.join([
        '# M4 E1 computation handoff',
        'Status: computed_pending_review. M3 statistical review and M5 independent archive review remain pending.',
        'This report must be interpreted using the enclosing run manifest mode and frozen plan; the table builder itself does not establish formal provenance.',
        f'Independent units are dialogues ({sample_counts}); each dialogue has {cfg["T"]} questions. Algorithm seeds are averaged within each dialogue.',
        'Fixed references were selected on development data only: ' + json.dumps(baselines, sort_keys=True),
        '## Seven-method means', _markdown_table(summary),
        '## Prespecified primary utility comparisons', _markdown_table(primary),
        'The primary family contains exactly two CTS-minus-fixed-arm comparisons, one per scenario. low/high are 95% percentile paired-bootstrap intervals; family_low/family_high are 97.5% intervals for this two-comparison family. Finite-sample bootstrap coverage is approximate.',
        '## Existing exploratory TS-minus-fixed-arm comparisons', _markdown_table(secondary),
        '## Additional direct utility comparisons', _markdown_table(direct_utility),
        'CTS-minus-TS and CTS-minus-RuleRouter intervals are exploratory 95% intervals, without familywise adjustment. The five-metric intervals are saved in direct_comparisons.csv. They do not enlarge or replace the prespecified primary family.',
        '## Accuracy and cost decomposition', _markdown_table(decomposition),
        f'Delta utility = delta accuracy - {cfg["lambda"]} * delta cost / {cfg["cost_reference"]}. Metrics share the same paired dialogue resampling indices within a scenario; interval endpoints themselves are not additive. Input cost is a text-length proxy, not measured API cost or latency.',
        'All computed effects, including negative and uncertain results, are retained. An interval spanning zero does not establish equivalence. No practical-superiority threshold is inferred from point estimates alone.',
    ]) + '\n'
    return {
        'tables/evaluation_outcomes.csv': outcomes,
        'tables/replay.csv': replay,
        'tables/episode_metrics.csv': metrics,
        'tables/primary_effects.csv': primary,
        'tables/secondary_effects.csv': secondary,
        'tables/method_summary.csv': summary,
        'tables/paired_dialogue_differences.csv': differences,
        'tables/direct_comparisons.csv': direct,
        'tables/effect_decomposition.csv': decomposition,
        'reports/M4_handoff.md': report,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    prep=commands.add_parser('freeze')
    prep.add_argument('--plan',type=Path,required=True)
    prep.add_argument('--evidence',type=Path,required=True,help='JSON mapping evidence names to paths relative to this file')
    prep.add_argument('--destination',type=Path,required=True)
    run=commands.add_parser('run')
    run.add_argument('--frozen',type=Path,required=True)
    run.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if args.command=='freeze':
        evidence={k:(args.evidence.resolve().parent/v).resolve() for k,v in json.loads(args.evidence.read_text(encoding='utf-8')).items()}
        freeze(json.loads(args.plan.read_text(encoding='utf-8')),evidence,code_paths(),args.destination)
        print('Frozen approved plan:',args.destination)
        return
    frozen=verify_frozen(args.frozen)
    for name,path in code_paths().items():
        if digest(path)!=frozen['files']['code/'+name]:
            raise ValueError('Current code differs from approved snapshot: '+name)
    if not args.run_id.replace('-','').replace('_','').isalnum():
        raise ValueError('Invalid run ID')
    plan=frozen['plan'];cfg=plan['config']
    ns=load(code_paths()['notebook'],'m2');ns.update(load(code_paths()['notebook'],'m3'))
    nb=json.loads(code_paths()['notebook'].read_text(encoding='utf-8'))
    exec(''.join(next(c['source'] for c in nb['cells'] if c.get('id')=='m4-experiment-skeleton')),ns)
    # Recompute baselines from exactly the approved development table, never test data.
    development=ns['pd'].read_csv(args.frozen/'evidence'/'development_outcomes')
    if ns['choose_fixed_baselines'](development)!=plan['baselines']:
        raise ValueError('Baseline does not match approved development data')
    if set(development.seed) & {s for v in plan['evaluation_seeds'].values() for s in v}:
        raise ValueError('Development/evaluation seed overlap')
    target=ROOT/'outputs'/'formal'/args.run_id
    if target.exists():raise FileExistsError(target)
    registry=ROOT/'team_workspace'/'formal_runs.json'
    seeds=[s for v in plan['evaluation_seeds'].values() for s in v]
    register_event(registry,dict(run_id=args.run_id,status='started',evaluation_seeds=seeds,
        plan_sha256=frozen['plan_sha256'],frozen_sha256=digest(args.frozen/'frozen_config.json')))
    try:
        target.mkdir(parents=True,exist_ok=False)
        episodes=[ns['generate_episode'](seed,scenario,cfg) for scenario,ss in plan['evaluation_seeds'].items() for seed in ss]
        truth=[ns['audit_truth'](e) for e in episodes]
        if not all(t['passed'] for t in truth):raise ValueError('Truth audit failed')
        outcomes,replay=ns['run_evaluation'](episodes,ns['METHODS'],cfg['algorithm_seeds'],cfg)
        artifacts=build_analysis_artifacts(ns,outcomes,replay,plan['baselines'],cfg,plan['evaluation_seeds'])
        artifacts.update({
            'data/evaluation_dialogues.jsonl.gz':gzip.compress(('\n'.join(json.dumps(e) for e in episodes)+'\n').encode(),mtime=0),
            'audit/truth_checks.json':json.dumps(truth),
            'config/frozen_config.json':(args.frozen/'frozen_config.json').read_bytes(),
            'config/notebook_snapshot.ipynb':code_paths()['notebook'].read_bytes(),
            'audit/review_snapshot.json':(args.frozen/'evidence'/'approvals').read_bytes()})
        for relative in frozen['files']:
            artifacts['config/frozen_inputs/'+relative]=(args.frozen/relative).read_bytes()
        env=dict(python=platform.python_version(),packages={k:version(k) for k in ['numpy','pandas','scipy','scikit-learn']})
        artifacts['config/environment.json']=json.dumps(env)
        metadata=dict(mode='formal',run_id=args.run_id,config=cfg,baselines=plan['baselines'],
            analysis_spec=plan['analysis_spec'],
            frozen_directory=str(args.frozen.resolve()),plan_sha256=frozen['plan_sha256'],
            code_sha256=digest(code_paths()['notebook']),environment=env,
            seeds=dict(evaluation=seeds,algorithm=cfg['algorithm_seeds'],development=sorted(map(int,development.seed.unique()))),
            counts=dict(dialogues=len(episodes),outcomes=len(outcomes),replay=len(replay)))
        manifest=ns['export_run'](target,artifacts,metadata)
        for name,sha in manifest['files'].items():
            if digest(target/name)!=sha:raise ValueError('Archive hash mismatch')
        register_event(registry,dict(run_id=args.run_id,status='computed_pending_review',manifest_sha256=digest(target/'manifest.json')))
        print(target)
    except BaseException as exc:
        record_failure(target, registry, args.run_id, seeds, exc)
        raise


if __name__=='__main__':main()
