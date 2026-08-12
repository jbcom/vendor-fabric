# Vendor Fabric

`vendor-fabric` is the optional vendor integration layer for the
Extended Data Python stack. It depends on `extended-data>=8.4.0` for the
polymorphic `ExtendedData` root, concrete containers, local file sync, inputs,
logging, and workflow utilities, then adds
adapter-registered API clients and vendor-backed sync capabilities.

Documentation: [jonbogaty.com/vendor-fabric](https://jonbogaty.com/vendor-fabric/)

```bash
pip install vendor-fabric
pip install "vendor-fabric[github,slack]"
pip install "vendor-fabric[aws,google,vault,secrets-sync]"
pip install secrets-sync-python-binding
pip install pytest-vendor-fabric
```

The base install keeps vendor SDKs out of the environment. Connector metadata
is available even when an optional SDK is absent:

```python
from vendor_fabric import get_connector_info, list_connector_info

print(get_connector_info("github")["available"])
print(list_connector_info(include_unavailable=True))
```

Construct connectors through the registry or `ConnectorFabric`:

```python
from vendor_fabric import ConnectorFabric

fabric = ConnectorFabric(inputs={"GITHUB_TOKEN": "..."})
github = fabric.get_connector("github")
```

Unavailable features report install guidance instead of requiring callers to
wrap their own imports.

## Command-line interface

The `vendor-fabric` command exposes the same Extended Data-returning connector
surface as the Python registry. Connector credentials come from environment
variables, the AWS default credential chain, or SecretSync configuration; the
CLI has no credential flags.

```bash
# Discover connectors and their callable data surface.
vendor-fabric list
vendor-fabric list --category cloud --available-only
vendor-fabric info github
vendor-fabric methods github
vendor-fabric methods github --json
vendor-fabric credentials
vendor-fabric credentials github --json

# Provider commands use the connector method name and --name value arguments.
vendor-fabric github list_repositories --type-filter public
vendor-fabric meshy text3d_generate --prompt "a low-poly observatory" --wait false

# The generic spelling remains available for scripts that select a provider.
vendor-fabric call github list_repositories --type-filter public --json

# SecretSync is also routed through the unified command.
vendor-fabric secrets-sync validate --config pipeline.yaml
vendor-fabric secrets-sync info --config pipeline.yaml
vendor-fabric secrets-sync pipeline --config pipeline.yaml --dry-run --diff
```

`methods` prints each callable signature, including required and optional
arguments. Argument names accept either underscores or hyphens. Values are
decoded as JSON first, then as booleans, integers, floats, or strings. Use JSON
for structured arguments:

```bash
vendor-fabric anthropic create_message \
  --model claude-sonnet-4-20250514 \
  --max-tokens 1024 \
  --messages '[{"role":"user","content":"Summarize this change"}]'
```

Sensitive method inputs are never accepted as literal command-line values.
Use the generated `--<name>-env`, `--<name>-file`, or `--<name>-stdin` form so
the value does not land in shell history. These source forms also work for
non-sensitive structured or multiline inputs. File and environment contents
receive the same JSON-first decoding as ordinary arguments.

```bash
# APP_SECRET contains the value; only its variable name appears in history.
vendor-fabric aws create_secret --name app/api --secret-value-env APP_SECRET

# Read a Google Workspace initial password from standard input.
security find-generic-password -w -s workspace-bootstrap \
  | vendor-fabric google create_user \
      --primary-email new.user@example.com \
      --given-name New \
      --family-name User \
      --password-stdin

# Keep a large request payload in a permission-controlled file.
vendor-fabric anthropic create_message \
  --model claude-sonnet-4-20250514 \
  --max-tokens 1024 \
  --messages-file request-messages.json
```

### Credential sources

`vendor-fabric credentials [connector]` reports these names without reading or
printing their values. Optional SDK extras remain discoverable even when they
are not installed.

| Connector | Credential and configuration sources |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `aws` | Standard boto3 credential/config chain; optional `EXECUTION_ROLE_ARN` and `ROLE_SESSION_NAME` |
| `cursor` | `CURSOR_API_KEY` |
| `github` | `GITHUB_TOKEN`, `GITHUB_OWNER`; optional `GITHUB_REPO` and `GITHUB_BRANCH` |
| `google` | `GOOGLE_SERVICE_ACCOUNT` (service-account JSON) |
| `jules` | `JULES_API_KEY` |
| `meshy` | `MESHY_API_KEY` |
| `slack` | `SLACK_TOKEN`, `SLACK_BOT_TOKEN` |
| `vault` | `VAULT_ADDR`; `VAULT_TOKEN` or `VAULT_ROLE_ID` plus `VAULT_SECRET_ID`; optional `VAULT_NAMESPACE` and `VAULT_APPROLE_PATH` |
| `zoom` | `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ZOOM_ACCOUNT_ID` |

### Connector commands

Every command below is available through both
`vendor-fabric <connector> <method>` and
`vendor-fabric call <connector> <method>`. Run
`vendor-fabric methods <connector>` for its argument signature.

| Connector | Commands |
|---|---|
| `anthropic` | `create_message`, `get_available_models`, `get_model`, `list_models` |
| `aws` | `add_user_to_group`, `classify_accounts`, `classify_aws_accounts`, `copy_object`, `copy_secrets_to_s3`, `create_account_assignment`, `create_bucket`, `create_secret`, `create_sso_group`, `create_sso_user`, `delete_account_assignment`, `delete_object`, `delete_secret`, `delete_secrets_matching`, `find_buckets_by_name`, `get_accounts`, `get_bucket_features`, `get_bucket_location`, `get_bucket_sizes`, `get_bucket_tags`, `get_caller_account_id`, `get_controltower_accounts`, `get_identity_store_id`, `get_json_object`, `get_object`, `get_organization_accounts`, `get_organization_units`, `get_secret`, `get_sso_instance_arn`, `get_sso_user`, `label_aws_account`, `label_aws_accounts`, `list_account_assignments`, `list_objects`, `list_permission_sets`, `list_s3_buckets`, `list_secrets`, `list_sso_groups`, `list_sso_users`, `load_secrets_by_prefix`, `preprocess_aws_organization`, `preprocess_organization`, `put_json_object`, `put_object`, `update_secret` |
| `cursor` | `get_agent_conversation`, `get_agent_status`, `launch_agent`, `list_agents`, `list_models`, `list_repositories` |
| `github` | `build_workflow`, `build_workflow_job`, `build_workflow_step`, `create_python_ci_workflow`, `execute_graphql`, `get_org_member`, `get_repository`, `get_repository_file`, `get_team`, `get_users_with_verified_emails`, `list_org_members`, `list_repositories`, `list_teams` |
| `google` | `add_group_member`, `add_iam_binding`, `batch_enable_services`, `create_group`, `create_kms_key`, `create_kms_keyring`, `create_or_update_group`, `create_or_update_user`, `create_project`, `create_service_account`, `create_user`, `delete_project`, `disable_project_billing`, `disable_service`, `enable_service`, `find_inactive_projects`, `get_bigquery_billing_dataset`, `get_billing_account`, `get_billing_account_iam_policy`, `get_gke_cluster`, `get_group`, `get_iam_policy`, `get_license_summary`, `get_org_policy`, `get_organization`, `get_organization_id`, `get_project`, `get_project_billing_info`, `get_project_iam_users`, `get_pubsub_resources_for_project`, `get_user`, `list_available_licenses`, `list_billing_account_projects`, `list_billing_accounts`, `list_compute_instances`, `list_enabled_services`, `list_folders`, `list_gke_clusters`, `list_group_members`, `list_groups`, `list_kms_keyrings`, `list_org_units`, `list_projects`, `list_pubsub_subscriptions`, `list_pubsub_topics`, `list_service_accounts`, `list_sql_instances`, `list_storage_buckets`, `list_users`, `list_workspace_groups`, `list_workspace_users`, `move_project`, `set_billing_account_iam_policy`, `set_iam_policy`, `set_org_policy`, `setup_billing_export`, `update_project_billing_info`, `update_user` |
| `jules` | `add_user_response`, `approve_plan`, `create_session`, `get_session`, `list_sessions`, `list_sources`, `resume_session` |
| `meshy` | `apply_animation`, `image3d_generate`, `retexture_model`, `rig_model`, `text3d_generate` |
| `slack` | `get_bot_channels`, `list_conversations`, `list_usergroups`, `list_users`, `send_message` |
| `vault` | `generate_aws_credentials`, `get_aws_iam_role`, `get_secret`, `list_aws_iam_roles`, `list_secrets`, `read_secret` |
| `zoom` | `get_meeting`, `get_user`, `list_meetings`, `list_users` |

The CLI deliberately does not expose raw HTTP/SDK clients, sessions,
resources, authentication helpers, connector lifecycle methods, duplicate
agent-tool wrappers, Meshy persistence/webhook internals, SecretSync's
transitional Python helpers, or connector methods whose public return contract
is a raw `bool`, `str`, `None`, or SDK object. Those APIs either bypass the
Extended Data serialization/redaction boundary, duplicate a command above, or
need an application lifecycle rather than a one-shot shell command.

SecretSync access is exposed through a binding-backed facade:

```python
from vendor_fabric.secrets_sync import ProviderSession, SyncOptions, get_targets, run_pipeline

result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True))
targets = get_targets("pipeline.yaml")

print(result["success"])
print(targets["targets"])

session = ProviderSession(
    vault_address="https://vault.example.com",
    vault_token=vault_token,
    aws_region="us-east-1",
    aws_access_key_id=aws_credentials.access_key,
    aws_secret_access_key=aws_credentials.secret_key,
    aws_session_token=aws_credentials.token,
)
run_pipeline("pipeline.yaml", SyncOptions(dry_run=True), provider_session=session)
```

`vendor-fabric` consumes the `secrets_sync` import from
`secrets-sync-python-binding` and shapes those payloads into Extended Data
values. The canonical SecretSync runtime, CLI, pipeline semantics, and gopy
binding source live in `jbcom/secrets-sync`.

Connector and sync payloads are `ExtendedData` values at the boundary. Dict,
list, string, tuple, and set payloads are concrete extended subclasses, so code
can use normal container operations and extended-data methods without import
juggling.

Testing support lives in the separately published `pytest-vendor-fabric`
package. It provides connector fixtures, E2E controls, and credential guards
without forcing test-only dependencies into the runtime package.
