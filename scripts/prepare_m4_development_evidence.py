"""Regenerate development evidence and verify the pending M1 review; no approvals."""
import argparse
import json
import subprocess
from io import BytesIO
from pathlib import Path
import pandas as pd
from test_member_handoff import ROOT, load
from m4_protocol import digest, canonical_hash, write_new, validate_config, validate_evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--m1-ref',default='origin/m1-review-20261125')
    args=parser.parse_args()
    if not args.run_id.replace('_','').replace('-','').isalnum():raise ValueError('Invalid run ID')
    dest=ROOT/'outputs/development'/args.run_id
    dest.mkdir(parents=True,exist_ok=False)
    notebook=ROOT/'ARIN7101_Context_Bandit_Release_Notebook.ipynb'
    source_hash=digest(notebook)
    commit=subprocess.check_output(['git','rev-parse',args.m1_ref],cwd=ROOT,text=True).strip()
    def upstream(path):return subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)
    for name,path in [('audit_review.csv','team_workspace/m2_handoff/audit_review.csv'),('M1_review.md','deliverables/M1_review_20261123.md')]:
        (dest/name).write_bytes(upstream(path))
    review=pd.read_csv(dest/'audit_review.csv',keep_default_na=False)
    ns=load(notebook,'m2');cfg=dict(ns['PROTOCOL_DRAFT']);validate_config(cfg)
    ns['display']=lambda *a:None
    nb=json.loads(notebook.read_text(encoding='utf-8'))
    for cell in nb['cells']:
        if cell.get('id') in ['m2-checks-workspace','m2-isolation-and-version-checks']:
            exec(''.join(cell['source']),ns)
    print('M2 fixture checks passed.',flush=True)
    episodes=[ns['generate_episode'](130000+100*s+i,scenario,cfg) for s,scenario in enumerate(['stable','abrupt']) for i in range(cfg['n_dev_per_scenario'])]
    truth=[ns['audit_truth'](e) for e in episodes]
    assert all(x['passed'] for x in truth)
    frames=[]
    for e in episodes:
        frames.append(ns['evaluate_episode'](e,cfg));print('Recomputed',e['seed'],flush=True)
    outcomes=pd.concat(frames,ignore_index=True)
    ns['m2_validate_development_outcomes'](episodes,outcomes,cfg)
    examples=ns['m2_build_audit_examples'](episodes,outcomes,cfg,ns['M2_DEVELOPMENT_AUDIT_KEYS'])
    original=json.loads((ROOT/'team_workspace/m2_handoff/audit_examples.json').read_bytes())['questions']
    assert examples==original
    assert len(review)==10 and not review.duplicated(['seed','t']).any()
    assert set(zip(review.seed,review.t))==set(ns['M2_DEVELOPMENT_AUDIT_KEYS'])
    assert review[['m1_reviewer','m2_reviewer','m1_notes','m2_notes']].apply(lambda c:c.str.strip().ne('')).all().all()
    assert review.verdict.eq('pending').all()
    report=(dest/'M1_review.md').read_text(encoding='utf-8')
    for q in examples:
        assert f"{q['seed']}/{q['t']}" in report
    # Verify every numeric cell of M1's two Markdown summary tables.
    lines=[line for line in report.splitlines() if line.startswith('| ') and '/' in line.split('|')[1]]
    by_key={f"{q['seed']}/{q['t']}":q for q in examples}
    checked=0
    for line in lines:
        fields=[v.strip() for v in line.strip('|').split('|')]
        if fields[0] not in by_key:continue
        q=by_key[fields[0]]
        if len(fields)==9:
            assert fields[1]==f"0–{q['end']-1}" and fields[4]==q['gold']
            assert int(fields[5])==q['evidence'] and int(fields[6])==len(q['old_values'])
            assert fields[7]==q['qtype']+'/'+q['state']
        elif len(fields)==5:
            for value,arm in zip(fields[1:],q['arms']):
                assert value==f"{arm['y']}/{arm['coverage']}/{arm['outdated']}；{arm['cost']}"
        else:raise ValueError('Unexpected M1 table')
        checked+=1
    assert checked==20
    print('M1 tables and 40 audit arms verified; verdicts remain pending.',flush=True)
    outcomes.to_csv(dest/'development_outcomes.csv',index=False)
    m3=load(notebook,'m3')
    methods,replay=m3['run_m3_method_checks'](outcomes[outcomes.seed==130100].copy(),cfg)
    methods['source']=dict(seed=130100,scenario='abrupt',rows=1200)
    replay.to_csv(dest/'method_check_replay.csv',index=False)
    binding=dict(config_sha256=canonical_hash(cfg),notebook_sha256=source_hash,development_sha256=digest(dest/'development_outcomes.csv'))
    write_new(dest/'development_provenance.json',dict(binding,mode='regenerated_development',m1_review_commit=commit))
    strategy=dict(fixture_checks=ns['M2_CHECKS'],development_checks=dict.fromkeys(['unique_keys_four_arms_and_matching_metadata','cost_count_and_utility_consistency','m1_independent_truth_audit','audit_coverage_and_reconstruction_match_outcomes'],'pass'),row_counts=dict(outcomes=len(outcomes)))
    for name,payload in [('truth_checks',truth),('strategy_checks',strategy),('method_checks',methods)]:
        write_new(dest/(name+'.json'),dict(binding,status='passed',payload=payload))
    scores=outcomes.groupby(['scenario','seed','arm']).utility.mean().groupby(['scenario','arm']).mean().unstack().reindex(columns=ns['ARMS'])
    plan=dict(config=cfg,baselines=scores.idxmax(axis=1).to_dict(),evaluation_seeds=dict(stable=[],abrupt=[]),used_seeds=sorted(outcomes.seed.unique().tolist()))
    write_new(dest/'plan_draft.json',plan)
    names=['truth_checks','strategy_checks','method_checks','development_provenance','approvals']
    evidence={k:dest/(k+'.json') for k in names}
    evidence.update(audit_review=dest/'audit_review.csv',development_outcomes=dest/'development_outcomes.csv')
    validate_evidence(plan,evidence,dict(notebook=notebook))
    assert digest(notebook)==source_hash
    (dest/'notebook_snapshot.ipynb').write_bytes(notebook.read_bytes())
    write_new(dest/'evidence.json',{k:p.name for k,p in evidence.items()})
    write_new(dest/'readiness.json',dict(status='technical_evidence_passed_human_review_pending',m1_review_commit=commit,audit_questions=10,audit_arms=40,verified_summary_rows=checked,development_rows=len(outcomes),method_replay_rows=len(replay),human_verdicts=review.verdict.value_counts().to_dict(),missing=['M1 personal confirmation and M1/M2 joint verdicts','M3 statistics review','team approvals','formal seeds and full used-seed disclosure'],formal_generated=False))
    write_new(dest/'manifest.json',dict(files={p.name:digest(p) for p in dest.iterdir() if p.is_file()}))
    print('Evidence validated:',dest,flush=True)


if __name__=='__main__':main()
