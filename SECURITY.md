# Security Policy

## Supported versions

Security fixes are made on the current `main` branch and released through
release-please. Supported Python releases are 3.11 through 3.14.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting flow for this repository.
Do not open a public issue for a suspected credential exposure, authentication
weakness, unsafe workflow, or provider integration vulnerability.

Include a minimal reproduction, affected version or commit, impact, and any
safe mitigation you have identified. Do not include production credentials,
tokens, customer data, or exploit payloads in the report.

We will acknowledge reports, assess severity, coordinate a fix, and publish a
security advisory when appropriate. Contributors are credited only with their
permission.

## Repository security boundaries

- Provider SDKs remain optional and unavailable extras provide install guidance.
- Diagnostics must redact credential material before logging errors or traces.
- Live provider E2E tests require explicit `--e2e` opt-in and credentials.
- Pull requests from arbitrary forks run without secrets, write tokens, or
  deployment/publishing permissions.
- Release, PyPI, and Pages jobs execute only from trusted release source.
