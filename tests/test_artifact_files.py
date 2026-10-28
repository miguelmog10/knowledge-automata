import pytest

from knowledge_automata.storage import artifact_files
from knowledge_automata.storage.artifact_files import ArtifactPathError


def test_a_copy_keeps_the_exact_bytes_and_is_never_overwritten(tmp_path):
    raw = b"\xef\xbb\xbf# Notes\r\nline\r"
    stored = "artifacts/ART-0001-notes.md"
    path = artifact_files.write_copy(tmp_path, stored, raw)
    assert path == tmp_path / "artifacts" / "ART-0001-notes.md"
    assert artifact_files.read_copy(tmp_path, stored) == raw
    with pytest.raises(FileExistsError):
        artifact_files.write_copy(tmp_path, stored, b"other")
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "stored",
    [
        "artifacts/../.env",
        "artifacts/..",
        "artifacts/sub/ART-0001.md",
        "artifacts\\ART-0001.md",
        "registers/decision-log/DEC-0001.json",
        "/etc/passwd",
        "artifacts/",
        "artifacts/.hidden",
        "artifacts/-x.md",
        "artifacts/café.md",
        "C:/artifacts/ART-0001.md",
    ],
)
def test_paths_outside_the_artifacts_folder_are_refused(tmp_path, stored):
    with pytest.raises(ArtifactPathError):
        artifact_files.resolve(tmp_path, stored)
    with pytest.raises(ArtifactPathError):
        artifact_files.write_copy(tmp_path, stored, b"x")
    assert not (tmp_path / "artifacts").exists()
