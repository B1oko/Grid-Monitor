# Security Policy

## Supported Versions

Grid Monitor is in early development (`0.x`). Security fixes are applied to the
latest release on `main` only.

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report them privately via GitHub Security Advisories on this repository
(Security → Report a vulnerability), or by emailing the maintainer listed on
the GitHub profile.

You should receive an acknowledgement within a few days. Once a fix is
available we will publish a release and credit the reporter if they wish.

## Deployment notes

- Grid Monitor has **no authentication** in this version. Do not expose it to
  the public internet. Keep it on your LAN or behind a reverse proxy with
  access control.
- Network discovery scans the local subnet and probes Modbus TCP ports. Only
  run a scan on networks you own or are authorized to scan.
- Treat the `/data` volume as sensitive: it contains inverter history and
  configuration.
