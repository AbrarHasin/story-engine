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


FUNCTIONS = ("StoryApiFunction", "StoryGraphFunction", "MigrateFunction")
SECRETS = ("ANTHROPIC_API_KEY", "JWT_SECRET_KEY", "SSLCOMMERZ_STORE_ID", "SSLCOMMERZ_STORE_PASS")


def _env(app, fn):
    return app[fn]["Properties"]["Environment"]["Variables"]


def _statements(app, fn, conditional=False):
    out = []
    for pol in app[fn]["Properties"]["Policies"]:
        if "Statement" in pol:
            out += pol["Statement"]
        elif conditional and "Fn::If" in pol:
            out += pol["Fn::If"][1]["Statement"]
    return out


def _actions(stmts):
    return {a for st in stmts for a in (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])}


def _subs(resource):
    return {r["Fn::Sub"] for r in (resource if isinstance(resource, list) else [resource])}


def test_story_api_lambda_shape(app):
    # ADR split-api-graph: small, buffered, every route except generation
    p = app["StoryApiFunction"]["Properties"]
    assert p["PackageType"] == "Image"
    assert p["MemorySize"] == 512 and p["Timeout"] == 30
    assert p["AutoPublishAlias"] == "live"
    assert "ReservedConcurrentExecutions" not in p  # never starved by a generation burst
    assert "FunctionUrlConfig" not in p  # API Gateway is the only way in
    env = p["Environment"]["Variables"]
    assert env["RUN_ROLE"] == "api"
    assert env["AWS_LWA_INVOKE_MODE"] == "buffered"
    assert env["CHECKPOINTER"] == "none"
    assert app["StoryApiFunction"]["Metadata"]["DockerBuildTarget"] == "api"
    assert {"rds-data:BeginTransaction", "rds-data:CommitTransaction",
            "rds-data:RollbackTransaction"} <= _actions(_statements(app, "StoryApiFunction"))


def test_story_graph_lambda_shape(app):
    p = app["StoryGraphFunction"]["Properties"]
    assert p["PackageType"] == "Image"
    assert p["MemorySize"] == 2048 and p["Timeout"] == 900
    assert p["ReservedConcurrentExecutions"] == {"Ref": "ReservedConcurrency"}
    assert load("template.yaml")["Parameters"]["ReservedConcurrency"]["Default"] == 20
    assert p["AutoPublishAlias"] == "live"
    assert "FunctionUrlConfig" not in p
    env = p["Environment"]["Variables"]
    assert env["RUN_ROLE"] == "graph"
    assert env["AWS_LWA_INVOKE_MODE"] == "response_stream"
    assert env["RUN_DEADLINE_SECONDS"] == "600"  # under the 900 s Lambda timeout
    assert env["SEMANTIC_CACHE_ENABLED"] == {"Ref": "SemanticCacheEnabled"}
    assert app["StoryGraphFunction"]["Metadata"]["DockerBuildTarget"] == "graph"
    assert {"rds-data:BeginTransaction", "rds-data:CommitTransaction",
            "rds-data:RollbackTransaction"} <= _actions(_statements(app, "StoryGraphFunction"))


def test_llm_settings_on_both_functions(app):
    for fn in ("StoryApiFunction", "StoryGraphFunction"):
        env = _env(app, fn)
        assert env["TRACING_ENABLED"] == "false"  # D5: no Langfuse in prod
        assert env["LLM_PROVIDER"] == {"Ref": "LlmProvider"}  # D4, default anthropic
        for var, param in (("MODEL_ROUTER", "ModelRouter"), ("MODEL_WRITER", "ModelWriter"),
                           ("MODEL_SYNTHESIZER", "ModelSynthesizer")):
            assert env[var] == {"Ref": param}


def test_migrate_is_pretraffic_hook_of_both(app):
    for fn in ("StoryApiFunction", "StoryGraphFunction"):
        dp = app[fn]["Properties"]["DeploymentPreference"]
        assert dp["Hooks"]["PreTraffic"] == {"Ref": "MigrateFunction"}
    assert app["StoryApiFunction"]["Properties"]["DeploymentPreference"]["Alarms"] == [
        {"Ref": "StoryApiErrorsAlarm"}]
    assert app["StoryGraphFunction"]["Properties"]["DeploymentPreference"]["Alarms"] == [
        {"Ref": "StoryGraphErrorsAlarm"}]
    m = app["MigrateFunction"]["Properties"]
    assert str(m["FunctionName"]["Fn::Sub"]).startswith("CodeDeployHook_")
    assert m["ReservedConcurrentExecutions"] == 1  # the two hooks never migrate in parallel
    assert m["ImageConfig"]["Command"] == ["app.migrate.handler"]
    env = m["Environment"]["Variables"]
    assert not any(k.startswith("AWS_LWA_") for k in env) and "RUN_MODE" not in env
    # one Dockerfile (backend/Dockerfile.lambda), three targets
    targets = {}
    for fn in FUNCTIONS:
        md = app[fn]["Metadata"]
        assert md["Dockerfile"] == "Dockerfile.lambda" and md["DockerContext"] == "../backend"
        targets[fn] = md["DockerBuildTarget"]
    assert targets == {"StoryApiFunction": "api", "StoryGraphFunction": "graph",
                       "MigrateFunction": "migrate"}


def test_env_matches_app_contract(app):
    # Names from backend/.env.lambda.example (branch aws-app).
    for fn in FUNCTIONS:
        env = _env(app, fn)
        assert env["DB_BACKEND"] == "dataapi" and env["TRACING_ENABLED"] == "false"
        assert env["DATAAPI_RESOURCE_ARN"] == {"Fn::GetAtt": ["AuroraCluster", "DBClusterArn"]}
        assert env["DATAAPI_SECRET_ARN"] == {
            "Fn::GetAtt": ["AuroraCluster", "MasterUserSecret.SecretArn"]}
        assert env["DATAAPI_DATABASE"] == "storyengine"
        assert not any(k.startswith("AURORA_") for k in env)
        assert "DATABASE_URL" not in env
        for secret in SECRETS:
            assert secret not in env  # SSM only, never env


def test_ssm_paths_and_least_privilege(app):
    api_env, graph_env = _env(app, "StoryApiFunction"), _env(app, "StoryGraphFunction")
    assert api_env["SSM_PARAMETER_PATH"] == {"Fn::Sub": "/story-engine/${Stage}/shared/"}
    assert graph_env["SSM_PARAMETER_PATH"] == {
        "Fn::Sub": "/story-engine/${Stage}/shared/,/story-engine/${Stage}/graph/"}
    assert "SSM_PARAMETER_PATH" not in _env(app, "MigrateFunction")

    def ssm_resources(fn):
        stmts = [st for st in _statements(app, fn) if "ssm:GetParametersByPath" in _actions([st])]
        return set().union(*(_subs(st["Resource"]) for st in stmts)) if stmts else set()

    api_res, graph_res = ssm_resources("StoryApiFunction"), ssm_resources("StoryGraphFunction")
    for res in (api_res, graph_res):  # the path itself (GetParametersByPath) and names under it
        assert any(r.endswith(":parameter/story-engine/${Stage}/shared") for r in res)
        assert any(r.endswith(":parameter/story-engine/${Stage}/shared/*") for r in res)
    # only story-graph may read the LLM key (graph/ANTHROPIC_API_KEY)
    assert any(r.endswith(":parameter/story-engine/${Stage}/graph/*") for r in graph_res)
    assert not [r for r in api_res if "/graph" in r or r.endswith("${Stage}/*")]
    assert ssm_resources("MigrateFunction") == set()
    for fn in ("StoryApiFunction", "StoryGraphFunction"):
        kms = next(st for st in _statements(app, fn) if st["Action"] == "kms:Decrypt")
        assert kms["Condition"]["StringEquals"]["kms:ViaService"] == {
            "Fn::Sub": "ssm.${AWS::Region}.amazonaws.com"}
    assert "codedeploy:PutLifecycleEventHookExecutionStatus" in _actions(
        _statements(app, "MigrateFunction"))


def test_llm_parameters_and_bedrock_only_on_graph_when_enabled():
    t = load("template.yaml")
    params = t["Parameters"]
    assert params["LlmProvider"]["Default"] == "anthropic"
    for p in ("ModelRouter", "ModelWriter", "ModelSynthesizer"):
        assert params[p]["Default"] == "claude-haiku-5-5"
    assert params["UseBedrock"]["Default"] == "false"
    assert t["Conditions"]["UseBedrock"] == {"Fn::Equals": [{"Ref": "UseBedrock"}, "true"]}
    res = t["Resources"]
    policies = res["StoryGraphFunction"]["Properties"]["Policies"]
    conditional = [p for p in policies if "Fn::If" in p]
    assert len(conditional) == 1
    cond, granted, otherwise = conditional[0]["Fn::If"]
    assert cond == "UseBedrock" and otherwise == {"Ref": "AWS::NoValue"}
    assert set(granted["Statement"][0]["Action"]) == {
        "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}
    unconditional = _actions(_statements(res, "StoryGraphFunction"))
    assert not [a for a in unconditional if a.startswith("bedrock:")]
    for fn in ("StoryApiFunction", "MigrateFunction"):
        assert "bedrock" not in str(res[fn]["Properties"]["Policies"])


def _integ(api, path, method):
    return api["DefinitionBody"]["paths"][path][method]["x-amazon-apigateway-integration"]


def test_api_gateway_splits_by_route(app):
    api = app["StoryApi"]["Properties"]
    assert api["EndpointConfiguration"]["Type"] == "REGIONAL"
    assert api["DisableExecuteApiEndpoint"] is True
    paths = api["DefinitionBody"]["paths"]
    # generation (and its CORS preflight) -> story-graph, STREAM
    assert set(paths["/api/v1/stories/generate"]) == {"post", "options"}
    for method in ("post", "options"):
        integ = _integ(api, "/api/v1/stories/generate", method)
        assert integ["type"] == "aws_proxy"
        assert integ["responseTransferMode"] == "STREAM"
        uri = integ["uri"]["Fn::Sub"]
        assert "/2021-11-15/functions/" in uri[0]
        assert uri[0].endswith("/response-streaming-invocations")
        assert uri[1] == {"AliasArn": {"Ref": "StoryGraphFunction.Alias"}}
    # every other path -> story-api, BUFFERED (no transfer mode, classic invocations URI)
    for path in ("/", "/api", "/api/v1", "/api/v1/stories", "/{proxy+}"):
        integ = _integ(api, path, "x-amazon-apigateway-any-method")
        assert integ["type"] == "aws_proxy"
        assert integ.get("responseTransferMode", "BUFFERED") == "BUFFERED"
        assert integ["timeoutInMillis"] <= 29000
        uri = integ["uri"]["Fn::Sub"]
        assert "/2015-03-31/functions/" in uri[0] and uri[0].endswith("/invocations")
        assert uri[1] == {"AliasArn": {"Ref": "StoryApiFunction.Alias"}}
    assert set(paths) == {"/", "/api", "/api/v1", "/api/v1/stories",
                          "/api/v1/stories/generate", "/{proxy+}"}
    # each alias may be invoked by API Gateway; story-graph only on its route
    assert app["StoryApiInvokePermission"]["Properties"]["FunctionName"] == {
        "Ref": "StoryApiFunction.Alias"}
    graph_perms = [v["Properties"] for k, v in app.items()
                   if v["Type"] == "AWS::Lambda::Permission"
                   and v["Properties"]["FunctionName"] == {"Ref": "StoryGraphFunction.Alias"}]
    assert {p["SourceArn"]["Fn::Sub"].split("/")[-5] for p in graph_perms} == {"POST", "OPTIONS"}
    assert all(p["SourceArn"]["Fn::Sub"].endswith("/api/v1/stories/generate") for p in graph_perms)


def test_alarms_per_function(app):
    for prefix, fn in (("StoryApi", "StoryApiFunction"), ("StoryGraph", "StoryGraphFunction")):
        for kind in ("Errors", "Throttles", "DurationP95"):
            alarm = app[f"{prefix}{kind}Alarm"]["Properties"]
            assert alarm["AlarmActions"] == [{"Ref": "AlarmTopic"}]
            name = "story-api" if prefix == "StoryApi" else "story-graph"
            assert alarm["Dimensions"][0]["Value"] in (
                {"Ref": fn}, {"Fn::Sub": "${AWS::StackName}-" + name})
    assert app["StoryApiDurationP95Alarm"]["Properties"]["Threshold"] < 30000
    assert app["StoryGraphDurationP95Alarm"]["Properties"]["Threshold"] < 600000


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
    for fn in FUNCTIONS:
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
