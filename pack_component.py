#!/usr/bin/env python3
"""Rebuild a reviewed component ZIP from tracked files in a local upstream clone."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from publish import HERE, install_path, require, verify_release


def pack(package, release, checkout):
    component = install_path(package)
    require(package['source_path'] == component, 'expected a split component')
    data = subprocess.check_output(['git', '-C', checkout, 'archive', '--format=tar',
                                    release['revision'], component, 'LICENSE'])
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
        for item in tar:
            if item.name == 'LICENSE':
                entries['LICENSE'] = tar.extractfile(item).read()
            elif item.name.startswith(component + '/'):
                name = item.name[len(component) + 1:]
                require(item.isdir() or item.isfile(), 'unsupported component file')
                require(name != 'LICENSE', 'preserve the component license separately')
                entries[name + '/' if item.isdir() else name] = None if item.isdir() else tar.extractfile(item).read()
    require('LICENSE' in entries, 'missing upstream license')
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
