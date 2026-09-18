import importlib.util,json,os
s=importlib.util.spec_from_file_location('bridge','integrations/pijit/bridge.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
source='import argparse\ndef build_parser():\n    p=argparse.ArgumentParser()\n    p.add_argument("--workers", type=int, default=4, help="old", required=False)\n    p.add_argument("--timeout", type=float, default=1.5)\n    p.add_argument("--host", default="localhost")\n    return p\n'
for task in ['Change --workers default to 6.', 'Change --timeout default to 2.5.', 'Change --host default to "remote".', 'Change --workers help to "Worker count".', 'Change --workers required to true.', 'Add alias -w to --workers.']:
 updated,record=b.schema_edit(source,task)
 print(json.dumps({'task':task,'record':record,'updated':updated},ensure_ascii=False),flush=True)
