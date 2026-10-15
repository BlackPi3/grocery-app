"""Every file the server reads besides code goes into the server image.

2026-10-15: the privacy page was served from the working tree in every test
and was missing from the installed package, so the live `/privacy` was a 500.
"""

from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "grocery_app"


def test_every_page_script_and_seed_is_packaged():
    patterns = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "tool"]["setuptools"]["package-data"]["grocery_app"]
    shipped = [f.relative_to(PACKAGE).as_posix() for suffix in ("html", "js", "sql")
               for f in PACKAGE.rglob(f"*.{suffix}")]
    assert shipped, "found the files to check"
    missing = [f for f in shipped if not any(fnmatch(f, p) for p in patterns)]
    assert missing == [], f"not in [tool.setuptools.package-data]: {missing}"
