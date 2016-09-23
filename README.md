pyindexer
=========

Simple Python file indexing service for web servers.


### Supported features

1. Indexing!
2. Breadcrumbs!
3. Custom headers and footers!


### `indexer.json` file

Each directory can be configured with `indexer.json` file. The `indexer.json`
works recursively unless marked otherwise. Its structure is as follows:

```json
{
    "header": "Extra information to show above the file table (HTML)",
    "footer": "Extra information to show below the file table (HTML)",
    "sort_style": "One of following: ['name', 'size', 'date']",
    "sort_dir": "One of following: ['ascending', 'descending']",
    "recursive": "Whether the file applies to subdirectories"
}
```

Note that the engine looks for `indexer.json` in parent directories and *stops
on the first file found*. It does *not* merge settings
from multiple parent directories.


### Example deployment with nginx, uwsgi and systemd

1. Copy `indexer.service` to `~/.config/systemd/user`.
2. Edit `~/.config/systemd/user/indexer.service` and change the path to the
   `indexer.py` executable.
3. Run `systemctl --user daemon-reload` to make systemd see the above file.
4. Run `systemctl --user enable indexer` to start indexer service at boot.
5. Run `systemctl --user start indexer` to run indexer now.
6. Edit `/etc/nginx.conf` and configure your site to use indexer:
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
    }
    ```
