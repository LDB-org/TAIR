import json
from pathlib import Path
def settings():
    return json.loads((Path(__file__).parent/'config/settings.json').read_text())
