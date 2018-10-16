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
9. Basic multiple user scenario!
10. Pretty!

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
    "show_images_as_files": "Whether to show images in file list (true/false)",
    "auth": ["user1:password1", "user2":"password2"],
    "auth_default": "Default user names that have access to all resources
    (user1:user2)",
    "auth_filtering": "Whether to use extended file attribute to control which
    user can see which files (true/false)"
}
```

Note that the engine looks for `indexer.json` in parent directories and *stops
on the first file found*. It does *not* merge settings
from multiple parent directories.

`auth_filtering` turns on basic view permission system. User names that are by
default eligible to access each file/directory are specified in `auth_default`
configuration field. This list can be overridden through extended file
attributes for each indexed file/directory. The engine looks for the following
three attributes:

- `access` - overrides `auth_default` completely
- `access_add` - permits additional user names with relation to the
`auth_default` configuration field
- `access_del` - revokes user names even if they were specified in
`auth_default` configuration field

Each of these fields contains user names separated with `:`.
Permissions are inherited from parent directories.


### Example deployment with nginx, uwsgi and systemd

1. Install `webindexer` with `pip`: `pip install --user .`.
2. Install `uwsgi` with `pip`: `pip install --user uwsgi`.
3. Copy `indexer.service` to `~/.config/systemd/user`.
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
        server_name example.com;
        location ~ ^.*/$ {  # redirect only directories
            uwsgi_pass indexer;
        }
        location ~ ^/.thumb/ {  # for image galleries
            uwsgi_pass indexer;
        }
    }
    ```

8. Run `systemctl restart nginx` and open the site with your favorite web
   browser to see indexer in action.
