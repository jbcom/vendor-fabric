"""E2E test configuration.

Fixtures and CLI options are provided by pytest-vendor-fabric-agent plugin.
This file is kept for any project-specific customizations.
"""

from __future__ import annotations

# All fixtures come from pytest_vendor_fabric.agentic.plugin:
# - check_api_key
# - check_aws_credentials
# - simple_agent_config
# - simple_task_config
# - simple_crew_config
# - multi_agent_crew_config
# - crew_with_knowledge
# - temp_crew_dir
#
# CLI options:
# - --e2e: Enable E2E tests
# - --framework=<name>: Filter by framework
