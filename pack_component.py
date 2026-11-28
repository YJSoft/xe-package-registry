#!/usr/bin/env python3
"""Rebuild a reviewed component ZIP from tracked files in a local upstream clone."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from publish import HERE, install_path, require, verify_release


def pack(package, release, checkout):
    if package.get('bundle_composer'):
        return pack_composer(package, release, checkout)
    component = install_path(package)
    require(package['source_path'] == component, 'expected a split component')
    notices = subprocess.check_output(['git', '-C', checkout, 'ls-tree', '--name-only',
                                       release['revision'], 'LICENSE', 'NOTICE'], text=True).splitlines()
    data = subprocess.check_output(['git', '-C', checkout, 'archive', '--format=tar',
                                    release['revision'], component, *notices])
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
        for item in tar:
            if item.name in notices:
                entries[item.name] = tar.extractfile(item).read()
            elif item.name.startswith(component + '/'):
                name = item.name[len(component) + 1:]
                require(item.isdir() or item.isfile(), 'unsupported component file')
                require(name not in notices, 'preserve the component license separately')
                entries[name + '/' if item.isdir() else name] = None if item.isdir() else tar.extractfile(item).read()
    require('LICENSE' in entries, 'missing upstream license')
    return write_zip(component, entries)


def pack_composer(package, release, checkout):
    # Build from the pinned commit in a clean directory, without any local settings or keys.
    data = subprocess.check_output(['git', '-C', checkout, 'archive', release['revision']])
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
            tar.extractall(root, filter='data')
        require((root / 'composer.lock').is_file(), 'expected a locked Composer project')
        subprocess.run(['composer', 'install', '--no-dev', '--prefer-dist', '--no-plugins', '--no-scripts',
                        '--optimize-autoloader', '--no-interaction'], cwd=root, check=True,
                       env=dict(os.environ, COMPOSER_ROOT_VERSION=release['version']))
        entries = {}
        for path in root.rglob('*'):
            require(not path.is_symlink() and (path.is_dir() or path.is_file()), 'unsupported Composer file')
            name = path.relative_to(root).as_posix()
            entries[name + '/' if path.is_dir() else name] = None if path.is_dir() else path.read_bytes()
    return write_zip(package['repo'].split('/')[1] + '-' + release['revision'], entries)


def write_zip(component, entries):
    archive = io.BytesIO()
    with ZipFile(archive, 'w') as output:
        for name, contents in sorted(entries.items()):
            entry = ZipInfo(component + '/' + name, (2025, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o40755 if contents is None else 0o100644) << 16
            output.writestr(entry, contents or b'', compress_type=ZIP_DEFLATED, compresslevel=9)
    return archive.getvalue()


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('checkout', type=Path)
    cli.add_argument('package_id')
    cli.add_argument('version')
    cli.add_argument('output', type=Path)
    args = cli.parse_args()
    package = next(p for p in json.loads((HERE / 'packages.json').read_text()) if p['id'] == args.package_id)
    release = next(r for r in package['releases'] if r['version'] == args.version)
    archive = pack(package, release, args.checkout)
    verify_release(package, release, archive)
    args.output.write_bytes(archive)
