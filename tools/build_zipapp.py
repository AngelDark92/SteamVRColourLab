#!/usr/bin/env python3
"""Build the runnable .pyz from source without including tests or dependencies."""
from pathlib import Path
import argparse
import os
import shutil
import tempfile
import zipapp


def main():
    root = Path(__file__).resolve().parents[1]
    output_root = Path(os.environ.get('COLOURLAB_OUTPUT_ROOT') or root.parent / 'builds' / 'SteamVRColourLab').resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=output_root / 'dist' / 'SteamVRColourLab.pyz')
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.is_relative_to(root):
        parser.error('Build output must be outside the source checkout')
    staging_root = output_root / 'build' / 'zipapp'
    if staging_root.is_relative_to(root) or root.is_relative_to(output_root):
        parser.error('COLOURLAB_OUTPUT_ROOT must be outside the source checkout and must not contain it')
    staging_root.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as temp:
        staging = Path(temp)
        shutil.copy2(root / "app.py", staging / "app.py")
        shutil.copytree(root / "colourlab", staging / "colourlab",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (staging / "__main__.py").write_text(
            "from app import main\nraise SystemExit(main())\n", encoding="utf-8")
        shutil.copy2(root / "LICENSE", staging / "LICENSE")
        zipapp.create_archive(staging, args.output, compressed=True)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
