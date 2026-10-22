"""Tests for matching unofficial server/frontend build inputs."""

from pathlib import Path

import pytest

from scripts.prepare_test_release import prepare, set_project_version


@pytest.mark.parametrize(
    "frontend_pin",
    [
        "music-assistant-frontend==2.17.347",
        "music-assistant-frontend @ "
        "https://example.com/music_assistant_frontend-2.17.347-py3-none-any.whl#sha256=" + "a" * 64,
    ],
)
def test_prepare_pins_both_packages_and_image_requirements(
    tmp_path: Path, frontend_pin: str
) -> None:
    """The image resolves its custom frontend from the local wheel directory."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "0.0.0"\ndependencies = ["{frontend_pin}", "other==1"]\n'
    )
    (frontend / "pyproject.toml").write_text('[project]\nversion = "0.0.0"\n')
    (tmp_path / "requirements_all.txt").write_text(f"{frontend_pin}\nother==1\n")

    prepare(tmp_path, frontend, "2.11.0.dev1001")

    assert 'version = "2.11.0.dev1001"' in (tmp_path / "pyproject.toml").read_text()
    assert 'version = "2.11.0.dev1001"' in (frontend / "pyproject.toml").read_text()
    assert "music-assistant-frontend==2.11.0.dev1001" in (tmp_path / "pyproject.toml").read_text()
    assert (tmp_path / "requirements_all.txt").read_text() == (
        "music-assistant-frontend==2.11.0.dev1001\nother==1\n"
    )


@pytest.mark.parametrize("version", ["latest", "2.10.7", "2.11.0.dev0", "2.11.0.dev1\nbad"])
def test_prepare_rejects_non_test_versions(tmp_path: Path, version: str) -> None:
    """A test pipeline cannot accidentally prepare an official stable release."""
    with pytest.raises(ValueError, match="unique"):
        prepare(tmp_path, tmp_path / "frontend", version)


def test_set_version_rejects_already_versioned_checkout(tmp_path: Path) -> None:
    """A rerun cannot silently build a differently versioned source tree."""
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nversion = "2.10.7"\n')
    with pytest.raises(ValueError, match="unversioned"):
        set_project_version(project, "2.11.0.dev1")
