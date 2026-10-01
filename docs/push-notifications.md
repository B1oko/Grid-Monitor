# Push notifications

Grid Monitor can send alerts to your phone or desktop as web push notifications.
They work like notifications from a native app, without installing anything
from an app store.

This guide covers what you need on the server, the network and the device.

## How it works

```
Grid Monitor ──(1) encrypted push──► Browser push service ──(2)──► Your phone
     ▲                               (Google FCM, Apple,
     │                                Mozilla autopush)
     └──(0) the phone subscribes once, over HTTPS, while on your network
```

0. You open Grid Monitor on the device and press **Enable notifications on this
   device**. The browser creates a subscription and the app stores it.
1. When an alert fires, Grid Monitor encrypts the message and sends it to the
   browser vendor's push service. This is an **outbound** HTTPS request.
2. The push service delivers it to the device **wherever it is**: home Wi-Fi,
   mobile data or abroad.

Grid Monitor never needs to be reachable from the internet. You only need
access to it, over HTTPS, while you subscribe a device.

## Requirements

| Requirement | Why |
| --- | --- |
| Grid Monitor served over **HTTPS with a certificate the device trusts** | Browsers only allow service workers and push on secure origins. Clicking through a certificate warning is **not** enough. |
| Outbound internet access from the server | To reach the push services (`fcm.googleapis.com`, `*.push.apple.com`, `*.push.services.mozilla.com`). |
| A persistent `DATA_DIR` | Holds the VAPID key pair (`vapid_private.pem`) that identifies your server. |
| A supported browser | Chrome, Edge, Firefox or Samsung Internet on Android or desktop, and Safari on macOS 13+. On iPhone/iPad (iOS/iPadOS 16.4+), the app must be added to the Home Screen first. |

`http://localhost` is treated as secure, which is handy for local development.
A LAN IP address such as `http://192.168.1.50:8000` is not.

## Step 1: Serve Grid Monitor over trusted HTTPS

Grid Monitor itself speaks plain HTTP. The usual setup puts a reverse proxy
(Nginx, Caddy, Traefik, Nginx Proxy Manager…) in front of it to terminate TLS.

### Getting a certificate for a LAN-only service

Certificates from a public CA such as Let's Encrypt need a domain you own.
Reserved local names like `.local`, `.lan` or `.home.arpa` cannot get one.

The approach that keeps the app private:

1. **Use a domain or subdomain you control** for your home services, for
   example `home.example.com`.
2. **Validate with the ACME DNS-01 challenge.** The CA checks a TXT record in
   public DNS instead of connecting to your server, so no port has to be opened.
   Most DNS providers with an API are supported by
   [acme.sh](https://github.com/acmesh-official/acme.sh), certbot plugins,
   Caddy, Traefik and Nginx Proxy Manager. If your DNS provider has no usable
   API, point `_acme-challenge.home.example.com` at an
   [acme-dns](https://github.com/joohoi/acme-dns) instance with a one-time
   CNAME.
3. **Request a wildcard certificate**, `*.home.example.com`. One certificate
   then covers all your home services, and the individual host names do not
   show up in public certificate transparency logs.
4. **Resolve the names locally.** Add the records to your LAN DNS (Pi-hole,
   AdGuard Home, router, dnsmasq…) instead of public DNS. For example, with
   dnsmasq or Pi-hole:

   ```text
   address=/home.example.com/192.168.1.50
   ```

   If you do publish an A record pointing to a private IP, some routers block
   it as "DNS rebinding". Add an exception for your domain in that case.

Renewal must be automatic. Let's Encrypt certificates are valid for 90 days or
less, so let your ACME client renew them and reload the proxy.

### Reverse proxy configuration

Grid Monitor uses a WebSocket at `/ws/live` for live data, so the proxy must
forward upgrade requests.

**Nginx**

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name grid.home.example.com;

    ssl_certificate     /etc/nginx/ssl/home.example.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/home.example.com/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 1h;
    }
}
```

**Caddy** (the DNS provider module depends on your provider)

```caddyfile
grid.home.example.com {
    tls {
        dns <provider> {env.DNS_API_TOKEN}
    }
    reverse_proxy 127.0.0.1:8000
}
```

Caddy forwards WebSocket upgrades automatically.

**Nginx Proxy Manager:** create a Let's Encrypt certificate with **Use a DNS
Challenge**, then a proxy host to `http://<grid-monitor-host>:8000` with
**Websockets Support** enabled and **Force SSL** on.

If the proxy runs in a container without host networking, replace
`127.0.0.1` with the address of the Grid Monitor host or container.

### Using your own CA instead

If you prefer a private certificate authority (step-ca, mkcert, OpenSSL…),
install its root certificate on **every** device that will receive
notifications:

- **Android:** *Settings → Security → Encryption & credentials → Install a
  certificate → CA certificate*.
- **iOS/iPadOS:** install the profile, then turn it on under *Settings →
  General → About → Certificate Trust Settings*.
- **Desktop:** add it to the operating system trust store (Firefox uses its
  own store unless `security.enterprise_roots.enabled` is set).

This works, but every new device needs the CA. A public certificate avoids
that.

## Step 2: Check the server settings

Nothing is required: the VAPID key pair is generated on first start. Optionally:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VAPID_SUBJECT` | project URL | Contact the push services can use if your server misbehaves. Use `mailto:you@example.com` or an `https://` URL you own. |

Keep `DATA_DIR/vapid_private.pem` in your backups. If the key changes, existing
subscriptions stop working and every device has to enable notifications again.

## Step 3: Configure the alerts

Open **Settings → Alerts** in Grid Monitor:

| Alert | Settings |
| --- | --- |
| Contracted power exceeded | Contracted power (W) and how many minutes grid import must stay above it. Grid power is positive when importing. |
| No solar production in daylight | Minutes, power threshold (W), minimum sun elevation (°), and latitude/longitude. The alert is inactive until a location is set; **Use this device's location** fills it in. |
| Inverter not responding | Minutes without a Modbus response. |

Each alert notifies once when it fires and once when it clears. The checks run
on the server every 10 seconds, whether or not a browser is open.

## Step 4: Enable notifications on each device

Open Grid Monitor at its HTTPS address, for example
`https://grid.home.example.com`.

**Android, desktop:**

1. Go to **Settings → Alerts → Enable notifications on this device**.
2. Allow notifications when the browser asks.
3. Press **Send test**.

**iPhone / iPad (iOS 16.4 or later):**

1. In Safari, tap **Share → Add to Home Screen**.
2. Open Grid Monitor **from the Home Screen icon**. Push is not available in a
   regular Safari tab.
3. Go to **Settings → Alerts → Enable notifications on this device**, allow
   notifications, then press **Send test**.

Repeat on every device that should receive alerts. To stop alerts on a
device, press the same button again (**Disable notifications on this
device**).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "Push notifications need HTTPS with a certificate this device trusts" | The page is loaded over HTTP, by IP address, or with an untrusted certificate. See step 1. |
| "This browser does not support push notifications" | On iOS the app is open in a Safari tab instead of from the Home Screen, or the iOS version is older than 16.4. |
| "Notifications are blocked for this site" | Permission was denied earlier. Re-enable it in the browser's site settings (or in iOS *Settings → Notifications → Grid Monitor*). |
| **Send test** reports "No device accepted the notification" | The server cannot reach the push service (firewall, no outbound internet), or the subscription expired. Check the server logs, then disable and re-enable on the device. |
| The test is sent but nothing appears | The OS is in Do Not Disturb or Focus mode, or battery optimisation is killing the browser. On Android, allow the browser to run unrestricted in the background. |
| The domain does not resolve at home | The device is not using your LAN DNS (Android "Private DNS", iCloud Private Relay, a VPN), or the router blocks private IPs in public DNS. |
| Live data does not update behind the proxy | WebSocket upgrade headers are missing from the proxy configuration. |

Expired subscriptions (the push service answers 404 or 410) are removed
automatically.

## Privacy and security notes

- Message contents are end-to-end encrypted between Grid Monitor and the
  device. The push service sees only metadata: when a message was sent and to
  which subscription.
- Grid Monitor has no authentication yet. Anyone who can open the web UI can
  subscribe a device or send a test notification. Keep it on your LAN or VPN,
  or behind a proxy with access control.
