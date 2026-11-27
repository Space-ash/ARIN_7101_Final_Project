"""Compare M2 delivered results with M4's independently archived development runs."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
import numpy as np
from test_member_handoff import ROOT
from verify_m2_development import main as verify_source


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    verify_source()
    handoff=ROOT/'team_workspace/m2_handoff'
    archive_path=handoff/'m2_to_m4_20261123.zip'
    with ZipFile(archive_path) as outer:
        archive=outer.read('m2_development_20261119.zip')
    with ZipFile(BytesIO(archive)) as inner:
        m2=pd.read_csv(BytesIO(inner.read('m2_development_20261119/tables/development_outcomes.csv')))
    default=ROOT/'outputs/development/m4_default_benchmark_20261123'
    candidates=ROOT/'outputs/development/m4_candidates_8_9_12_20261123'
    for run in [default,candidates]:
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in manifest['files'].items():
            if sha(run/name)!=digest:raise ValueError('Archive changed: '+name)
    m4=pd.read_csv(default/'tables/development_outcomes.csv')
    keys=['scenario','seed','t','arm'];columns=[c for c in m2.columns if c!='construction_ms']
    pd.testing.assert_frame_equal(m2[columns].sort_values(keys).reset_index(drop=True),m4[columns].sort_values(keys).reset_index(drop=True),check_dtype=False)
    supplied=pd.read_csv(handoff/'candidate_limits_by_dialogue.csv')
    recomputed=[];baselines={}
    for k in [8,9,12]:
        rows=pd.read_csv(candidates/f'k{k}/outcomes.csv')
        groups=rows.groupby(['scenario','seed','arm']).agg(n_questions=('y','size'),accuracy=('y','mean'),mean_cost=('cost','mean'),mean_utility=('utility','mean'),outdated_rate=('outdated','mean')).reset_index()
        groups['k']=k;recomputed.append(groups[groups.arm.isin(['tfidf','resolved_tfidf'])])
        scores=groups.groupby(['scenario','arm']).mean_utility.mean().unstack()
        baselines[str(k)]=scores.idxmax(axis=1).to_dict()
    expected=pd.concat(recomputed,ignore_index=True)
    index=['scenario','seed','arm','k']
    cols=['n_questions','accuracy','mean_cost','mean_utility','outdated_rate']
    pd.testing.assert_frame_equal(expected.set_index(index)[cols].sort_index(),supplied.set_index(index)[cols].sort_index(),check_dtype=False)
    paired=expected.merge(expected[expected.k==8][['scenario','seed','arm']+cols],on=['scenario','seed','arm'],suffixes=('','_8'),validate='many_to_one')
    for col in cols[1:]:
        actual=paired.set_index(index).sort_index()
        if not np.allclose(actual[col]-actual[col+'_8'], supplied.set_index(index).sort_index()['delta_'+col+'_vs_8']):
            raise ValueError('Candidate delta mismatch: '+col)
    assert all(b=={'abrupt':'resolved_tfidf','stable':'recent_short'} for b in baselines.values())
    review=pd.read_csv(handoff/'audit_review.csv').fillna('')
    record=dict(date='2026-11-25',status='technical_checks_passed_human_signoff_pending',
        checks=dict(full_outcome_rows=7200,questions=1800,reconstructed_audit_arms=40,candidate_dialogue_rows=len(expected),
                    full_outcomes_match=True,candidate_metrics_and_deltas_match=True),
        baselines_by_candidate=baselines,recommended_candidate_limit=8,
        human_review_counts=review.verdict.value_counts().to_dict(),
        hashes=dict(m2_outer_archive=sha(archive_path),m2_inner_archive=hashlib.sha256(archive).hexdigest(),
                    live_review=sha(handoff/'audit_review.csv'),m2_candidate_table=sha(handoff/'candidate_limits_by_dialogue.csv'),
                    m4_default_manifest=sha(default/'manifest.json'),m4_candidate_manifest=sha(candidates/'manifest.json')),
        scope='Automated technical acceptance; no human signatures, approval or formal execution generated.')
    output=ROOT/'deliverables/M4_M2_acceptance_20261125.json'
    if output.exists():raise FileExistsError(output)
    output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
