Testing
=======

``pytest-vendor-fabric`` is the supported pytest plugin for projects
that test code built on Vendor Fabric.

.. code:: bash

   pip install pytest-vendor-fabric

The plugin registers the ``e2e`` marker, the ``--e2e`` CLI option, and
seven fixtures:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Fixture / hook
     - Purpose
   * - ``mock_logger``
     - A ``MagicMock(spec=Logging)`` for connector tests that need a
       logger without configuring a real one.
   * - ``base_connector_kwargs``
     - Common kwargs for connector construction:
       ``{"logger": mock_logger, "from_environment": False}``.
   * - ``anthropic_api_key``
     - Returns ``ANTHROPIC_API_KEY`` from the environment, or ``None``.
   * - ``skip_without_anthropic``
     - Skips the test when ``ANTHROPIC_API_KEY`` is unset.
   * - ``check_api_key``
     - Skips the test when ``ANTHROPIC_API_KEY`` is unset (alias of
       ``skip_without_anthropic`` for live Anthropic E2E tests).
   * - ``check_aws_credentials``
     - Skips the test when neither ``AWS_ACCESS_KEY_ID`` nor
       ``AWS_PROFILE`` is set.
   * - ``pytest_collection_modifyitems``
     - Adds a ``skip`` marker to every ``e2e``-marked test when
       ``--e2e`` is not passed.

.. code:: python

   def test_connector(base_connector_kwargs):
       assert base_connector_kwargs["from_environment"] is False


   def test_live_provider(check_api_key):
       assert check_api_key is None


   def test_mocked_connector(mock_logger):
       assert mock_logger.logger is not None

E2E tests are skipped unless ``--e2e`` is passed. They may call paid
provider APIs and require provider credentials:

.. code:: bash

   pytest --e2e

The repository's ``providers`` tox environment installs optional SDK extras
for AWS, Google, GitHub, Slack, Vault, and SecretSync unit tests:

.. code:: bash

   tox -e providers

This gate is part of CI and CD release verification. It does not enable live
E2E tests; those still require ``--e2e`` and credentials.

Agent runtime fixtures, framework-specific agent execution, and runner
selection live in ``pytest-agentic-fabric``. This plugin stays focused on
provider-facing test support.
