"""Verify portable artifacts without needing SteamVR or a graphics driver."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def verify_archive(archive: Path, plan: dict) -> dict:
    expected = archive.with_suffix(archive.suffix + '.sha256').read_text(encoding='ascii').split()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected != [digest, archive.name]:
        raise ValueError('ZIP checksum or recorded filename does not match')
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        root = 'SteamVRColourLab/'
        for name in names:
            parts = name.replace('\\', '/').split('/')
            if not name.startswith(root) or '..' in parts or ':' in name:
                raise ValueError(f'Unsafe package path: {name}')
            if any(part.lower() in {'runs', 'settings', '__pycache__'} for part in parts):
                raise ValueError(f'Personal or source-only data in archive: {name}')
        required = ('SteamVRColourLab.exe', 'BUILD_INFO.json', 'LICENSE',
                    'THIRD_PARTY_NOTICES.md', 'licenses/MANIFEST.json',
                    'licenses/CPython-LICENSE.txt', 'start_windows.bat')
        missing = [name for name in required if root + name not in names]
        if missing or not any(name.startswith(root + '_internal/') for name in names):
            raise ValueError(f'Incomplete portable archive: {missing}')
        corrupt = bundle.testzip()
        if corrupt:
            raise ValueError(f'Corrupt ZIP member: {corrupt}')
        info = json.loads(bundle.read(root + 'BUILD_INFO.json').decode('utf-8-sig'))
        if (info.get('version'), info.get('source_commit')) != (plan['version'], plan['commit']):
            raise ValueError('Package version/commit does not match the release plan')
    return info


def smoke_executable(archive: Path, version: str) -> None:
    # A separate path containing spaces catches accidental dependencies on the
    # build directory. No external Python is visible to the frozen process.
    with tempfile.TemporaryDirectory(prefix='Colour Lab portable ') as temporary:
        home = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(home)
        executable = home / 'SteamVRColourLab' / 'SteamVRColourLab.exe'
        environment = os.environ.copy()
        system = Path(os.environ['SystemRoot'])
        environment['PATH'] = os.pathsep.join((str(system / 'System32'), str(system)))
        for name in ('PYTHONHOME', 'PYTHONPATH'):
            environment.pop(name, None)
        for argument in ('--help', '--version'):
            result = subprocess.run([str(executable), argument], cwd=home,
                                    env=environment, capture_output=True, text=True,
                                    check=True, timeout=60)
            if argument == '--version' and result.stdout.strip() != version:
                raise ValueError(f'Executable version mismatch: {result.stdout!r}')
            if argument == '--help' and '--self-test' not in result.stdout:
                raise ValueError('Executable did not return application help')
        if (executable.parent / 'runs').exists() or (executable.parent / 'settings').exists():
            raise ValueError('Informational CLI options initialized application state')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    output_root = Path(os.environ.get('COLOURLAB_OUTPUT_ROOT') or Path(__file__).resolve().parents[2] / 'builds' / 'SteamVRColourLab')
    parser.add_argument('--archive', type=Path, default=output_root / 'dist' / 'SteamVRColourLab-Windows-x64.zip')
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    info = verify_archive(args.archive, plan)
    if os.name == 'nt':
        smoke_executable(args.archive, plan['version'])
    print(json.dumps({'verified': True, 'version': info['version'], 'source_commit': info['source_commit']}))


if __name__ == '__main__':
    main()
