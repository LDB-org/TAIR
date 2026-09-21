"""Audit full-Agent plan activation, cost accounting and output integrity."""
import argparse
import json
from pathlib import Path

from compare_pijit_presets import summarize


def report(out):
    manifest=json.loads((out/'manifest.json').read_text())
    strong_reference='Native permits multiple tool calls' in manifest['method']
    rows=[json.loads(line) for line in (out/'rows.jsonl').read_text().splitlines()]
    assert len(rows)==27
    details=[]
    for row in rows:
        assert row['passed'] and row['usage_complete'] and row['protected_intact'] and row['only_requested_output']
        folder=out/f"{row['case']}-{row['round']}-{row['arm']}"
        assert row==json.loads((folder/'final-result.json').read_text())
        metrics=row['metrics'];plans=[m for m in metrics if m['action']=='plan']
        if row['arm']=='native':
            assert not plans
            if strong_reference:
                native=[json.loads(line) for line in (folder/'native-inference.jsonl').read_text().splitlines()]
                requests=[event['payload'] for event in native if event['event']=='request']
                assert requests and all(r['parallel_tool_calls'] and r['max_tokens']==4096 for r in requests)
                assert len({r['cache_salt'] for r in requests})==1
        else:
            assert len(plans)>=1 and all(p['status']=='ok' for p in plans)
            assert 'plan' in next(m for m in metrics if m['action']=='chat')['available_tools']
        if row['arm']=='plan_no_book':assert not any(p['cache_hit'] for p in plans)
        warm_source_reused=None
        if row['arm']=='adaptive' and row['round']==1:
            cold=out/f"{row['case']}-0-adaptive"/'plan-codebook.json'
            entries=json.loads(cold.read_text())['entries']
            warm_source_reused=any(e['source']==(folder/'adapter.py').read_text() for e in entries)
            assert any(p['cache_hit'] for p in plans) and warm_source_reused
        before=json.loads((folder/'inventory-before.json').read_text())
        after=json.loads((folder/'inventory-after.json').read_text())
        assert set(after)-set(before)=={'adapter.py'}
        assert all(after[path]==value for path,value in before.items())
        events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
        starts=[e for e in events if e.get('type')=='tool_execution_start']
        if row['arm']!='native':assert starts[0]['toolName']=='plan'
        details.append(dict(case=row['case'],round=row['round'],arm=row['arm'],passed=row['passed'],
            seconds=row['validated_seconds'],plan_calls=len(plans),hits=sum(p['cache_hit'] for p in plans),
            recoveries=sum(p['recovered'] for p in plans),
            requests=sum(m['accounting']['inference_requests'] for m in metrics),
            generated_tokens=sum(m['accounting']['known_generated_argument_tokens'] for m in metrics),
            controls=sum(m['accounting']['known_classification_control_records'] for m in metrics),
            warm_source_reused=warm_source_reused))
    summary=summarize(rows)
    summary['strong_reference_verified']=strong_reference
    summary['details']=details
    summary['groups']={str(round_):summarize([r for r in rows if r['round']==round_])['arms'] for round_ in range(3)}
    summary['limitations']='Three small adapters backed by pinned Rich, CPython and TAIR dependencies; not full upstream test suites. First tool is forced to plan only in explicit new-Python-module mode. All outer/inner requests, checks and final replies included. Plan-without-reuse controls for the changed outer policy. Trusted validator is also rerun for final acceptance, not an unseen holdout. Upstream integrity independently hashed.'
    (out/'audit-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args()
    print(json.dumps(report(a.out),indent=2))
