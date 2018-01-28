import os
import re
import io
import json
import base64
from datetime import datetime
from urllib.parse import parse_qsl, quote
from enum import Enum
from logging import getLogger
import webob
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageOps


logger = getLogger(__name__)
SETTINGS_FILE = 'indexer.json'
IMAGE_RESIZER_REGEX = re.compile('/image-resizer?(/.*)')
IMAGE_EXTENSIONS = ('.jpg', '.gif', '.png', '.jpeg')


class SortStyle(Enum):
    Date = 'date'
    Name = 'name'
    Size = 'size'


class SortDir(Enum):
    Ascending = 'asc'
    Descending = 'desc'

    @staticmethod
    def reverse(sort_dir):
        if sort_dir == SortDir.Ascending:
            return SortDir.Descending
        return SortDir.Ascending


class Settings:
    def __init__(self):
        self.filter = ''
        self.header = ''
        self.footer = ''
        self.sort_style = SortStyle.Date
        self.sort_dir = SortDir.Descending
        self.recursive = True
        self.enable_galleries = True
        self.show_images_as_files = False
        self.user = ''
        self.password = ''


class EntryProxy:
    def __init__(self, base_url, web_path, path, is_dir, stat):
        _, ext = os.path.splitext(path)
        self.path = path
        self.name = os.path.basename(self.path)
        self.url = os.path.join(base_url, quote(web_path), quote(self.name))
        if is_dir:
            self.url += '/'
        self.is_dir = is_dir
        self.is_image = ext.lower() in IMAGE_EXTENSIONS
        self.size = stat.st_size
        self.mtime = datetime.fromtimestamp(stat.st_mtime)

    @staticmethod
    def from_scandir(base_url, web_path, entry):
        return EntryProxy(
            base_url, web_path, entry.path, entry.is_dir(), entry.stat())

    @staticmethod
    def from_path(base_url, web_path, local_path):
        return EntryProxy(
            base_url, web_path, local_path,
            os.path.isdir(local_path),
            os.stat(local_path))


def list_entries(
        base_url, web_path, local_path, filter, sort_style, sort_dir):
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

    dir_entries = []
    file_entries = []
    for entry in os.scandir(local_path):
        if entry.name == SETTINGS_FILE:
            continue
        try:
            entry.stat()
        except FileNotFoundError:
            continue
        entry_proxy = EntryProxy.from_scandir(base_url, web_path, entry)
        if filter and re.search(filter, entry_proxy.name):
            continue
        [file_entries, dir_entries][entry.is_dir()].append(entry_proxy)

    for group in (dir_entries, file_entries):
        group.sort(key=sort_funcs[sort_style])
        if sort_dir == SortDir.Descending:
            group.reverse()

    dir_entries.insert(
        0, EntryProxy.from_path(
            base_url, web_path, os.path.join(local_path, '..')))

    return dir_entries + file_entries


def deserialize_settings(settings_path):
    settings = Settings()
    with open(settings_path, 'r') as handle:
        try:
            obj = json.load(handle)
            if 'filter' in obj:
                settings.filter = str(obj['filter'])
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
            if 'enable_galleries' in obj:
                settings.enable_galleries = bool(obj['enable_galleries'])
            if 'show_images_as_files' in obj:
                settings.show_images_as_files = bool(
                    obj['show_images_as_files'])
            if 'user' in obj:
                settings.user = str(obj['user'])
            if 'password' in obj:
                settings.password = str(obj['password'])
        except Exception as ex:
            logger.warning('Failed to decode %s (%s)', settings_path, ex)
        return settings


def get_settings(local_path, root_path):
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


class Application:
    def __init__(self):
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self._jinja_env = Environment(loader=FileSystemLoader(templates_dir))

    def __call__(self, env, start_response):
        request = webob.Request(env)
        setattr(request, 'root_path', str(env['DOCUMENT_ROOT']))
        setattr(request, 'local_path', request.root_path + request.path_info)

        response = self._try_respond_image_resizer(
            env, start_response, request)
        if response:
            return response

        if not os.path.exists(request.local_path):
            return self._respond_not_found(env, start_response, request)

        if not os.path.isdir(request.local_path):
            return self._respond_file(env, start_response, request)

        settings = get_settings(request.local_path, request.root_path)
        if not self._is_authorized(request, settings):
            return self._respond_login(env, start_response)

        return self._respond_listing(env, start_response, request, settings)

    def _is_authorized(self, request, settings):
        if settings.user or settings.password:
            auth = request.authorization
            if auth and auth[0] == 'Basic':
                credentials = base64.b64decode(auth[1]).decode('UTF-8')
                user, password = credentials.split(':', 1)
                return user == settings.user and password == settings.password
            return False
        return True

    def _respond_login(self, env, start_response):
        response = webob.Response()
        response.status = 401
        response.www_authenticate = ('Basic', {'realm': 'Protected'})
        return response(env, start_response)

    def _respond_file(self, env, start_response, request):
        response = webob.Response()
        response.content_type = 'application/octet-stream'
        with open(request.local_path, 'rb') as handle:
            response.body = handle.read()
        return response(env, start_response)

    def _respond_not_found(self, env, start_response, request):
        response = webob.Response()
        response.status = 404
        response.content_type = 'text/html'
        response.text = (
            self._jinja_env
            .get_template('not-found.htm')
            .render(path=request.path_info))
        return response(env, start_response)

    def _respond_listing(self, env, start_response, request, settings):
        try:
            obj = dict(parse_qsl(request.query_string))
            if 'sort_style' in obj:
                settings.sort_style = SortStyle(obj['sort_style'])
            if 'sort_dir' in obj:
                settings.sort_dir = SortDir(obj['sort_dir'])
        except:
            pass

        links = []
        link = '/'
        for group in [f for f in request.path_info.split('/') if f] + ['']:
            links.append((link, group))
            link += '%s/' % group

        response = webob.Response()
        response.content_type = 'text/html'
        response.text = (
            self._jinja_env
            .get_template('index.htm')
            .render(
                SortDir=SortDir,
                sort_styles=(
                    (SortStyle.Name, 'name'),
                    (SortStyle.Size, 'size'),
                    (SortStyle.Date, 'date'),
                ),
                settings=settings,
                path=request.path_info,
                links=links,
                entries=list_entries(
                    request.path_url,
                    request.path_info,
                    request.local_path,
                    settings.filter,
                    settings.sort_style,
                    settings.sort_dir)))
        return response(env, start_response)

    def _try_respond_image_resizer(self, env, start_response, request):
        match = IMAGE_RESIZER_REGEX.match(request.path_info)
        if not match:
            return None

        local_path = request.root_path + match.group(1)
        if not os.path.exists(local_path):
            response = webob.Response()
            response.status = 404
            response.content_type = 'text/html'
            response.text = (
                self._jinja_env
                .get_template('not-found.htm')
                .render(path=local_path))
            return response(env, start_response)
        image = Image.open(local_path).convert('RGB')
        thumb = ImageOps.fit(image, (150, 150), Image.ANTIALIAS)
        with io.BytesIO() as handle:
            thumb.save(handle, format='jpeg')
            response = webob.Response()
            response.content_type = 'image/jpeg'
            response.body = handle.getvalue()
            return response(env, start_response)


application = Application()
