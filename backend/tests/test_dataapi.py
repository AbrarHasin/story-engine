"""Unit tests for the RDS Data API dialect (app.core.dataapi) with a stubbed Data API.

No AWS: a recording fake stands in for the boto3 `rds-data` client, and one test runs a
real boto3 client under botocore's Stubber to check the request shapes against the
service model. Real-Aurora integration tests are T014 (pending).
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import exc as sa_exc
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database  # noqa: F401 — registers postgresql+dataapi
from app.core import dataapi, limits
from app.core.config import Settings
from app.core.database import build_engine
from app.models.db import PlanTier, Story, StoryStatus, User

ARN = "arn:aws:rds:us-east-1:123456789012:cluster:story"
SECRET = "arn:aws:secretsmanager:us-east-1:123456789012:secret:db"


def _meta(*cols):
    return [{"name": n, "label": n, "typeName": t} for n, t in cols]


USER_COLS = _meta(
    ("id", "uuid"), ("email", "varchar"), ("name", "varchar"), ("password_hash", "varchar"),
    ("plan", "plantier"), ("stories_this_month", "int4"), ("quota_period_start", "timestamptz"),
    ("total_tokens_used", "int4"), ("created_at", "timestamp"),
)


def _user_record(uid, plan="free", stories=0, period="2026-03-01 00:00:00"):
    return [
        {"stringValue": str(uid)}, {"stringValue": "a@b.test"}, {"isNull": True},
        {"isNull": True}, {"stringValue": plan}, {"longValue": stories},
        {"stringValue": period} if period else {"isNull": True},
        {"longValue": 0}, {"stringValue": "2026-01-02 03:04:05.5"},
    ]


class FakeRdsData:
    """Records every call; answers execute_statement from `routes` (sql substring -> response)."""

    def __init__(self, routes=None, fail=None):
        self.calls: list[tuple[str, dict]] = []
        self.routes = routes or []
        self.fail = fail or {}   # method -> list of exceptions to raise first
        self.tx = 0

    def _maybe_fail(self, method):
        queue = self.fail.get(method)
        if queue:
            raise queue.pop(0)

    def begin_transaction(self, **kw):
        self.calls.append(("begin", kw))
        self._maybe_fail("begin_transaction")
        self.tx += 1
        return {"transactionId": f"tx{self.tx}"}

    def commit_transaction(self, **kw):
        self.calls.append(("commit", kw))
        return {"transactionStatus": "Transaction Committed"}

    def rollback_transaction(self, **kw):
        self.calls.append(("rollback", kw))
        return {"transactionStatus": "Rollback Complete"}

    def execute_statement(self, **kw):
        self.calls.append(("exec", kw))
        self._maybe_fail("execute_statement")
        for needle, resp in self.routes:
            if needle in kw["sql"]:
                return resp
        return {"numberOfRecordsUpdated": 1}

    @property
    def statements(self):
        return [kw for name, kw in self.calls if name == "exec"]

    @property
    def methods(self):
        return [name for name, _ in self.calls]


def _engine(fake):
    return create_async_engine(
        "postgresql+dataapi://",
        connect_args={"resource_arn": ARN, "secret_arn": SECRET, "database": "storyengine",
                      "client": fake, "resume_timeout": 5},
    )


def _client_error(code, message):
    return ClientError({"Error": {"Code": code, "Message": message}}, "ExecuteStatement")


# ── value conversion ──────────────────────────────────────────────────────────

def test_parameters_are_typed_for_the_data_api():
    uid = uuid.uuid4()
    p = dataapi.to_sql_parameter
    assert p("a", None) == {"name": "a", "value": {"isNull": True}}
    assert p("a", True) == {"name": "a", "value": {"booleanValue": True}}
    assert p("a", 7) == {"name": "a", "value": {"longValue": 7}}
    assert p("a", 1.5) == {"name": "a", "value": {"doubleValue": 1.5}}
    assert p("a", Decimal("1.10"))["typeHint"] == "DECIMAL"
    assert p("a", uid) == {"name": "a", "value": {"stringValue": str(uid)}, "typeHint": "UUID"}
    assert p("a", str(uid))["typeHint"] == "UUID"        # raw text() queries pass str(uuid)
    assert "typeHint" not in p("a", "plain text")
    aware = datetime(2026, 3, 1, 5, 30, tzinfo=timezone(timedelta(hours=5)))
    assert p("a", aware)["value"]["stringValue"] == "2026-03-01 00:30:00+00:00"
    assert p("a", datetime(2026, 3, 1, 1, 2, 3))["value"]["stringValue"] == "2026-03-01 01:02:03"
    assert p("a", date(2026, 3, 1))["value"]["stringValue"] == "2026-03-01"
    assert p("a", ["x", 'q"t'])["value"]["stringValue"] == '{"x","q\\"t"}'
    assert p("a", b"\x00\x01") == {"name": "a", "value": {"blobValue": b"\x00\x01"}}


def test_fields_become_asyncpg_types():
    uid = uuid.uuid4()
    f = dataapi.from_field
    assert f({"isNull": True}, "uuid") is None
    assert f({"stringValue": str(uid)}, "uuid") == uid
    assert f({"stringValue": "2026-03-01 00:00:00"}, "timestamptz") == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert f({"stringValue": "2026-01-02 03:04:05.5"}, "timestamp") == datetime(2026, 1, 2, 3, 4, 5, 500000)
    assert f({"stringValue": "2026-01-02"}, "date") == date(2026, 1, 2)
    assert f({"stringValue": "1.25"}, "numeric") == Decimal("1.25")
    assert f({"stringValue": "[1,2]"}, "vector") == "[1,2]"
    assert f({"longValue": 3}, "int4") == 3
    assert f({"booleanValue": False}, "bool") is False
    assert f({"arrayValue": {"stringValues": ["a"]}}, "_text") == ["a"]


# ── ORM over the stub ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orm_select_maps_types_and_casts_binds():
    uid = uuid.uuid4()
    fake = FakeRdsData(routes=[("FROM users", {"columnMetadata": USER_COLS, "records": [_user_record(uid)]})])
    eng = _engine(fake)
    async with async_sessionmaker(eng, class_=AsyncSession)() as db:
        user = await db.get(User, uid)
    await eng.dispose()

    assert user.id == uid
    assert user.plan is PlanTier.free
    assert user.quota_period_start == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert user.created_at == datetime(2026, 1, 2, 3, 4, 5, 500000)
    stmt = fake.statements[0]
    assert "users.id = :pk_1::UUID" in stmt["sql"]
    assert stmt["parameters"] == [{"name": "pk_1", "value": {"stringValue": str(uid)}, "typeHint": "UUID"}]
    assert stmt["transactionId"] == "tx1"
    assert stmt["resourceArn"] == ARN and stmt["secretArn"] == SECRET
    assert fake.methods == ["begin", "exec", "rollback"]   # session closed without commit


@pytest.mark.asyncio
async def test_insert_casts_enum_uuid_and_commits_once():
    uid = uuid.uuid4()
    fake = FakeRdsData()
    eng = _engine(fake)
    async with async_sessionmaker(eng, class_=AsyncSession)() as db:
        db.add(Story(id=uuid.uuid4(), user_id=uid, topic="t", status=StoryStatus.running))
        await db.commit()
    await eng.dispose()

    sql = fake.statements[0]["sql"]
    assert sql.startswith("INSERT INTO stories")
    assert ":user_id::UUID" in sql and ":status::storystatus" in sql
    assert ":embedding::VECTOR(384)" in sql
    params = {p["name"]: p for p in fake.statements[0]["parameters"]}
    assert params["status"]["value"] == {"stringValue": "running"}
    assert params["personality_id"]["value"] == {"isNull": True}
    assert fake.methods == ["begin", "exec", "commit"]
    assert fake.calls[-1][1]["transactionId"] == "tx1"


@pytest.mark.asyncio
async def test_vector_and_json_binds():
    fake = FakeRdsData(routes=[("<=>", {"columnMetadata": _meta(("id", "uuid"), ("d", "float8")), "records": []})])
    eng = _engine(fake)
    async with eng.connect() as conn:
        await conn.execute(select(Story.id, Story.embedding.cosine_distance([0.5, 0.25] + [0.0] * 382).label("d")))
    await eng.dispose()
    stmt = fake.statements[0]
    assert ":embedding_1::VECTOR(384)" in stmt["sql"]
    assert stmt["parameters"][0]["value"]["stringValue"].startswith("[0.5,0.25,0")


@pytest.mark.asyncio
async def test_update_rowcount_from_data_api():
    fake = FakeRdsData(routes=[("UPDATE users", {"numberOfRecordsUpdated": 1})])
    eng = _engine(fake)
    async with eng.begin() as conn:
        result = await conn.execute(update(User).where(User.id == uuid.uuid4()).values(total_tokens_used=1))
        assert result.rowcount == 1
    await eng.dispose()
    assert fake.methods == ["begin", "exec", "commit"]


@pytest.mark.asyncio
async def test_enforce_quota_locks_user_row_in_one_transaction(monkeypatch):
    """limits.enforce_quota over the Data API: FOR UPDATE + count in the same transaction."""
    monkeypatch.setattr(limits, "_utcnow", lambda: datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    uid = uuid.uuid4()
    fake = FakeRdsData(routes=[
        ("FOR UPDATE", {"columnMetadata": USER_COLS,
                        "records": [_user_record(uid, stories=9, period="2026-03-01 00:00:00")]}),
        ("count(*)", {"columnMetadata": _meta(("count_1", "int8")), "records": [[{"longValue": 1}]]}),
    ])
    eng = _engine(fake)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as db:
        with pytest.raises(Exception) as exc:
            await limits.enforce_quota(db, User(id=uid))
        assert getattr(exc.value, "status_code", None) == 402   # 9 completed + 1 running >= 10
        await db.rollback()
    await eng.dispose()

    lock, count = fake.statements
    assert "FOR UPDATE" in lock["sql"] and lock["transactionId"] == count["transactionId"] == "tx1"
    assert ":status_1::storystatus" in count["sql"]
    assert ":created_at_1::TIMESTAMP WITHOUT TIME ZONE" in count["sql"]   # stale running rows ignored
    assert fake.methods[-1] == "rollback"


@pytest.mark.asyncio
async def test_autocommit_runs_without_a_transaction():
    fake = FakeRdsData(routes=[("SELECT 1", {"columnMetadata": _meta(("x", "int4")), "records": [[{"longValue": 1}]]})])
    eng = _engine(fake)
    async with eng.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    await eng.dispose()
    assert fake.methods == ["exec"]
    assert "transactionId" not in fake.statements[0]


@pytest.mark.asyncio
async def test_empty_result_still_has_columns():
    fake = FakeRdsData(routes=[("FROM users", {"columnMetadata": USER_COLS, "records": []})])
    eng = _engine(fake)
    async with async_sessionmaker(eng, class_=AsyncSession)() as db:
        assert await db.get(User, uuid.uuid4()) is None
    await eng.dispose()


# ── paused cluster and errors ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resuming_cluster_is_retried(monkeypatch):
    sleeps = []

    async def no_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(dataapi.asyncio, "sleep", no_sleep)
    resuming = _client_error("DatabaseResumingException", "The Aurora DB instance is resuming after being auto-paused.")
    fake = FakeRdsData(
        routes=[("SELECT 1", {"columnMetadata": _meta(("x", "int4")), "records": [[{"longValue": 1}]]})],
        fail={"begin_transaction": [resuming, resuming]},
    )
    eng = _engine(fake)
    async with eng.connect() as conn:
        assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    await eng.dispose()
    assert fake.methods[:3] == ["begin", "begin", "begin"]
    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
async def test_resume_gives_up_after_timeout(monkeypatch):
    async def no_sleep(s):
        pass

    monkeypatch.setattr(dataapi.asyncio, "sleep", no_sleep)
    clock = iter(range(0, 1000, 3))
    monkeypatch.setattr(dataapi, "_monotonic", lambda: next(clock))
    resuming = _client_error("DatabaseResumingException", "resuming")
    fake = FakeRdsData(fail={"begin_transaction": [resuming] * 50})
    eng = _engine(fake)
    with pytest.raises(sa_exc.OperationalError):
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    await eng.dispose()
    assert 1 < fake.methods.count("begin") < 50


@pytest.mark.asyncio
async def test_unique_violation_is_integrity_error():
    dup = _client_error(
        "BadRequestException",
        'ERROR: duplicate key value violates unique constraint "users_email_key"; SQLState: 23505',
    )
    fake = FakeRdsData(fail={"execute_statement": [dup]})
    eng = _engine(fake)
    with pytest.raises(sa_exc.IntegrityError):
        async with eng.begin() as conn:
            await conn.execute(text("INSERT INTO users (email) VALUES ('x')"))
    await eng.dispose()
    assert fake.methods[-1] == "rollback"


@pytest.mark.asyncio
async def test_bad_sql_is_programming_error():
    fake = FakeRdsData(fail={"execute_statement": [_client_error("BadRequestException", "syntax error")]})
    eng = _engine(fake)
    with pytest.raises(sa_exc.ProgrammingError):
        async with eng.connect() as conn:
            await conn.execute(text("SELEC 1"))
    await eng.dispose()


# ── real boto3 client, botocore Stubber (request shapes vs the service model) ─

@pytest.mark.asyncio
async def test_requests_match_the_rds_data_service_model():
    import boto3
    from botocore.stub import ANY, Stubber

    client = boto3.client(
        "rds-data", region_name="us-east-1",
        aws_access_key_id="testing", aws_secret_access_key="testing",
    )
    uid = uuid.uuid4()
    with Stubber(client) as stub:
        stub.add_response(
            "begin_transaction", {"transactionId": "abc"},
            {"resourceArn": ARN, "secretArn": SECRET, "database": "storyengine"},
        )
        stub.add_response(
            "execute_statement",
            {"columnMetadata": USER_COLS, "records": [_user_record(uid)], "numberOfRecordsUpdated": 0},
            {"resourceArn": ARN, "secretArn": SECRET, "database": "storyengine", "sql": ANY,
             "parameters": [{"name": "pk_1", "value": {"stringValue": str(uid)}, "typeHint": "UUID"}],
             "includeResultMetadata": True, "transactionId": "abc"},
        )
        stub.add_response(
            "commit_transaction", {"transactionStatus": "Transaction Committed"},
            {"resourceArn": ARN, "secretArn": SECRET, "transactionId": "abc"},
        )
        eng = _engine(client)
        async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as db:
            user = await db.get(User, uid)
            await db.commit()
        await eng.dispose()
        stub.assert_no_pending_responses()
    assert user.id == uid


# ── T015: alembic over the Data API ──────────────────────────────────────────

def test_alembic_upgrade_head_over_data_api(monkeypatch):
    """Every migration runs as single statements inside one Data API transaction."""
    from alembic import command

    from app.core.config import settings
    from app.migrate import alembic_config

    class EmptyCatalog(FakeRdsData):
        def execute_statement(self, **kw):
            resp = super().execute_statement(**kw)
            if kw["sql"].lstrip().upper().startswith("SELECT") and "columnMetadata" not in resp:
                return {"columnMetadata": _meta(("x", "text")), "records": []}
            if " RETURNING " in kw["sql"]:   # echo the inserted key, as Aurora would
                first = kw["parameters"][0]["value"] if kw["parameters"] else {"isNull": True}
                return {"columnMetadata": _meta(("k", "varchar")), "records": [[first]]}
            return resp

    fake = EmptyCatalog()
    monkeypatch.setattr(dataapi, "_client", fake)
    monkeypatch.setattr(settings, "DB_BACKEND", "dataapi")
    monkeypatch.setattr(settings, "DATAAPI_RESOURCE_ARN", ARN)
    monkeypatch.setattr(settings, "DATAAPI_SECRET_ARN", SECRET)

    command.upgrade(alembic_config(), "head")

    sqls = [s["sql"] for s in fake.statements]
    assert fake.methods[0] == "begin" and fake.methods[-1] == "commit"
    assert fake.methods.count("begin") == 1
    assert {s.get("transactionId") for s in fake.statements} == {"tx1"}
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in s for s in sqls)
    assert any("CREATE TABLE rate_limit_window" in s for s in sqls)
    version_writes = [
        st for st in fake.statements
        if "alembic_version" in st["sql"] and not st["sql"].lstrip().upper().startswith("SELECT")
    ]
    assert any(
        "'0005'" in st["sql"] or any(p["value"].get("stringValue") == "0005" for p in st["parameters"])
        for st in version_writes
    )
    # the Data API rejects multi-statement strings
    for s in sqls:
        assert ";" not in s.strip().rstrip(";"), s


# ── backend switch ────────────────────────────────────────────────────────────

def test_build_engine_switches_on_db_backend():
    data = build_engine(Settings(_env_file=None, DB_BACKEND="dataapi",
                                 DATAAPI_RESOURCE_ARN=ARN, DATAAPI_SECRET_ARN=SECRET))
    assert data.dialect.driver == "dataapi"
    local = build_engine(Settings(_env_file=None, DB_BACKEND="asyncpg"))
    assert local.dialect.driver == "asyncpg"
    with pytest.raises(ValueError):
        build_engine(Settings(_env_file=None, DB_BACKEND="sqlite"))
