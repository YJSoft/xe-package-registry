#!/usr/bin/env python3
"""Validate reviewed GitHub source archives and build the XE package registry v1."""
import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
LIMIT = 32 * 1024 * 1024


def serialized(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_release(package, release, archive):
    require(len(archive) == release['size'] and digest(archive) == release['sha256'], 'ZIP digest or size mismatch')
    prefix = package['repo'].split('/')[1] + '-' + release['revision'] + '/'
    entries = {}
    seen = set()
    size = 0
    with ZipFile(io.BytesIO(archive)) as z:
        require(len(z.infolist()) <= 8192, 'too many entries')
        for item in z.infolist():
            require(item.filename.startswith(prefix), 'unexpected ZIP root')
            path = item.filename[len(prefix):]
            if not path:
                continue
            parts = path.rstrip('/').split('/')
            require(all(re.fullmatch(r'[-a-zA-Z0-9_.@+ ]+', x) and x not in ('.', '..') for x in parts), 'unsafe ZIP path')
            key = path.rstrip('/').lower()
            require(key not in seen, 'duplicate ZIP path')
            seen.add(key)
            size += item.file_size
            kind = stat.S_IFMT(item.external_attr >> 16)
            require(size <= LIMIT and item.file_size <= 8 * 1024 * 1024 and kind in (0, stat.S_IFDIR, stat.S_IFREG), 'invalid ZIP entry')
            entries[path] = '-' if item.is_dir() else digest(z.read(item))
        require(package['id'] + '.class.php' in entries, 'missing module class')
        info = ET.fromstring(z.read(prefix + 'conf/info.xml'))
        require(info.findtext('version') == release['version'], 'module version mismatch')
    tree = b''.join((name + '\0' + entries[name] + '\n').encode() for name in sorted(entries))
    require(digest(tree) == release['tree'], 'installed tree digest mismatch')


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(data)
    tmp.replace(path)


def check_history(old, packages):
    current = {p['id']: p for p in packages}
    for before in old:
        after = current.get(before['id'])
        require(after and before['repo'] == after['repo'], 'registered package identity changed')
        versions = {r['version']: r for r in after['releases']}
        for r in before['releases']:
            new = versions.get(r['version'])
            require(new and all(new[k] == r[k] for k in ('revision','size','sha256','tree')), 'published artifact changed or disappeared')


def build(output, key, baseline):
    packages = json.loads((HERE / 'packages.json').read_text())
    if baseline:
        check_history(json.loads(baseline.read_text()), packages)
    summaries = {}
    links = []
    for p in packages:
        name = p['id']
        require(re.fullmatch(r'[a-z][a-z0-9_]*', name) and name not in summaries, 'invalid or duplicate module id')
        require(re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', p['repo']), 'invalid repository')
        versions = set()
        for r in p['releases']:
            require(re.fullmatch(r'[0-9a-f]{40}', r['revision']) and 0 < r['size'] <= LIMIT, 'invalid revision or size')
            require(r['version'] not in versions and isinstance(r['withdrawn'], bool), 'duplicate or invalid release')
            versions.add(r['version'])
            require(re.fullmatch(r'[0-9a-f]{64}', r['sha256']), 'invalid archive hash')
            path = HERE / 'archives' / (r['sha256'] + '.zip')
            require(path.is_file() and path.stat().st_size == r['size'], 'approved ZIP missing')
            archive = path.read_bytes()
            verify_release(p, r, archive)
            atomic_write(output / 'v1/files' / (r['sha256'] + '.zip'), archive)
        require(versions, 'empty release list')
        detail = serialized(p)
        location = 'v1/details/' + digest(detail) + '.json'
        atomic_write(output / location, detail)
        summaries[name] = digest(detail)
        links.append('<li><a href="https://github.com/%s">%s</a> · <a href="%s">버전 정보</a></li>' %
                     (html.escape(p['repo']), html.escape(p['title']), location))
    atomic_write(output / 'index.html', ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>XE 쉬운설치 자료실</title><h1>XE 쉬운설치 자료실</h1><ul>' + ''.join(links) + '</ul><a href="v1/index.json">서명된 자료 목록</a></html>').encode())
    if key:
        now = int(time.time())
        payload = serialized(dict(schema=1, generation=now, issued=now, expires=now + 21 * 86400, packages=summaries))
        sig = subprocess.run(['openssl','dgst','-sha256','-sign',key], input=payload, capture_output=True, check=True).stdout
        public = subprocess.check_output(['openssl','pkey','-in',key,'-pubout'])
        require(public == (HERE / 'registry.pem').read_bytes(), 'signing key mismatch')
        atomic_write(output / 'v1/index.json', serialized(dict(payload=base64.b64encode(payload).decode(), signature=base64.b64encode(sig).decode())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, help='previously published packages.json')
    parser.add_argument('--key', help='PEM private key, for a trusted production build')
    args = parser.parse_args()
    build(args.output, args.key, args.baseline)
