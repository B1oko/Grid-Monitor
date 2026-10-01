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


def parse_bucket_ts(value: object) -> datetime:
    """Return a bucket value from ``time_bucket`` as an aware UTC datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace(" ", "T"))
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    raise TypeError(f"Cannot parse timestamp {value!r}")


def serialize_bucket_ts(value: object) -> str:
    try:
        return parse_bucket_ts(value).isoformat()
    except TypeError as exc:
        raise TypeError(f"Cannot serialize timestamp {value!r}") from exc
