# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Pluggable inverter driver registry with a canonical reading model
- SAJ H2 / AIO3 Modbus TCP driver
- Multi-inverter support with configuration stored in the database
- SQLite by default, PostgreSQL optional
- Alembic migrations applied on startup
- First-run setup wizard and settings UI
- Optional history retention and hourly downsampling
- Multi-arch Docker image publishing workflow
- Alerts with web push notifications: grid import above the contracted power,
  no solar production in daylight, and inverter not responding
- Alert history (`GET /api/alerts`) and an active-alert banner on the dashboard
- English and Spanish translations. The language follows the browser and can be
  changed in Settings → Appearance; push notifications use each device's language
- `AGENTS.md` with working and translation rules for contributors and AI agents

### Changed

- New web UI: sidebar on desktop and tab bar on mobile, with Home, History,
  Alerts and Settings pages instead of a single page with dialogs
- Home shows the energy flow and cards for solar, home, battery and grid, with
  grid import against the contracted power
- Settings is split into Inverters, Alerts, Location, Data, Appearance and
  About, with a save bar that appears only when there are unsaved changes
- First-run setup is a page instead of a wizard dialog
- Alert events and push subscriptions store parameters and language instead of
  rendered text (migration `0003`, applied on startup)

## [0.1.0] - 2026-08-21

- Initial public release
