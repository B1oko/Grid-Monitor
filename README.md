# Grid Monitor

Self-hosted live dashboard for solar inverters. Drop a container on a Raspberry Pi
or any Linux box, add your inverter, and watch PV, battery, home load and grid
power in real time.

> **Do not expose this app to the public internet.** There is no authentication
> yet. Keep it on your LAN, a VPN, or behind a reverse proxy with access control.

## Quick start

```bash
docker run -d --name grid-monitor \
  --restart unless-stopped \
  --network host \
  -v gridmonitor:/data \
  ghcr.io/<your-username>/grid-monitor:latest
```

Then open `http://<host>:8000`. The first-run wizard will ask you to scan the
network or enter the inverter address.

`docker compose up -d` with the bundled [docker-compose.yml](docker-compose.yml)
does the same thing.

On Docker Desktop (macOS/Windows), host networking is not available. Use
[docker-compose.bridge.yml](docker-compose.bridge.yml) and add the inverter IP
manually:

```bash
docker compose -f docker-compose.bridge.yml up -d
```

The UI will be at `http://localhost:8080`.

### Tags

| Tag | Meaning |
| --- | --- |
| `latest` | Latest stable release |
| `edge` | Build from `main` |
| `0.1.0`, `0.1`, `0` | Semver from a git tag `v0.1.0` |

Images are published to GitHub Container Registry and, when configured, Docker Hub.

## Supported inverters

| Driver id | Brand / model | Protocol |
| --- | --- | --- |
| `saj-h2` | SAJ H2 with AIO3 | Modbus TCP (port 502, unit 1) |

More drivers can be added without changing the rest of the app. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

- Live values are polled over Modbus only while a browser is connected.
- A background recorder writes samples to SQLite (default every 5 minutes).
- Configuration (inverters, intervals, retention) is stored in the database and
  edited from the UI. Environment variables are only for bootstrap.

## Alerts and push notifications

Grid Monitor checks the inverter every 10 seconds in the background, with or
without a browser open, and sends a web push notification to your phone when:

| Alert | Default |
| --- | --- |
| Grid import above the contracted power | 5,500 W for 1 minute |
| No solar production while the sun is up | under 50 W for 30 minutes, sun above 15° |
| Inverter not responding | 10 minutes |

Each alert also notifies you when it clears. Thresholds, delays and your
location (needed to know when it is daytime) are set in **Settings → Alerts**.
Overload uses grid power where positive means importing from the grid.

Notifications are delivered as web push, so they reach your phone anywhere
without exposing the app to the internet. They need Grid Monitor served over
HTTPS with a trusted certificate. See
[docs/push-notifications.md](docs/push-notifications.md) for the full setup:
certificates for a LAN-only service, reverse proxy examples, enabling
notifications on Android and iOS, and troubleshooting.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `/data` in Docker, `./data` locally | SQLite file and runtime data |
| `DATABASE_URL` | `sqlite+aiosqlite:///$DATA_DIR/gridmonitor.db` | Set this to use PostgreSQL |
| `TZ` | `UTC` | Container timezone |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PORT` | `8000` | Used only by local uvicorn helpers |
| `VAPID_SUBJECT` | project URL | Contact (`mailto:` or URL) sent to push services |

PostgreSQL example:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Or:

```text
DATABASE_URL=postgresql+asyncpg://gridmonitor:gridmonitor@db:5432/gridmonitor
```

## Network notes

- **Host networking (Linux)** is the plug-and-play option: the container can
  scan the LAN and reach the inverter.
- **Bridge networking** needs the inverter IP typed in the wizard. Discovery
  cannot see your home LAN from Docker Desktop.
- **Network scans** walk a `/24` and probe Modbus TCP. Only run a scan on a
  network you own or are authorized to scan.
- Some inverters (including the SAJ AIO3) accept a limited number of Modbus
  clients. If Home Assistant is already polling the same unit, readings can
  flake. Prefer a single active Modbus reader.

If the container cannot write to `/data`, the volume is probably owned by root.
The image runs as uid `1000` after fixing ownership on startup. You can also
`chown 1000:1000` the bind mount.

## Local development

```bash
uv sync --all-groups
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
```

## HTTP API

| Endpoint | Description |
| --- | --- |
| `GET /health` | App status and configured inverters |
| `GET /api/drivers` | Installed inverter drivers |
| `GET/POST/PATCH/DELETE /api/inverters` | Inverter configuration |
| `GET /api/inverters/{id}/snapshot` | One-shot live reading |
| `GET/PUT /api/settings` | Persisted app settings |
| `GET /api/history` | Aggregated history (`inverter_id`, `from`, `to`, `resolution`) |
| `GET /api/alerts` | Alert history (`limit`, `active`) |
| `GET /api/push/public-key` | VAPID public key and number of subscribed devices |
| `POST /api/push/subscribe`, `/unsubscribe` | Register or remove a push subscription |
| `POST /api/push/test` | Send a test notification to every device |
| `POST /api/discover` | Opt-in LAN scan |
| `WS /ws/live` | Live samples (`inverter_id` on every message) |

## Roadmap

- Optional authentication for the UI and API
- Home Assistant MQTT discovery
- Additional inverter drivers
- 32-bit ARM (`linux/arm/v7`) images if there is demand

## License

[MIT](LICENSE)
