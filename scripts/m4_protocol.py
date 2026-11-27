"""M4 protocol binding and append-only formal attempt events.

Human approval files are attestations, not cryptographic identity verification.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())


ARMS = ('recent_short', 'recent_long', 'tfidf', 'resolved_tfidf')


def analysis_specification():
    """The E1 analysis approved with the plan; no result-dependent selection."""
    return {
        'version': 'm4-e1-v1',
        'independent_unit': 'dialogue',
        'aggregation': ['mean_questions_within_algorithm_seed', 'mean_algorithm_seeds_within_dialogue',
                        'equal_weight_mean_dialogues_within_scenario'],
        'primary': {'method': 'LaplaceCTS', 'reference': 'development_selected_fixed_arm',
                    'metric': 'utility', 'scenarios': ['stable', 'abrupt'],
                    'bootstrap': 'paired_dialogue_percentile', 'confidence': 0.95,
                    'family_confidence': 0.975, 'family_size': 2,
                    'practical_utility_threshold': 0.02},
        'supplementary': {'comparisons': ['TS_minus_fixed', 'CTS_minus_TS', 'CTS_minus_RuleRouter'],
                          'confidence': 0.95, 'family_adjusted': False, 'interpretation': 'exploratory'},
        'metrics': ['y', 'cost', 'utility', 'coverage', 'outdated'],
        'baseline_selection': 'development_only_equal_dialogue_utility_exact_ties_ARMS_order',
        'bootstrap_keeps_baseline_fixed': True,
        'direct_comparisons_share_indices_across_metrics': True,
        'generator_defaults_bound_in_notebook': {'n_projects': 6, 'alias_probability': 0.5},
        'failure_policy': 'retain_failed_attempt_and_seeds_no_silent_row_deletion',
        'other_experiments': 'E2-E5 excluded from this E1 formal execution',
    }


def validate_config(cfg):
    import math
    if not isinstance(cfg, dict):
        raise ValueError('Configuration must be an object')
    integers = {'T':300, 'n_formal_per_scenario':30, 'n_dev_per_scenario':None,
                'n_demo_per_scenario':None, 'refit_every':None, 'n_bootstrap':None}
    for name, fixed in integers.items():
        value = cfg.get(name)
        if type(value) is not int or value < 1 or (fixed is not None and value != fixed):
            raise ValueError('Invalid/missing configuration: '+name)
    for name in ['lambda','cost_reference','prior_precision','p_recent_stable',
                 'p_recent_abrupt_before','p_recent_abrupt_after','update_probability','initial_conflict_fraction']:
        value=cfg.get(name)
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError('Invalid/missing configuration: '+name)
        if name.startswith('p_recent') or name in ['update_probability','initial_conflict_fraction']:
            if not 0<=value<=1: raise ValueError('Probability out of range: '+name)
        elif value < 0 or (name!='lambda' and value==0):
            raise ValueError('Invalid positive parameter: '+name)
    seeds=cfg.get('algorithm_seeds')
    if not isinstance(seeds,list) or not seeds or any(type(v) is not int or v<0 for v in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('Invalid algorithm seeds')
    if type(cfg.get('bootstrap_seed')) is not int or cfg['bootstrap_seed']<0:
        raise ValueError('Invalid bootstrap seed')
    budgets=cfg.get('budgets',{})
    if not isinstance(budgets,dict) or set(budgets)!=set(ARMS) or any(type(v) is not int or v<0 for v in budgets.values()):
        raise ValueError('Invalid budgets')
    for name in ['n_projects']:
        if name in cfg and (type(cfg[name]) is not int or cfg[name]<2):raise ValueError(name)
    if 'alias_probability' in cfg and (type(cfg['alias_probability']) not in (int,float) or not 0<=cfg['alias_probability']<=1):
        raise ValueError('alias_probability')


def validate_evidence(plan,evidence,code_files):
    import numpy as np
    import pandas as pd
    cfg=plan['config']
    required={'audit_review','truth_checks','strategy_checks','method_checks','development_outcomes','development_provenance','approvals'}
    if set(evidence)!=required: raise ValueError('Evidence set differs from required schema')
    provenance=json.loads(Path(evidence['development_provenance']).read_text(encoding='utf-8'))
    bindings=dict(config_sha256=canonical_hash(cfg),notebook_sha256=digest(code_files['notebook']),
                  development_sha256=digest(evidence['development_outcomes']))
    if not isinstance(provenance,dict) or any(provenance.get(k)!=v for k,v in bindings.items()):
        raise ValueError('Development data configuration/code binding mismatch; regenerate evidence')
    data=pd.read_csv(evidence['development_outcomes'])
    columns=['scenario','seed','t','arm','y','cost','utility','coverage','outdated']
    if not set(columns).issubset(data) or data[columns].isna().any().any():raise ValueError('Incomplete development columns')
    if not np.isfinite(data[['seed','t','y','cost','utility','coverage','outdated']].to_numpy(dtype=float)).all():raise ValueError('Nonfinite development data')
    if not data[['y','coverage','outdated']].isin([0,1]).all().all() or (data.cost<0).any():raise ValueError('Invalid outcome values')
    if not np.allclose(data.utility,data.y-cfg['lambda']*data.cost/cfg['cost_reference'],rtol=0,atol=1e-12):raise ValueError('Development utility/config mismatch')
    if set(data.scenario)!={'stable','abrupt'} or data.duplicated(['seed','t','arm']).any():raise ValueError('Invalid development identities')
    identities=data[['scenario','seed']].drop_duplicates()
    if identities.seed.duplicated().any() or not (identities.groupby('scenario').size()==cfg['n_dev_per_scenario']).all():raise ValueError('Development dialogue count mismatch')
    for _,g in data.groupby(['scenario','seed']):
        if set(zip(g.t,g.arm))!={(t,a) for t in range(cfg['T']) for a in ARMS}:raise ValueError('Incomplete development grid')
    if set(data.seed)&{s for group in plan['evaluation_seeds'].values() for s in group}:raise ValueError('Development/test overlap')
    scores=data.groupby(['scenario','seed','arm']).utility.mean().groupby(['scenario','arm']).mean().unstack().reindex(columns=ARMS)
    if scores.idxmax(axis=1).to_dict()!=plan['baselines']:raise ValueError('Baseline mismatch')
    payloads={}
    for name in ['truth_checks','strategy_checks','method_checks']:
        envelope=json.loads(Path(evidence[name]).read_text(encoding='utf-8'))
        if not isinstance(envelope,dict) or envelope.get('status')!='passed' or any(envelope.get(k)!=v for k,v in bindings.items()):raise ValueError('Failed/unbound evidence: '+name)
        payloads[name]=envelope.get('payload')
    truth=payloads['truth_checks']
    expected=set(map(tuple,identities.to_numpy()))
    if not isinstance(truth,list) or any(not isinstance(x,dict) for x in truth) or len(truth)!=len(expected) or {(x.get('scenario'),x.get('seed')) for x in truth}!=expected:
        raise ValueError('Truth audit coverage mismatch')
    if any(x.get('passed') is not True or x.get('question_count')!=cfg['T'] or x.get('errors') for x in truth):raise ValueError('Truth audit failed')
    strategy=payloads['strategy_checks']
    if not isinstance(strategy,dict):raise ValueError('Invalid strategy checks')
    if not strategy.get('fixture_checks') or any(x.get('result')!='pass' for x in strategy['fixture_checks']):raise ValueError('Strategy fixtures failed')
    checks=strategy.get('development_checks',{})
    required_checks={'unique_keys_four_arms_and_matching_metadata','cost_count_and_utility_consistency','m1_independent_truth_audit','audit_coverage_and_reconstruction_match_outcomes'}
    if not required_checks.issubset(checks) or any(v!='pass' for v in checks.values()):raise ValueError('Strategy development checks failed')
    if strategy.get('row_counts',{}).get('outcomes')!=len(data):raise ValueError('Strategy coverage mismatch')
    method=payloads['method_checks']
    if not isinstance(method,dict):raise ValueError('Invalid method checks')
    if method.get('beta_posterior')!=[3,2] or method.get('reset_and_unchosen_reward_flip')!='passed':raise ValueError('Method checks failed')
    if method.get('algorithm_seeds')!=cfg['algorithm_seeds'] or method.get('refit_every_selected_feedbacks')!=cfg['refit_every']:raise ValueError('Method config mismatch')
    if set(method.get('methods',[]))!=set(ARMS+('TS','LaplaceCTS','RuleRouter')):raise ValueError('Missing method checks')
    for name,limit in [('map_gradient_norm',1e-3),('gradient_fd_max_error',1e-5),('hessian_fd_max_error',1e-5)]:
        v=method.get(name)
        if type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=limit:raise ValueError('Method numeric check failed: '+name)
    v=method.get('covariance_min_eigenvalue')
    if type(v) not in (int,float) or not np.isfinite(v) or v<=0:raise ValueError('Invalid covariance')
    source=method.get('source',{})
    if (source.get('scenario'),source.get('seed')) not in expected or method.get('replay_rows')!=cfg['T']*7*len(cfg['algorithm_seeds']):raise ValueError('Method coverage mismatch')
    review=pd.read_csv(evidence['audit_review'])
    if not set(zip(review.seed,review.t)).issubset(set(zip(data.seed,data.t))):raise ValueError('Audit questions outside development data')


def validate_machine_plan(plan, evidence, code_files):
    """Validate computable preparation without claiming human approval."""
    cfg = plan['config']
    validate_config(cfg)
    if set(code_files) != {'notebook','runner','protocol','loader','analysis'}:
        raise ValueError('All execution source snapshots required')
    if plan.get('analysis_spec') != analysis_specification():
        raise ValueError('Analysis specification differs from the implemented E1 protocol')
    if cfg['T'] != 300 or cfg['n_formal_per_scenario'] != 30:
        raise ValueError('This runner supports the agreed 30 x 300 design only')
    if set(plan['evaluation_seeds']) != {'stable', 'abrupt'}:
        raise ValueError('Two scenarios required')
    if any(not isinstance(group, list) for group in plan['evaluation_seeds'].values()):
        raise ValueError('Evaluation seed groups must be lists')
    seeds = [x for group in plan['evaluation_seeds'].values() for x in group]
    if any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError('Seeds must be nonnegative integers')
    if any(len(v) != 30 for v in plan['evaluation_seeds'].values()) or len(set(seeds)) != 60:
        raise ValueError('Exactly 60 distinct dialogue seeds required')
    used = plan.get('used_seeds')
    if not isinstance(used, list) or any(type(s) is not int or s < 0 for s in used) or len(set(used)) != len(used):
        raise ValueError('Used seeds must be distinct nonnegative integers')
    excluded = set(plan['used_seeds']) | set(range(20261105,20261135)) | set(range(20261205,20261235))
    # Known development/demo and test seeds from this repository.
    excluded |= set(range(130000,130003)) | set(range(130100,130103))
    excluded |= set(range(730000,730006)) | set(range(730100,730106))
    excluded |= {42,910001,910002,910003,910010}
    if excluded.intersection(seeds):
        raise ValueError('Evaluation seeds overlap used/reference seeds')
    if len(cfg['algorithm_seeds']) != len(set(cfg['algorithm_seeds'])) or not cfg['algorithm_seeds']:
        raise ValueError('Invalid algorithm seeds')
    inventory = plan.get('seed_inventory')
    if inventory is not None:
        if inventory.get('candidate_seeds') != plan['evaluation_seeds'] or inventory.get('collisions'):
            raise ValueError('Seed inventory does not match noncolliding candidates')
        if not set(inventory['known_used_seeds']).issubset(used):
            raise ValueError('Used-seed list omits repository inventory')
        if inventory.get('scan_errors'):
            raise ValueError('Seed inventory contains unresolved scan errors')
    validate_evidence(plan, evidence, code_files)
    return {'technical_checks': 'passed', 'formal_generated': False,
            'dialogues': len(seeds), 'questions': len(seeds) * cfg['T']}


def validate_plan(plan, evidence, code_files):
    import pandas as pd
    validate_machine_plan(plan, evidence, code_files)
    review = pd.read_csv(evidence['audit_review']).fillna('')
    columns = ['seed','t','m1_reviewer','m2_reviewer','verdict','m1_notes','m2_notes']
    if not set(columns).issubset(review) or len(review)!=10 or review.duplicated(['seed','t']).any():
        raise ValueError('Ten distinct audit records required')
    if not (review.verdict=='pass').all() or not review[columns[2:]].astype(str).apply(lambda c:c.str.strip().ne('')).all().all():
        raise ValueError('Audit pending/failed or unsigned')
    approvals=json.loads(Path(evidence['approvals']).read_text(encoding='utf-8'))
    if approvals.get('plan_sha256')!=canonical_hash(plan):
        raise ValueError('Approval does not bind this exact plan')
    expected_code={k:digest(v) for k,v in code_files.items()}
    if approvals.get('code_sha256')!=expected_code:
        raise ValueError('Approval code hashes differ')
    expected_evidence={k:digest(v) for k,v in evidence.items() if k!='approvals'}
    if approvals.get('evidence_sha256')!=expected_evidence:
        raise ValueError('Approval evidence hashes differ')
    members=approvals.get('members',{})
    for member in ['M1','M2','M3','M4','M5']:
        entry=members.get(member,{})
        if entry.get('approved') is not True or any(not isinstance(entry.get(k),str) or not entry[k].strip() for k in ['name','date']):
            raise ValueError('Missing real team approval: '+member)
        try:
            datetime.fromisoformat(entry['date'])
        except ValueError as exc:
            raise ValueError('Invalid approval date: '+member) from exc
        additional=entry.get('additional_dialogue_seeds')
        if entry.get('seeds_disclosed') is not True or not isinstance(additional,list):
            raise ValueError('Missing individual seed disclosure: '+member)
        if any(type(s) is not int or s<0 for s in additional) or len(set(additional))!=len(additional):
            raise ValueError('Invalid individual seed disclosure: '+member)
        if not set(additional).issubset(plan['used_seeds']):
            raise ValueError('Disclosed seeds absent from bound plan: '+member)
    if approvals.get('m3_statistics_reviewed') is not True or approvals.get('all_used_seeds_disclosed') is not True:
        raise ValueError('Statistics review/seed disclosure not confirmed')
    # Require upstream evidence as actual files; signatures bind their content.
    for name in ['truth_checks','strategy_checks','method_checks','development_outcomes']:
        if name not in evidence:
            raise ValueError('Missing upstream evidence: '+name)
    return approvals


def freeze(plan, evidence, code_files, destination):
    approvals=validate_plan(plan,evidence,code_files)
    dest=Path(destination)
    dest.mkdir(parents=True,exist_ok=False)
    files={}
    for category, mapping in [('code',code_files),('evidence',evidence)]:
        for name,path in mapping.items():
            if not name.replace('_','').isalnum():
                raise ValueError('Unsafe snapshot name')
            target=dest/category/name
            target.parent.mkdir(exist_ok=True)
            with target.open('xb') as out: out.write(Path(path).read_bytes())
            files[target.relative_to(dest).as_posix()]=digest(target)
    frozen=dict(plan=plan,plan_sha256=canonical_hash(plan),files=files,
                created_at=datetime.now(timezone.utc).isoformat(),status='frozen_pending_execution')
    write_new(dest/'frozen_config.json',frozen)
    return frozen


def verify_frozen(directory):
    root=Path(directory).resolve()
    frozen=json.loads((root/'frozen_config.json').read_text(encoding='utf-8'))
    if canonical_hash(frozen['plan'])!=frozen['plan_sha256']:
        raise ValueError('Frozen plan changed')
    for name,expected in frozen['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or digest(path)!=expected:
            raise ValueError('Frozen artifact changed: '+name)
    codes={p.name:p for p in (root/'code').iterdir()}
    evidence={p.name:p for p in (root/'evidence').iterdir()}
    validate_plan(frozen['plan'],evidence,codes)
    return frozen


def register_event(registry, event):
    """Exclusive lock + atomic replacement; preserve all previous events.

    A crashed process leaves a lock to investigate, never silently discard.
    """
    path=Path(registry)
    lock=path.with_suffix(path.suffix+'.lock')
    with lock.open('x'):
        pass
    try:
        events=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        if not isinstance(events,list): raise ValueError('Registry must be a list')
        if event['status']=='started':
            if any(e.get('run_id')==event['run_id'] for e in events):
                raise ValueError('Formal run ID already registered')
            used={s for e in events for s in e.get('evaluation_seeds',[])}
            if used.intersection(event['evaluation_seeds']):
                raise ValueError('Formal seeds already attempted')
        else:
            previous=[e for e in events if e.get('run_id')==event['run_id']]
            if not previous or previous[-1]['status']!='started':
                raise ValueError('No active attempt')
            if event['status'] not in ['failed','computed_pending_review']:
                raise ValueError('Unsupported terminal status')
        event=dict(event, timestamp=datetime.now(timezone.utc).isoformat())
        temporary=path.with_suffix(path.suffix+'.new')
        write_new(temporary,events+[event])
        os.replace(temporary,path)
    finally:
        lock.unlink()


def record_failure(target, registry, run_id, seeds, original):
    """Best-effort independent persistence; caller re-raises original exception."""
    errors=[]
    try:
        if Path(target).exists():write_new(Path(target)/'failure.json',dict(type=type(original).__name__,message=str(original)))
    except BaseException as exc:errors.append('failure report: '+repr(exc))
    try:
        register_event(registry,dict(run_id=run_id,status='failed',error=repr(original),evaluation_seeds=seeds))
    except BaseException as exc:errors.append('registry: '+repr(exc))
    for message in errors:original.add_note(message)
    return errors
