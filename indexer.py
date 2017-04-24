import os
import re
import json
from urllib.parse import parse_qsl, quote
from jinja2 import Environment, FileSystemLoader
from enum import Enum
from logging import getLogger
from typing import Mapping, List, Any, Callable
from datetime import datetime

logger = getLogger(__name__)
SETTINGS_FILE = 'indexer.json'


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


class EntryProxy:
    def __init__(
            self, base_url: str, web_path: str, path: str,
            is_dir: bool, stat: os.stat_result) -> None:
        self.path = path
        self.name = os.path.basename(self.path)
        self.url = os.path.join(base_url, quote(web_path), quote(self.name))
        if is_dir:
            self.url += '/'
        self.is_dir = is_dir
        self.size = stat.st_size
        self.mtime = datetime.fromtimestamp(stat.st_mtime)

    @staticmethod
    def from_scandir(base_url: str, web_path: str, entry: Any):
        return EntryProxy(
            base_url, web_path, entry.path, entry.is_dir(), entry.stat())

    @staticmethod
    def from_path(base_url: str, web_path: str, local_path: str):
        return EntryProxy(
            base_url, web_path, local_path,
            os.path.isdir(local_path),
            os.stat(local_path))


def get_not_found_response(jinja_env: Any, web_path: str) -> str:
    return jinja_env.get_template('not-found.htm').render(path=web_path)


def list_entries(
        base_url: str, web_path: str, local_path: str,
        sort_style: SortStyle, sort_dir: SortDir) -> List[EntryProxy]:
    def name_sort_func(entry):
        return [
            int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', entry.name)]

    def size_sort_func(entry):
        return entry.size

    def date_sort_func(entry):
        return entry.mtime

    sort_funcs = {
        SortStyle.Name: name_sort_func,
        SortStyle.Date: date_sort_func,
        SortStyle.Size: size_sort_func,
    }

    # TODO: Use proper type annotations when Python 3.6 comes out
    dir_entries = []  # type: List[EntryProxy]
    file_entries = []  # type: List[EntryProxy]
    for entry in os.scandir(local_path):
        if entry.name == SETTINGS_FILE:
            continue
        entry_proxy = EntryProxy.from_scandir(base_url, web_path, entry)
        [file_entries, dir_entries][entry.is_dir()].append(entry_proxy)

    for group in (dir_entries, file_entries):
        group.sort(key=sort_funcs[sort_style])
        if sort_dir == SortDir.Descending:
            group.reverse()

    dir_entries.insert(
        0, EntryProxy.from_path(
            base_url, web_path, os.path.join(local_path, '..')))

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
        jinja_env: Any,
        base_url: str,
        local_path: str,
        web_path: str,
        settings: Settings) -> str:

    links = []
    link = '/'
    for group in [f for f in web_path.split('/') if f] + ['']:
        links.append((link, group))
        link += '%s/' % group

    return jinja_env.get_template('index.htm').render(
        SortDir=SortDir,
        sort_styles=(
            (SortStyle.Name, 'name'),
            (SortStyle.Date, 'date'),
            (SortStyle.Size, 'size'),
        ),
        settings=settings,
        path=web_path,
        links=links,
        entries=list_entries(
            base_url, web_path, local_path,
            settings.sort_style, settings.sort_dir))


def application(
        env: Mapping[str, object], start_response: Callable) -> List[bytes]:

    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    jinja_env = Environment(loader=FileSystemLoader(templates_dir))

    base_url = '%s://%s/' % (env['REQUEST_SCHEME'], env['HTTP_HOST'])
    web_path = str(env['PATH_INFO']).encode('latin-1').decode('utf-8')
    root_path = str(env['DOCUMENT_ROOT'])
    local_path = root_path + web_path
    query_string = str(env['QUERY_STRING'])

    if not os.path.exists(local_path):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return [get_not_found_response(jinja_env, web_path).encode()]

    if not os.path.isdir(local_path):
        start_response(
            '200 OK', [('Content-Type', 'application/octet-stream')])
        with open(local_path, 'rb') as handle:
            return [handle.read()]

    settings = get_settings(local_path, root_path)
    update_settings_from_query_string(settings, query_string)

    start_response('200 OK', [('Content-Type', 'text/html')])
    return [get_listing_response(
        jinja_env, base_url, local_path, web_path, settings).encode()]
