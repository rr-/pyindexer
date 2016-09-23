pyindexer
=========

Simple Python file indexing service for web servers.

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
