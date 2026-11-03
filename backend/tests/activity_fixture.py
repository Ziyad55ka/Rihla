import json
from pathlib import Path


def mock_data():
    return json.loads(
        (Path(__file__).parent / "fixtures/activities.json").read_text(encoding="utf8")
    )
