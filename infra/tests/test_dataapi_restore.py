"""dataapi_restore against a stubbed rds-data client (no AWS calls)."""
import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import ANY, Stubber

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dataapi_restore as dr  # noqa: E402

ARN = "arn:aws:rds:us-east-1:111122223333:cluster:story"
SECRET = "arn:aws:secretsmanager:us-east-1:111122223333:secret:rds-abc"
BASE = {"resourceArn": ARN, "secretArn": SECRET, "database": "storyengine"}


def s(v):
    return {"stringValue": v}


@pytest.fixture
def client():
    c = boto3.client("rds-data", region_name="us-east-1",
                     aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(c) as st:
        yield c, st
        st.assert_no_pending_responses()


def test_load_order_parents_first():
    edges = [["stories", "users"], ["payments", "users"], ["payments", "stories"]]
    assert dr.load_order(["payments", "stories", "users"], edges) == ["users", "stories", "payments"]


def test_load_order_survives_cycle():
    assert sorted(dr.load_order(["a", "b"], [["a", "b"], ["b", "a"]])) == ["a", "b"]


def test_insert_sql_casts_every_column():
    sql = dr.insert_sql("stories", ["id", "embedding"], {"id": "uuid", "embedding": "vector(384)"})
    assert sql == ('INSERT INTO "stories" ("id", "embedding") '
                   "VALUES (CAST(:p0 AS uuid), CAST(:p1 AS vector(384)))")


def test_to_params_null_marker_and_empty_string():
    assert dr.to_params(["\\N", ""]) == [
        {"name": "p0", "value": {"isNull": True}},
        {"name": "p1", "value": {"stringValue": ""}},
    ]


def test_restore_loads_in_fk_order_in_one_transaction(tmp_path, client):
    c, st = client
    (tmp_path / "users.csv").write_text("id,email\nu1,a@x\nu2,\\N\n", encoding="utf-8")
    (tmp_path / "stories.csv").write_text('id,user_id,body\ns1,u1,"two\nlines"\n', encoding="utf-8")
    (tmp_path / "alembic_version.csv").write_text("version_num\n0004\n", encoding="utf-8")

    st.add_response("execute_statement", {"records": [[s("stories"), s("users")]]},
                    {**BASE, "sql": dr.FK_SQL})
    # users first
    st.add_response("execute_statement",
                    {"records": [[s("id"), s("uuid")], [s("email"), s("text")]]},
                    {**BASE, "sql": dr.COLUMNS_SQL, "parameters": [{"name": "t", "value": s("users")}]})
    st.add_response("begin_transaction", {"transactionId": "tx1"}, BASE)
    st.add_response("batch_execute_statement", {"updateResults": []}, {
        **BASE, "transactionId": "tx1",
        "sql": 'INSERT INTO "users" ("id", "email") VALUES (CAST(:p0 AS uuid), CAST(:p1 AS text))',
        "parameterSets": [
            [{"name": "p0", "value": s("u1")}, {"name": "p1", "value": s("a@x")}],
            [{"name": "p0", "value": s("u2")}, {"name": "p1", "value": {"isNull": True}}],
        ]})
    st.add_response("commit_transaction", {"transactionStatus": "committed"},
                    {"resourceArn": ARN, "secretArn": SECRET, "transactionId": "tx1"})
    st.add_response("execute_statement", {"records": [[{"longValue": 2}]]},
                    {**BASE, "sql": 'SELECT count(*) FROM "users"'})
    # then stories; the multi-line body arrives intact
    st.add_response("execute_statement",
                    {"records": [[s("id"), s("uuid")], [s("user_id"), s("uuid")], [s("body"), s("text")]]},
                    {**BASE, "sql": dr.COLUMNS_SQL, "parameters": [{"name": "t", "value": s("stories")}]})
    st.add_response("begin_transaction", {"transactionId": "tx2"}, BASE)
    st.add_response("batch_execute_statement", {"updateResults": []}, {
        **BASE, "transactionId": "tx2", "sql": ANY,
        "parameterSets": [[{"name": "p0", "value": s("s1")}, {"name": "p1", "value": s("u1")},
                           {"name": "p2", "value": s("two\nlines")}]]})
    st.add_response("commit_transaction", {"transactionStatus": "committed"},
                    {"resourceArn": ARN, "secretArn": SECRET, "transactionId": "tx2"})
    st.add_response("execute_statement", {"records": [[{"longValue": 1}]]},
                    {**BASE, "sql": 'SELECT count(*) FROM "stories"'})

    res = dr.restore(dr.DataApi(c, ARN, SECRET, "storyengine"), tmp_path, log=lambda *_: None)
    assert res == {"users": (2, 2), "stories": (1, 1)}


def test_restore_rolls_back_on_error(tmp_path, client):
    c, st = client
    (tmp_path / "users.csv").write_text("id\nu1\n", encoding="utf-8")
    st.add_response("execute_statement", {"records": []}, {**BASE, "sql": dr.FK_SQL})
    st.add_response("execute_statement", {"records": [[s("id"), s("uuid")]]},
                    {**BASE, "sql": dr.COLUMNS_SQL, "parameters": ANY})
    st.add_response("begin_transaction", {"transactionId": "tx9"}, BASE)
    st.add_client_error("batch_execute_statement", "BadRequestException", "boom")
    st.add_response("rollback_transaction", {"transactionStatus": "rolled back"},
                    {"resourceArn": ARN, "secretArn": SECRET, "transactionId": "tx9"})
    with pytest.raises(Exception, match="boom"):
        dr.restore(dr.DataApi(c, ARN, SECRET, "storyengine"), tmp_path, log=lambda *_: None)


def test_restore_rejects_unknown_column(tmp_path, client):
    c, st = client
    (tmp_path / "users.csv").write_text("id,ghost\nu1,x\n", encoding="utf-8")
    st.add_response("execute_statement", {"records": []}, {**BASE, "sql": dr.FK_SQL})
    st.add_response("execute_statement", {"records": [[s("id"), s("uuid")]]},
                    {**BASE, "sql": dr.COLUMNS_SQL, "parameters": ANY})
    with pytest.raises(ValueError, match="ghost"):
        dr.restore(dr.DataApi(c, ARN, SECRET, "storyengine"), tmp_path, log=lambda *_: None)
