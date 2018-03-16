import os
import re
import mimetypes
from datetime import datetime
from tempfile import gettempdir
from base64 import b64encode, b64decode
from urllib.parse import parse_qsl, quote

import jinja2
from PIL import Image
from PIL import ImageOps
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.response import FileResponse

from webindexer.settings import Settings
from webindexer.settings import SortStyle
from webindexer.settings import SortDir
from webindexer.settings import Credentials
from webindexer.settings import deserialize_settings


SETTINGS_FILE = 'indexer.json'
THUMBNAIL_REGEX = re.compile('/.thumb(/.*)')
IMAGE_EXTENSIONS = ('.jpg', '.gif', '.png', '.jpeg')


templates_dir = os.path.join(os.path.dirname(__file__), 'data')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))


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


def get_mimetype(filename):
    mime_type, _encoding = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


def is_authorized(request, settings):
    if settings.auth:
        auth = request.authorization
        if auth and auth[0] == 'Basic':
            user, password = b64decode(auth[1]).decode('utf-8').split(':', 1)
            credentials = Credentials(user, password)
            return credentials in settings.auth
        return False
    return True


def respond_login():
    response = Response()
    response.status = 401
    response.www_authenticate = ('Basic', {'realm': 'Protected'})
    return response


def respond_not_found(request):
    response = Response()
    response.status = 404
    response.content_type = 'text/html'
    response.text = (
        jinja_env
        .get_template('not-found.htm')
        .render(path=request.path_info))
    return response


def respond_listing(request, local_path, settings):
    try:
        obj = dict(parse_qsl(request.query_string))
        if 'sort_style' in obj:
            settings.sort_style = SortStyle(obj['sort_style'])
        if 'sort_dir' in obj:
            settings.sort_dir = SortDir(obj['sort_dir'])
    except Exception:
        pass

    links = []
    link = '/'
    for group in [f for f in request.path_info.split('/') if f] + ['']:
        links.append((link, group))
        link += '%s/' % group

    response = Response()
    response.content_type = 'text/html'
    response.text = (
        jinja_env
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
                local_path,
                settings.filter,
                settings.sort_style,
                settings.sort_dir)))
    return response


def try_respond_image_resizer(root_path, request):
    match = THUMBNAIL_REGEX.match(request.path_info)
    if not match:
        return None

    local_path = root_path + match.group(1)

    if not os.path.exists(local_path):
        return respond_not_found(request)

    thumb_path = os.path.join(
        gettempdir(),
        'indexer-thumbs',
        b64encode(local_path.encode()).decode() + '.jpg')
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)

    if not os.path.exists(thumb_path):
        image = Image.open(local_path).convert('RGB')
        thumb = ImageOps.fit(image, (150, 150), Image.ANTIALIAS)
        with open(thumb_path, 'wb') as handle:
            thumb.save(handle, format='jpeg')

    return FileResponse(thumb_path, content_type='image/jpeg')


def catch_all_route(request):
    root_path = request.environ['DOCUMENT_ROOT']
    local_path = root_path + request.path_info
    settings = get_settings(local_path, root_path)

    response = try_respond_image_resizer(root_path, request)
    if response:
        return response

    if not os.path.exists(local_path):
        return respond_not_found(request)

    if not os.path.isdir(local_path):
        return FileResponse(local_path, content_type=get_mimetype(local_path))

    if not is_authorized(request, settings):
        return respond_login()

    return respond_listing(request, local_path, settings)


def make_wsgi_app():
    config = Configurator()
    config.add_route('catch-all', '/*subpath')
    config.add_view(catch_all_route, route_name='catch-all')
    return config.make_wsgi_app()


application = make_wsgi_app()
