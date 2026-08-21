from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func
from sqlalchemy.sql.elements import ColumnElement as SQLColumn


def time_bucket(column: SQLColumn, resolution: str, dialect_name: str) -> ColumnElement:
    """Dialect-aware equivalent of Postgres date_trunc()."""
    if dialect_name == "postgresql":
        return func.date_trunc(resolution, column)

    formats = {
        "minute": "%Y-%m-%d %H:%M:00",
        "hour": "%Y-%m-%d %H:00:00",
        "day": "%Y-%m-%d 00:00:00",
        "month": "%Y-%m-01 00:00:00",
    }
    try:
        fmt = formats[resolution]
    except KeyError as exc:
        raise ValueError(f"Unsupported resolution {resolution!r}") from exc
    return func.strftime(fmt, column)


def serialize_bucket_ts(value: object) -> str:
    if isinstance(value, str):
        normalized = value.replace(" ", "T")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    raise TypeError(f"Cannot serialize timestamp {value!r}")
