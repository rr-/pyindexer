import os
import re
import json
from urllib.parse import parse_qsl, quote
from enum import Enum
from logging import getLogger
from typing import Mapping, List, Any, Callable
from datetime import datetime
from humanize import naturalsize

logger = getLogger(__name__)


SETTINGS_FILE = 'indexer.json'

CSS = (
    'body{background:#fafafa;color:#444;font-family:sans-serif}' +
    'a{color:green;text-decoration:none}' +
    'a:hover{color:red}' +
    'a:visited{color:brown}' +
    'table{margin:1em 0;min-width:50vw;border-collapse:collapse}' +
    '.size{width:8em}' +
    '.date{width:10em}' +
    'th{font-weight:normal;background:#DDC;border:1px solid #AAA}' +
    'h1{font-weight:normal;font-size:20pt;padding:0;margin:0}' +
    'td, th{text-align:left;padding:0.2em 0.4em}' +
    'td{border-left:1px solid #AAA;border-right:1px solid #AAA}' +
    'tr:last-child td{border-bottom:1px solid #AAA}' +
    'tr:nth-child(even){background:#F4F4F4}' +
    '.icon{display:inline-block;text-align:center;width:16px;height:16px;background-repeat:no-repeat;background-size:contain}' +
    '.icon.go-up{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48cGF0aCBmaWxsPSIjNDQ0IiBkPSJNMTMgMTRoLTJWN0g3LjA1MVY1SDEzeiIvPjxwYXRoIGZpbGw9IiM0NDQiIGQ9Ik04IDkuMzkxTDIgNmw2LTMuMzkxeiIvPjwvc3ZnPg==")}' +
    '.icon.dir{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48ZyBmaWxsPSIjNDQ0Ij48cGF0aCBkPSJNNSAzaDEwdjJINXpNMSA2aDE0djdIMXoiLz48L2c+PC9zdmc+")}' +
    '.icon.file{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48cGF0aCBmaWxsPSIjNDQ0IiBkPSJNMTMgMTVIM1YxaDcuNjAxTDEzIDMuNFYxNXpNMTEgNUw5IDNINXYxMGg2VjV6Ii8+PC9zdmc+")}' +
    '.icon.sort-asc{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48cGF0aCBmaWxsPSIjNDQ0IiBkPSJNMTQgMTNMOCA3bC02IDZ6Ii8+PC9zdmc+")}' +
    '.icon.sort-desc{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48cGF0aCBmaWxsPSIjNDQ0IiBkPSJNMTQgOGwtNiA2LTYtNnoiLz48L3N2Zz4=")}' +
    'th .icon{padding-left:0.25em}' +
    'td .icon{padding-right:0.25em}')

HTML_TEMPLATE = (
    '<!DOCTYPE html>' +
    '<html>' +
    '<head>' +
    '<meta charset="utf-8"/>' +
    '<title>{title}</title>' +
    '<style type="text/css">' +
    CSS.replace('{', '{{').replace('}', '}}') +
    '</style>' +
    '</head>' +
    '<body>{body}</body>' +
    '</html>')

NOT_FOUND_TEMPLATE = (
    '<h1>Not found</h1>' +
    '<p>The path <code>{path}</code> was not found on this server.</p>')

ROW_TEMPLATE = (
    '<tr>' +
    '<td class="name">' +
    '<span class="icon {class_name}"></span> ' +
    '<a href="{url}">{name}</a>' +
    '</td>' +
    '<td class="size">{size}</td>' +
    '<td class="date">{date:%Y-%m-%d %H:%M}</td>' +
    '</tr>')


class SortStyle(Enum):
    Date = 'date'
    Name = 'name'
    Size = 'size'


class SortDir(Enum):
    Ascending = 'asc'
    Descending = 'desc'

    @staticmethod
    def reverse(sort_dir: 'SortDir') -> 'SortDir':
        if sort_dir == SortDir.Ascending:
            return SortDir.Descending
        return SortDir.Ascending


class Settings:
    # TODO: use this version once Python 3.6 comes out
    # header: str = ''
    # footer: str = ''
    # sort_style: SortStyle = SortStyle.Date
    # sort_dir: SortDir = SortDir.Descending
    # recursive: bool = True

    def __init__(self):
        # TODO: remove this version once Python 3.6 comes out
        self.header = ''
        self.footer = ''
        self.sort_style = SortStyle.Date
        self.sort_dir = SortDir.Descending
        self.recursive = True


def get_not_found_response(web_path: str) -> str:
    return HTML_TEMPLATE.format(
        title='Not found',
        body=NOT_FOUND_TEMPLATE.format(path=web_path))


def list_entries(
        local_path: str, sort_style: SortStyle, sort_dir: SortDir) -> List:
    def name_sort_func(entry):
        return [
            int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', entry.name)]

    def size_sort_func(entry):
        return entry.stat().st_size

    def date_sort_func(entry):
        return entry.stat().st_mtime

    sort_funcs = {
        SortStyle.Name: name_sort_func,
        SortStyle.Date: date_sort_func,
        SortStyle.Size: size_sort_func,
    }

    # TODO: Use proper type annotations when Python 3.6 comes out
    dir_entries = []  # type: List[object]
    file_entries = []  # type: List[object]
    for entry in os.scandir(local_path):
        if entry.name != SETTINGS_FILE:
            [file_entries, dir_entries][entry.is_dir()].append(entry)
    for group in (dir_entries, file_entries):
        group.sort(key=sort_funcs[sort_style])
        if sort_dir == SortDir.Descending:
            group.reverse()
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
            if 'recursive' in obj:
                settings.recursive = bool(obj['recursive'])
        except Exception as ex:
            logger.warning('Failed to decode %s (%s)', settings_path, ex)
        return settings


def get_settings(local_path: str, root_path: str) -> Settings:
    current_path = local_path
    iterations = 0
    while current_path.startswith(root_path):
        settings_path = os.path.join(current_path, SETTINGS_FILE)
        current_path = os.path.dirname(current_path)
        iterations += 1
        if os.path.exists(settings_path):
            settings = deserialize_settings(settings_path)
            if iterations > 1 and not settings.recursive:
                return Settings()
            return settings
    return Settings()


def update_settings_from_query_string(settings: Settings, query_string: str):
    try:
        obj = dict(parse_qsl(query_string))
        if 'sort_style' in obj:
            settings.sort_style = SortStyle(obj['sort_style'])
        if 'sort_dir' in obj:
            settings.sort_dir = SortDir(obj['sort_dir'])
    except:
        pass


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

    classes = {
        SortStyle.Name: 'name',
        SortStyle.Date: 'date',
        SortStyle.Size: 'size',
    }
    names = {key: value.title() for key, value in classes.items()}

    for sort_style in [SortStyle.Name, SortStyle.Size, SortStyle.Date]:
        body += '<th class="{}">'.format(classes[sort_style])
        body += '<a href="?sort_style={}&sort_dir={}">'.format(
            sort_style.value,
            SortDir.reverse(settings.sort_dir).value
            if sort_style == settings.sort_style
            else SortDir.Ascending.value)

        body += names[sort_style]
        if sort_style == settings.sort_style:
            body += ' <span class="icon %s"></span>' % (
                ['sort-desc', 'sort-asc']
                [settings.sort_dir == SortDir.Ascending])

        body += '</a>'
        body += '</th>'

    body += '</tr></thead>'
    body += '<tbody>'

    body += ROW_TEMPLATE.format(
        class_name='go-up',
        url=os.path.join(base_url, quote(web_path), os.path.pardir),
        name='..',
        size='-',
        date=datetime.fromtimestamp(
            os.stat(os.path.join(local_path, os.path.pardir)).st_mtime))

    for entry in list_entries(
            local_path, settings.sort_style, settings.sort_dir):
        stat = entry.stat()
        name = entry.name + ('/' if entry.is_dir() else '')
        body += ROW_TEMPLATE.format(
            class_name=['file', 'dir'][entry.is_dir()],
            url=os.path.join(base_url, quote(web_path), quote(name)),
            name=name,
            size='-' if entry.is_dir() else naturalsize(stat.st_size),
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
    web_path = str(env['PATH_INFO'].encode('latin-1').decode('utf-8'))
    root_path = str(env['DOCUMENT_ROOT'])
    local_path = root_path + web_path
    query_string = str(env['QUERY_STRING'])

    if not os.path.exists(local_path):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return [get_not_found_response(web_path).encode()]
    if not os.path.isdir(local_path):
        start_response(
            '200 OK', [('Content-Type', 'application/octet-stream')])
        with open(local_path, 'rb') as handle:
            return [handle.read()]

    settings = get_settings(local_path, root_path)
    update_settings_from_query_string(settings, query_string)

    start_response('200 OK', [('Content-Type', 'text/html')])
    return [get_listing_response(
        base_url, local_path, web_path, settings).encode()]
