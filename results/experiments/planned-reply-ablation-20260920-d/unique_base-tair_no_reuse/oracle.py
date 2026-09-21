import os, sys
sys.path.insert(0, os.getcwd())
import subprocess
p=subprocess.run(["node","--input-type=module","-e",'import assert from \'node:assert/strict\'; import {uniqueStrings} from \'./unique_base.mjs\';\nconst input=[\'A\',\'a\',\'A\',\' B \',\'b\',\'中文\',\'中文\',\'\',\'\']; const copy=[...input];\nconst result=uniqueStrings(input);assert.deepEqual(result,["A", "a", " B ", "b", "中文", ""]);\nassert.deepEqual(input,copy);assert.notEqual(result,input);assert.deepEqual(uniqueStrings([]),[]);'],capture_output=True,text=True,timeout=5)
assert p.returncode==0,p.stderr
