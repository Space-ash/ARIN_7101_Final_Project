"""E5 alias diagnostics on saved public questions and latest-evidence text.

Alias labels are analysis metadata only. This module never calls a selector,
changes its inputs, or generates dialogues. It reuses the dialogue-level grouping
and missing-stratum conventions of E3; all intervals remain exploratory.
"""
import re

import pandas as pd

from m4_analysis import ARMS, METRICS, SCENARIOS
from m4_temporal import (KEYS, QTYPES, _validated_points, _dialogue_groups,
                         _descriptive_summary, _paired_groups, _effect_summary,
                         _arm_shares)


ALIAS_COLUMNS = ['question_alias', 'evidence_alias']


def _metadata(ns, episodes, outcomes, cfg):
    episodes = list(episodes)
    observed_keys = set(outcomes[['scenario', 'seed']].itertuples(index=False, name=None))
    episode_keys = [(episode['scenario'], episode['seed']) for episode in episodes]
    if len(episode_keys) != len(set(episode_keys)) or set(episode_keys) != observed_keys:
        raise ValueError('Alias metadata episodes do not match the outcome dialogue grid')
    aliases = ns.get('M1_ATTRIBUTE_ALIASES')
    if (not isinstance(aliases, dict) or not aliases
            or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
                   for k, v in aliases.items())):
        raise ValueError('M1 attribute/alias mapping is required')
    mapping = {term.lower(): canonical.lower()
               for canonical, alias in aliases.items() for term in (canonical, alias)}
    if len(mapping) != 2 * len(aliases):
        raise ValueError('Attribute and alias surface forms must be distinct')
    alias_terms = {alias.lower() for alias in aliases.values()}
    terms = '|'.join(re.escape(term) for term in sorted(mapping, key=len, reverse=True))
    question_pattern = re.compile(r'(?<!\w)(?:' + terms + r')(?!\w)', re.I)
    fact_pattern = re.compile(r'^For project P\d+: the (?P<attribute>' + terms + r') is V\d+\.', re.I)
    records = []
    for episode in episodes:
        if len(episode['probes']) != cfg['T']:
            raise ValueError('Alias metadata dialogue length differs from cfg.T')
        audited = ns['audit_truth'](episode)
        if not audited.get('passed') or audited.get('question_count') != cfg['T']:
            raise ValueError('Alias metadata requires independently verified latest evidence')
        history = episode['history']
        for probe in episode['probes']:
            evidence_id = probe['evidence']
            if type(evidence_id) is not int or not 0 <= evidence_id < probe['end'] <= len(history):
                raise ValueError('Latest evidence must be inside the public prefix')
            evidence = history[evidence_id]
            if evidence['id'] != evidence_id:
                raise ValueError('Evidence IDs do not match history positions')
            matches = question_pattern.findall(probe['question'])
            fact = fact_pattern.match(evidence['text'])
            if len(matches) != 1 or fact is None:
                raise ValueError('Expected one attribute term in question and a structured latest fact')
            question_term, evidence_term = matches[0].lower(), fact.group('attribute').lower()
            if mapping[question_term] != mapping[evidence_term]:
                raise ValueError('Question attribute differs from latest-evidence attribute')
            records.append(dict(scenario=episode['scenario'], seed=int(episode['seed']),
                t=int(probe['t']), question=probe['question'], qtype=probe['qtype'],
                attribute=mapping[question_term], question_attribute_surface=question_term,
                evidence_attribute_surface=evidence_term,
                question_alias=question_term in alias_terms, evidence_alias=evidence_term in alias_terms,
                latest_evidence_id=evidence_id, latest_evidence_text=evidence['text'],
                public_history_end=probe['end']))
    metadata = pd.DataFrame(records).sort_values(KEYS).reset_index(drop=True)
    columns = KEYS + ['question', 'qtype']
    actual = outcomes[columns].drop_duplicates().sort_values(KEYS).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(metadata[columns], actual, check_dtype=False)
    except AssertionError as exc:
        raise ValueError('Episode question metadata differs from the four-arm table') from exc
    return metadata


def alias_analysis(ns, episodes, outcomes, replay, cfg, baselines):
    """Return alias strata, dialogue means, paired effects, and selected-arm shares.

    question_alias and evidence_alias describe the attribute's lexical surface
    form in the original question and its specified latest supporting statement.
    That evidence is first verified by M1's independent public-prefix truth audit.
    Algorithm seeds are averaged at each question, then questions within each
    dialogue/stratum. Missing strata remain explicit with zero questions and NaN
    metrics. Intervals use available independent dialogues, reporting both their
    count and the total; there is no interval with fewer than two observations.
    """
    if set(baselines) != set(SCENARIOS) or any(b not in ARMS for b in baselines.values()):
        raise ValueError('Both development-selected fixed baselines are required')
    selected = _validated_points(replay, outcomes, cfg)
    metadata = _metadata(ns, episodes, outcomes, cfg)
    selected = selected.merge(metadata[KEYS + ALIAS_COLUMNS], on=KEYS, validate='many_to_one')
    point_keys = KEYS + ['method', 'qtype', *ALIAS_COLUMNS]
    points = selected.groupby(point_keys, sort=True)[METRICS].mean().reset_index()
    levels = {'question_alias': (False, True), 'evidence_alias': (False, True), 'qtype': QTYPES}
    tables = {'alias_question_metadata': metadata}
    for name, group_columns in [('alias', ALIAS_COLUMNS), ('alias_query', ALIAS_COLUMNS + ['qtype'])]:
        grouped = _dialogue_groups(points, group_columns, levels)
        tables[name + '_episode_metrics'] = grouped
        tables[name + '_summary'] = _descriptive_summary(grouped, group_columns)
        differences = _paired_groups(grouped, baselines, group_columns)
        tables[name + '_paired_differences'] = differences
        effects = _effect_summary(differences, group_columns, cfg)
        effects['population'] = 'dialogues_containing_the_specified_alias_stratum'
        tables[name + '_effects'] = effects
        shares = _arm_shares(selected, group_columns, levels, cfg)
        tables['arm_choice_by_' + name] = shares
        tables['arm_choice_by_' + name + '_summary'] = shares.groupby(
            ['scenario', 'method', *group_columns, 'arm'], sort=True).agg(
                share=('share', 'mean'), n=('observed', 'sum'), n_total=('seed', 'size'),
                n_questions=('n_questions', 'sum')).reset_index()
    return tables
