"""SSM secrets loader and the CodeDeploy hook status. No AWS: botocore Stubber only."""
import boto3
import pytest
from botocore.stub import Stubber

from app import migrate
from app.core import ssm
from app.core.config import Settings
from app.core.prod_guard import UnsafeProductionConfig, assert_production_safe

PATH = "/story-engine/prod/"


def _client(service):
    return boto3.client(
        service, region_name="us-east-1",
        aws_access_key_id="test", aws_secret_access_key="test",  # never used: stubbed
    )


def _param(name, value):
    return {"Name": f"/story-engine/prod/{name}", "Type": "SecureString", "Value": value, "Version": 1}


# ── SSM loader ───────────────────────────────────────────────────────────────

def test_loads_all_pages_decrypted_and_env_wins():
    client = _client("ssm")
    with Stubber(client) as stub:
        stub.add_response(
            "get_parameters_by_path",
            {"Parameters": [_param("ANTHROPIC_API_KEY", "sk-ant-from-ssm"),
                            _param("JWT_SECRET_KEY", "j" * 40)],
             "NextToken": "page2"},
            {"Path": "/story-engine/prod", "Recursive": False, "WithDecryption": True},
        )
        stub.add_response(
            "get_parameters_by_path",
            {"Parameters": [_param("SSLCOMMERZ_STORE_ID", "store"),
                            _param("SSLCOMMERZ_STORE_PASS", "pass"),
                            _param("NOT_A_SETTING", "x")]},
            {"Path": "/story-engine/prod", "Recursive": False, "WithDecryption": True,
             "NextToken": "page2"},
        )
        env = {"SSM_PARAMETER_PATH": PATH, "SSLCOMMERZ_STORE_ID": "from-env"}
        applied = ssm.load_parameters_into_env(Settings.model_fields, environ=env, client=client)
        stub.assert_no_pending_responses()

    assert sorted(applied) == ["ANTHROPIC_API_KEY", "JWT_SECRET_KEY", "SSLCOMMERZ_STORE_PASS"]
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-from-ssm"
    assert env["SSLCOMMERZ_STORE_ID"] == "from-env"  # environment wins
    assert "NOT_A_SETTING" not in env


def test_no_path_means_no_call():
    class Boom:
        def get_parameters_by_path(self, **_):
            raise AssertionError("SSM must not be called without SSM_PARAMETER_PATH")

    env: dict[str, str] = {}
    assert ssm.load_parameters_into_env(Settings.model_fields, environ=env, client=Boom()) == []
    assert env == {}


def test_ssm_failure_fails_cold_start():
    client = _client("ssm")
    with Stubber(client) as stub:
        stub.add_client_error("get_parameters_by_path", "AccessDeniedException", http_status_code=400)
        with pytest.raises(Exception, match="AccessDenied"):
            ssm.load_parameters_into_env(
                Settings.model_fields, environ={"SSM_PARAMETER_PATH": PATH}, client=client)


def test_values_never_logged(caplog):
    client = _client("ssm")
    with Stubber(client) as stub:
        stub.add_response("get_parameters_by_path",
                          {"Parameters": [_param("JWT_SECRET_KEY", "super-secret-value-123")]}, None)
        with caplog.at_level("INFO"):
            ssm.load_parameters_into_env(
                Settings.model_fields, environ={"SSM_PARAMETER_PATH": PATH}, client=client)
    assert "JWT_SECRET_KEY" in caplog.text
    assert "super-secret-value-123" not in caplog.text


def test_loaded_secrets_feed_settings_and_prod_guard(monkeypatch):
    """Loader runs before Settings is built; the prod guard then sees the SSM values."""
    from app.core import config

    client = _client("ssm")
    stub = Stubber(client)
    stub.add_response("get_parameters_by_path", {"Parameters": [
        _param("ANTHROPIC_API_KEY", "sk-ant-from-ssm"),
        _param("JWT_SECRET_KEY", "k" * 48),
    ]}, None)
    stub.activate()
    monkeypatch.setattr(ssm, "_default_client", lambda: client)
    for name in ("ANTHROPIC_API_KEY", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SSM_PARAMETER_PATH", PATH)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("DB_BACKEND", "dataapi")
    monkeypatch.setenv("DATAAPI_RESOURCE_ARN", "arn:aws:rds:us-east-1:1:cluster:c")
    monkeypatch.setenv("DATAAPI_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:1:secret:s")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    config.get_settings.cache_clear()
    try:
        s = config.get_settings()
        stub.assert_no_pending_responses()
        assert s.ANTHROPIC_API_KEY == "sk-ant-from-ssm" and s.JWT_SECRET_KEY == "k" * 48
        assert_production_safe(s)  # passes only because SSM supplied the secrets
    finally:
        config.get_settings.cache_clear()
        for name in ("ANTHROPIC_API_KEY", "JWT_SECRET_KEY"):
            monkeypatch.delenv(name, raising=False)  # loader wrote os.environ directly
        stub.deactivate()


def test_prod_guard_still_refuses_without_ssm_secrets(monkeypatch):
    s = Settings(_env_file=None, APP_ENV="production", DB_BACKEND="dataapi",
                 DATAAPI_RESOURCE_ARN="arn:x", DATAAPI_SECRET_ARN="arn:y")
    with pytest.raises(UnsafeProductionConfig, match="ANTHROPIC_API_KEY"):
        assert_production_safe(s)


# ── CodeDeploy PreTraffic hook ───────────────────────────────────────────────

HOOK = {"DeploymentId": "d-ABC123", "LifecycleEventHookExecutionId": "hook-exec-1"}


def _stub_codedeploy(monkeypatch, status):
    client = _client("codedeploy")
    stub = Stubber(client)
    stub.add_response(
        "put_lifecycle_event_hook_execution_status",
        {"lifecycleEventHookExecutionId": "hook-exec-1"},
        {"deploymentId": "d-ABC123", "lifecycleEventHookExecutionId": "hook-exec-1",
         "status": status},
    )
    stub.activate()
    monkeypatch.setattr(migrate, "_codedeploy_client", lambda: client)
    return stub


def test_hook_success_reports_succeeded(monkeypatch):
    calls = []
    monkeypatch.setattr(migrate, "upgrade", lambda rev="head": calls.append(rev))
    monkeypatch.setattr(migrate, "_current_revision", _async_value("0005"))
    stub = _stub_codedeploy(monkeypatch, "Succeeded")
    out = migrate.handler(dict(HOOK))
    stub.assert_no_pending_responses()
    assert calls == ["head"]
    assert out["hook_status"] == "Succeeded" and out["revision"] == "0005"


def test_hook_failure_logs_and_reports_failed(monkeypatch, caplog):
    def broken(rev="head"):
        raise RuntimeError("relation already exists")

    monkeypatch.setattr(migrate, "upgrade", broken)
    stub = _stub_codedeploy(monkeypatch, "Failed")
    with caplog.at_level("ERROR"):
        out = migrate.handler(dict(HOOK))
    stub.assert_no_pending_responses()
    assert out["hook_status"] == "Failed" and out["status"] == "error"
    assert "relation already exists" in caplog.text


def test_hook_ignores_revision_in_event_and_always_targets_head(monkeypatch):
    calls = []
    monkeypatch.setattr(migrate, "upgrade", lambda rev="head": calls.append(rev))
    monkeypatch.setattr(migrate, "_current_revision", _async_value("0005"))
    stub = _stub_codedeploy(monkeypatch, "Succeeded")
    migrate.handler({**HOOK, "revision": "0001"})
    stub.assert_no_pending_responses()
    assert calls == ["head"]


def test_manual_invoke_does_not_call_codedeploy(monkeypatch):
    def no_codedeploy():
        raise AssertionError("manual invoke must not report to CodeDeploy")

    calls = []
    monkeypatch.setattr(migrate, "_codedeploy_client", no_codedeploy)
    monkeypatch.setattr(migrate, "upgrade", lambda rev="head": calls.append(rev))
    monkeypatch.setattr(migrate, "_current_revision", _async_value("0005"))
    assert migrate.handler({"revision": "head"}) == {
        "status": "ok", "upgraded_to": "head", "revision": "0005"}
    assert migrate.handler({"action": "current"}) == {"status": "ok", "revision": "0005"}
    assert calls == ["head"]


def test_manual_invoke_failure_still_raises(monkeypatch):
    def broken(rev="head"):
        raise RuntimeError("boom")

    monkeypatch.setattr(migrate, "_codedeploy_client", lambda: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(migrate, "upgrade", broken)
    with pytest.raises(RuntimeError, match="boom"):
        migrate.handler({})


def _async_value(value):
    async def f():
        return value
    return f
