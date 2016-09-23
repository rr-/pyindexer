import os
import re
import json
from enum import Enum
from logging import getLogger
from typing import Mapping, List, Any, Callable
from datetime import datetime
from humanize import naturalsize

logger = getLogger(__name__)


SETTINGS_FILE = 'indexer.json'
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <style type="text/css">
        body {{
            background: #fafafa;
            color: #444;
            font-family: sans-serif;
        }}
        a {{
            color: green;
            text-decoration: none;
        }}
        a:hover {{
            color: red;
        }}
        a:visited {{
            color: brown;
        }}
        table {{
            margin: 1em 0;
            min-width: 50vw;
            border-collapse: collapse;
        }}
        .size {{
            width: 8em;
        }}
        .date {{
            width: 10em;
        }}
        th {{
            font-weight: normal;
            text-align: left;
            background: #DDC;
            border: 1px solid #AAA;
        }}
        h1 {{
            font-size: 20pt;
            font-weight: normal;
            padding: 0;
            margin: 0;
        }}
        hr {{
            margin: 0.25em 0;
            border: 1px solid #ddd;
        }}
        td, th {{
            text-align: left;
            padding: 0.2em 0.4em;
        }}
        td {{
            border-left: 1px solid #AAA;
            border-right: 1px solid #AAA;
        }}
        tr:last-child td {{
            border-bottom: 1px solid #AAA;
        }}
        tr:nth-child(even) {{
            background: #F4F4F4;
        }}
    </style>
</head>
    <body>{body}</body>
</html>'''

NOT_FOUND_TEMPLATE = '''
        <h1>Not found</h1>
        <p>The path <code>{path}</code> was not found on this server.</p>
'''


class SortStyle(Enum):
    Date = 'date'
    Name = 'name'
    Size = 'size'


class SortDir(Enum):
    Ascending = 'asc'
    Descending = 'desc'


class Settings:
    # TODO: use this version once Python 3.6 comes out
    # header: str = ''
    # footer: str = ''
    # sort_style: SortStyle = SortStyle.Date
    # sort_dir: SortDir = SortDir.Descending

    def __init__(self):
        # TODO: remove this version once Python 3.6 comes out
        self.header = ''
        self.footer = ''
        self.sort_style = SortStyle.Date
        self.sort_dir = SortDir.Descending


def get_not_found_response(web_path: str) -> str:
    return HTML_TEMPLATE.format(
        title='Not found',
        body=NOT_FOUND_TEMPLATE.format(path=web_path))


def list_entries(
        local_path: str, sort_style: SortStyle, sort_dir: SortDir) -> List:
    def convert(text: str) -> Any:
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key: str) -> List[Any]:
        return [convert(c) for c in re.split(r'(\d+)', key)]

    def name_sort_func(entry):
        return alphanum_key(entry.name)

    def size_sort_func(entry):
        return entry.stat().st_size

    def date_sort_func(entry):
        return entry.stat().st_mtime

    sort_funcs = {
        SortStyle.Name: name_sort_func,
        SortStyle.Date: date_sort_func,
        SortStyle.Size: size_sort_func,
    }

    # TODO: Use type annotations when Python 3.6 comes out
    dir_entries = []
    file_entries = []
    for entry in os.scandir(local_path):
        if entry.name != SETTINGS_FILE:
            [file_entries, dir_entries][entry.is_dir()].append(entry)
    dir_entries.sort(key=sort_funcs[sort_style])
    file_entries.sort(key=sort_funcs[sort_style])
    if sort_dir == SortDir.Descending:
        dir_entries.reverse()
        file_entries.reverse()
    return dir_entries + file_entries


def deserialize_settings(settings_path: str) -> Settings:
    settings = Settings()
    with open(settings_path, 'r') as handle:
        try:
            obj = json.load(handle)
            if 'header' in obj:
                settings.header = str(obj['header'])
            if 'footer' in obj:
                settings.footer = str(obj['footer'])
            if 'sort_style' in obj:
                settings.sort_style = SortStyle(obj['sort_style'])
            if 'sort_dir' in obj:
                settings.sort_dir = SortDir(obj['sort_dir'])
        except Exception as ex:
            logger.warning('Failed to decode %s (%s)', settings_path, ex)
        return settings


def get_settings(local_path: str, root_path: str) -> Settings:
    current_path = local_path
    while current_path.startswith(root_path):
        settings_path = os.path.join(current_path, SETTINGS_FILE)
        current_path = os.path.dirname(current_path)
        if os.path.exists(settings_path):
            return deserialize_settings(settings_path)
    return Settings()


def get_listing_response(
        base_url: str,
        local_path: str,
        web_path: str,
        settings: Settings) -> str:
    body = '<h1>Index of '
    link = '/'
    for group in [f for f in web_path.split('/') if f] + ['']:
        body += '<a href="%s">/</a>%s' % (link, group)
        link += '%s/' % group
    body += '</h1>'
    body += settings.header
    body += '<table>'
    body += '<thead><tr>'
    body += '<th class="name">Name</th>'
    body += '<th class="size">Size</th>'
    body += '<th class="date">Date</th>'
    body += '</tr></thead>'
    body += '<tbody>'

    for entry in list_entries(
            local_path, settings.sort_style, settings.sort_dir):
        stat = entry.stat()
        name = entry.name + ('/' if entry.is_dir() else '')
        body += '''<tr>
                <td class="name"><a href="{url}">{name}</a></td>
                <td class="size">{size}</td>
                <td class="date">{date:%Y-%m-%d %H:%M}</td>
            </tr>'''.format(
                url=os.path.join(base_url, web_path, name),
                name=name,
                size=naturalsize(stat.st_size),
                date=datetime.fromtimestamp(stat.st_mtime))
    body += '</tbody>'
    body += '</table>'
    body += settings.footer
    return HTML_TEMPLATE.format(
        title='Index of ' + web_path,
        body=body)


def application(
        env: Mapping[str, object], start_response: Callable) -> List[bytes]:
    base_url = '%s://%s/' % (env['REQUEST_SCHEME'], env['HTTP_HOST'])
    web_path = str(env['PATH_INFO'])
    root_path = str(env['DOCUMENT_ROOT'])
    local_path = root_path + web_path
    if not os.path.exists(local_path):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return [get_not_found_response(web_path).encode()]
    if not os.path.isdir(local_path):
        start_response(
            '200 OK', [('Content-Type', 'application/octet-stream')])
        with open(local_path, 'rb') as handle:
            return [handle.read()]

    settings = get_settings(local_path, root_path)

    start_response('200 OK', [('Content-Type', 'text/html')])
    return [get_listing_response(
        base_url, local_path, web_path, settings).encode()]
