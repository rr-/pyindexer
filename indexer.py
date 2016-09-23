import os
import re
from typing import Mapping, List, Any, Callable
from datetime import datetime
from humanize import naturalsize


HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <style type="text/css">
        body {{ background: #FFFAF5; font-family: sans-serif; }}
        a {{ color: green; }}
        table {{ border-collapse: collapse; min-width: 50vw; }}
        h1 {{ font-size: 20pt; font-weight: normal; }}
        th, td {{ text-align: left; padding: 0.3em; }}
        th {{ font-weight: normal; background: #DDC; }}
        td {{ border-left: 1px solid #DDC; border-right: 1px solid #DDC; }}
        tr:last-child td {{ border-bottom: 1px solid #DDC; }}
    </style>
</head>
    <body>{body}</body>
</html>'''

NOT_FOUND_TEMPLATE = '''
        <h1>Not found</h1>
        <p>The path <code>{path}</code> was not found on this server.</p>
'''


def get_not_found_response(web_path):
    return HTML_TEMPLATE.format(
        title='Not found',
        body=NOT_FOUND_TEMPLATE.format(path=web_path))


def list_entries(local_path: str) -> List:
    def convert(text: str) -> List[Any]:
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key: str) -> List[Any]:
        return [convert(c) for c in re.split(r'(\d+)', key)]

    def sort_func(entry):
        return not entry.is_dir(), alphanum_key(entry.name)

    entries = list(os.scandir(local_path))
    entries.sort(key=sort_func)
    return entries


def get_listing_response(base_url: str, local_path: str, web_path: str) -> str:
    body = '<h1>Index of ' + web_path + '</h1>'
    body += '<table>'
    body += '<thead><tr>'
    for column_name in ['Name', 'Size', 'Date']:
        body += '<th>%s</th>' % column_name
    body += '</tr></thead>'
    body += '<tbody>'


    for entry in list_entries(local_path):
        stat = entry.stat()
        name = entry.name + ('/' if entry.is_dir() else '')
        body += '''<tr>
                <td><a href="{url}">{name}</a></td>
                <td>{size}</td>
                <td>{date:%Y-%m-%d %H:%M}</td>
            </tr>'''.format(
                url=os.path.join(base_url, web_path, name),
                name=name,
                size=naturalsize(stat.st_size),
                date=datetime.fromtimestamp(stat.st_mtime))
    body += '</tbody>'
    body += '</table>'
    return HTML_TEMPLATE.format(
        title='Index of ' + web_path,
        body=body)


def application(
        env: Mapping[str, object], start_response: Callable) -> List[bytes]:
    base_url = env['REQUEST_SCHEME'] + '://' + env['HTTP_HOST'] + '/'
    web_path = env['PATH_INFO']
    local_path = env['DOCUMENT_ROOT'] + web_path
    if not os.path.exists(local_path):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return [get_not_found_response(web_path).encode()]
    if not os.path.isdir(local_path):
        start_response('200 OK', [('Content-Type', 'application/octet-stream')])
        with open(local_path, 'rb') as handle:
            return [handle.read()]

    start_response('200 OK', [('Content-Type', 'text/html')])
    return [get_listing_response(base_url, local_path, web_path).encode()]
