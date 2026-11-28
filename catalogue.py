"""Render the public, script-free package catalogue from reviewed metadata."""
from html import escape
from pathlib import Path
from string import Template

SITE = Path(__file__).resolve().parent / 'site'
GROUPS = (
    ('modules', '모듈', ('module',)),
    ('layouts', '레이아웃', ('layout',)),
    ('skins', '스킨과 스타일', ('module_skin', 'widget_skin', 'editor_style')),
    ('widgets', '위젯', ('widget',)),
    ('addons', '애드온', ('addon',)),
)


def package_row(package, by_id):
    name = escape(package['id'])
    title = escape(package['title'])
    thumb = ''
    if package.get('thumbnail'):
        thumb = f'<img class="thumb" src="v1/thumbnails/{escape(package["thumbnail"])}" width="96" height="72" alt="">'
    downloads = []
    for release in package['releases']:
        if not release['withdrawn']:
            version = escape(release['version'])
            downloads.append(f'<a class="download" href="v1/files/{release["sha256"]}.zip" '
                             f'download="{name}-{version}.zip" aria-label="{title} {version} ZIP 다운로드">'
                             f'<span>{version}</span> ZIP 다운로드</a>')
    dependencies = [f'<a href="#{escape(dep)}">{escape(by_id[dep]["title"])}</a>' for dep in package.get('requires', [])]
    required = '<div class="requirements"><strong>함께 설치할 자료</strong><ul>' + ''.join(
        f'<li>{link}</li>' for link in dependencies) + '</ul></div>' if dependencies else ''
    description = f'<p>{escape(package["description"])}</p>' if package.get('description') else ''
    return f'''<li class="entry" id="{name}">
      {thumb}<div class="details"><h3><a href="https://github.com/{escape(package['repo'])}">{title}</a></h3>
      {description}<div class="meta"><span>{escape(package['author'])}</span><span>{escape(package['license'])}</span></div>{required}</div>
      <div class="downloads">{''.join(downloads) or '현재 내려받을 수 있는 버전이 없습니다.'}</div>
    </li>'''


def render(packages, by_id):
    links, sections = [], []
    for anchor, title, types in GROUPS:
        members = [p for p in packages if p['type'] in types]
        if not members:
            continue
        links.append(f'<a href="#group-{anchor}"><span>{title}</span><span>{len(members)}개</span></a>')
        rows = ''.join(package_row(p, by_id) for p in members)
        sections.append(f'<section class="group" aria-labelledby="group-{anchor}">'
                        f'<h2 id="group-{anchor}">{title}</h2><ul class="entries">{rows}</ul></section>')
    template = Template((SITE / 'index.html').read_text(encoding='utf-8'))
    return template.substitute(total=len(packages), category_links='\n'.join(links),
                               sections='\n'.join(sections) or '<p>등록된 자료가 없습니다.</p>').encode()
