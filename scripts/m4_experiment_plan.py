"""Versioned development-only experiment presets; these are not formal approvals."""
from copy import deepcopy
from pathlib import Path
import json

from m4_variants import load_namespace

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb'
STAGES = ('E0', 'E1', 'E2', 'E3', 'E4', 'E5', 'E5a', 'E5b', 'E5c', 'E5d',
          'E6', 'E6a', 'E6b', 'E7', 'E7a', 'E7b', 'E7c', 'E7d', 'E7e', 'A')


def make_plan(stage, profile='development', source_run=None):
    """Emit a complete plan without generating a dialogue or reading results."""
    if stage not in STAGES or profile not in ('smoke', 'development'):
        raise ValueError('Unknown stage or profile')
    cfg = deepcopy(load_namespace(NOTEBOOK)['PROTOCOL_DRAFT'])
    cfg['formal_seed'] = None
    if profile == 'smoke':
        cfg.update(T=12, n_dev_per_scenario=2, n_bootstrap=200)
        if source_run is not None:
            raise ValueError('Smoke fixtures do not consume an external archive')
    variants = [dict(id='default', config={}, adapter={}, rebuild='none')]

    def add(name, config=None, adapter=None, rebuild='none'):
        variants.append(dict(id=name, config=config or {}, adapter=adapter or {}, rebuild=rebuild))

    if stage == 'E2':
        add('constant_features', adapter={'feature_mode': 'constant'})
    if stage == 'E4':
        for value, label in [(0.25, '025'), (1.0, '100')]:
            add('lambda_' + label, {'lambda': value})
    if stage in ('E5', 'E5a'):
        for k in (9, 12):
            add('resolved_k' + str(k), adapter={'resolved_top_k': k}, rebuild='arms')
    if stage in ('E5', 'E5b'):
        for name in ('resolve_pronouns', 'normalize_aliases', 'preserve_focus'):
            add('without_' + name, adapter={name: False}, rebuild='arms')
    if stage in ('E5', 'E5c'):
        add('algorithm_seeds_5', {'algorithm_seeds': [17, 37, 53, 71, 89]})
    if stage == 'E5d':
        for budget in (128, 512):
            add('resolved_budget_' + str(budget),
                {'budgets': dict(cfg['budgets'], resolved_tfidf=budget)}, rebuild='arms')
    if stage in ('E6', 'E6a'):
        for value, name in [(0.1, '01'), (10., '10')]:
            add('prior_' + name, {'prior_precision': value})
    if stage in ('E6', 'E6b'):
        for interval in (1, 10):
            add('refit_' + str(interval), {'refit_every': interval})
    grids = {
        'E7a': ('p_recent_abrupt_after', [0.9, 0.5]),
        'E7b': ('update_probability', [0.1, 0.5]),
        'E7c': ('initial_conflict_fraction', [0., 0.5]),
        'E7d': ('alias_probability', [0., 1.]),
        'E7e': ('n_projects', [3, 12]),
    }
    for child, (name, values) in grids.items():
        if stage in ('E7', child):
            for value in values:
                add(name + '_' + str(value).replace('.', 'p'), {name: value}, rebuild='environment')
    count = cfg['n_dev_per_scenario']
    options = dict(analyses=['A1', 'A2', 'A3', 'A4', 'A5', 'A6'], metrics=['utility'],
                   bootstrap_resamples=[200, 400] if profile == 'smoke' else [2000, 10000],
                   bootstrap_methods=['percentile', 'BCa'], confidence=0.95,
                   tie_tolerance=1e-12, sign_flip_resamples=200 if profile == 'smoke' else 10000,
                   seed=2026,
                   rope=dict(mu_prior_sd=0.1, sigma_prior_shape=2., sigma_prior_scale=0.01, delta=0.02))
    return dict(schema_version='m4-stage-plan-v1', stage=stage, profile=profile,
        formal=False, fixture=profile == 'smoke', config=cfg,
        source_run=None if profile == 'smoke' else str(source_run or 'outputs/development/m4_default_benchmark_20261123'),
        dialogue_seeds={'stable': list(range(130000, 130000 + count)),
                        'abrupt': list(range(130100, 130100 + count))},
        variants=variants, window_size=25, statistics=options,
        baseline_rule='default_development_selected_fixed_arm_retained_for_all_variants',
        inference='exploratory; dialogues paired within scenario; algorithm seeds averaged within dialogue',
        environment_pairing='preassigned common dialogue seeds; histories may differ across environment variants',
        rope_status='explicit exploratory candidate prior, not a team-approved formal analysis',
        source_expectation='full hash-verified development archive; no formal or demo tuning input')


def validate_plan(plan):
    """Only reviewed versioned presets run here; edited grids require a new preset."""
    if not isinstance(plan, dict):
        raise ValueError('Expected plan object')
    expected = make_plan(plan.get('stage'), plan.get('profile'), plan.get('source_run'))
    if json.dumps(plan, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError('Plan differs from the versioned development preset; formal/custom seeds are forbidden')
    return plan
