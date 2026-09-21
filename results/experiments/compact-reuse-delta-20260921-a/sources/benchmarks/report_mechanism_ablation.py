"""Report all attempts and conditional single-factor deltas without discarding failures."""
import argparse
import json
from pathlib import Path
import statistics


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def change(before, after):
    return {'before_seconds': before, 'after_seconds': after, 'saved_seconds': before - after,
            'saved_percent': 100 * (before - after) / before if before else None}


def agent_summary(rows):
    records = [m for row in rows for m in row['metrics']]
    times = [r['validated_seconds'] for r in rows]
    return {'tasks': len(rows), 'basic_passed': sum(r['base_passed'] for r in rows),
            'audited_passed': sum(r['passed'] for r in rows), 'wall_seconds': sum(times),
            'p50_seconds': statistics.median(times),
            'p95_seconds': statistics.quantiles(times, n=20, method='inclusive')[18] if len(times) > 1 else times[0],
            'timeouts': sum(r['timed_out'] for r in rows),
            'usage_complete': all(r['usage_complete'] for r in rows),
            'counts_are_lower_bounds': not all(r['usage_complete'] for r in rows),
            **{k: sum(m['accounting'].get(k, 0) for m in records) for k in (
                'inference_requests', 'known_input_tokens', 'known_generated_argument_tokens',
                'known_classification_control_records', 'unknown_usage_requests')},
            **{k: sum(bool(m.get(k)) for m in records) for k in (
                'cache_hit', 'jit_hit', 'schema_hit', 'label_cache_hit', 'continuation_cache_hit',
                'local_route', 'directory_read_redirect', 'plan_deferred_calls')},
            'batch_plans': sum('batch_tool_count' in m for m in records),
            'nested_edit_calls': sum(m['action'] != 'chat' for m in records),
            'tokenizer_requests': sum(h['route'] == '/tokenize' for m in records for h in m.get('http_requests', [])),
            'preparation_seconds': sum(sum(m.get('stage_seconds', {}).get(k, 0) for k in
                ('generation_preparation', 'cache_preparation')) for m in records)}


def report(out):
    manifest = json.loads((out / 'agent/manifest.json').read_text())
    rows = read_rows(out / 'agent/rows.jsonl')
    expected = {(a, c, r, k) for a in manifest['arms'] for c in manifest['cases']
                for r in range(manifest['repeats']) for k in (1, 2)}
    assert len(rows) == len(expected)
    assert {(r['arm'], r['case'], r['repeat'], r['round']) for r in rows} == expected
    audit = {r['case']: r for r in json.loads((out / 'agent/requested-test-review.json').read_text())}
    for row in rows:
        row['base_passed'] = row['passed']
        key = f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}"
        if row['case'] == 'summary_bug':
            assert key in audit
            row['requested_tests_effective'] = audit[key]['requested_tests_effective']
            row['passed'] &= row['requested_tests_effective'] is True
    arms = {a: agent_summary([r for r in rows if r['arm'] == a]) for a in manifest['arms']}
    comparisons = {}
    for treatment, (parent, flag) in manifest['comparisons'].items():
        before, after = arms[parent], arms[treatment]
        item = {**change(before['wall_seconds'], after['wall_seconds']), 'parent': parent, 'flag': flag,
                'before_passed': before['audited_passed'], 'after_passed': after['audited_passed'],
                'by_round': {}, 'by_case': {}}
        for field, values in [('round', (1, 2)), ('case', manifest['cases'])]:
            for value in values:
                groups = [[r for r in rows if r['arm'] == a and r[field] == value] for a in (parent, treatment)]
                item['by_' + field][value] = {**change(*(sum(r['validated_seconds'] for r in g) for g in groups)),
                    'before_passed': sum(r['passed'] for r in groups[0]), 'after_passed': sum(r['passed'] for r in groups[1]),
                    'tasks_per_arm': len(groups[0])}
        indexed = {(r['case'], r['repeat'], r['round']): r for r in rows if r['arm'] == parent}
        paired = [(indexed[(r['case'], r['repeat'], r['round'])], r) for r in rows if r['arm'] == treatment]
        successful = [(a, b) for a, b in paired if a['passed'] and b['passed']]
        item['mutually_successful_subset'] = {'pairs': len(successful),
            **change(sum(a['validated_seconds'] for a, _ in successful), sum(b['validated_seconds'] for _, b in successful)),
            'limitation': 'Selected successful subset, not a replacement for all-attempt quality and costs.'}
        comparisons[treatment] = item
    micros = {}
    for section, expected_count in [('edits', 63), ('replay', 54)]:
        micro_rows = read_rows(out / section / 'rows.jsonl')
        assert len(micro_rows) == expected_count
        grouped = {}
        for arm in dict.fromkeys(r['arm'] for r in micro_rows):
            groups = {'all': [r for r in micro_rows if r['arm'] == arm]}
            if section == 'replay':
                groups.update({f'{case}_round{round_}': [r for r in micro_rows if r['arm'] == arm and r['case'] == case and r['round'] == round_]
                               for case in ('float', 'help', 'alias') for round_ in (1, 2)})
            grouped[arm] = {}
            for name, group in groups.items():
                results = [r['result'] for r in group]
                grouped[arm][name] = {'tasks': len(group), 'correct': sum(r['correct'] for r in group),
                    'total_seconds': sum(r['wall_seconds'] for r in results),
                    'mean_seconds': statistics.mean(r['wall_seconds'] for r in results),
                    **{k: sum(bool(r.get(k)) for r in results) for k in ('cache_hit', 'jit_hit', 'schema_hit')},
                    **{k: sum(r['accounting'].get(k, 0) for r in results) for k in ('inference_requests',
                        'known_input_tokens', 'known_generated_argument_tokens', 'known_classification_control_records')},
                    'usage_complete': all(r['accounting']['usage_complete'] for r in results)}
        micros[section] = grouped
    ideal = json.loads((out / 'ideal/summary.json').read_text())
    assert sum(r['n'] for r in ideal) == 18
    data = {'agent': arms, 'single_factor_comparisons': comparisons, 'micros': micros, 'ideal': ideal,
            'failed_agent_tasks': [{k: r[k] for k in ('arm', 'case', 'round', 'repeat', 'base_passed', 'passed', 'timed_out', 'validation')} for r in rows if not r['passed']],
            'limitations': manifest['limitations']}
    (out / 'analysis.json').write_text(json.dumps(data, indent=2))
    lines = ['# Mechanism ablation: current implementation', '', manifest['limitations'], '',
             '## Full Agent: all attempts', '',
             '| Arm | Basic/audited passed | Tasks | Total s | p95 s | Requests | Timeouts | Usage complete |',
             '|---|---:|---:|---:|---:|---:|---:|---|']
    for arm, s in arms.items():
        lines.append(f"| {arm} | {s['basic_passed']}/{s['audited_passed']} | {s['tasks']} | {s['wall_seconds']:.3f} | {s['p95_seconds']:.3f} | {s['inference_requests']} | {s['timeouts']} | {s['usage_complete']} |")
    lines += ['', '## One-factor edges', '',
              'Negative savings mean a slowdown. Serial is the treatment that DISABLES preparation overlap; swap before/after and recompute the percentage denominator when discussing enabling parallel preparation. Counts are lower bounds whenever usage is incomplete. Fast failed tasks are not equivalent completed work.', '',
              '| Parent → treatment | Before s | After s | Saved s | Saved % | Audited passes before/after |',
              '|---|---:|---:|---:|---:|---:|']
    for arm, s in comparisons.items():
        lines.append(f"| {s['parent']} → {arm} | {s['before_seconds']:.3f} | {s['after_seconds']:.3f} | {s['saved_seconds']:.3f} | {s['saved_percent']:.1f}% | {s['before_passed']}/{s['after_passed']} |")
    lines += ['', '## Mutually successful pairs (selected subsets)', '',
              'These omit failed tasks and are NOT a substitute for the complete outcomes above. Different edges can contain different pairs. They show whether a lower total merely reflects faster failures.', '',
              '| Parent → treatment | Successful pairs | Before s | After s | Saved s | Saved % |',
              '|---|---:|---:|---:|---:|---:|']
    for arm, comparison in comparisons.items():
        s = comparison['mutually_successful_subset']
        percent = f"{s['saved_percent']:.1f}%" if s['saved_percent'] is not None else 'n/a'
        lines.append(f"| {comparison['parent']} → {arm} | {s['pairs']} | {s['before_seconds']:.3f} | {s['after_seconds']:.3f} | {s['saved_seconds']:.3f} | {percent} |")
    lines += ['', '## Mechanism activation', '', '| Arm | Codebook hits | Local routes | Label hits | Continuation hits | Directory redirects | Plans | Tokenize requests | Preparation s |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm, s in arms.items():
        lines.append(f"| {arm} | {s['cache_hit']} | {s['local_route']} | {s['label_cache_hit']} | {s['continuation_cache_hit']} | {s['directory_read_redirect']} | {s['batch_plans']} | {s['tokenizer_requests']} | {s['preparation_seconds']:.3f} |")
    lines += ['', '## Edit-level controls', '', '| Experiment | Arm | Passed/tasks | Total s | Generated tokens | Controls | Input tokens |', '|---|---|---:|---:|---:|---:|---:|']
    for section, groups in micros.items():
        for arm, groups2 in groups.items():
            s = groups2['all']
            lines.append(f"| {section} | {arm} | {s['correct']}/{s['tasks']} | {s['total_seconds']:.4f} | {s['known_generated_argument_tokens']} | {s['known_classification_control_records']} | {s['known_input_tokens']} |")
    lines += ['', 'Cold and warm replay details, ideal-classification service/HTTP times, per-case and per-round Agent deltas, mutually successful subsets, and failures are in analysis.json. The ideal study excludes recorded offline preparation and two separately preserved warmups; full-Agent/edit studies exclude no warmup or formal failed attempt. These boundaries must not be combined.', '',
              'The repaired context grammar is used throughout. Single-factor configuration checks passed before the run. Behavior oracles are outside Agent workspaces; original test integrity is checked. Summary-task requested tests receive an additional post-run mutation review, preserving original raw results.', '',
              'No model service restart or patch installation. Shared backend, one cold/warm pair per Agent family; observed deltas do not establish a stable speedup. Compare cold/warm and family variation before attributing an overall delta to a mechanism. Entire plans are generated and are not codebook entries.', '']
    (out / 'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps({'agent': arms, 'comparisons': comparisons, 'micros': micros, 'ideal': ideal}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    report(parser.parse_args().out.resolve())
