# Runbook: Story Engine on AWS (spec 002, Option S)

What the human does to stand up, deploy, move data, roll back and restore the AWS
stack. Decisions (2026-10-16): Option S Serverless, region **us-east-1**, Anthropic API,
**Langfuse local only** (production runs with tracing off; nothing in AWS), Route 53
sub-zone NS-delegated from Cloudflare, API Gateway REST streaming, no nginx.

| File | What it is |
|---|---|
| `infra/bootstrap.yaml` | One-time stack: GitHub OIDC + deploy role, CloudFormation execution role, ECR, SAM artifact bucket, Route 53 zone, $25 budget. Deployed by you, never by CI. |
| `infra/template.yaml` | App stack (SAM): Aurora Serverless v2, story-api + migrate Lambdas (one image), API Gateway REST (STREAM), ACM, CloudFront + S3, DNS records, alarms. |
| `infra/samconfig.toml` | `prod` config, us-east-1, stack `story-engine-prod`. |
| `.github/workflows/deploy.yml` | Manual deploy and rollback (workflow_dispatch only). |
| `infra/scripts/dataapi_restore.py` | Loads CSV exports into Aurora over the Data API (T012). |

Cost guide: ~$12.60/month at 1,000 stories, ~$2.40 idle (the ~$2 plan figure plus
~$0.40 for the RDS-managed master secret in Secrets Manager, which the Data API needs).
LLM tokens are extra.

## 0. Before you start

- Branch `aws-app` (T013-T021) must be merged: the template builds `backend/Dockerfile.lambda`
  and expects the app to honour the runtime contract in section 9.
- A funded Anthropic API key (T004). The current key has no credit.
- Tools on your machine: AWS CLI v2, SAM CLI, Docker, `psql`.

## 1. AWS account (T007)

1. Create the AWS account (or a member account in an Organization). Use a dedicated email.
2. Root user: turn on MFA, create **no** access keys, then stop using root.
3. IAM Identity Center: create an admin user for yourself with MFA; sign in with
   `aws configure sso` (profile name e.g. `story-admin`, region `us-east-1`).
4. Check: `aws sts get-caller-identity --profile story-admin` shows the SSO role, not root.

## 2. Bootstrap stack (T008, T009, zone, budget)

```bash
aws cloudformation deploy --profile story-admin --region us-east-1 \
  --stack-name story-engine-bootstrap \
  --template-file infra/bootstrap.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides BudgetEmail=you@example.com
# If the account already has a GitHub OIDC provider:
#   CreateOidcProvider=false ExistingOidcProviderArn=arn:aws:iam::<acct>:oidc-provider/token.actions.githubusercontent.com
aws cloudformation describe-stacks --profile story-admin --stack-name story-engine-bootstrap \
  --query 'Stacks[0].Outputs' --output table
```

Keep the outputs: `DeployRoleArn`, `CfnExecutionRoleArn`, `ImageRepositoryUri`,
`ArtifactBucketName`, `HostedZoneId`, `HostedZoneNameServers`.

## 3. Secrets in SSM Parameter Store

CloudFormation cannot create SecureString parameters, so you add them by hand. The app
reads every parameter under `/story-engine/prod/` once per cold start; the names are the
`Settings` field names. Type the values at a prompt so they stay out of shell history.

```bash
put() { read -rsp "$1: " v; echo; aws ssm put-parameter --profile story-admin --region us-east-1 \
        --name "/story-engine/prod/$1" --type SecureString --value "$v" --overwrite >/dev/null; }
put ANTHROPIC_API_KEY
put JWT_SECRET_KEY          # e.g. paste the output of: openssl rand -base64 48
put SSLCOMMERZ_STORE_ID
put SSLCOMMERZ_STORE_PASS
```

No `LANGFUSE_*` parameters: tracing is off in production (D5). No database password:
the Lambdas reach Aurora through the Data API with the RDS-managed secret.

## 4. GitHub

1. Settings > Environments > New `production`; add yourself as required reviewer;
   deployment branches: `master` only.
2. Settings > Variables > Actions (repository variables):
   `AWS_DEPLOY_ROLE_ARN`, `AWS_CFN_EXEC_ROLE_ARN`, `ECR_REPOSITORY_URI`,
   `SAM_ARTIFACT_BUCKET` (from step 2) and `ALARM_EMAIL`.
3. Nothing else: there are no AWS keys to store (OIDC).

## 5. First app deploy, without touching live DNS

The app stack's ACM certificate validates by DNS. Until cutover, Cloudflare still serves
`storyteller.techvigilant.com` through the Tunnel, so validate with two CNAMEs in
Cloudflare instead of delegating the whole name.

1. Run the deploy (either way):
   - GitHub: Actions > Deploy (AWS) > Run workflow > `deploy` (on `master`), approve the
     environment; or
   - locally: `cd infra && sam build --config-env prod && sam deploy --config-env prod --profile story-admin --s3-bucket <ArtifactBucketName> --image-repositories StoryApiFunction=<uri> --image-repositories MigrateFunction=<uri> --role-arn <CfnExecutionRoleArn> --parameter-overrides Stage=prod BootstrapStackName=story-engine-bootstrap AlarmEmail=you@example.com`
2. While the stack sits on `Certificate CREATE_IN_PROGRESS`, open ACM (us-east-1) and copy
   the two validation CNAMEs (`_xxxx.storyteller…` and `_yyyy.api.storyteller…`) into
   Cloudflare DNS for `techvigilant.com`, **DNS only** (grey cloud). They do not clash with
   the Tunnel record. The certificate issues within minutes; the stack continues.
3. Confirm the SNS email for alarms.
4. **Create the schema**: on the first create no CodeDeploy deployment runs, so the
   PreTraffic migration does not run. Invoke migrate once by hand:
   ```bash
   aws lambda invoke --profile story-admin --region us-east-1 \
     --function-name CodeDeployHook_story-engine-prod-migrate \
     --payload '{"manual": true}' --cli-binary-format raw-in-base64-out /dev/stdout
   ```
   The first call may take ~15 s while Aurora resumes. Later deploys migrate automatically.
5. Before cutover run the workflow with `smoke` unticked: the name still points at the
   Tunnel, so `/health` on it tests the old server. Test the new stack by pinning the names:
   ```bash
   API_TARGET=$(aws apigateway get-domain-name --profile story-admin \
     --domain-name api.storyteller.techvigilant.com --query regionalDomainName --output text)
   curl --resolve api.storyteller.techvigilant.com:443:$(dig +short $API_TARGET | tail -1) \
     https://api.storyteller.techvigilant.com/health
   ```
   Same idea for the SPA with the CloudFront domain (`SpaDistributionId` output).
6. **Spike (T020)**: generate one story through the pinned API and check that events
   arrive one by one, not all at the end. If API Gateway returns 500 for streamed
   responses, Lambda Web Adapter's output is not accepted by REST STREAM: stop and use the
   fallback (function URL behind CloudFront, research.md R1).

## 6. Move the data (T012)

Aurora has no reachable port, so `pg_restore` cannot connect. Export CSV at home, load
through the Data API.

```bash
# On the home server, against the current Postgres. Stop writes first (maintenance window).
mkdir -p dump && for t in $(psql "$DATABASE_URL" -Atc \
  "select tablename from pg_tables where schemaname='public' and tablename<>'alembic_version'"); do
  psql "$DATABASE_URL" -c "\copy public.$t TO 'dump/$t.csv' WITH (FORMAT csv, HEADER, NULL '\N')"
done
psql "$DATABASE_URL" -Atc "select current_setting('server_version'), (select version_num from alembic_version)"

# On your machine, with the admin profile, after step 5.4 created the schema at the same
# alembic revision:
python infra/scripts/dataapi_restore.py --dir dump \
  --cluster-arn <AuroraClusterArn> --secret-arn <AuroraSecretArn> --dry-run
python infra/scripts/dataapi_restore.py --dir dump \
  --cluster-arn <AuroraClusterArn> --secret-arn <AuroraSecretArn>
```

The script loads parents before children, one transaction per table, casts every value
to the column's type (uuid, timestamptz, `vector(384)`, jsonb), and prints `OK`/`BAD` per
table with CSV vs Aurora row counts; exit code 1 on any mismatch. Run it once into an empty
schema; to retry, recreate the schema (or truncate the tables) first. Rehearse on a
copy before the real move.

## 7. Cutover: NS delegation in Cloudflare (T023, T041)

Rehearse first with a staging sub-zone (e.g. `staging-storyteller`), then:

1. Cloudflare DNS for `techvigilant.com`: delete the `storyteller` Tunnel record and the two
   ACM validation CNAMEs from step 5.2.
2. Add four `NS` records named `storyteller`, one per value in `HostedZoneNameServers`.
3. Wait for `dig NS storyteller.techvigilant.com +short` to show the AWS servers, then
   `curl https://api.storyteller.techvigilant.com/health` and open the site.
4. Keep the home server read-only for 7 days as fallback. Going back = put the Tunnel record
   back in place of the NS records.
5. SSLCommerz: the IPN URL becomes `https://api.storyteller.techvigilant.com/api/v1/payments/ipn`
   (`BACKEND_PUBLIC_URL`); test with the sandbox before setting `SslcommerzSandbox=false`.

## 8. Deploy, roll back, restore

**Deploy** (T030/T031): Actions > Deploy (AWS) > `deploy`. Checks CI is green on the
commit, builds one arm64 image, `sam deploy`; CodeDeploy runs migrate as the PreTraffic
hook, then moves the `live` alias. A failed migration or the errors alarm moves it back.
Then the SPA is built with `VITE_API_BASE_URL=https://api.storyteller.techvigilant.com`,
synced to S3, CloudFront invalidated, `/health` smoke-tested.
Automatic deploys on green `master` are **off** on purpose; turn them on only with the
human's approval (add a `workflow_run` trigger on `ci.yml`).

**Roll back the code** (T033): Actions > Deploy (AWS) > `rollback`, optional version number
(empty = the version before `live`). Or by hand:
`aws lambda update-alias --function-name story-engine-prod-story-api --name live --function-version <N>`.
The next deploy resets the alias to its own version. **The schema is not rolled back**:
migrations must stay backward compatible (expand, then contract in a later release). If a
migration must be undone, run `alembic downgrade` against the Data API from the migrate
image before moving the alias.

**Roll back the SPA**: re-run the deploy workflow on the previous good commit.

**Restore the database** (T035): Aurora keeps 7 days of point-in-time recovery. Restore
to a new scratch cluster, check it, then point the stack at it only if needed:
```bash
aws rds restore-db-cluster-to-point-in-time --profile story-admin \
  --source-db-cluster-identifier <cluster id> --db-cluster-identifier story-restore-test \
  --restore-to-time 2026-10-20T10:00:00Z --serverless-v2-scaling-configuration MinCapacity=0,MaxCapacity=2 \
  --db-subnet-group-name <subnet group> --enable-http-endpoint
aws rds create-db-instance --profile story-admin --db-instance-identifier story-restore-test-1 \
  --db-cluster-identifier story-restore-test --engine aurora-postgresql --db-instance-class db.serverless
```
Record the time it took (SC-005), then delete the scratch cluster. Deleting the stack
leaves a final snapshot (`DeletionPolicy: Snapshot`); deletion protection is on.

## 9. Runtime contract with the app (for T013-T021)

| Variable | Value | Meaning |
|---|---|---|
| `APP_ENV` | `production` | prod_guard on |
| `TRACING_ENABLED` | `false` | no Langfuse client; prod_guard must not demand `LANGFUSE_*` |
| `LLM_PROVIDER` | `anthropic` | D4 |
| `DB_BACKEND` | `dataapi` | use the Data API adapter; no `DATABASE_URL` |
| `AURORA_CLUSTER_ARN`, `AURORA_SECRET_ARN`, `AURORA_DATABASE` | from the stack | Data API target |
| `SSM_PARAMETER_PATH` | `/story-engine/prod/` | load SecureStrings into Settings at cold start |
| `CHECKPOINTER` | `none` | no Redis |
| `RUN_DEADLINE_SECONDS` | `600` | app deadline under the 900 s Lambda timeout |
| `FRONTEND_URL`, `BACKEND_PUBLIC_URL`, `BACKEND_CORS_ORIGINS` | site / api URLs | CORS and payment callbacks |
| `AWS_LWA_INVOKE_MODE` | `response_stream` (story-api), `buffered` (migrate) | Lambda Web Adapter |
| `AWS_LWA_PORT`, `AWS_LWA_READINESS_CHECK_PATH` | `8080`, `/health` | uvicorn port and readiness |
| `RUN_MODE` | `migrate` (migrate only) | mount only `POST /events` |
| `AWS_LWA_PASS_THROUGH_PATH` | `/events` (migrate only) | non-HTTP events arrive here |

Migrate handler (`RUN_MODE=migrate`, `POST /events`): run `alembic upgrade head` over the
Data API. If the event has `DeploymentId` and `LifecycleEventHookExecutionId` (CodeDeploy
hook), report `Succeeded` or `Failed` with `codedeploy:PutLifecycleEventHookExecutionStatus`;
a manual event (`{"manual": true}`) just returns the result.

## 10. Monitoring

Alarms (SNS email): story-api Errors >= 3 in 5 min (also the CodeDeploy rollback alarm),
Throttles >= 1, Duration p95 > 300 s, API Gateway 5XX >= 5 in 5 min, Aurora not paused for
6 h (minimum ACU > 0: the bill heads to ~$45/month). Logs keep 14 days. Budget emails at
80% actual and 100% forecast of $25.
