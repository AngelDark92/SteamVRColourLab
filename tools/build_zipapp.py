#!/usr/bin/env python3
"""Build the runnable .pyz from source without including tests or dependencies."""
from pathlib import Path
import argparse
import shutil
import tempfile
import zipapp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/SteamVRColourLab.pyz"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
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
