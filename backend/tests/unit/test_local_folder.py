from pathlib import Path

import pytest
from app.services.local_folder import list_local_files, local_folder, read_local_file


def test_local_folder_rejects_paths_outside_the_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VAVE_DATA_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    folder = local_folder()
    (folder / "ideas.csv").write_text("Idea_ID\nVAVE-1\n", encoding="utf-8")
    names = [item["name"] for item in list_local_files()]
    assert names == ["ideas.csv"]
    filename, content = read_local_file("ideas.csv")
    assert filename == "ideas.csv"
    assert b"VAVE-1" in content
    with pytest.raises(ValueError):
        read_local_file("../secrets.env")
    with pytest.raises(ValueError):
        read_local_file(str(Path("nested") / "ideas.csv"))
    get_settings.cache_clear()
