from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import PushSubscription

logger = logging.getLogger(__name__)

VAPID_KEY_FILE = "vapid_private.pem"
PUSH_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    tag: str
    url: str = "/"


class Notifier(Protocol):
    async def send(self, notification: Notification) -> int:
        """Deliver a notification and return how many devices accepted it."""


def load_or_create_vapid(data_dir: Path) -> Vapid01:
    path = data_dir / VAPID_KEY_FILE
    if path.exists():
        return Vapid01.from_file(str(path))
    vapid = Vapid01()
    vapid.generate_keys()
    vapid.save_key(str(path))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("Generated VAPID key pair at %s", path)
    return vapid


def application_server_key(vapid: Vapid01) -> str:
    raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class WebPushNotifier:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        vapid: Vapid01,
        subject: str,
    ) -> None:
        self._session_factory = session_factory
        self._vapid = vapid
        self._subject = subject

    @property
    def public_key(self) -> str:
        return application_server_key(self._vapid)

    async def subscribe(
        self, *, endpoint: str, p256dh: str, auth: str, user_agent: str | None
    ) -> None:
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(PushSubscription).where(PushSubscription.endpoint == endpoint)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    PushSubscription(
                        endpoint=endpoint,
                        p256dh=p256dh,
                        auth=auth,
                        user_agent=(user_agent or "")[:255] or None,
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                existing.p256dh = p256dh
                existing.auth = auth
            await session.commit()

    async def unsubscribe(self, endpoint: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
            await session.commit()

    async def subscription_count(self) -> int:
        async with self._session_factory() as session:
            rows = (await session.execute(select(PushSubscription.id))).all()
        return len(rows)

    async def send(self, notification: Notification) -> int:
        async with self._session_factory() as session:
            subscriptions = (await session.execute(select(PushSubscription))).scalars().all()

        payload = json.dumps(asdict(notification))
        delivered = 0
        gone: list[int] = []
        for sub in subscriptions:
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=self._vapid,
                    vapid_claims={"sub": self._subject},
                    ttl=PUSH_TTL_SECONDS,
                    headers={"Urgency": "high"},
                    timeout=10,
                )
                delivered += 1
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (404, 410):
                    gone.append(sub.id)
                else:
                    logger.warning("Web push to %s failed: %s", _host(sub.endpoint), exc)
            except Exception as exc:
                logger.warning("Web push to %s failed: %s", _host(sub.endpoint), exc)

        if gone:
            async with self._session_factory() as session:
                await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
                await session.commit()
            logger.info("Removed %d expired push subscription(s)", len(gone))
        return delivered


def _host(endpoint: str) -> str:
    return endpoint.split("/")[2] if endpoint.count("/") >= 2 else endpoint
