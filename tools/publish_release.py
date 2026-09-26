"""Publish a verified archive, pinning its version tag to the tested commit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from tools.verify_package import verify_archive


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding='utf-8').strip()


def publish(artifacts: Path) -> None:
    plan = json.loads((artifacts / 'build/release-plan.json').read_text(encoding='utf-8'))
    archive = artifacts / 'dist/SteamVRColourLab-Windows-x64.zip'
    verify_archive(archive, plan)
    if not plan['release']:
        raise ValueError('This commit does not request a release')
    commit, tag = plan['commit'], plan['tag']
    if run('git', 'rev-parse', 'HEAD') != commit:
        raise ValueError('Refusing to publish artifacts built from another commit')
    # Refresh tags after the potentially long build, then recompute the plan.
    # A conflicting tag or rerun of an older commit must never move a release.
    run('git', 'fetch', 'origin', '--tags')
    fresh = json.loads(run(sys.executable, 'tools/release_policy.py', '--output', 'build/publish-plan.json'))
    if fresh['version'] != plan['version']:
        raise ValueError('Release version changed during the build; rerun the workflow')
    known_tags = run('git', 'tag', '--list', 'v*').splitlines()
    versions = [tuple(map(int, value[1:].split('.'))) for value in known_tags
                if re.fullmatch(r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', value)]
    wanted = tuple(map(int, plan['version'].split('.')))
    if versions and max(versions) > wanted:
        raise ValueError('A newer version already exists; refusing a stale release')
    if tag in known_tags:
        if run('git', 'rev-parse', f'{tag}^{{commit}}') != commit:
            raise ValueError('Version tag already belongs to another commit')
    else:
        run('git', 'tag', tag, commit)
        run('git', 'push', 'origin', f'refs/tags/{tag}')

    # Query with a command that distinguishes absence from network/auth failure.
    # Pagination prevents old reruns from mistaking an existing release as absent.
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', 'repos/{owner}/{repo}/releases?per_page=100'))
    existing = next((release for page in pages for release in page if release['tag_name'] == tag), None)
    if existing and not existing['draft']:
        print(f'{tag} is already published; leaving existing assets unchanged.')
        return
    if not existing:
        notes = artifacts / 'release-notes.md'
        revision = f"{plan['base_tag']}..{commit}" if plan['base_tag'] else commit
        subjects = run('git', 'log', '--format=- %s (%h)', revision)
        notes.write_text(
            f"Portable Windows x64 build from `{commit}`.\n\n"
            f"Extract the complete ZIP and run `SteamVRColourLab.exe`; Python is bundled.\n\n"
            f"Validation: automated tests with Mesa software rendering, Windows package integrity, "
            f"and relocated executable startup. Headset behavior requires separate runtime testing.\n\n"
            f"Changes since the previous version:\n\n{subjects}\n", encoding='utf-8')
        run('gh', 'release', 'create', tag, '--verify-tag', '--draft', '--title', tag, '--notes-file', str(notes))
    run('gh', 'release', 'upload', tag, str(archive), str(archive) + '.sha256', '--clobber')
    run('gh', 'release', 'edit', tag, '--draft=false', '--latest')
    print(f'Published {tag} from {commit}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    publish(parser.parse_args().artifacts)
