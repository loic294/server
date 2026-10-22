"""Prepare the server and matching frontend wheels for an unofficial test image."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def set_project_version(path: Path, version: str) -> None:
    """Set exactly one project version without changing unrelated TOML formatting."""
    text = path.read_text()
    if tomllib.loads(text)["project"]["version"] != "0.0.0":
        raise ValueError(f"{path} is not an unversioned source checkout")
    text, count = re.subn(r'(?m)^version\s*=\s*"0\.0\.0"\s*$', f'version = "{version}"', text)
    if count != 1:
        raise ValueError(f"Expected exactly one project version in {path}")
    path.write_text(text)


def prepare(root: Path, frontend: Path, version: str) -> None:
    """Pin both source packages and the image requirements to the same test version."""
    if not re.fullmatch(r"2\.11\.0\.dev[1-9][0-9]*", version):
        raise ValueError("Expected a unique 2.11.0.devN test version")
    project = root / "pyproject.toml"
    dependencies = tomllib.loads(project.read_text())["project"]["dependencies"]
    pins = [
        dep
        for dep in dependencies
        if dep.startswith(("music-assistant-frontend==", "music-assistant-frontend @ "))
    ]
    if len(pins) != 1:
        raise ValueError("Expected exactly one pinned frontend dependency")
    old_pin = pins[0]
    new_pin = f"music-assistant-frontend=={version}"
    requirements = root / "requirements_all.txt"
    for path in (project, requirements):
        text = path.read_text()
        if text.count(old_pin) != 1:
            raise ValueError(f"Expected exactly one {old_pin} in {path}")
        path.write_text(text.replace(old_pin, new_pin))
    set_project_version(project, version)
    set_project_version(frontend / "pyproject.toml", version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--frontend-dir", type=Path, required=True)
    arguments = parser.parse_args()
    prepare(Path.cwd(), arguments.frontend_dir, arguments.version)
