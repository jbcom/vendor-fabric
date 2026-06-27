Testing
=======

``pytest-vendor-fabric`` is the supported pytest plugin for projects
that test code built on Vendor Fabric.

.. code:: bash

   pip install pytest-vendor-fabric

The plugin provides connector fixtures, credential guards, framework
selection for provider tool tests, and E2E controls.

.. code:: python

   def test_connector(base_connector_kwargs):
       assert base_connector_kwargs["from_environment"] is False


   def test_live_provider(check_api_key):
       assert check_api_key is None

E2E tests are skipped unless ``--e2e`` is passed. Framework-specific
selections use ``--framework``:

.. code:: bash

   pytest --e2e --framework=crewai
   pytest --e2e --framework=langgraph
   pytest --e2e --framework=strands

The repository's ``providers`` tox environment installs optional SDK extras
for AWS, Google, GitHub, Slack, Vault, MCP, and LangChain-backed unit tests:

.. code:: bash

   tox -e providers

This gate is part of CI and CD release verification. It does not enable live
E2E tests; those still require ``--e2e`` and credentials.

Agent runtime fixtures live in ``pytest-agentic-fabric``. This plugin
stays focused on provider-facing test support.
