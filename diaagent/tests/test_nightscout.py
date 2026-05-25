import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nightscout import _extract_entry, mgdl_to_mmol, normalize_nightscout_url  # noqa: E402


def test_mgdl_to_mmol() -> None:
    assert mgdl_to_mmol(108) == 6.0


def test_normalize_nightscout_url_adds_https() -> None:
    assert normalize_nightscout_url("example.org/") == "https://example.org"


def test_extract_entry_from_list_response() -> None:
    entry = _extract_entry([{"sgv": 110, "direction": "Flat"}])

    assert entry == {"sgv": 110, "direction": "Flat"}
