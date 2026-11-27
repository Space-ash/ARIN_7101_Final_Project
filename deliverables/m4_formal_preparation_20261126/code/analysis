"""Dialogue-level supplemental comparisons for M4 experiment E1.

The notebook's two primary utility comparisons remain unchanged. Intervals
here concern CTS versus TS/RuleRouter and are exploratory, not family adjusted.
"""
import numpy as np
import pandas as pd

ARMS = ('recent_short', 'recent_long', 'tfidf', 'resolved_tfidf')
METHODS = ARMS + ('TS', 'LaplaceCTS', 'RuleRouter')
SCENARIOS = ('stable', 'abrupt')
METRICS = ['y', 'cost', 'utility', 'coverage', 'outdated']


def _check_config(cfg):
    for name in ['T', 'n_bootstrap']:
        if type(cfg.get(name)) is not int or cfg[name] < 1:
            raise ValueError('Invalid positive integer: ' + name)
    if type(cfg.get('bootstrap_seed')) is not int or cfg['bootstrap_seed'] < 0:
        raise ValueError('Invalid bootstrap seed')
    seeds = cfg.get('algorithm_seeds')
    if (not isinstance(seeds, list) or not seeds
            or any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError('Invalid or duplicate algorithm seeds')
    for name in ['lambda', 'cost_reference']:
        value = cfg.get(name)
        if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
            raise ValueError('Invalid cost parameter: ' + name)
    if cfg['cost_reference'] == 0:
        raise ValueError('Cost reference must be positive')


def _check_frame(frame, keys, metrics=METRICS):
    required = list(dict.fromkeys([*keys, *metrics]))
    if frame.empty or not set(required).issubset(frame.columns):
        raise ValueError('Empty table or missing columns')
    if frame[required].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError('Missing values or duplicate keys')
    if not np.isfinite(frame[list(metrics)].to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite metrics')


def _check_values(frame, cfg, binary=True):
    for name in ['y', 'coverage', 'outdated']:
        valid = frame[name].isin([0, 1]) if binary else frame[name].between(0, 1)
        if not valid.all():
            raise ValueError('Invalid probability/binary outcome: ' + name)
    if (frame.cost < 0).any():
        raise ValueError('Negative input cost')
    expected = frame.y - cfg['lambda'] * frame.cost / cfg['cost_reference']
    if not np.allclose(frame.utility, expected, rtol=0, atol=1e-12):
        raise ValueError('Utility does not match accuracy and cost')


def validate_outcomes(frame, cfg, expected_seeds):
    _check_config(cfg)
    keys = ['scenario', 'seed', 't', 'arm']
    _check_frame(frame, keys)
    _check_values(frame, cfg)
    if set(expected_seeds) != set(SCENARIOS) or any(not group for group in expected_seeds.values()):
        raise ValueError('Both scenarios are required')
    seeds = [s for group in expected_seeds.values() for s in group]
    if any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError('Invalid or colliding dialogue seeds')
    expected = {(sc, s, t, a) for sc, group in expected_seeds.items()
                for s in group for t in range(cfg['T']) for a in ARMS}
    if set(frame[keys].itertuples(index=False, name=None)) != expected:
        raise ValueError('Incomplete or unexpected four-arm grid')
    if 'question' not in frame or frame.question.isna().any():
        raise ValueError('Missing public questions')
    if not frame.groupby(['scenario', 'seed', 't']).question.nunique().eq(1).all():
        raise ValueError('Arms do not share the same question')


def validate_replay(replay, outcomes, cfg):
    _check_config(cfg)
    keys = ['scenario', 'seed', 't', 'method', 'alg_seed']
    _check_frame(replay, keys)
    _check_values(replay, cfg)
    expected_seeds = {sc: sorted(map(int, outcomes.loc[outcomes.scenario == sc, 'seed'].unique()))
                      for sc in SCENARIOS}
    validate_outcomes(outcomes, cfg, expected_seeds)
    expected = {(sc, s, t, method, alg) for sc, group in expected_seeds.items()
                for s in group for t in range(cfg['T'])
                for method in METHODS for alg in cfg['algorithm_seeds']}
    if set(replay[keys].itertuples(index=False, name=None)) != expected:
        raise ValueError('Incomplete or unexpected replay grid')
    if 'arm' not in replay or not replay.arm.isin(ARMS).all():
        raise ValueError('Unknown selected arm')
    fixed = replay.method.isin(ARMS)
    if not replay.loc[fixed, 'method'].eq(replay.loc[fixed, 'arm']).all():
        raise ValueError('Fixed method changed its arm')
    joined = replay.merge(outcomes[['scenario', 'seed', 't', 'arm', *METRICS]],
                          on=['scenario', 'seed', 't', 'arm'], how='left',
                          suffixes=('', '_source'), validate='many_to_one')
    for metric in METRICS:
        if not np.allclose(joined[metric], joined[metric + '_source'], rtol=0, atol=1e-12):
            raise ValueError('Selected result mismatch: ' + metric)


def aggregate_dialogues(replay):
    _check_frame(replay, ['scenario', 'seed', 't', 'method', 'alg_seed'])
    trajectories = replay.groupby(['scenario', 'seed', 'method', 'alg_seed'])[METRICS].mean()
    return trajectories.groupby(['scenario', 'seed', 'method']).mean().reset_index()


def paired_comparisons(metrics, baselines, cfg):
    """Return all three paired differences and two exploratory contrast CIs.

    One sorted dialogue index draw per scenario is shared across metrics and
    direct comparisons. CI endpoints themselves are not additive. Fixed-arm
    utility intervals are produced by the original notebook function instead.
    """
    _check_config(cfg)
    _check_frame(metrics, ['scenario', 'seed', 'method'])
    _check_values(metrics, cfg, binary=False)
    if set(metrics.scenario) != set(SCENARIOS) or set(baselines) != set(SCENARIOS):
        raise ValueError('Both scenarios and fixed baselines required')
    if any(b not in ARMS for b in baselines.values()):
        raise ValueError('Baseline must be a fixed arm')
    count = cfg['n_bootstrap']
    if type(count) is not int or count < 1:
        raise ValueError('n_bootstrap must be a positive integer')
    rng = np.random.default_rng(cfg['bootstrap_seed'])
    all_differences, all_effects = [], []
    for scenario in SCENARIOS:
        frame = metrics[metrics.scenario == scenario]
        seeds = sorted(frame.seed.unique())
        if len(seeds) < 2:
            raise ValueError('At least two independent dialogues required')
        expected = {(s, m) for s in seeds for m in METHODS}
        if set(frame[['seed', 'method']].itertuples(index=False, name=None)) != expected:
            raise ValueError('Incomplete paired dialogue methods')
        indices = rng.integers(0, len(seeds), size=(count, len(seeds)))
        cts = frame[frame.method == 'LaplaceCTS'].set_index('seed').loc[seeds, METRICS]
        comparisons = [('cts_vs_fixed', baselines[scenario]),
                       ('cts_vs_ts', 'TS'), ('cts_vs_router', 'RuleRouter')]
        for comparison, reference in comparisons:
            control = frame[frame.method == reference].set_index('seed').loc[seeds, METRICS]
            delta = cts.to_numpy() - control.to_numpy()
            if not np.allclose(delta[:, 2], delta[:, 0] - cfg['lambda'] * delta[:, 1] / cfg['cost_reference'],
                               rtol=0, atol=1e-12):
                raise ValueError('Paired utility decomposition failed')
            for seed, values in zip(seeds, delta):
                all_differences.append(dict(scenario=scenario, seed=int(seed),
                    comparison=comparison, reference=reference,
                    **{'delta_' + m: float(v) for m, v in zip(METRICS, values)}))
            if comparison == 'cts_vs_fixed':
                continue
            samples = delta[indices].mean(axis=1)
            if not np.allclose(samples[:, 2], samples[:, 0] - cfg['lambda'] * samples[:, 1] / cfg['cost_reference'],
                               rtol=0, atol=1e-12):
                raise ValueError('Bootstrap utility decomposition failed')
            for i, metric in enumerate(METRICS):
                low, high = np.quantile(samples[:, i], [.025, .975])
                all_effects.append(dict(scenario=scenario, comparison=comparison,
                    reference=reference, metric=metric, n=len(seeds), effect=float(delta[:, i].mean()),
                    low=float(low), high=float(high), family_low=np.nan, family_high=np.nan))
    return pd.DataFrame(all_differences), pd.DataFrame(all_effects)
