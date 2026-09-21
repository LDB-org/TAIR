"""Audit persisted codebook learning and separate edit-stage timing from Agent claims."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
WARM={'repeat_default','new_parameter','updated_snapshot','new_help','new_alias','compound_repeat','guard_repeat'}


def report(folder):
    rows=[json.loads(s) for s in (folder/'rows.jsonl').read_text().splitlines()]
    manifest=json.loads((folder/'manifest.json').read_text())
    expected=len(manifest['cases'])*len(manifest['arms'])*manifest['repeats']
    assert len(rows)==expected==len({(r['case'],r['arm'],r['repeat']) for r in rows})
    source_checks=[]
    for path in (folder/'sources').rglob('*.py'):
        relative=path.relative_to(folder/'sources')
        assert path.read_bytes()==(ROOT/relative).read_bytes(), 'Changed runtime source: '+str(relative)
        source_checks.append(dict(path=str(relative),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for index,row in enumerate(rows):
        response=row['response'];account=response['accounting']
        assert account['usage_complete']
        if row['arm']=='generate':
            assert not response['cache_hit'] and response['admitted']==0
        elif row['case'] in WARM:
            assert row['passed'] and response['cache_hit'] and account['inference_requests']==0
            assert account['known_generated_argument_tokens']==account['known_classification_control_records']==0
            assert (folder/'attempts'/str(index)/'book-before.json').is_file()
        else:
            assert not response['cache_hit'], 'Unexpected reuse on cold/rejected task'
        if row['arm']=='safe_book' and row['case']=='cold_default':
            assert not (folder/'attempts'/str(index)/'book-before.json').exists()
            assert response['admitted']>0
        if row['arm']=='safe_book' and row['case']=='unverified_no_admission':
            assert response['admitted']==0
            assert response['admission_skipped_reason']=='no_task_binding_or_project_check'
            assert (folder/'attempts'/str(index)/'book-before.json').read_bytes()==(folder/'attempts'/str(index)/'book-after.json').read_bytes()
    summaries=[]
    for scope in ['all','warm','cold_or_rejected']:
        for arm in manifest['arms']:
            group=[r for r in rows if r['arm']==arm and (scope=='all' or (r['case'] in WARM)==(scope=='warm'))]
            summaries.append(dict(scope=scope,arm=arm,n=len(group),passed=sum(r['passed'] for r in group),
                seconds=sum(r['seconds'] for r in group),median_seconds=statistics.median(r['seconds'] for r in group),
                hits=sum(r['response']['cache_hit'] for r in group),
                bound_hits=sum(r['response'].get('bound_reuse_hit',False) for r in group),
                exact_hits=sum(r['response'].get('exact_reuse_hit',False) for r in group),
                **{key:sum(r['response']['accounting'][key] for r in group) for key in ['inference_requests','known_input_tokens','known_generated_argument_tokens','known_classification_control_records']}))
    percase=[]
    for spec in manifest['cases']:
        case={'case':spec['name']}
        for arm in manifest['arms']:
            group=[r for r in rows if r['case']==spec['name'] and r['arm']==arm]
            case[arm]=dict(passed=sum(r['passed'] for r in group),n=len(group),mean_seconds=statistics.mean(r['seconds'] for r in group),hits=sum(r['response']['cache_hit'] for r in group))
        percase.append(case)
    # Request IDs are preserved in the bridge result requests field even when raw HTTP responses are omitted.
    engine_ids=[req['request_id'] for row in rows for req in row['response'].get('requests',[]) if req['request_id'].startswith('openjev-')]
    events=[json.loads(s) for s in (folder/'engine-events.jsonl').read_text().splitlines()]
    assert all(any(e.get('request_id','').startswith(rid) and e.get('sampler_bypassed') for e in events) for rid in engine_ids)
    index={(r['scope'],r['arm']):r for r in summaries}
    return dict(attempts=len(rows),passed=sum(r['passed'] for r in rows),source_checks=source_checks,summaries=summaries,percase=percase,
        generation_requests_verified=len(engine_ids),
        saved_fraction={scope:1-index[scope,'safe_book']['seconds']/index[scope,'generate']['seconds'] for scope in ['all','warm','cold_or_rejected']},
        scope='Actual compact_edit runtime and persisted learned book, fresh process for every request. Not full Agent or universal natural-language reuse.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();data=report(a.folder);a.out.write_text(json.dumps(data,indent=2))
    print(json.dumps({k:v for k,v in data.items() if k not in ['source_checks','percase']},indent=2))
