"""Plan an immutable Git-tag release from conventional commit subjects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


VERSION_PATTERN = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
TAG_PATTERN = re.compile(r"v" + VERSION_PATTERN + r"\Z")
VERSION_ASSIGNMENT = re.compile(
    r"(?m)^__version__[ \t]*=[ \t]*(?P<quote>['\"])(?P<version>"
    + VERSION_PATTERN
    + r")(?P=quote)"
)
COMMIT_PREFIX = re.compile(r"^(fix|feat|rework)(?:\([^()\r\n]+\))?:[ \t]+\S")
BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
PREFIX_BUMP = {"fix": "patch", "feat": "minor", "rework": "major"}


class ReleasePolicyError(ValueError):
    """The repository cannot safely produce a release plan."""


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ReleasePolicyError(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def version_assignment(repo: Path, *, committed: bool = False) -> tuple[Path, str, re.Match[str]]:
    path = repo / "colourlab" / "__init__.py"
    # Decode bytes directly so stamping preserves the original line endings.
    source = (git(repo, "show", "HEAD:colourlab/__init__.py") if committed
              else path.read_bytes().decode("utf-8"))
    assignments = list(VERSION_ASSIGNMENT.finditer(source))
    if len(assignments) != 1:
        raise ReleasePolicyError(f"Expected one semantic __version__ assignment in {path}")
    return path, source, assignments[0]


def release_plan(repo: Path) -> dict[str, object]:
    repo = Path(repo).resolve()
    if git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise ReleasePolicyError("Full Git history is required; fetch with fetch-depth: 0")
    commit = git(repo, "rev-parse", "HEAD^{commit}")
    head_tags = [
        tag for tag in git(repo, "tag", "--points-at", "HEAD").splitlines()
        if TAG_PATTERN.fullmatch(tag)
    ]
    if len(head_tags) > 1:
        raise ReleasePolicyError("Ambiguous semantic version tags on HEAD: " + ", ".join(head_tags))
    if head_tags:
        tag = head_tags[0]
        return {
            "version": tag[1:], "tag": tag, "commit": commit, "base_tag": tag,
            "bump": "none", "release": True, "already_tagged": True,
        }

    tagged_versions = [
        (tuple(int(part) for part in match.groups()), tag)
        for tag in git(repo, "tag", "--merged", "HEAD").splitlines()
        if (match := TAG_PATTERN.fullmatch(tag))
    ]
    if tagged_versions:
        version, base_tag = max(tagged_versions)
    else:
        # A prior --stamp must not move the seed before the first release tag.
        _, _, assignment = version_assignment(repo, committed=True)
        version = tuple(int(part) for part in assignment.group("version").split("."))
        base_tag = None

    revision_range = f"{base_tag}..HEAD" if base_tag else "HEAD"
    bump = "none"
    for subject in git(repo, "log", "--format=%s", revision_range, "--").splitlines():
        match = COMMIT_PREFIX.match(subject)
        if match:
            candidate = PREFIX_BUMP[match.group(1)]
            if BUMP_RANK[candidate] > BUMP_RANK[bump]:
                bump = candidate
    major, minor, patch = version
    if bump == "major":
        version = (major + 1, 0, 0)
    elif bump == "minor":
        version = (major, minor + 1, 0)
    elif bump == "patch":
        version = (major, minor, patch + 1)
    version_text = ".".join(str(part) for part in version)
    tag = f"v{version_text}"
    should_release = bump != "none"
    # Feature branches may calculate a version already released on main.
    # They must still build; the publisher enforces immutable tag ownership.
    return {
        "version": version_text, "tag": tag, "commit": commit, "base_tag": base_tag,
        "bump": bump, "release": should_release, "already_tagged": False,
    }


def stamp_version(repo: Path, version: str) -> None:
    path, source, assignment = version_assignment(repo)
    start, end = assignment.span("version")
    path.write_bytes((source[:start] + version + source[end:]).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stamp", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = release_plan(args.repo)
        if args.stamp:
            stamp_version(args.repo, str(plan["version"]))
        encoded = json.dumps(plan, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
                for name, value in plan.items():
                    if isinstance(value, bool):
                        value = str(value).lower()
                    elif value is None:
                        value = ""
                    output.write(f"{name}={value}\n")
        print(encoded, end="")
        return 0
    except (ReleasePolicyError, OSError, UnicodeError) as error:
        print(f"release policy: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
