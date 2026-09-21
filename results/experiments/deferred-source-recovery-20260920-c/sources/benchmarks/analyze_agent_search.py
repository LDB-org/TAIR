"""Locate filesystem-root searches in saved Agent traces without rerunning tools."""
import argparse
import json
from pathlib import Path
import re


def analyze(folder):
    findings = []
    for line in (folder / 'rows.jsonl').read_text().splitlines():
        row = json.loads(line)
        path = folder / f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}" / 'events.jsonl'
        chats = [m for m in row['metrics'] if m['action'] == 'chat']
        pending, turn = {}, 0
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') != 'message_end':
                continue
            message = event.get('message', {})
            if message.get('role') == 'assistant':
                metric = chats[turn] if turn < len(chats) else {}
                turn += 1
                for block in message.get('content', []):
                    command = block.get('arguments', {}).get('command', '')
                    if block.get('name') == 'bash' and re.search(r'(?:^|[;&|])\s*find\s+/\s', command):
                        pending[block['id']] = (message.get('timestamp'), metric.get('wall_seconds', metric.get('seconds')))
            elif message.get('role') == 'toolResult' and message.get('toolCallId') in pending:
                started, generation = pending.pop(message['toolCallId'])
                span = (message['timestamp'] - started) / 1000
                findings.append({k: row[k] for k in ['case', 'arm', 'repeat', 'round', 'passed', 'timed_out']} |
                                dict(assistant_start_to_tool_result_seconds=span,
                                     generation_seconds=generation,
                                     estimated_tool_seconds=max(0, span - generation) if generation is not None else None))
    return dict(searches=findings,
                timing='Assistant timestamp to tool-result timestamp includes generating the tool call. Subtract recorded generation time for an approximate tool duration; this is not a separate profiler. Interrupted searches without a tool-result message are excluded. No commands are re-executed.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    data = analyze(args.folder)
    args.out.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
