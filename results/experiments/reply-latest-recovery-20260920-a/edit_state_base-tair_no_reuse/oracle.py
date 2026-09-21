import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
import json
assert json.loads(Path("service.json").read_text())=={'service': {'port': 8443, 'label': '现有配置', 'features': ['a', 'b']}, 'other': {'port': 9000}, 'enabled': True}
