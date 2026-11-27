"""E0 implementation checks against public-prefix execution and stored replay.

The input tables must be complete development/fixture data. This module writes
no files, creates no formal runs, and produces no human approvals. It reconstructs
every supplied four-arm outcome, then checks complete online/table trajectories
for the first dialogue of each scenario (all methods and algorithm seeds).
"""
from copy import deepcopy

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, METRICS, SCENARIOS, validate_replay
from test_member_handoff import m1 as handoff_m1, m2 as handoff_m2, m3 as handoff_m3


STATE_FIELDS = ('mean', 'covariance', 'successes', 'failures', 'features', 'rewards')
OUTCOME_KEYS = ['scenario', 'seed', 't', 'arm']
OUTCOME_FIELDS = ['question', 'qtype', 'state', *METRICS]
REPLAY_KEYS = ['scenario', 'seed', 't', 'method', 'alg_seed']


def _same_state(online, table, context):
    """Compare learned state, including unselected arms, after every operation."""
    for name in STATE_FIELDS:
        if not hasattr(online, name) or not hasattr(table, name):
            raise ValueError('Selector is missing a required state field: ' + name)
        left, right = getattr(online, name), getattr(table, name)
        if name in ('features', 'rewards'):
            if len(left) != len(right) or any(len(a) != len(b) for a, b in zip(left, right)):
                raise ValueError(f'Selector state mismatch ({name}, {context})')
            pairs = zip(left, right)
        else:
            pairs = [(left, right)]
        for first, second in pairs:
            try:
                np.testing.assert_allclose(np.asarray(first, dtype=float),
                    np.asarray(second, dtype=float), rtol=0, atol=1e-12)
            except AssertionError as exc:
                raise ValueError(f'Selector state mismatch ({name}, {context})') from exc
    for name in ('selected_counts', 'refit_counts'):
        if hasattr(online, name) or hasattr(table, name):
            if not np.array_equal(getattr(online, name, None), getattr(table, name, None)):
                raise ValueError(f'Selector diagnostic mismatch ({name}, {context})')
    if online.rng.bit_generator.state != table.rng.bit_generator.state:
        raise ValueError('Selector RNG state mismatch: ' + context)


def _public_view(ns, episode, probe):
    view = ns['public_view'](episode, probe)
    expected = {'question': probe['question'], 'history': [
        {'id': message['id'], 'text': message['text']}
        for message in episode['history'][:probe['end']]]}
    if view != expected or set(view) != {'question', 'history'}:
        raise ValueError('Public view contains future or hidden information')
    future = dict(episode, history=[*episode['history'],
        {'id': len(episode['history']), 'text': 'FUTURE E0 SENTINEL: this message is not yet visible.'}])
    if ns['public_view'](future, probe) != view:
        raise ValueError('Future appended history changed the public view')
    return view


def _construct_current_arms(ns, episode, probe, cfg):
    """Independently assemble the evaluation fields without evaluate_episode."""
    view = _public_view(ns, episode, probe)
    preserved = deepcopy(view)
    rows = []
    for arm in ARMS:
        context = ns['select_context'](view, arm, cfg)
        if view != preserved:
            raise ValueError('Context construction mutated the public input')
        ids = [message['id'] for message in context]
        visible = {message['id']: message for message in view['history']}
        if (ids != sorted(set(ids)) or any(
                identifier not in visible or message != visible[identifier]
                for identifier, message in zip(ids, context))):
            raise ValueError('Context contains altered, duplicate, or nonpublic messages')
        if ns['count_input_units'](ns['m2_context_text'](context)) > cfg['budgets'][arm]:
            raise ValueError('Context exceeds its body budget')
        answer = ns['rule_reader'](view['question'], context)
        cost = ns['count_input_units'](ns['m2_build_prompt'](view['question'], context))
        reward = int(answer == probe['gold'])
        rows.append(dict(scenario=episode['scenario'], seed=int(episode['seed']),
            t=int(probe['t']), arm=arm, question=view['question'], qtype=probe['qtype'],
            state=probe['state'], y=reward, cost=cost,
            utility=reward-cfg['lambda']*cost/cfg['cost_reference'],
            coverage=int(probe['evidence'] in ids), outdated=int(answer in probe['old_values'])))
    return pd.DataFrame(rows).set_index('arm').loc[list(ARMS)]


def _compare_outcome(constructed, stored, context):
    for name in ('question', 'qtype', 'state'):
        if not constructed[name].equals(stored[name]):
            raise ValueError(f'Reconstructed outcome metadata differs ({name}, {context})')
    for name in METRICS:
        if not np.allclose(constructed[name].to_numpy(dtype=float),
                           stored[name].to_numpy(dtype=float), rtol=0, atol=1e-12):
            raise ValueError(f'Reconstructed outcome differs ({name}, {context})')


def _compare_replay_row(constructed, stored, selected_arm, context):
    if stored.arm != selected_arm:
        raise ValueError('Stored replay selected a different arm: ' + context)
    for name in METRICS:
        if not np.isclose(float(constructed[name]), float(stored[name]), rtol=0, atol=1e-12):
            raise ValueError(f'Stored replay differs ({name}, {context})')


def validate_pipeline(ns, episodes, outcomes, replay, cfg):
    """Validate E0 without writing files or altering the caller's inputs.

    Every supplied dialogue is truth-audited and every four-arm row reconstructed.
    Two selectors are independently advanced at every question for one complete
    dialogue per scenario, all seven methods, and every configured algorithm seed.
    They see only question/costs and their own selected binary feedback. Learned
    state is checked initially, after choose, and after update. The trajectory is
    also checked against the supplied replay. Timing fields are intentionally not
    compared. The return value records the exact scope, not a formal approval.
    """
    validate_replay(replay, outcomes, cfg)
    missing = set(OUTCOME_FIELDS) - set(outcomes.columns)
    if missing:
        raise ValueError('E0 requires complete question metadata: ' + ', '.join(sorted(missing)))
    episodes = list(episodes)
    episode_keys = [(episode['scenario'], episode['seed']) for episode in episodes]
    table_keys = set(outcomes[['scenario', 'seed']].itertuples(index=False, name=None))
    if len(episode_keys) != len(set(episode_keys)) or set(episode_keys) != table_keys:
        raise ValueError('Episodes do not match the outcome dialogue grid')
    if any(len(episode['probes']) != cfg['T'] for episode in episodes):
        raise ValueError('Episode question count differs from cfg.T')
    untouched_episodes, untouched_cfg = deepcopy(episodes), deepcopy(cfg)
    checked_outcomes = outcomes.copy(deep=True)
    checked_replay = replay.copy(deep=True)
    selected_keys = {(scenario, min(seed for sc, seed in episode_keys if sc == scenario))
                     for scenario in SCENARIOS}
    table_index = outcomes.set_index(OUTCOME_KEYS).sort_index()
    replay_index = replay.set_index(REPLAY_KEYS).sort_index()
    truth_checks, scope = [], []
    comparisons, state_comparisons = 0, 0
    for episode in sorted(episodes, key=lambda row: (row['scenario'], row['seed'])):
        scenario, seed = episode['scenario'], int(episode['seed'])
        check = ns['audit_truth'](episode)
        if not check.get('passed') or check.get('question_count') != cfg['T']:
            raise ValueError(f'Independent truth audit failed for {scenario}/{seed}')
        truth_checks.append(dict(scenario=scenario, seed=seed, passed=True,
                                 question_count=check['question_count']))
        selectors = []
        if (scenario, seed) in selected_keys:
            for method in METHODS:
                for algorithm_seed in cfg['algorithm_seeds']:
                    online = ns['Selector'](method, algorithm_seed, cfg)
                    table = ns['Selector'](method, algorithm_seed, cfg)
                    _same_state(online, table, f'{scenario}/{seed}/{method}/{algorithm_seed}/initial')
                    state_comparisons += 1
                    selectors.append((method, algorithm_seed, online, table))
            scope.append(dict(scenario=scenario, seed=seed, questions=cfg['T']))
        for probe in episode['probes']:
            t = int(probe['t'])
            context = f'{scenario}/{seed}/{t}'
            constructed = _construct_current_arms(ns, episode, probe, cfg)
            stored = table_index.loc[(scenario, seed, t)].loc[list(ARMS)]
            _compare_outcome(constructed, stored, context)
            for method, algorithm_seed, online, table in selectors:
                label = f'{context}/{method}/{algorithm_seed}'
                online_index = online.choose(probe['question'], constructed.cost.to_numpy(dtype=float))
                table_arm_index = table.choose(stored.question.iloc[0], stored.cost.to_numpy(dtype=float))
                if online_index != table_arm_index:
                    raise ValueError('Online/table action mismatch: ' + label)
                _same_state(online, table, label + '/choose')
                arm = ARMS[online_index]
                online_result, table_result = constructed.loc[arm], stored.loc[arm]
                online_reward, table_reward = int(online_result.y), int(table_result.y)
                if online_reward != table_reward:
                    raise ValueError('Online/table selected feedback mismatch: ' + label)
                online.update(online_index, online_reward, probe['question'])
                table.update(table_arm_index, table_reward, stored.question.iloc[0])
                _same_state(online, table, label + '/update')
                stored_replay = replay_index.loc[(scenario, seed, t, method, algorithm_seed)]
                _compare_replay_row(online_result, stored_replay, arm, label)
                comparisons += 1
                state_comparisons += 2

    # Existing independently authored fixtures remain distinct from these source
    # checks. Their declared fixed fixture seeds are never formal candidate seeds.
    handoff_m1(ns)
    handoff_m2(ns)
    handoff_m3(ns)
    method_checks = []
    for scenario, seed in sorted(selected_keys):
        group = outcomes[(outcomes.scenario == scenario) & (outcomes.seed == seed)]
        checks, checked = ns['run_m3_method_checks'](group, cfg)
        original = replay[(replay.scenario == scenario) & (replay.seed == seed)]
        try:
            pd.testing.assert_frame_equal(checked.sort_values(REPLAY_KEYS).reset_index(drop=True),
                original[checked.columns].sort_values(REPLAY_KEYS).reset_index(drop=True),
                check_dtype=False, check_exact=False, rtol=0, atol=1e-12)
        except AssertionError as exc:
            raise ValueError('Method-check replay differs from supplied trajectory') from exc
        method_checks.append(dict(scenario=scenario, seed=seed, **checks))
    if episodes != untouched_episodes or cfg != untouched_cfg:
        raise ValueError('Validation mutated supplied episodes or configuration')
    pd.testing.assert_frame_equal(outcomes, checked_outcomes)
    pd.testing.assert_frame_equal(replay, checked_replay)
    return {
        'status': 'passed', 'formal_generated': False, 'human_approval_generated': False,
        'interpretation': 'implementation_correctness_checks_not_effectiveness_or_human_acceptance',
        'truth_checks': truth_checks,
        'four_arm_reconstruction': {
            'dialogues': len(episodes), 'questions': len(episodes)*cfg['T'], 'rows': len(outcomes),
            'compared_fields': OUTCOME_FIELDS, 'excluded_fields': ['construction_ms'],
            'public_prefix_only': True, 'future_history_invariance': 'passed'},
        'online_table_equivalence': {
            'scope_rule': 'first_seed_per_scenario_complete_dialogue', 'dialogues': scope,
            'methods': list(METHODS), 'algorithm_seeds': list(cfg['algorithm_seeds']),
            'question_method_seed_steps': comparisons, 'state_comparisons': state_comparisons,
            'state_fields': list(STATE_FIELDS), 'rng_state_compared': True,
            'stored_replay_matched': True},
        'member_handoff_fixtures': {'m1': 'passed', 'm2': 'passed', 'm3': 'passed',
                                   'fixture_dialogue_seeds': [910001, 910002, 910003]},
        'method_checks': method_checks,
    }
