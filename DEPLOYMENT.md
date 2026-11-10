# Deploy DST Helper

The app runs on Starlette and Uvicorn with one worker. Python 3.11+ is required;
the Docker image uses Python 3.13. Runtime dependencies are pinned in
`requirements.txt`. Node, a frontend build, a separate database server, and saved
wiki pages are unnecessary. User preferences and Farming plans stay in each
browser; the application does not need a persistent server volume.

## Docker behind your existing Nginx

From the repository root on the server:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 dst-helper
curl --fail http://127.0.0.1:8765/healthz
```

The health response is `{"status": "ok"}`. Compose publishes
**127.0.0.1:8765**, leaving host port 80 for your Nginx. The process listens on
`0.0.0.0:8765` inside the container. This setup assumes Nginx runs on the host;
if Nginx is another container, connect both containers to a shared Docker network
and proxy to `dst-helper:8765` instead of its own loopback address.

The image runs as UID/GID 10001, and Compose mounts the root filesystem read-only.
No volumes or secrets are required. All 229 PNGs and the read-only content/defaults
are included. Docker's health check uses Python, so installing curl inside the
image is unnecessary. A health failure marks the container unhealthy; Docker's
restart policy restarts exited processes, not containers merely marked unhealthy.
Inspect logs if health checks fail.

The request path is:

```text
Browser HTTPS -> Cloudflare Tunnel -> Nginx 127.0.0.1:80 -> app 127.0.0.1:8765
```

Adapt [deploy/nginx.conf.example](deploy/nginx.conf.example) to your existing Nginx
configuration and hostname. It is an example for the existing gateway, not a
second Nginx service. Test changes with `nginx -t` before reloading Nginx. Keep
the site at `/`: frontend routes and API URLs are root-relative.

The example preserves the public `Host` for the same-origin POST checks and the
original HTTPS scheme forwarded through the tunnel. It buffers and limits request
bodies and sets upstream timeouts. The app independently enforces actual JSON body
limits: 16 KiB for Cooking requests and 64 KiB for Farming, including chunked bodies.

### Trusted proxy addresses

Uvicorn trusts forwarded headers only from loopback by default. With Docker's port
mapping, host Nginx typically appears to the container as its bridge gateway.
Identify it on the deployment host:

```sh
docker inspect --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' \
  "$(docker compose ps -q dst-helper)"
```

Set `FORWARDED_ALLOW_IPS` to that actual address in an ignored `.env` file next to
Compose, then recreate the service. For example, if it is `172.18.0.1`:

```text
FORWARDED_ALLOW_IPS=127.0.0.1,::1,172.18.0.1
```

```sh
docker compose up -d --force-recreate
```

Verify the connecting address in your deployment; Docker Desktop or a different
network layout can use another address. Recheck after changing Docker networks.
Trust only the proxy addresses you control. When running directly on the host,
Nginx's loopback connection already matches the default. The app works without
forwarded headers, but request scheme/client metadata will describe the internal hop.

## Run without Docker

Create an environment, install dependencies, and start the app. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m dst_helper --host 127.0.0.1 --port 8765
```

On Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m dst_helper --host 127.0.0.1 --port 8765
```

Use systemd or your host's process manager to start that command at boot and
restart it on failure. The existing `python dst_helper` and
`python DST_Cooking_Data_v0_1/run_handbook.py` entry points use the same Uvicorn
launcher. `--database`, `--assets`, `--settings`, and `--exclusions` still select
read-only content/default files. `--forwarded-allow-ips`, `--limit-concurrency`,
and `--log-level` control serving. The launcher starts one worker, limits concurrent
connections/tasks to 64, and allows 25 seconds for graceful shutdown. Compose waits
35 seconds before forcing a stop. WebSocket support and development reload are off.

An ASGI entry point is also available for external process managers:

```sh
.venv/bin/python -m uvicorn dst_helper.asgi:app --host 127.0.0.1 --port 8765 \
  --workers 1 --ws none --limit-concurrency 64 --timeout-graceful-shutdown 25
```

Run the ASGI command from the repository root. Forwarded-header trust can be set
with Uvicorn's `--forwarded-allow-ips` or `FORWARDED_ALLOW_IPS`. Application data is
initialized during lifespan startup before any requests are served. The existing
synchronous SQLite reads and calculations run in Starlette's thread pool.

## Updates and checks

```sh
git pull
docker compose up -d --build
docker compose logs --tail=100 dst-helper
curl --fail http://127.0.0.1:8765/healthz
```

Keep a consistent public HTTPS origin: browser storage belongs to the scheme, host,
and port. Container rebuilds preserve visitors' browser data. Clearing site data
or switching origins can reset it. Browser export/import is not implemented.

Run the automated checks with the virtual environment's Python (from the root):

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s DST_Farming_v0_1/tests -v
cd DST_Cooking_Data_v0_1
../.venv/bin/python -m unittest discover -s tests -v
```

On Windows, substitute the equivalent `.venv\Scripts\python.exe` paths. The
optional Windows browser checks use `python tests/browser_smoke.py` with the same
environment. Unit/HTTP tests run the actual Uvicorn server on temporary ports.
No test or deployment task needs to regenerate the curated database or JSON.
