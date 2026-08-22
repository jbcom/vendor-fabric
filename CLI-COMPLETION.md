# Vendor Fabric CLI completion

## Result

The package now has one coherent CLI over the complete registry connector
surface:

- `vendor-fabric list`, `info`, and `methods` retain their existing roles.
- `methods` now includes callable signatures and works for built-in connectors
  even when the connector's optional SDK extra is not installed.
- `vendor-fabric call <connector> <method>` remains the generic automation
  spelling.
- `vendor-fabric <connector> <method>` is a direct alias for each of
  `anthropic`, `aws`, `cursor`, `github`, `google`, `jules`, `meshy`, `slack`,
  `vault`, and `zoom`.
- `vendor-fabric credentials [connector]` reports credential/configuration
  environment names and default-chain notes without reading or printing
  values.
- `vendor-fabric secrets-sync ...` delegates to the existing binding-backed
  SecretSync parser, including its help and exit codes. The standalone
  `vendor-fabric-secrets-sync` entry point remains supported.
- Dynamic method arguments are signature-validated before connector creation.
  Structured values keep the existing JSON-first decoding behavior.
- `--<name>-env`, `--<name>-file`, and `--<name>-stdin` source values without
  putting them in process arguments. Credential-like and secret-like inputs
  are rejected when passed as literal argv values.
- GitHub constructor context follows the existing fabric environment pattern:
  `GITHUB_OWNER` is required and `GITHUB_REPO`/`GITHUB_BRANCH` are optional;
  `GITHUB_TOKEN` is still read by the connector and never forwarded as a CLI
  constructor argument. AWS keeps the boto3 default chain and honors the
  established optional role environment names.

The package README documents every top-level command, every credential source,
safe argument sourcing, SecretSync routing, and every connector method exposed
by the CLI. A test now compares the README connector-command table to the live
Extended Data method surface so future drift fails visibly.

## Connector survey

The CLI deliberately follows `vendor_fabric.surface.connector_data_methods`.
That is the repository's tested public serialization boundary: a callable must
be public, belong to the connector rather than `ConnectorBase`/`InputProvider`,
and advertise an Extended Data payload.

| Connector | Exposed CLI surface | Deliberately not made commands |
|---|---|---|
| Anthropic | Message creation plus local/API model discovery | `count_tokens`, `validate_model`, recommendation/availability helpers return primitive Python values; raw response/error helpers are transport internals. |
| AWS | 45 payload operations across caller identity, Secrets Manager, S3, Organizations, and IAM Identity Center | boto3 sessions/clients/resources, role-assumption objects, retry configuration, and primitive-returning deletes are SDK/lifecycle APIs. Module-level CodeDeploy and `tools.py` functions are secondary wrappers rather than registry-connector methods. |
| Cursor | Agent launch/status/conversation and repository/model listing | `add_followup` returns `None`; availability and request helpers are primitive/transport APIs. It should first gain an Extended Data connector contract if it needs CLI exposure. |
| GitHub | Repository/file reads, organization members, teams, GraphQL, verified-email data, and workflow payload builders | Branch objects and file/team mutations currently return SDK objects, `bool`, or `None`. Exposing them would bypass the existing data/redaction boundary. Duplicate `tools.py` wrappers were not given a second command namespace. |
| Google | 58 Extended Data operations across Workspace, Cloud Resource Manager, billing, IAM, services, KMS, storage, SQL, GKE, and Pub/Sub | Credential/service client factories and primitive-returning user/group removals are application or SDK plumbing. Duplicate `tools.py` wrappers were omitted. |
| Jules | Source and session listing/creation/read, plan approval, user response, and resume | HTTP/model parsing, header, and diagnostic helpers are transport internals. All public Extended Data session operations are included. |
| Meshy | High-level text/image-to-3D, rigging, animation, and retexturing | Lower-level functional create/get/refine/poll modules duplicate the connector workflows. Persistence repositories, vector stores, asset jobs, and webhook handlers require longer-lived local/application state and are not one-shot registry connector commands. |
| Slack | Messaging, bot-channel discovery, users, user groups, and conversations | Block-formatting helpers are local presentation utilities; `_call_api` is raw transport; `tools.py` duplicates the connector and adds a history wrapper not present in the connector contract. |
| Vault | KV list/read/search and AWS secrets-engine role/credential payloads | Raw client/authentication/token lifecycle and primitive-returning `write_secret` are outside the Extended Data CLI boundary. `tools.py` duplicates list/read operations. |
| Zoom | User and meeting list/get operations | Access-token/header helpers expose authentication plumbing; create/remove user currently return `bool`/`None` and should gain Extended Data result contracts before CLI exposure. |
| SecretSync | Binding CLI `validate`, `info`, and `pipeline` | Transitional Python stores, graph, merge, file, and bundle helpers are not a second pipeline CLI; canonical semantics stay in the binding-backed parser. |

This is intentionally not a raw reflection CLI. SDK clients, authentication
material, transport functions, lifecycle methods, duplicate tool wrappers, and
primitive/raw-object returns remain Python-only until they have a stable
Extended Data payload contract suitable for redaction and machine output.

## Tests and mutation evidence

- Focused CLI suite: 44 passed after the README guard was added.
- Full package suite on Python 3.11, 3.12, and 3.13: 1,452 passed and 6 expected
  skips on each interpreter before the final documentation guard (the guard was
  then covered again in the Python 3.14 provider run).
- Final Python 3.14 provider/coverage suite: 1,453 passed, 6 expected skips,
  90.34% total coverage.
- pytest plugin suite: 9 passed.
- Ruff: clean across both packages, tests, and examples.
- Dedicated mypy environment: clean across 74 source files.
- Sphinx `-W -E`: clean.
- Both package sdists and wheels built successfully with the declared
  hatchling backend; the built vendor wheel was imported outside the checkout
  and its `credentials github --json` path ran successfully. Console-script and
  connector entry points were present in the wheel.

The following deliberate mutants were each observed failing, then restored:

1. accepted a literal password argument;
2. dropped the Zoom provider alias;
3. removed built-in method discovery when an optional extra is absent;
4. collapsed SecretSync's delegated failure exit code to zero;
5. stopped forwarding `GITHUB_OWNER` from the environment;
6. removed Anthropic `get_model` from the README command table.

## Environment notes for the next agent

- Direct `uv` execution in this sandbox could not use the normal uv cache, and
  an isolated build attempted to resolve hatchling over blocked DNS. The same
  declared hatchling backend was already installed locally, so offline direct
  backend builds were used successfully instead.
- The pre-existing `.tox/py314` interpreter is a Python 3.14.4 free-threaded
  build without pytest. Reusing the standard-ABI provider site-packages with it
  fails in native `regex`/Hypothesis modules before repository code imports.
  The fully provisioned non-free-threaded Python 3.14 provider environment was
  used for the package/coverage gate. This is tox environment provisioning,
  not a CLI failure.
- Generated `.venv`, `docs/_build`, and `dist` directories from verification
  were moved out of the worktree after evidence collection to the recoverable
  `/private/tmp/vendor-fabric-cli-verification-artifacts-20260812` holding
  directory; they are ignored and not part of the committed change.
- No external APIs were called, no credential values were printed, and no E2E
  tests requiring paid services were run.

## Commits

- `f88aae5 docs: specify unified connector CLI`
- `e35ce27 test: define complete connector CLI behavior`
- `c9a5a02 feat: unify connector command routing`

The README drift guard and this completion report are committed after those
three implementation commits.
