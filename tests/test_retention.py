from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import make_engine, make_session_factory
from app.db.models import Inverter, InverterSample
from app.services.retention import RetentionService


async def _session_factory(tmp_path) -> async_sessionmaker[AsyncSession]:
    from app.db.engine import apply_migrations

    url = f"sqlite+aiosqlite:///{(tmp_path / 'ret.db').as_posix()}"
    engine = make_engine(url)
    await apply_migrations(engine)
    return make_session_factory(engine), engine


async def test_retention_purges_old_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'ret.db').as_posix()}")
    from app.core.config import get_settings

    get_settings.cache_clear()
    factory, engine = await _session_factory(tmp_path)
    now = datetime.now(UTC)

    async with factory() as session:
        inverter = Inverter(name="A", driver_id="saj-h2", host="192.0.2.1")
        session.add(inverter)
        await session.flush()
        session.add_all(
            [
                InverterSample(
                    inverter_id=inverter.id,
                    ts=now - timedelta(days=400),
                    pv_power_w=10,
                ),
                InverterSample(
                    inverter_id=inverter.id,
                    ts=now - timedelta(hours=1),
                    pv_power_w=20,
                ),
            ]
        )
        await session.commit()

    service = RetentionService(factory, "sqlite")
    await service.run(retention_days=365, downsample_after_days=0)

    async with factory() as session:
        rows = (await session.execute(select(InverterSample))).scalars().all()
        assert len(rows) == 1
        assert rows[0].pv_power_w == 20

    await engine.dispose()
    get_settings.cache_clear()
