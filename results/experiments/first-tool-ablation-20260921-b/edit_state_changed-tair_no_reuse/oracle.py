import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
import json
assert json.loads(Path("service.json").read_text())=={'service': {'port': 8443, 'label': '另一台机器', 'features': ['b', '新增']}, 'other': {'port': 9100}, 'enabled': False, 'retention': {'days': 17}}
