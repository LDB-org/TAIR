"""Local direct-logit classification + cached, grammar-constrained arguments."""
import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import random
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('engine', ROOT/'deploy/logit_toolcall.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
CASES = [
 ('read', 'Read notes.txt starting at line 1, with a limit of 3 lines.', {'path':'notes.txt','offset':1,'limit':3}),
 ('bash', "Run the exact Bash command printf 'hello\\n' with timeout 5 seconds.", {'command':"printf 'hello\\n'",'timeout':5}),
 ('edit', 'In config.txt replace the exact text DEBUG=0 with DEBUG=1 using one edit.', {'path':'config.txt','edits':[{'oldText':'DEBUG=0','newText':'DEBUG=1'}]}),
 ('write', 'Write notes.txt with exactly Hello. as its entire content, with no newline.', {'path':'notes.txt','content':'Hello.'}),
 ('grep', 'Search for the literal TODO in the current directory (path .), with at most 5 matches.', {'pattern':'TODO','path':'.','literal':True,'limit':5}),
 ('find', 'Find files matching *.py in the current directory (path .), with at most 5 results.', {'pattern':'*.py','path':'.','limit':5}),
 ('ls', 'List the current directory (path .), with at most 5 entries.', {'path':'.','limit':5}),
 ('powershell', "Run the exact PowerShell command Write-Output 'hello' with timeout 5 seconds.", {'command':"Write-Output 'hello'",'timeout':5}),
 ('reply_user', 'Send the user exactly Done. as the final reply, with no newline.', {'content':'Done.'}),
]


def main(args):
    import torch
    from openjev_phase1.core import load_causal_model
    args.out.mkdir(); (args.out/'sources').mkdir()
    for file in [Path(__file__), ROOT/'deploy/logit_toolcall.py', ROOT/'src/openjev_phase1/direct.py']:
        shutil.copyfile(file, args.out/'sources'/file.name)
    tools = json.loads(args.schemas.read_text())
    (args.out/'tools.json').write_text(json.dumps(tools, ensure_ascii=False, indent=2))
    model, tokenizer, metadata = load_causal_model(str(args.model), args.model.name)
    metadata.update(gpu=torch.cuda.get_device_name(), xgrammar=importlib.metadata.version('xgrammar'),
                    methods=['whole','direct_cached','direct_reprefill'], repeats=args.repeats,
                    limitation='Small local model, exact-argument screening, no Pi tool execution, no shared DeepSeek service changes')
    (args.out/'manifest.json').write_text(json.dumps({'metadata':metadata,'cases':CASES},ensure_ascii=False,indent=2))
    start=time.perf_counter(); engine=module.Engine(model,tokenizer,tools)
    metadata['grammar_compile_seconds']=time.perf_counter()-start
    # Warm both mask and model paths. Warmup is retained, excluded from measured rows.
    warm=engine.run('Send the user exactly OK.', 'direct_cached', args.limit)
    (args.out/'warmup.json').write_text(json.dumps(warm,ensure_ascii=False,indent=2))
    (args.out/'compile.json').write_text(json.dumps(metadata,indent=2))
    jobs=[(case,repeat,mode) for case in CASES for repeat in range(args.repeats) for mode in metadata['methods']]
    random.Random(20260919).shuffle(jobs)
    for (name,task,arguments),repeat,mode in jobs:
        result=engine.run(task,mode,args.limit)
        row={'case':name,'repeat':repeat,'tool_correct':bool(result['call']) and result['call']['name']==name,
             'exact_call':result['call']=={'name':name,'arguments':arguments},**result}
        with (args.out/'rows.jsonl').open('a') as output:output.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(name,repeat,mode,'tool',row['tool_correct'],'exact',row['exact_call'],'tokens',row['output_tokens_including_eos'],'seconds',round(row['seconds'],3),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path)
    p.add_argument('--schemas',required=True,type=Path)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--limit',type=int,default=192)
    main(p.parse_args())
