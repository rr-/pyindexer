pyindexer
=========

Simple Python file indexer for web servers.


### Features

1. Indexing!
2. Breadcrumbs!
3. Custom headers and footers!
4. Server-side sorting!
5. User-side sorting!
6. Version sorting!
7. Image previews!
8. Basic authentication!
9. Pretty!

### What it looks like

![20161124_115320_soq](https://cloud.githubusercontent.com/assets/1045476/20597637/272a5100-b245-11e6-8445-503d2ef4e9e9.png)

### Why not fancyindex or mod\_autoindex

Fancyindex didn't suit my fancy
([#16](https://github.com/aperezdc/ngx-fancyindex/issues/16),
[#17](https://github.com/aperezdc/ngx-fancyindex/issues/17),
[#48](https://github.com/aperezdc/ngx-fancyindex/issues/48), doesn't support
natural sorting, you gotta compile it in yourself etc.), whereas mod\_autoindex
while being nice, is unfortunately not available for nginx.

### `indexer.json` file

Each directory can be configured with `indexer.json` file. The `indexer.json`
works recursively unless marked otherwise. Its structure is as follows:

```json
{
    "header": "Extra information to show above the file table (HTML)",
    "footer": "Extra information to show below the file table (HTML)",
    "sort_style": "One of following: ['name', 'size', 'date']",
    "sort_dir": "One of following: ['asc', 'desc']",
    "recursive": "Whether the config applies to subdirectories (true/false)",
    "filter": "Optional regex for hiding files by their names",
    "enable_galleries": "Whether to show image galleries (true/false)",
    "show_images_as_files": "Wheter to show images in file list (true/false)",
    "user": "User for basic authentication",
    "password": "Password for basic authentication",
}
```

Note that the engine looks for `indexer.json` in parent directories and *stops
on the first file found*. It does *not* merge settings
from multiple parent directories.


### Example deployment with nginx, uwsgi and systemd

1. Install dependencies (`wsgi` for integration with nginx and `jinja` for
   sane HTML rendering) with `pip`: `pip install -r requirements.txt`.
2. Copy `indexer.service` to `~/.config/systemd/user`.
3. Edit `~/.config/systemd/user/indexer.service` and change the path to the
   `indexer.py` script.
4. Run `systemctl --user daemon-reload` to make systemd see the above file.
5. Run `systemctl --user enable indexer` to start indexer service at boot.
6. Run `systemctl --user start indexer` to run indexer now.
7. Edit `/etc/nginx.conf` and configure your site to use indexer:

    ```
    upstream indexer {
        server 127.0.0.1:40001;
    }
    server {
        include uwsgi_params;  # should come with your distribution
        server_name tmp.sakuya.pl;
        location ~ ^.*/$ {  # redirect only directories
            uwsgi_pass indexer;
        }

        # for image galleries
        location ~ ^/image-resize(/.*) {
            root /tmp/nginx-thumbs/;
            error_page 404 = /image-resizer$1;
        }

        location ~ ^/image-resizer(/.*) {
            uwsgi_pass indexer;
            uwsgi_store /tmp/nginx-thumbs/image-resize/$1;
            uwsgi_store_access user:rw group:rw all:r;
            uwsgi_temp_path /tmp/nginx;
        }
    }
    ```

8. Run `systemctl restart nginx` and open the site with your favorite web
   browser to see indexer in action.
