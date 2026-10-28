import json
from pathlib import Path

import pytest

from proving_ground.sandbox.loadgen import context_fill_text, generate_inputs


def test_tickets_are_deterministic(tmp_path: Path):
    a = generate_inputs("tickets", 3, tmp_path / "a", seed=1)
    b = generate_inputs("tickets", 3, tmp_path / "b", seed=1)
    names = sorted(p.name for p in a.iterdir())
    assert names == ["T-00000.json", "T-00001.json", "T-00002.json"]
    for name in names:
        assert (a / name).read_text() == (b / name).read_text()
    ticket = json.loads((a / "T-00001.json").read_text())
    assert set(ticket) == {"id", "customer", "plan", "priority", "subject", "body"}


def test_rows_and_files(tmp_path: Path):
    rows = generate_inputs("rows", 5, tmp_path)
    lines = (rows / "rows.csv").read_text().splitlines()
    assert lines[0] == "id,region,amount,note"
    assert len(lines) == 6
    files = generate_inputs("files", 4, tmp_path)
    assert len(list(files.iterdir())) == 4


def test_unknown_generator(tmp_path: Path):
    with pytest.raises(ValueError, match="built-in generators: files, rows, tickets"):
        generate_inputs("emails", 1, tmp_path)


def test_context_fill_size_and_determinism():
    text = context_fill_text(5000, seed=3)
    assert 20_000 <= len(text) < 21_500
    assert text == context_fill_text(5000, seed=3)
    assert text.startswith("# Project notes (background)")
