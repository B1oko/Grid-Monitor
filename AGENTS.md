# AGENTS.md

Instructions for AI coding agents (and humans) working on Grid Monitor. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the general workflow and how to add an
inverter driver.

## Project layout

| Path | Contents |
| --- | --- |
| `app/drivers/` | Inverter drivers, one module per model, registered with `@register_driver` |
| `app/services/` | Live polling, recorder, retention, alerts and push notifier |
| `app/api/routers/` | FastAPI routers (`/api/*`, `/ws/live`, UI and `/i18n/*`) |
| `app/db/` | SQLAlchemy models; migrations live in `alembic/versions/` |
| `app/i18n/` | Translation catalogs (`locales/<lang>.json`) and formatting helpers |
| `app/web/static/` | Web UI: plain ES modules, no build step |
| `tests/` | pytest suite; driver golden files under `tests/fixtures/drivers/` |

## Working rules

- Branch from `develop` as `feature/<name>` and open the PR against `develop`.
  Never commit directly to `main` or `develop`.
- Before finishing, run:

  ```bash
  uv run pytest
  uv run ruff check .
  uv run ruff format --check .
  ```

- Keep changes focused. Do not mix a new driver with unrelated UI work.
- Add or update tests for behavior you change.
- Add user-visible changes to `CHANGELOG.md` under **Unreleased**, and update
  `README.md` or `docs/` when the UI, configuration or API changes.
- Database changes need a new Alembic migration in `alembic/versions/`
  (numbered `000N_<name>.py`). Migrations run on startup, so they must work on
  both SQLite and PostgreSQL and must not lose existing data.
- Configuration that users edit belongs in the database and the Settings page.
  Environment variables are only for bootstrap (paths, database URL, logging).
- The app has no authentication. Do not add features that assume it is exposed
  to the internet.

## Web UI

- The UI is vanilla JavaScript ES modules served as-is from `app/web/static/`.
  Do not add a bundler, framework or npm dependency.
- Pages are hash routes rendered from `js/views/`. Shared state is in
  `js/state.js`, API calls go through `js/api.js`.
- Escape every value inserted into HTML with `esc()` from `js/format.js`.
- When you add, rename or remove a file under `js/`, update `PRECACHE` in
  `sw.js` and bump `CACHE` (`grid-monitor-vN`) so installed apps pick up the
  change. `tests/test_i18n.py` fails if a module is missing from `PRECACHE`.
- Check new screens on a phone-sized viewport and in both light and dark themes.

## Translations

Every user-facing string, in the UI and in push notifications, comes from
`app/i18n/locales/<lang>.json`. The backend reads the catalogs directly; the UI
loads them from `/i18n/<lang>.json`.

### Rules

1. **No hard-coded text.** Use `t("section.key", params)` in the UI and
   `translate("section.key", language, **params)` in Python. This includes
   button labels, toasts, errors, `title`/`aria-label` attributes and
   notification bodies.
2. **English is the reference.** Add a key to `en.json` first, then to every
   other locale in the same change. All catalogs must have exactly the same
   keys and the same placeholders. Do not leave a value empty or copy the
   English text into another language as a placeholder.
3. **Keys are nested by area** (`nav`, `dashboard`, `history`, `alerts`,
   `push`, `settings`, `setup`, `common`, ...) and written in `snake_case`.
   Reuse `common.*` for generic words such as Save or Cancel. Keep the same
   key order in every file so diffs are easy to review.
4. **Write keys literally** in `t("...")` calls so the tests can find them. A
   template literal is fine when only the last segments vary, for example
   ``t(`alerts.${kind}.name`)``, as long as a matching key exists.
5. **Store raw values, not text.** Pass numbers to templates and let the
   placeholder suffix format them:

   | Suffix | Formats as | Example |
   | --- | --- | --- |
   | `*_w` | Power with the language's thousands separator | `{limit_w}` → `5,500 W` / `5.500 W` |
   | `*_min` | Duration from minutes | `{duration_min}` → `1 h 05 min` |
   | `*_deg` | Rounded angle | `{elevation_deg}` → `15°` |
   | anything else | Inserted as-is | `{inverter}` → `Roof` |

   The rules are implemented twice, in `app/i18n/__init__.py` and
   `app/web/static/js/i18n.js`. Change both together.
6. **Alerts and notifications stay language-neutral in the database.** Alert
   events store the alert kind and its parameters, not rendered text. Each push
   subscription stores the device language, and the notifier renders each
   message in that language when it is sent. Every alert kind needs
   `name`, `description`, `fire.title`, `fire.body`, `resolve.title` and
   `resolve.body` under `alerts.<kind>`.
7. **Do not translate** brand and model names, units (`W`, `kWh`, `%`), protocol
   names (Modbus TCP) or API field names.

### Style

- English: sentence case ("Contracted power", not "Contracted Power"), short
  and direct. Use the same word for the same thing everywhere (Solar, Home,
  Battery, Grid).
- Spanish: use *tú*, sentence case, and Spain conventions (`5.500 W`,
  `1,5 kWh`, *potencia contratada*). Translate the meaning, not word by word.
- Keep labels short enough for the mobile tab bar and cards. If a translation
  is much longer than the English text, check it on a narrow screen.

### Adding a language

1. Copy `en.json` to `app/i18n/locales/<code>.json` (ISO 639-1 code) and
   translate every value. Set `meta.language_name` to the language's own name
   and the `meta` separators.
2. The language is picked up automatically by the backend, the language
   selector and browser detection. No code changes are needed.
3. Run `uv run pytest tests/test_i18n.py`.

### What the tests check

`tests/test_i18n.py` fails when:

- a locale is missing a key from `en.json`, or has extra keys;
- a translation uses different placeholders than the English text;
- a value is empty;
- the UI uses a key that does not exist in `en.json`;
- an alert kind is missing one of its notification keys;
- a module under `js/` is not precached by the service worker.
