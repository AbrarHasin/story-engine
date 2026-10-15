"""Static checks on the SAM templates: the decisions of spec 002 stay encoded.

Uses cfn-lint's YAML loader (understands !Sub, !Ref ...). cfn-lint itself runs
in test_cfn_lint_clean when installed: pip install cfn-lint.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

decode = pytest.importorskip("cfnlint.decode.cfn_yaml")

INFRA = Path(__file__).resolve().parents[1]
REPO = INFRA.parent


def load(name):
    return decode.load(str(INFRA / name))


@pytest.fixture(scope="module")
def app():
    return load("template.yaml")["Resources"]


@pytest.fixture(scope="module")
def boot():
    return load("bootstrap.yaml")["Resources"]


def test_aurora_scales_to_zero_with_data_api(app):
    p = app["AuroraCluster"]["Properties"]
    assert p["Engine"] == "aurora-postgresql"
    assert p["EngineVersion"].startswith("16.")
    assert int(p["EngineVersion"].split(".")[1]) >= 3  # 0 ACU needs >= 16.3
    assert p["EnableHttpEndpoint"] is True
    sc = p["ServerlessV2ScalingConfiguration"]
    assert sc["MinCapacity"] == 0 and sc["SecondsUntilAutoPause"] == 300
    assert p["BackupRetentionPeriod"] == 7
    assert app["AuroraInstance"]["Properties"]["PubliclyAccessible"] is False


def test_story_api_lambda_shape(app):
    p = app["StoryApiFunction"]["Properties"]
    assert p["PackageType"] == "Image"
    assert p["MemorySize"] == 2048 and p["Timeout"] == 900
    assert p["AutoPublishAlias"] == "live"
    assert "FunctionUrlConfig" not in p  # API Gateway is the only way in
    env = p["Environment"]["Variables"]
    assert env["AWS_LWA_INVOKE_MODE"] == "response_stream"
    assert env["TRACING_ENABLED"] == "false"  # D5: no Langfuse in prod
    assert not any(k.startswith("LANGFUSE") for k in env)
    assert env["LLM_PROVIDER"] == "anthropic"  # D4
    assert env["CHECKPOINTER"] == "none"
    actions = {a for st in p["Policies"][0]["Statement"] for a in
               (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])}
    assert {"rds-data:BeginTransaction", "rds-data:CommitTransaction",
            "rds-data:RollbackTransaction"} <= actions


def test_migrate_is_pretraffic_hook(app):
    dp = app["StoryApiFunction"]["Properties"]["DeploymentPreference"]
    assert dp["Hooks"]["PreTraffic"] == {"Ref": "MigrateFunction"}
    m = app["MigrateFunction"]["Properties"]
    assert str(m["FunctionName"]["Fn::Sub"]).startswith("CodeDeployHook_")
    assert app["MigrateFunction"]["Metadata"] == app["StoryApiFunction"]["Metadata"]  # one image


def test_api_streams_through_rest_api(app):
    api = app["StoryApi"]["Properties"]
    assert api["EndpointConfiguration"]["Type"] == "REGIONAL"
    assert api["DisableExecuteApiEndpoint"] is True
    for path in ("/", "/{proxy+}"):
        integ = api["DefinitionBody"]["paths"][path]["x-amazon-apigateway-any-method"][
            "x-amazon-apigateway-integration"]
        assert integ["type"] == "aws_proxy"
        assert integ["responseTransferMode"] == "STREAM"
        assert "/2021-11-15/functions/" in integ["uri"]["Fn::Sub"][0]
        assert integ["uri"]["Fn::Sub"][0].endswith("/response-streaming-invocations")


def test_edge_domains_and_spa(app):
    cert = app["Certificate"]["Properties"]
    assert cert["SubjectAlternativeNames"] == [{"Ref": "ApiDomain"}]
    assert cert["ValidationMethod"] == "DNS" and len(cert["DomainValidationOptions"]) == 2
    dist = app["SpaDistribution"]["Properties"]["DistributionConfig"]
    assert dist["Origins"][0]["S3OriginConfig"]["OriginAccessIdentity"] == ""
    assert "OriginAccessControlId" in dist["Origins"][0]
    assert {e["ErrorCode"] for e in dist["CustomErrorResponses"]} == {403, 404}
    assert app["ApiDomainName"]["Properties"]["EndpointConfiguration"]["Types"] == ["REGIONAL"]


def test_no_langfuse_resources(app):
    # D5: Langfuse runs locally only; nothing in AWS.
    assert not [k for k in app if "langfuse" in k.lower()]
    for fn in ("StoryApiFunction", "MigrateFunction"):
        env = app[fn]["Properties"]["Environment"]["Variables"]
        assert not any("LANGFUSE" in k for k in env)


def test_bootstrap_oidc_scoped_to_environment(boot):
    trust = boot["GitHubDeployRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    sub = trust["Condition"]["StringEquals"]["token.actions.githubusercontent.com:sub"]
    assert sub["Fn::Sub"] == "repo:${GitHubRepo}:environment:${GitHubEnvironment}"
    ecr = boot["ImageRepository"]["Properties"]
    assert ecr["ImageScanningConfiguration"]["ScanOnPush"] is True
    assert '"countNumber":10' in ecr["LifecyclePolicy"]["LifecyclePolicyText"].replace(" ", "")
    budget = boot["MonthlyBudget"]["Properties"]["Budget"]
    assert budget["BudgetLimit"]["Amount"] == {"Ref": "MonthlyBudgetUsd"}
    assert load("bootstrap.yaml")["Parameters"]["MonthlyBudgetUsd"]["Default"] == 25


def test_deploy_workflow_is_manual_only():
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((REPO / ".github/workflows/deploy.yml").read_text())
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML reads `on:` as True
    assert set(triggers) == {"workflow_dispatch"}
    assert wf["permissions"]["id-token"] == "write"
    assert all(j["environment"] == "production" for j in wf["jobs"].values())


@pytest.mark.skipif(not shutil.which("cfn-lint"), reason="cfn-lint not installed")
def test_cfn_lint_clean():
    r = subprocess.run(["cfn-lint", "template.yaml", "bootstrap.yaml"], cwd=INFRA,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
