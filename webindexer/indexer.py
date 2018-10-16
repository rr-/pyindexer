import os
import re
import logging
import mimetypes
import hashlib
import typing as T
from pathlib import Path
from datetime import datetime
from base64 import b64decode
from urllib.parse import parse_qsl, quote

import jinja2
import xdg
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


logger = logging.getLogger(__name__)
SETTINGS_FILE = 'indexer.json'
THUMBNAIL_REGEX = re.compile('/.thumb(/.*)')
IMAGE_EXTENSIONS = ('.jpg', '.gif', '.png', '.jpeg')


thumbs_dir = Path(xdg.XDG_CACHE_HOME) / 'webindexer-thumbs'
templates_dir = Path(__file__).parent / 'data'
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(templates_dir)))


class Entry:
    def __init__(
            self,
            base_url: str,
            web_path: str,
            local_path: Path,
    ) -> None:
        self.local_path = local_path
        self.url = os.path.join(base_url, quote(web_path), quote(self.name))
        if local_path.is_dir():
            self.url += '/'

    @property
    def name(self) -> str:
        return self.local_path.name

    @property
    def is_dir(self) -> bool:
        return self.local_path.is_dir()

    @property
    def is_image(self) -> bool:
        return self.local_path.suffix.lower() in IMAGE_EXTENSIONS

    @property
    def mtime(self) -> datetime:
        return datetime.fromtimestamp(self.local_path.stat().st_mtime)

    @property
    def size(self) -> int:
        return self.local_path.stat().st_size


def list_entries(
        base_url: str,
        web_path: str,
        local_path: Path,
        settings,
        credentials,
):
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

    dir_entries: T.List[Entry] = []
    file_entries: T.List[Entry] = []
    for subpath in local_path.iterdir():
        if subpath.name == SETTINGS_FILE:
            continue

        try:
            subpath.stat()
        except FileNotFoundError:
            continue

        if settings.filter and re.search(settings.filter, subpath.name):
            continue

        entry = Entry(
            base_url=base_url,
            web_path=web_path,
            local_path=subpath,
        )

        if settings.auth_filtering:
            valid_users = set(settings.auth_default.split(':'))
            try:
                for attr in os.listxattr(entry.local_path):
                    if attr == 'user.access':
                        valid_users = set(
                            os.getxattr(str(entry.local_path), attr)
                            .decode()
                            .split(':')
                        )
                    elif attr == 'user.access_add':
                        valid_users.update(
                            os.getxattr(str(entry.local_path), attr)
                            .decode()
                            .split(':')
                        )
                    elif attr == 'user.access_del':
                        valid_users.difference_update(
                            os.getxattr(str(entry.local_path), attr)
                            .decode()
                            .split(':')
                        )
            except OSError as ex:
                logger.error(ex)
                continue
            if credentials.user not in valid_users:
                continue

        [file_entries, dir_entries][entry.is_dir].append(entry)

    for group in (dir_entries, file_entries):
        group.sort(key=sort_funcs[settings.sort_style])
        if settings.sort_dir == SortDir.Descending:
            group.reverse()

    dir_entries.insert(
        0,
        Entry(
            base_url=base_url,
            web_path=web_path,
            local_path=local_path / '..',
        ),
    )

    return dir_entries + file_entries


def get_settings(local_path: Path, root_path: Path):
    current_path = local_path
    iterations = 0
    while True:
        try:
            current_path.relative_to(root_path)
        except ValueError:
            break
        settings_path = current_path / SETTINGS_FILE
        current_path = current_path.parent
        iterations += 1
        if settings_path.exists():
            settings = deserialize_settings(settings_path)
            if iterations > 1 and not settings.recursive:
                return Settings()
            return settings
    return Settings()


def get_mimetype(filename: Path):
    mime_type, _encoding = mimetypes.guess_type(str(filename))
    return mime_type or 'application/octet-stream'


def get_credentials(request):
    auth = request.authorization
    if auth and auth[0] == 'Basic':
        user, password = b64decode(auth[1]).decode('utf-8').split(':', 1)
        return Credentials(user, password)
    return None


def is_authorized(request, settings):
    if settings.auth:
        return get_credentials(request) in settings.auth
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


def respond_access_denied(request):
    response = Response()
    response.status = 403
    response.content_type = 'text/html'
    response.text = (
        jinja_env
        .get_template('access-denied.htm')
        .render(path=request.path_info))
    return response


def respond_listing(request, local_path: Path, settings):
    try:
        obj = dict(parse_qsl(request.query_string))
        if 'sort_style' in obj:
            settings.sort_style = SortStyle(obj['sort_style'])
        if 'sort_dir' in obj:
            settings.sort_dir = SortDir(obj['sort_dir'])
    except Exception:
        pass

    links = []
    link = ''
    for group in [''] + [f for f in request.path_info.split('/') if f]:
        link += group + '/'
        links.append((link, group))

    credentials = get_credentials(request)

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
                settings,
                credentials)))
    return response


def try_respond_image_resizer(root_path: Path, request):
    match = THUMBNAIL_REGEX.match(request.path_info)
    if not match:
        return None

    local_path = root_path / match.group(1).lstrip('/')

    if not local_path.exists():
        return respond_not_found(request)

    thumb_path = thumbs_dir / (
        hashlib.sha1(str(local_path).encode()).hexdigest() + '.jpg')

    if not thumb_path.exists():
        try:
            image = Image.open(str(local_path)).convert('RGB')
            thumb = ImageOps.fit(image, (150, 150), Image.ANTIALIAS)
        except Exception as ex:
            logging.error(ex)
            return respond_not_found(request)
        else:
            thumbs_dir.mkdir(exist_ok=True, parents=True)
            with thumb_path.open('wb') as handle:
                thumb.save(handle, format='jpeg')

    return FileResponse(str(thumb_path), content_type='image/jpeg')


def catch_all_route(request):
    root_path = Path(request.environ['DOCUMENT_ROOT'])
    local_path = root_path / request.path_info.lstrip('/')
    settings = get_settings(local_path, root_path)

    response = try_respond_image_resizer(root_path, request)
    if response:
        return response

    if not local_path.exists():
        return respond_not_found(request)

    if not local_path.is_dir():
        if local_path.name == SETTINGS_FILE:
            return respond_access_denied(request)
        return FileResponse(
            str(local_path),
            content_type=get_mimetype(local_path))

    if not is_authorized(request, settings):
        return respond_login()

    return respond_listing(request, local_path, settings)


def make_wsgi_app():
    config = Configurator()
    config.add_route('catch-all', '/*subpath')
    config.add_view(catch_all_route, route_name='catch-all')
    return config.make_wsgi_app()


application = make_wsgi_app()
