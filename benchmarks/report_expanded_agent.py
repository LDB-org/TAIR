"""Failure-aware latency and paired comparisons for complete Agent experiments."""
import argparse
import json
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values)-1)*q
    low = int(position)
    high = min(low+1, len(values)-1)
    return values[low] + (values[high]-values[low])*(position-low)


def summarize(rows):
    times = [r['validated_seconds'] for r in rows]
    metrics = [m for r in rows for m in r['metrics']]
    return {'tasks': len(rows), 'base_passed': sum(r.get('base_passed',r['passed']) for r in rows), 'passed': sum(r['passed'] for r in rows),
            'timed_out': sum(r['timed_out'] for r in rows),
            'complete_usage_tasks': sum(r['usage_complete'] for r in rows),
            'seconds': sum(times), 'p50_seconds': percentile(times,.5),
            'p95_seconds': percentile(times,.95), 'max_seconds': max(times,default=None),
            'inference_count_is_lower_bound': any(not r['usage_complete'] for r in rows),
            'inference_requests': sum(m['accounting']['inference_requests'] for m in metrics),
            'generated_tokens': sum(m['accounting']['known_generated_argument_tokens'] for m in metrics),
            'control_records': sum(m['accounting']['known_classification_control_records'] for m in metrics),
            'input_tokens': sum(m['accounting']['known_input_tokens'] for m in metrics),
            'unknown_usage_requests': sum(m['accounting']['unknown_usage_requests'] for m in metrics),
            'inner_edit_calls': sum(m['action']=='edit' for m in metrics),
            'edit_cache_hits': sum(bool(m.get('cache_hit')) for m in metrics),
            'tokenizer_requests': sum(h['route']=='/tokenize' for m in metrics for h in m.get('http_requests',[])),
            'deferred_plans': sum(bool(m.get('plan_deferred_calls')) for m in metrics)}


def report(out):
    rows = [json.loads(line) for line in (out/'rows.jsonl').read_text().splitlines()]
    test_reviews = {}
    for filename in ['requested-test-review.json','cli-test-review.json']:
        if (out/filename).exists():
            test_reviews.update({r['case']:r['requested_tests_effective'] for r in json.loads((out/filename).read_text())})
    rejected_tests = {case for case, passed in test_reviews.items() if not passed}
    rows = [{**r, 'base_passed': r['passed'], 'requested_tests_passed': test_reviews.get(f"{r['repeat']}-{r['case']}-{r['arm']}-{r['round']}"),
             'passed': r['passed'] and f"{r['repeat']}-{r['case']}-{r['arm']}-{r['round']}" not in rejected_tests} for r in rows]
    arms = ['native','batched','contextual']
    manifest = json.loads((out/'manifest.json').read_text())
    expected = len(manifest['scenarios'])*manifest['repeats']*manifest['rounds']*len(arms)
    assert len(rows)==expected, (len(rows),expected)
    assert len({(r['repeat'],r['case'],r['round'],r['arm']) for r in rows})==expected
    cases = list(dict.fromkeys(r['case'] for r in rows))
    grouped = {arm: summarize([r for r in rows if r['arm']==arm]) for arm in arms}
    by_case = {case: {arm:summarize([r for r in rows if r['case']==case and r['arm']==arm]) for arm in arms} for case in cases}
    keys = {(r['repeat'],r['case'],r['round']) for r in rows}
    complete_keys = {key for key in keys if len(matched:=[r for r in rows if (r['repeat'],r['case'],r['round'])==key])==len(arms) and all(r['passed'] for r in matched)}
    matched = {arm:summarize([r for r in rows if r['arm']==arm and (r['repeat'],r['case'],r['round']) in complete_keys]) for arm in arms}
    failed = [{k:r[k] for k in ['repeat','case','round','arm','passed','timed_out','usage_complete','validation','test_integrity','base_passed','requested_tests_passed']} for r in rows if not r['passed']]
    data = {'arms':grouped,'by_case':by_case,'common_successful_tuples':len(complete_keys),
            'common_successful_only':matched,'failures':failed,
            'by_round':{str(n):{a:summarize([r for r in rows if r['round']==n and r['arm']==a]) for a in arms} for n in (1,2)},
            'by_repeat':{str(n):{a:summarize([r for r in rows if r['repeat']==n and r['arm']==a]) for a in arms} for n in sorted({r['repeat'] for r in rows})}}
    (out/'expanded-analysis.json').write_text(json.dumps(data,indent=2)+'\n')
    lines=['# Expanded full-Agent comparison','',
           'Ten synthetic task families, two independent repeats, restored cold/warm pairs, three interleaved arms: 120 attempts. The seven added workloads cover new modules/CLI documentation, nested packages, quoted CSV, JSON configuration, exception boundaries, cross-file behavior, and an 84-file project with 80 unrelated modules. This is broader controlled coverage, not a real-repository or public coding benchmark.','',
           '## All attempts (failures retained)','','| Arm | Basic checks passed | After test-quality audit | Total seconds | p50 seconds | p95 seconds | Max seconds | Recorded inference requests | Complete usage |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for a,s in grouped.items():
        lines.append(f"| {a} | {s['base_passed']}/{s['tasks']} | {s['passed']}/{s['tasks']} | {s['seconds']:.2f} | {s['p50_seconds']:.2f} | {s['p95_seconds']:.2f} | {s['max_seconds']:.2f} | {s['inference_requests']} | {s['complete_usage_tasks']}/{s['tasks']} |")
    lines+=['','Basic checks preserve the original run criteria. Requested-test quality is an additional stricter post-run review, reported separately; the per-family and common-success tables use this audited criterion. A missing required CLI test can therefore make an originally passing basic-oracle row fail this complete-task review; A null requested-test audit means no additional test-quality review was applicable or performed for that row. Raw rows.jsonl is preserved and base_passed is retained in expanded-analysis.json. Latency covers startup, model/tool calls, tests, recovery, final reply and an independent oracle including a unittest rerun. Fixture reset and post-run audits are excluded. A fast failed task is not an equivalent completed task. p95 uses linear interpolation over all attempts (40 per arm), not a production-tail estimate.','',
            '## Token and codebook accounting','','| Arm | Generated tokens (known) | Control records (known) | Input tokens (known) | Inner edits | Edit hits | Tokenizer HTTP requests |','|---|---:|---:|---:|---:|---:|---:|']
    for a,s in grouped.items():lines.append('| '+a+' | '+' | '.join(str(s[k]) for k in ['generated_tokens','control_records','input_tokens','inner_edit_calls','edit_cache_hits','tokenizer_requests'])+' |')
    lines+=['','Incomplete usage, if present, is explicitly recorded in expanded-analysis.json and cannot be treated as a zero-cost request. Recorded inference/token counts are lower bounds for arms containing incomplete tasks: a killed in-flight request may not have emitted a final trace record. Plans are generated; only inner supported edits use the existing learned codebook.','',
            '## Per family (passed / attempts; total seconds)','','| Family | Native | Prior batched | Contextual |','|---|---:|---:|---:|']
    for c in cases:lines.append('| '+c+' | '+' | '.join(f"{s['passed']}/{s['tasks']}; {s['seconds']:.2f}s" for s in by_case[c].values())+' |')
    lines+=['','## Same completed tasks only','',f"All three arms passed {len(complete_keys)} matching (repeat, family, cold/warm) tuples. This subset omits harder failures and is descriptive, not a replacement for the all-attempt success rates.",'','| Arm | Matched tasks | Total seconds | p50 | p95 |','|---|---:|---:|---:|---:|']
    for a,s in matched.items():lines.append(f"| {a} | {s['tasks']} | {s['seconds']:.2f} | {s['p50_seconds'] or 0:.2f} | {s['p95_seconds'] or 0:.2f} |")
    lines+=['','## Failed attempts','']
    for r in failed:lines.append(f"- {r['repeat']}-{r['case']}-{r['arm']}-{r['round']}: oracle={r['validation']['passed']}, test integrity={r['test_integrity']}, requested-test audit={r['requested_tests_passed']}, timeout={r['timed_out']}, complete usage={r['usage_complete']}.")
    if not failed:lines.append('None.')
    lines+=['','## Controls and limitations','',
            'Same running 6 x RTX 5090 backend and Pi 0.85.1; no service restart or patch deployment. Native uses the ordinary tools API on the patched service and retains parallel_tool_calls=false. No comparison with a separate unpatched engine or enabled native parallel tools is implied. Tool catalogs, prompts, grammar and control granularity differ.','',
            'Code/runtime state is separate by arm and repeat. Warm pairs restore the original project while retaining only that arm runtime state; every Agent session is new. Execution is sequential across tasks with seeded interleaving, no replacement of failed attempts, and a 180-second per-Agent limit. Oracles are outside the Agent workspace. The seven new oracles reject the initial buggy projects and accept offline reference implementations before GPU execution. Original tests and designated unrelated files are protected by separate checks.','',
            'This suite deliberately includes supported and unsupported edits, generated new files, nested paths and discovery beyond a 64-entry root inventory. It does not establish generalization to arbitrary repositories, multi-user throughput, long-context limits, long-term codebook growth or correctness of admission. Same-task warm pairs do not establish transfer to unseen edits.','',
            'Source snapshots, raw events, final projects, independent oracle results, traces, per-repeat/cold-warm breakdowns and checksums accompany this report. Runtime was held fixed for the entire suite.']
    if (out/'grammar-compatibility.json').exists():
        probe=json.loads((out/'grammar-compatibility.json').read_text())
        lines+=['','## Deployed grammar incompatibility','',
                f"A CPU-only matcher probe of installed xgrammar {probe['xgrammar_version']} found {probe['mismatches']} mismatches across ten checks. Legal nonempty strings containing a double quote, newline or backslash are accepted without minLength and rejected with minLength=1. Python jsonschema independently accepts these strings.",'',
                'The added oldText.minLength=1 constraint therefore removes valid exact-match spans from the generated language on this deployment. This is a concrete contributor to quote-free/truncated edits and repeated failures; other tools or simpler spans can sometimes recover. CSV semantic errors remain a separate finding. See grammar-compatibility.json, grammar-jsonschema-validation.json, and sources/probe_json_string_grammar.py. No service update or runtime fix was applied during the suite, and this probe issued no model requests.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'arms':grouped,'common_successful_tuples':len(complete_keys),'failures':failed}))
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
    report(parser.parse_args().out)
