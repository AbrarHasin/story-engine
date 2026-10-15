"""Async SQLAlchemy dialect over the Aurora RDS Data API (spec 002 Option S, T013).

On AWS the backend runs in Lambda outside any VPC and reaches Aurora Serverless v2
through the Data API (HTTPS, no socket, no NAT). Selected with DB_BACKEND=dataapi;
local development keeps DB_BACKEND=asyncpg and never imports boto3.

    postgresql+dataapi://  connect_args={"resource_arn", "secret_arn", "database"}

The dialect is the stock PostgreSQL dialect with three changes:

* Parameters go out as Data API ``SqlParameter``s (named ``:name`` style). The
  Data API types a plain string as ``text``, so every bind whose column type is
  not text gets an explicit cast (``:id_1::UUID``, ``::storystatus``,
  ``::VECTOR(384)``, ``::TIMESTAMP WITH TIME ZONE``) through SQLAlchemy's
  render-casts bind typing, the same mechanism the asyncpg dialect uses. A
  UUID-shaped string sent from a raw ``text()`` query gets the ``UUID`` type hint.
* Results come back as Data API ``Field``s; they are converted to the Python
  types asyncpg returns (UUID, datetime, date, Decimal) using the column
  metadata, so every result processor above this layer works unchanged.
* A DB-API transaction maps to ``BeginTransaction`` / ``CommitTransaction`` /
  ``RollbackTransaction``, begun lazily on the first statement, so
  ``SELECT ... FOR UPDATE`` in ``enforce_quota`` holds its lock until commit.

A paused Aurora cluster (min 0 ACU) answers ``DatabaseResumingException`` while
it wakes; the first call of a transaction is retried for up to
DATAAPI_RESUME_TIMEOUT_SECONDS (45 s by default).

Limits to keep in mind: one statement per call (no multi-statement strings),
1 MB per result set, no array parameters, a transaction expires after 3 minutes
idle or 24 hours total.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, datetime, time as dtime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import pool
from sqlalchemy.dialects.postgresql import JSON, JSONB, ENUM
from sqlalchemy.dialects.postgresql.base import PGDialect, PGExecutionContext
from sqlalchemy.engine import AdaptedConnection, interfaces
from sqlalchemy.sql import sqltypes
from sqlalchemy.util.concurrency import await_only

logger = logging.getLogger(__name__)

paramstyle = "named"
apilevel = "2.0"
threadsafety = 1

RESUME_TIMEOUT_SECONDS = 45.0
_monotonic = time.monotonic   # seam for tests
_UUID_STR = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_RESUMING_MARKERS = ("DatabaseResumingException", "is resuming after being auto-paused")
_INTEGRITY_SQLSTATES = ("SQLState: 23",)


# ── DB-API exceptions ─────────────────────────────────────────────────────────

class Warning(Exception):  # noqa: A001 - DB-API name
    pass


class Error(Exception):
    pass


class InterfaceError(Error):
    pass


class DatabaseError(Error):
    pass


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    return str(response.get("Error", {}).get("Code", ""))


def _is_resuming(exc: Exception) -> bool:
    text = f"{_error_code(exc)} {exc}"
    return any(m in text for m in _RESUMING_MARKERS)


def _translate(exc: Exception) -> Error:
    """botocore ClientError -> DB-API exception (SQLAlchemy wraps it again)."""
    message = str(exc)
    code = _error_code(exc)
    if any(s in message for s in _INTEGRITY_SQLSTATES) or "violates" in message:
        return IntegrityError(message)
    if _is_resuming(exc) or code in ("StatementTimeoutException", "ServiceUnavailableError"):
        return OperationalError(message)
    if code == "BadRequestException":
        return ProgrammingError(message)
    return DatabaseError(message)


# ── Values in and out ─────────────────────────────────────────────────────────

def _format_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None).isoformat(sep=" ") + "+00:00"
    return value.isoformat(sep=" ")


def to_sql_parameter(name: str, value: Any) -> dict:
    """One bound Python value -> one Data API SqlParameter."""
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        return {"name": name, "value": {"doubleValue": value}}
    if isinstance(value, Decimal):
        return {"name": name, "value": {"stringValue": str(value)}, "typeHint": "DECIMAL"}
    if isinstance(value, UUID):
        return {"name": name, "value": {"stringValue": str(value)}, "typeHint": "UUID"}
    if isinstance(value, str):
        if _UUID_STR.match(value):
            # raw text() queries pass str(uuid); the Data API would type it text
            return {"name": name, "value": {"stringValue": value}, "typeHint": "UUID"}
        return {"name": name, "value": {"stringValue": value}}
    if isinstance(value, datetime):
        return {"name": name, "value": {"stringValue": _format_datetime(value)}}
    if isinstance(value, date):
        return {"name": name, "value": {"stringValue": value.isoformat()}}
    if isinstance(value, dtime):
        return {"name": name, "value": {"stringValue": value.isoformat()}}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"name": name, "value": {"blobValue": bytes(value)}}
    if isinstance(value, (list, tuple)):
        # the Data API rejects array parameters; send a PG array literal, the cast types it
        items = ",".join(
            '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"' for v in value
        )
        return {"name": name, "value": {"stringValue": "{" + items + "}"}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _parse_datetime(text: str) -> datetime:
    # Data API: "YYYY-MM-DD HH:MM:SS[.f{1,6}]" (timestamptz rendered in UTC)
    if "." in text:
        head, frac = text.split(".", 1)
        digits = re.match(r"\d*", frac).group(0)  # type: ignore[union-attr]
        text = f"{head}.{digits[:6].ljust(6, '0')}{frac[len(digits):]}"
    return datetime.fromisoformat(text)


def from_field(field: dict, type_name: str = "") -> Any:
    """One Data API Field -> the Python value asyncpg would have returned."""
    if field.get("isNull"):
        return None
    if "stringValue" in field:
        value = field["stringValue"]
        t = type_name.lower()
        if t == "uuid":
            return UUID(value)
        if t in ("timestamptz", "timestamp with time zone"):
            parsed = _parse_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        if t in ("timestamp", "timestamp without time zone"):
            return _parse_datetime(value)
        if t == "date":
            return date.fromisoformat(value)
        if t in ("numeric", "decimal"):
            return Decimal(value)
        return value
    for key in ("longValue", "doubleValue", "booleanValue"):
        if key in field:
            return field[key]
    if "blobValue" in field:
        return bytes(field["blobValue"])
    if "arrayValue" in field:
        av = field["arrayValue"]
        for key in ("stringValues", "longValues", "doubleValues", "booleanValues"):
            if key in av:
                return list(av[key])
        return []
    return None


# ── Async core: one Data API "connection" ─────────────────────────────────────

_client: Any = None


def _default_client() -> Any:
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("rds-data")
    return _client


class AsyncDataApiConnection:
    """Holds the ARNs and the current transaction id. Every call goes to boto3 in a thread."""

    def __init__(
        self,
        resource_arn: str,
        secret_arn: str,
        database: str,
        client: Any = None,
        resume_timeout: float = RESUME_TIMEOUT_SECONDS,
    ) -> None:
        self.resource_arn = resource_arn
        self.secret_arn = secret_arn
        self.database = database
        self.client = client if client is not None else _default_client()
        self.resume_timeout = resume_timeout
        self.transaction_id: str | None = None
        self.autocommit = False

    async def _call(self, method: str, retry_resume: bool, **kwargs: Any) -> dict:
        fn = getattr(self.client, method)
        deadline = _monotonic() + self.resume_timeout
        delay = 1.0
        while True:
            try:
                return await asyncio.to_thread(fn, **kwargs)
            except Exception as exc:  # noqa: BLE001 - botocore ClientError and friends
                if retry_resume and _is_resuming(exc) and _monotonic() + delay < deadline:
                    logger.info("Aurora is resuming; retrying %s in %.0f s", method, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 8.0)
                    continue
                raise _translate(exc) from exc

    async def begin(self) -> None:
        resp = await self._call(
            "begin_transaction", True,
            resourceArn=self.resource_arn, secretArn=self.secret_arn, database=self.database,
        )
        self.transaction_id = resp["transactionId"]

    async def execute(self, sql: str, parameters: list[dict]) -> dict:
        if self.transaction_id is None and not self.autocommit:
            await self.begin()
        kwargs: dict[str, Any] = dict(
            resourceArn=self.resource_arn,
            secretArn=self.secret_arn,
            database=self.database,
            sql=sql,
            parameters=parameters,
            includeResultMetadata=True,
        )
        if self.transaction_id is not None:
            kwargs["transactionId"] = self.transaction_id
        # inside a transaction the cluster is already awake
        return await self._call("execute_statement", self.transaction_id is None, **kwargs)

    async def commit(self) -> None:
        if self.transaction_id is None:
            return
        tid, self.transaction_id = self.transaction_id, None
        await self._call(
            "commit_transaction", False,
            resourceArn=self.resource_arn, secretArn=self.secret_arn, transactionId=tid,
        )

    async def rollback(self) -> None:
        if self.transaction_id is None:
            return
        tid, self.transaction_id = self.transaction_id, None
        await self._call(
            "rollback_transaction", False,
            resourceArn=self.resource_arn, secretArn=self.secret_arn, transactionId=tid,
        )


# ── DB-API facade used by SQLAlchemy (sync methods, awaited in its greenlet) ──

class DataApiCursor:
    arraysize = 1
    lastrowid = None

    def __init__(self, adapt_connection: "DataApiAdaptConnection") -> None:
        self._adapt_connection = adapt_connection
        self._connection = adapt_connection._connection
        self.description: list[tuple] | None = None
        self.rowcount = -1
        self._rows: list[tuple] = []

    def close(self) -> None:
        self._rows = []

    def _run(self, operation: str, parameters: Any) -> None:
        params = [to_sql_parameter(k, v) for k, v in (parameters or {}).items()]
        resp = await_only(self._connection.execute(operation, params))
        meta = resp.get("columnMetadata") or []
        types = [m.get("typeName", "") for m in meta]
        records = resp.get("records")
        if meta:
            self.description = [
                (m.get("label") or m.get("name"), m.get("typeName"), None, None, None, None, None)
                for m in meta
            ]
        else:
            self.description = None
        self._rows = [
            tuple(from_field(f, types[i] if i < len(types) else "") for i, f in enumerate(rec))
            for rec in (records or [])
        ]
        updated = resp.get("numberOfRecordsUpdated")
        if records is not None and meta:
            self.rowcount = len(self._rows)
        else:
            self.rowcount = updated if updated is not None else -1

    def execute(self, operation: str, parameters: Any = None) -> None:
        self._run(operation, parameters)

    def executemany(self, operation: str, seq_of_parameters: Any) -> None:
        total = 0
        for params in seq_of_parameters:
            self._run(operation, params)
            total += max(self.rowcount, 0)
        self.rowcount = total

    def setinputsizes(self, *args: Any) -> None:
        pass

    def fetchone(self) -> tuple | None:
        return self._rows.pop(0) if self._rows else None

    def fetchmany(self, size: int | None = None) -> list[tuple]:
        size = size or self.arraysize
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def fetchall(self) -> list[tuple]:
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self):
        while self._rows:
            yield self._rows.pop(0)


class DataApiAdaptConnection(AdaptedConnection):
    __slots__ = ("dbapi",)

    def __init__(self, dbapi: Any, connection: AsyncDataApiConnection) -> None:
        self.dbapi = dbapi
        self._connection = connection

    @property
    def autocommit(self) -> bool:
        return self._connection.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self._connection.autocommit = value

    def cursor(self, server_side: bool = False) -> DataApiCursor:
        return DataApiCursor(self)

    # Without an open transaction these are no-ops and must not need the greenlet
    # (pool reset and garbage collection call them outside one).
    def commit(self) -> None:
        if self._connection.transaction_id is not None:
            await_only(self._connection.commit())

    def rollback(self) -> None:
        if self._connection.transaction_id is not None:
            await_only(self._connection.rollback())

    def close(self) -> None:
        self.rollback()


class _DataApiDBAPI:
    """Module-like DB-API object handed to the dialect."""

    paramstyle = paramstyle
    apilevel = apilevel
    threadsafety = threadsafety
    Warning = Warning
    Error = Error
    InterfaceError = InterfaceError
    DatabaseError = DatabaseError
    DataError = DataError
    OperationalError = OperationalError
    IntegrityError = IntegrityError
    InternalError = InternalError
    ProgrammingError = ProgrammingError
    NotSupportedError = NotSupportedError

    def connect(
        self,
        resource_arn: str,
        secret_arn: str,
        database: str,
        client: Any = None,
        resume_timeout: float = RESUME_TIMEOUT_SECONDS,
    ) -> DataApiAdaptConnection:
        return DataApiAdaptConnection(
            self,
            AsyncDataApiConnection(resource_arn, secret_arn, database, client, resume_timeout),
        )


# ── Bind casts: everything that is not text says what it is ───────────────────

class _UUID(sqltypes.Uuid):
    render_bind_cast = True


class _DateTime(sqltypes.DateTime):
    render_bind_cast = True


class _Date(sqltypes.Date):
    render_bind_cast = True


class _Time(sqltypes.Time):
    render_bind_cast = True


class _Numeric(sqltypes.Numeric):
    render_bind_cast = True


class _Enum(ENUM):
    render_bind_cast = True


class _JSON(JSON):
    render_bind_cast = True


class _JSONB(JSONB):
    render_bind_cast = True


def _vector_colspec() -> dict:
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:  # pragma: no cover - pgvector is a hard dependency today
        return {}

    class _Vector(Vector):
        render_bind_cast = True
        cache_ok = True

    return {Vector: _Vector}


class PGExecutionContext_dataapi(PGExecutionContext):
    pass


class PGDialect_dataapi(PGDialect):
    driver = "dataapi"
    is_async = True
    supports_statement_cache = True
    supports_server_side_cursors = False
    supports_sane_multi_rowcount = False
    default_paramstyle = "named"
    bind_typing = interfaces.BindTyping.RENDER_CASTS
    execution_ctx_cls = PGExecutionContext_dataapi
    # Aurora PostgreSQL 16; asked without a round trip (see initialize)
    server_version_assumed = (16, 4)

    colspecs = {
        **PGDialect.colspecs,
        sqltypes.Uuid: _UUID,
        sqltypes.DateTime: _DateTime,
        sqltypes.Date: _Date,
        sqltypes.Time: _Time,
        sqltypes.Numeric: _Numeric,
        sqltypes.Enum: _Enum,
        ENUM: _Enum,
        sqltypes.JSON: _JSON,
        JSON: _JSON,
        JSONB: _JSONB,
        **_vector_colspec(),
    }
    # Float stays a doubleValue; a numeric cast on it is not needed
    colspecs[sqltypes.Float] = sqltypes.Float

    @classmethod
    def import_dbapi(cls) -> Any:
        return _DataApiDBAPI()

    @classmethod
    def get_pool_class(cls, url: Any) -> Any:
        # a Data API "connection" is a few strings; nothing worth pooling
        return pool.NullPool

    def create_connect_args(self, url: Any) -> tuple[list, dict]:
        opts: dict[str, Any] = {}
        if url.database:
            opts["database"] = url.database
        opts.update(url.query)
        return [], opts

    def get_driver_connection(self, connection: Any) -> Any:
        return connection._connection

    def is_disconnect(self, e: Exception, connection: Any, cursor: Any) -> bool:
        return False

    def do_ping(self, dbapi_connection: Any) -> bool:
        return True

    # No round trips while the dialect initializes (each would wake a paused cluster).
    def _get_server_version_info(self, connection: Any) -> tuple:
        return self.server_version_assumed

    def _get_default_schema_name(self, connection: Any) -> str:
        return "public"

    def _set_backslash_escapes(self, connection: Any) -> None:
        self._backslash_escapes = False

    def get_default_isolation_level(self, dbapi_conn: Any) -> Any:
        return "READ COMMITTED"

    def get_isolation_level(self, dbapi_connection: Any) -> Any:
        return "AUTOCOMMIT" if dbapi_connection.autocommit else "READ COMMITTED"

    def get_isolation_level_values(self, dbapi_conn: Any) -> Any:
        return ["AUTOCOMMIT", "READ COMMITTED"]

    def set_isolation_level(self, dbapi_connection: Any, level: str) -> None:
        dbapi_connection.autocommit = level == "AUTOCOMMIT"

    def set_readonly(self, connection: Any, value: bool) -> None:
        pass

    def get_readonly(self, connection: Any) -> bool:
        return False

    def set_deferrable(self, connection: Any, value: bool) -> None:
        pass

    def get_deferrable(self, connection: Any) -> bool:
        return False

    def do_begin(self, dbapi_connection: Any) -> None:
        pass  # BeginTransaction runs lazily on the first statement

    def do_rollback(self, dbapi_connection: Any) -> None:
        dbapi_connection.rollback()

    def do_commit(self, dbapi_connection: Any) -> None:
        dbapi_connection.commit()

    def do_terminate(self, dbapi_connection: Any) -> None:
        dbapi_connection.close()


dialect = PGDialect_dataapi
