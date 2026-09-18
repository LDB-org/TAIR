import json
from pathlib import Path
p=Path('results/experiments/codebook-outer-agent-20260919-b')
s=json.loads((p/'summary.json').read_text())['arms']
profiles=json.loads((p/'profile-summary.json').read_text())
rows=[json.loads(x) for x in (p/'rows.jsonl').read_text().splitlines()]
lines=['# Full Agent outer-loop optimization: repeated run B (2026-09-19)','',
'Two independent repetitions of three real Pi coding scenarios, each with a cold and warm round: 36 tasks total. Each arm starts a separate project and empty state per repetition/scenario. Warm rounds restore the original source and retain only runtime state, with a fresh Agent session. Arm order is interleaved using seed 921.','',
'## Full task outcomes','',
'| Arm | Completed correctly | Total seconds, all attempts | Inference requests | Generated tokens | Controls | Input tokens | Edit hits |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for name in ['native','c4','optimized']:
 r=s[name];lines.append(f"| {name} | {r['passed']}/{r['tasks']} | {r['wall_seconds']:.2f} | {r['inference_requests']} | {r['known_generated_argument_tokens']} | {r['known_classification_control_records']} | {r['known_input_tokens']} | {r['cache_hits']} |")
lines+=['',f"Optimized total time is {100*(1-s['optimized']['wall_seconds']/s['native']['wall_seconds']):.1f}% below native and {100*(1-s['optimized']['wall_seconds']/s['c4']['wall_seconds']):.1f}% below c4 in this run. All-attempt totals retain failures and their actual costs; an incomplete task is not equivalent completed work.",'','## Per scenario and repeat','','| Scenario | Native seconds | c4 seconds | Optimized seconds |','|---|---:|---:|---:|']
for case in profiles['native']['by_case']:
 lines.append('| '+case+' | '+' | '.join(f"{profiles[a]['by_case'][case]['seconds']:.2f}" for a in ['native','c4','optimized'])+' |')
lines+=['','| Independent repetition | Native seconds | c4 seconds | Optimized seconds |','|---|---:|---:|---:|']
for k in ['0','1']:
 lines.append('| '+str(int(k)+1)+' | '+' | '.join(f"{profiles[a]['by_repeat'][k]:.2f}" for a in ['native','c4','optimized'])+' |')
lines+=['','| Round | Native seconds | c4 seconds | Optimized seconds |','|---|---:|---:|---:|']
for k,name in [('1','Cold'),('2','Warm')]:
 lines.append('| '+name+' | '+' | '.join(f"{profiles[a]['by_round'][k]:.2f}" for a in ['native','c4','optimized'])+' |')
lines+=['','## Completed-pair comparison','']
key=lambda r:(r['repeat'],r['case'],r['round'])
for other in ['native','c4']:
 left={key(r):r for r in rows if r['arm']=='optimized'}
 right={key(r):r for r in rows if r['arm']==other}
 keys=[k for k in left.keys()&right.keys() if left[k]['passed'] and right[k]['passed']]
 ot=sum(left[k]['validated_seconds'] for k in keys);rt=sum(right[k]['validated_seconds'] for k in keys)
 lines.append(f'- Optimized vs {other}: {len(keys)} mutually successful pairs; {ot:.2f} vs {rt:.2f} seconds ({100*(1-ot/rt):.1f}% lower). All excluded failures remain in raw rows and the all-attempt table above.')
lines+=['','## Configuration and overhead','',
'Native uses stock Pi tools via the standard chat-completions endpoint on the same patched vLLM service. c4 uses the expanded learned codebook with all outer-loop optimization flags disabled. Optimized enables batched explicit-clause routing after a successful source read, revision-bound tokenizer label/continuation caches, and directory-read redirection. Schema execution, preset edits and exact zero-model replay are disabled for all TAIR arms. Inner codebook candidates still go through classification with NONE/generation fallback.','',
'| Client measure | c4 | Optimized |','|---|---:|---:|']
for k,title in [('tokenizer_requests','Tokenizer HTTP requests'),('local_routes','Locally dispatched outer calls'),('continuation_cache_hits','Continuation-cache hits'),('directory_redirects','Directory-read redirects'),('preparation_seconds','Measured preparation seconds')]:
 lines.append(f"| {title} | {profiles['c4'][k]:.2f} | {profiles['optimized'][k]:.2f} |")
lines+=['','Tokenizer HTTP calls are not inference requests. Preparation stages overlap with individual HTTP timings; their elapsed durations must not be summed with nested request durations. A local dispatch is not a zero-model edit. Cache initialization costs are included in cold rounds.','',
'## Correctness and evidence','',
'`rows.jsonl` and `summary.json` include final task-completeness decisions. The lower-level per-task `result.json` predates the added-test integrity check; use the separately saved `final-result.json` for the final verdict. A successful function oracle alone does not fulfill a request to add tests.','']
for r in rows:
 folder=p/f"{r['repeat']}-{r['case']}-{r['arm']}-{r['round']}"
 (folder/'final-result.json').write_text(json.dumps(r,indent=2)+'\n')
 if not r['passed']:lines.append(f"- Failed: repeat {r['repeat']+1}, {r['case']}, {r['arm']}, round {r['round']}; behavior oracle passed={r['validation']['passed']}, original/additional test integrity passed={r['test_integrity']}. Files and events are retained; no silent retry.")
lines+=['','Every final project has a separately recorded unittest rerun in `independent-unittest.json`. Engine classification evidence, tokenizer hashes, engine revision, unchanged service start time and source hashes are in `verification.json`, `engine-classification-events.jsonl` and `environment.json`. Worker event counts are not request counts. The post-run artifact audit is outside measured task time.','',
'## Limits','',
'This is a small handcrafted workload on a shared 6 x RTX 5090 backend, not a general coding benchmark or production throughput test. Native is not a separate unpatched server. Tool catalogs and provider prompts differ. The optimized configuration combines routing and transport improvements, so the end-to-end delta cannot be attributed solely to the classifier or learned codebook. Cold and warm tradeoffs and individual regressions are shown above. Compile-only admission does not prove semantic correctness; independent task oracles are applied afterward. Pinned continuation calibration is empirical for this deployed tokenizer/template.','',
'Diagnostic A is retained separately, including its original incomplete aggregate and corrected aggregate. Its measurements are not merged with run B. No model reload, service restart or production release replacement was performed.']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines[:16]))
