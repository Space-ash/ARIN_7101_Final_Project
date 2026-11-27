"""E3 temporal/stratified analysis and A7 hindsight-oracle diagnostics.

All resampling units are complete independent dialogues, after averaging
algorithm seeds. Intervals are exploratory; curve intervals are pointwise.
These functions neither generate data nor alter a formal protocol.
"""
import itertools

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, METRICS, SCENARIOS, validate_replay

KEYS = ['scenario', 'seed', 't']
QTYPES = ('recent', 'historical')
PHASES = ('pre', 'post')


def _validated_points(replay, outcomes, cfg, require_metadata=True):
    validate_replay(replay, outcomes, cfg)
    columns = list(KEYS)
    if require_metadata:
        if cfg['T'] < 2:
            raise ValueError('Temporal analysis requires at least two questions')
        if 'qtype' not in outcomes or not outcomes.qtype.isin(QTYPES).all():
            raise ValueError('Missing or unknown query types')
        if not outcomes.groupby(KEYS).qtype.nunique().eq(1).all():
            raise ValueError('Arms disagree about query type')
        columns.append('qtype')
    if 'state' in outcomes:
        if outcomes.state.isna().any() or not outcomes.groupby(KEYS).state.nunique().eq(1).all():
            raise ValueError('Missing or conflicting demand states')
        expected = np.where((outcomes.scenario == 'abrupt') & (outcomes.t >= cfg['T'] // 2), 'B', 'A')
        if not np.array_equal(outcomes.state.to_numpy(), expected):
            raise ValueError('Demand state does not match scenario/time boundary')
        columns.append('state')
    metadata = outcomes[columns].drop_duplicates()
    if metadata.duplicated(KEYS).any():
        raise ValueError('Nonunique question metadata')
    for column in set(columns) & set(replay.columns) - set(KEYS):
        checked = replay.merge(metadata[KEYS + [column]], on=KEYS,
                               suffixes=('', '_source'), validate='many_to_one')
        if not checked[column].eq(checked[column + '_source']).all():
            raise ValueError('Replay metadata differs from outcomes: ' + column)
    selected = replay.drop(columns=[c for c in columns if c not in KEYS and c in replay])
    selected = selected.merge(metadata, on=KEYS, validate='many_to_one')
    return selected.sort_values(KEYS + ['method', 'alg_seed']).reset_index(drop=True)


def _group_skeleton(points, group_columns, levels):
    dialogues = points[['scenario', 'seed']].drop_duplicates().sort_values(['scenario', 'seed'])
    return pd.DataFrame([
        (scenario, int(seed), method, *group)
        for scenario, seed in dialogues.itertuples(index=False, name=None)
        for method in METHODS
        for group in itertools.product(*(levels[c] for c in group_columns))
    ], columns=['scenario', 'seed', 'method', *group_columns])


def _dialogue_groups(points, group_columns, levels):
    keys = ['scenario', 'seed', 'method', *group_columns]
    grouped = points.groupby(keys, sort=True)[METRICS].mean().reset_index()
    counts = points.groupby(keys, sort=True).size().rename('n_questions').reset_index()
    table = _group_skeleton(points, group_columns, levels).merge(grouped, on=keys, how='left', validate='one_to_one')
    table = table.merge(counts, on=keys, how='left', validate='one_to_one')
    table['n_questions'] = table.n_questions.fillna(0).astype(int)
    table['observed'] = table.n_questions.gt(0)
    return table.sort_values(keys).reset_index(drop=True)


def _descriptive_summary(frame, group_columns):
    keys = ['scenario', 'method', *group_columns]
    groups = frame.groupby(keys, sort=True, dropna=False)
    means = groups[METRICS].mean()
    counts = groups.agg(n_total=('seed', 'size'), n=('observed', 'sum'),
                        n_questions=('n_questions', 'sum'))
    counts['n_missing'] = counts.n_total - counts.n
    return means.join(counts).reset_index()


def _paired_groups(frame, baselines, group_columns):
    keys = ['scenario', 'seed', *group_columns]
    parts = []
    for scenario in SCENARIOS:
        subset = frame[frame.scenario == scenario]
        cts = subset[subset.method == 'LaplaceCTS']
        for comparison, reference in [('cts_vs_fixed', baselines[scenario]),
                                      ('cts_vs_ts', 'TS'), ('cts_vs_router', 'RuleRouter')]:
            joined = cts.merge(subset[subset.method == reference], on=keys,
                               suffixes=('_cts', '_reference'), validate='one_to_one')
            if len(joined) != len(cts) or not joined.n_questions_cts.eq(joined.n_questions_reference).all():
                raise ValueError('Inconsistent paired subgroup questions')
            result = joined[keys].copy()
            result['comparison'], result['reference'] = comparison, reference
            result['n_questions'] = joined.n_questions_cts
            for metric in METRICS:
                result['delta_' + metric] = joined[metric + '_cts'] - joined[metric + '_reference']
            parts.append(result)
    return pd.concat(parts, ignore_index=True).sort_values(
        ['scenario', 'comparison', 'seed', *group_columns]).reset_index(drop=True)


def _effect_summary(differences, group_columns, cfg, pointwise=False):
    keys = ['scenario', 'comparison', 'reference', *group_columns]
    rng = np.random.default_rng(cfg['bootstrap_seed'])
    rows = []
    for group_key, group in differences.groupby(keys, sort=True, dropna=False):
        group = group.sort_values('seed')
        values = group[['delta_' + metric for metric in METRICS]].to_numpy(dtype=float)
        present = np.isfinite(values).all(axis=1)
        if np.any(np.isfinite(values).any(axis=1) != present):
            raise ValueError('Partially missing subgroup metrics')
        values = values[present]
        n = len(values)
        if n >= 2:
            indices = rng.integers(0, n, size=(cfg['n_bootstrap'], n))
            draws = values[indices].mean(axis=1)
            low, high = np.quantile(draws, [.025, .975], axis=0)
        else:
            low = high = np.full(len(METRICS), np.nan)
        means = values.mean(axis=0) if n else np.full(len(METRICS), np.nan)
        for index, metric in enumerate(METRICS):
            rows.append(dict(zip(keys, group_key), metric=metric, n=n, n_total=len(group),
                n_missing=len(group)-n, n_questions=int(group.loc[present, 'n_questions'].sum()),
                effect=means[index], low=low[index], high=high[index], confidence=.95,
                interpretation='exploratory', interval_scope='pointwise' if pointwise else 'groupwise',
                simultaneous=False, status='estimated' if n >= 2 else 'insufficient_dialogues'))
    return pd.DataFrame(rows)


def _curve_summary(curves, identity_columns, value, cfg):
    """Shared dialogue weights across time retain each bootstrap trajectory."""
    rng = np.random.default_rng(cfg['bootstrap_seed'])
    rows = []
    for key, group in curves.groupby(identity_columns, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        matrix = group.pivot(index='seed', columns='t', values=value).sort_index().sort_index(axis=1)
        if matrix.isna().any().any() or list(matrix.columns) != list(range(cfg['T'])):
            raise ValueError('Incomplete dialogue curve grid')
        values, n = matrix.to_numpy(dtype=float), len(matrix)
        if n >= 2:
            weights = rng.multinomial(n, np.full(n, 1. / n), size=cfg['n_bootstrap']) / n
            samples = weights @ values
            low, high = np.quantile(samples, [.025, .975], axis=0)
        else:
            low = high = np.full(cfg['T'], np.nan)
        for i, t in enumerate(matrix.columns):
            rows.append(dict(zip(identity_columns, key), t=int(t), n=n,
                effect=float(values[:, i].mean()), low=low[i], high=high[i], confidence=.95,
                interpretation='exploratory', interval_scope='pointwise', simultaneous=False,
                status='estimated' if n >= 2 else 'insufficient_dialogues'))
    return pd.DataFrame(rows)


def _arm_shares(selected, group_columns, levels, cfg):
    keys = ['scenario', 'seed', 'method', *group_columns]
    counts = selected.groupby(keys + ['arm'], sort=True).size().rename('selected_count').reset_index()
    denominators = selected.groupby(keys).size().rename('total_choices').reset_index()
    skeleton = _group_skeleton(selected, group_columns, levels)
    skeleton = skeleton.merge(pd.DataFrame({'arm': ARMS}), how='cross')
    table = skeleton.merge(counts, on=keys + ['arm'], how='left', validate='one_to_one')
    table = table.merge(denominators, on=keys, how='left', validate='many_to_one')
    table['n_questions'] = (table.total_choices.fillna(0) / len(cfg['algorithm_seeds'])).astype(int)
    table['n_algorithm_seeds'] = len(cfg['algorithm_seeds'])
    table['share'] = table.selected_count.fillna(0) / table.total_choices
    table['observed'] = table.n_questions.gt(0)
    # A known zero arm share is valid only when this query/phase group exists.
    table.loc[~table.observed, 'share'] = np.nan
    return table.drop(columns=['selected_count', 'total_choices']).sort_values(keys + ['arm']).reset_index(drop=True)


def temporal_analysis(replay, outcomes, baselines, cfg, window_size=25):
    """Return E3 tables; defaults are T//2 phases and nonoverlapping 25-question windows.

    Empty query strata are explicit rows with n_questions=0 and NaN metrics.
    Group summaries average available dialogue means rather than pooling queries.
    The independent dialogue count in every interval excludes algorithm seeds.
    """
    if type(window_size) is not int or window_size < 1:
        raise ValueError('window_size must be a positive integer')
    if set(baselines) != set(SCENARIOS) or any(b not in ARMS for b in baselines.values()):
        raise ValueError('Both development-selected fixed baselines required')
    selected = _validated_points(replay, outcomes, cfg)
    selected['phase'] = np.where(selected.t < cfg['T'] // 2, 'pre', 'post')
    selected['window'] = selected.t // window_size
    point_keys = KEYS + ['method', 'qtype', 'phase', 'window']
    points = selected.groupby(point_keys, sort=True)[METRICS].mean().reset_index()
    levels = {'phase': PHASES, 'qtype': QTYPES,
              'window': tuple(range((cfg['T'] + window_size - 1) // window_size))}
    tables = {}
    for name, group_columns in [('phase', ['phase']), ('query', ['qtype']),
                                ('phase_query', ['phase', 'qtype']), ('window', ['window'])]:
        frame = _dialogue_groups(points, group_columns, levels)
        if name == 'window':
            frame['start_t'] = frame.window * window_size
            frame['end_t'] = np.minimum(frame.start_t + window_size - 1, cfg['T'] - 1)
        tables[name + '_episode_metrics'] = frame
        tables[name + '_summary'] = _descriptive_summary(frame, group_columns)
        differences = _paired_groups(frame, baselines, group_columns)
        tables[name + '_paired_differences'] = differences
        tables[name + '_effects'] = _effect_summary(differences, group_columns, cfg, pointwise=name == 'window')

    phase = tables['phase_paired_differences']
    pair_keys = ['scenario', 'seed', 'comparison', 'reference']
    paired = phase[phase.phase == 'post'].merge(phase[phase.phase == 'pre'], on=pair_keys,
                                              suffixes=('_post', '_pre'), validate='one_to_one')
    post_pre = paired[pair_keys].copy()
    for metric in METRICS:
        post_pre['delta_' + metric] = paired['delta_' + metric + '_post'] - paired['delta_' + metric + '_pre']
    post_pre['n_questions'] = paired.n_questions_post + paired.n_questions_pre
    tables['post_pre_dialogue_differences'] = post_pre
    tables['post_pre_effects'] = _effect_summary(post_pre, [], cfg)

    instantaneous = points.copy()
    instantaneous['n_questions'] = 1
    differences = _paired_groups(instantaneous, baselines, ['t'])
    differences = differences.sort_values(pair_keys + ['t'])
    differences['cumulative_delta_utility'] = differences.groupby(pair_keys).delta_utility.cumsum()
    curves = differences[pair_keys + ['t', 'delta_utility', 'cumulative_delta_utility']].reset_index(drop=True)
    tables['cumulative_dialogue_differences'] = curves
    tables['cumulative_effects'] = _curve_summary(curves, ['scenario', 'comparison', 'reference'],
                                                 'cumulative_delta_utility', cfg)
    for name, group_columns in [('query', ['qtype']), ('phase_query', ['phase', 'qtype'])]:
        shares = _arm_shares(selected, group_columns, levels, cfg)
        tables['arm_choice_by_' + name] = shares
        tables['arm_choice_by_' + name + '_summary'] = shares.groupby(
            ['scenario', 'method', *group_columns, 'arm'], sort=True).agg(
                share=('share', 'mean'), n=('observed', 'sum'), n_total=('seed', 'size'),
                n_questions=('n_questions', 'sum')).reset_index()
    return tables


def oracle_analysis(replay, outcomes, cfg):
    """Return A7 realized hindsight-oracle gaps, never theoretical regret."""
    selected = _validated_points(replay, outcomes, cfg, require_metadata=False)
    oracle = outcomes.groupby(KEYS, sort=True).utility.max().rename('oracle_utility').reset_index()
    selected = selected.merge(oracle, on=KEYS, validate='many_to_one')
    selected['oracle_gap'] = selected.oracle_utility - selected.utility
    if (selected.oracle_gap < -1e-12).any():
        raise ValueError('Selected utility exceeds the four-arm oracle')
    selected['oracle_gap'] = selected.oracle_gap.clip(lower=0)
    trajectory_keys = ['scenario', 'seed', 'method', 'alg_seed']
    selected = selected.sort_values(trajectory_keys + ['t'])
    selected['cumulative_oracle_gap'] = selected.groupby(trajectory_keys).oracle_gap.cumsum()
    trajectories = selected[trajectory_keys + ['t', 'arm', 'oracle_utility', 'utility',
                                               'oracle_gap', 'cumulative_oracle_gap']].reset_index(drop=True)
    curves = trajectories.groupby(['scenario', 'seed', 'method', 't'], sort=True)[
        ['oracle_gap', 'cumulative_oracle_gap']].mean().reset_index()
    curves['n_algorithm_seeds'] = len(cfg['algorithm_seeds'])
    summary = _curve_summary(curves, ['scenario', 'method'], 'cumulative_oracle_gap', cfg)
    summary['reference'] = 'per_question_hindsight_oracle'
    summary['interpretation'] = 'descriptive_not_theoretical_regret'
    episode_metrics = curves[curves.t == cfg['T'] - 1].drop(columns=['t', 'oracle_gap']).copy()
    episode_metrics['mean_oracle_gap'] = episode_metrics.cumulative_oracle_gap / cfg['T']
    return {'oracle_trajectory_gaps': trajectories, 'oracle_dialogue_curves': curves,
            'oracle_episode_metrics': episode_metrics.reset_index(drop=True),
            'oracle_cumulative_summary': summary}
