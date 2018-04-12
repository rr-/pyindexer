import json
import logging
from pathlib import Path
from enum import Enum
from collections import namedtuple


logger = logging.getLogger(__name__)
Credentials = namedtuple('Credentials', ['user', 'password'])


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
        self.auth = []
        self.auth_filtering = False


def deserialize_settings(settings_path: Path):
    settings = Settings()
    try:
        obj = json.loads(settings_path.read_text())

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
        if 'auth' in obj:
            settings.auth = [
                Credentials(user, password)
                for user, password in (
                    str(term).split(':', 1)
                    for term in list(obj['auth'])
                )
            ]
        if 'auth_filtering' in obj:
            settings.auth_filtering = bool(obj['auth_filtering'])
    except Exception as ex:
        logger.warning('Failed to decode %s (%s)', settings_path, ex)
    return settings
