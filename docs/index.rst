Vendor Fabric
=============

``vendor-fabric`` is the optional vendor integration package for the
Extended Data stack. It depends on ``extended-data>=8.4.0`` for the
polymorphic ``ExtendedData`` root, concrete containers, file sync,
inputs, logging, and workflow helpers, then adds API clients and native
vendor sync capabilities.

.. code:: bash

   pip install vendor-fabric
   pip install "vendor-fabric[github,slack]"
   pip install "vendor-fabric[aws,google,vault,secrets-sync]"

The base install exposes the connector catalog without requiring every
vendor SDK. Optional connectors report availability and install guidance
through the registry.

SecretSync capabilities live in ``vendor_fabric.secrets_sync`` as a
binding-backed facade over the ``secrets_sync`` import from
``secrets-sync-python-binding``. The canonical SecretSync runtime,
pipeline semantics, CLI, and gopy binding source live in
``jbcom/secrets-sync``.

.. toctree::
   :maxdepth: 2

   architecture
   pillars
   integrations/connectors
   secrets-sync/index
   testing
   ownership-map
   api/index
