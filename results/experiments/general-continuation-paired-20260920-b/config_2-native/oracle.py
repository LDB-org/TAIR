import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
import json
assert json.loads(Path("service.json").read_text())=={'service': {'port': 9443, 'label': '保留', 'features': ['a', 'b']}, 'other': {'port': 9000}, 'enabled': True}
