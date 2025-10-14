"""Tests for repository-level metadata and documentation.

This module ensures essential top-level project files (e.g. README.md)
exist in the expected location.
"""

from pathlib import Path


def test_readme_exists(project_root: Path) -> None:
    """Ensure that a README file exists at the project root."""
    readme = project_root / "README.md"
    assert readme.exists(), "README.md should exist at the project root"
