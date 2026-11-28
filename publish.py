#!/usr/bin/env python3
"""Validate reviewed GitHub source archives and build the XE package registry v1."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from catalogue import SITE, render

HERE = Path(__file__).resolve().parent
LIMIT = 32 * 1024 * 1024
ENTRYPOINTS = {'module': '{id}.class.php', 'widget': '{id}.class.php', 'addon': '{id}.addon.php', 'layout': 'layout.html', 'mobile_layout': 'layout.html'}
RESERVED = {
    'module': 'addon admin adminlogging autoinstall board comment communication counter document editor file importer install integration_search krzip layout member menu message module packageinstaller page point poll rss seo session spamfilter tag trash widget',
    'addon': 'adminlogging autolink captcha captcha_member counter member_communication member_extra_info oembed point_level_icon resize_image',
    'widget': 'content counter_status language_select login_info mcontent',
    'layout': 'default user_layout xedition',
    'mobile_layout': 'default simplegray colorcode',
}


# Only nested component locations reviewed for this installer are accepted.
SKIN_PARENTS = {
    'module_skin': {'modules/board/skins', 'modules/member/skins', 'modules/communication/skins'},
    'mobile_module_skin': {'modules/board/m.skins', 'modules/member/m.skins', 'modules/communication/m.skins'},
    'editor_style': {'modules/editor/styles'},
    'widget_skin': {'widgets/content/skins'},
}
BUILTIN_SKINS = {'default', 'ckeditor_light', 'ckeditor_recommend', 'dreditor', 'xestyle', 'xestyleblack'}
DIRECTORIES = {'module': 'modules', 'addon': 'addons', 'layout': 'layouts', 'mobile_layout': 'm.layouts', 'widget': 'widgets'}


def install_path(package):
    kind, name = package['type'], package['id']
    if kind in SKIN_PARENTS:
        parent, _, folder = package.get('source_path', '').rpartition('/')
        require(parent in SKIN_PARENTS[kind] and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', folder)
                and folder not in BUILTIN_SKINS and package['source_path'] not in
                ('modules/board/skins/xedition', 'modules/board/m.skins/simplegray'), 'invalid skin destination')
        category = {'editor_style': 'style', 'mobile_module_skin': 'mskin'}.get(kind, 'skin')
        require(name == '_'.join([parent.split('/')[1], category, folder]), 'skin identity mismatch')
        return parent + '/' + folder
    if kind == 'mobile_layout':
        match = re.fullmatch(r'mobile_layout_([a-z][a-z0-9_]*)', name)
        require(match and 'source_path' in package, 'invalid mobile layout identity')
        name = match[1]
    require(kind in DIRECTORIES and name not in RESERVED[kind].split(), 'reserved installation path')
    target = DIRECTORIES[kind] + '/' + name
    require(package.get('source_path', target) == target, 'component source path mismatch')
    return target


def serialized(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_release(package, release, archive):
    require(len(archive) == release['size'] and digest(archive) == release['sha256'], 'ZIP digest or size mismatch')
    prefix = package.get('source_path', package['repo'].split('/')[1] + '-' + release['revision']) + '/'
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
        skin = package['type'] in SKIN_PARENTS
        descriptor = 'skin.xml' if skin else 'conf/info.xml'
        if not skin:
            require(ENTRYPOINTS[package['type']].format(id=package['id']) in entries, 'missing package entry point')
        info = ET.fromstring(z.read(prefix + descriptor))
        expected_tag = 'skin' if skin else package['type']
        if expected_tag == 'mobile_layout':
            expected_tag = 'layout'
        require(info.tag == expected_tag, 'package type mismatch')
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
        require(after and before['repo'] == after['repo'] and before.get('type', 'module') == after['type'] and before.get('source_path') == after.get('source_path'), 'registered package identity changed')
        versions = {r['version']: r for r in after['releases']}
        for r in before['releases']:
            new = versions.get(r['version'])
            require(new and all(new[k] == r[k] for k in ('revision','size','sha256','tree')), 'published artifact changed or disappeared')


def validate_dependencies(packages):
    by_id = {p['id']: p for p in packages}
    done = set()

    def visit(name, visiting):
        require(name in by_id and name not in visiting, 'missing or cyclic package dependency: ' + name)
        if name in done:
            return
        required = by_id[name].get('requires', [])
        require(isinstance(required, list) and all(isinstance(i, str) for i in required)
                and len(required) == len(set(required)), 'invalid dependency list')
        for dependency in required:
            visit(dependency, visiting | {name})
        done.add(name)

    for name in by_id:
        visit(name, set())
    return by_id


def build(output, key, baseline):
    packages = json.loads((HERE / 'packages.json').read_text())
    if baseline:
        check_history(json.loads(baseline.read_text()), packages)
    by_id = validate_dependencies(packages)
    summaries = {}
    v2 = {}
    legacy = {}
    for p in packages:
        name = p['id']
        install_path(p)
        require(re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) and name not in summaries, 'invalid or duplicate module id')
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
        if p['type'] not in ('mobile_module_skin', 'mobile_layout') and not p.get('source_path', '').startswith('modules/board/skins/'):
            v2[name] = digest(detail)
        if name in v2 and 'source_path' not in p and not p.get('requires'):
            legacy[name] = digest(detail)
        if 'thumbnail' in p:
            filename = p['thumbnail']
            require(re.fullmatch(r'[a-z][a-z0-9_-]{0,63}\.png', filename), 'invalid thumbnail filename')
            image = (HERE / 'thumbnails' / filename).read_bytes()
            require(image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) <= 512 * 1024, 'invalid PNG thumbnail')
            atomic_write(output / 'v1/thumbnails' / filename, image)
    # Older clients reject an entire index if any package uses an unknown destination.
    while True:
        missing = [name for name in v2 if any(dep not in v2 for dep in by_id[name].get('requires', []))]
        if not missing:
            break
        for name in missing:
            del v2[name]
    for filename in ('catalog.css', 'logo-light.png', 'logo-dark.png', 'favicon-light.png'):
        atomic_write(output / 'assets' / filename, (SITE / filename).read_bytes())
    atomic_write(output / 'index.html', render(packages, by_id))
    if key:
        now = int(time.time())
        public = subprocess.check_output(['openssl','pkey','-in',key,'-pubout'])
        require(public == (HERE / 'registry.pem').read_bytes(), 'signing key mismatch')
        for schema, filename, catalog in [(1, 'index.json', legacy), (2, 'index-v2.json', v2), (3, 'index-v3.json', summaries)]:
            payload = serialized(dict(schema=schema, generation=now, issued=now, expires=now + 21 * 86400, packages=catalog))
            sig = subprocess.run(['openssl','dgst','-sha256','-sign',key], input=payload, capture_output=True, check=True).stdout
            atomic_write(output / 'v1' / filename, serialized(dict(payload=base64.b64encode(payload).decode(), signature=base64.b64encode(sig).decode())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, help='previously published packages.json')
    parser.add_argument('--key', help='PEM private key, for a trusted production build')
    args = parser.parse_args()
    build(args.output, args.key, args.baseline)
