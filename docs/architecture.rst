Architecture Plan
=================

This page records the local plan for ``vendor-fabric``. It is the source
of truth for provider and vendor architecture in this repository.

Boundary
--------

``vendor-fabric`` owns vendor behavior for the Extended Data stack:

- provider discovery and availability reporting
- vendor connector base classes
- provider-specific SDK adapters
- capability dispatch for files, secrets, identity, billing, messaging,
  and other vendor surfaces
- provider-backed sync operations
- Python SecretSync binding facade capabilities
- pytest support for vendor/provider tests

``extended-data`` owns base data primitives, containers, input handling,
logging, files, and generic workflows. ``agentic-fabric`` owns agent
runtime orchestration.

Runtime orchestration, crew discovery, framework runner selection, and
agent fixtures are not part of this package. Provider modules may expose
plain capability functions, schemas, and metadata; framework-specific
tool factories live in ``agentic-fabric``.

VendorData
----------

``VendorData`` is the public data facade for this package. It inherits
from ``extended_data.ExtendedData`` and extends that data behavior with
provider state.

The outer ``VendorData`` object owns provider context. Its internal
``_data`` value owns the current extended shape.

.. code:: python

   from extended_data import ExtendedData


   class VendorData(ExtendedData):
       def __init__(self, value=None, *, fabric=None, logger=None):
           self._data = ExtendedData(value)
           self.fabric = fabric
           self.logger = logger
           self.active_provider = None

       @property
       def value(self):
           return self._data

       def cast(self, value):
           self._data = ExtendedData(value)
           return self

This preserves the ``ExtendedData`` contract while letting the vendor
layer add provider-aware operations such as:

.. code:: python

   data = VendorData({"resource": "config"})
   data.open("aws")
   data.get_file("s3://bucket/key.json")
   data.get_file("github", owner="jbcom", repo="extended-data", path="README.md")
   data.sync_secret("vault", "aws", name="prod/api")

Provider Capability Registry
----------------------------

Provider support should be declared on provider classes, not hardcoded
as a large repeated pass-through method matrix.

Use normal Python mechanisms:

- ``typing.Protocol`` for structural provider contracts
- abstract base classes for common connector behavior
- a ``@capability(...)`` decorator on provider methods
- ``CapabilityProviderMixin.__init_subclass__`` to collect decorated
  methods from the full method resolution order
- a read-only ``capabilities`` mapping for inspection and dispatch
- ``__getattr__`` only as a thin convenience for declared capabilities
- ``__dir__`` so editor autocomplete can show available dynamic
  operations

Do not use custom dunder names such as ``__SUPPORTS__``. Use ordinary
metadata such as ``_capability_spec`` on decorated methods and
``capabilities`` on provider classes.

.. code:: python

   class AwsConnector(ConnectorBase):
       @capability("get_file", kind="files", aliases=("read_file",))
       def get_object(self, bucket: str, key: str):
           ...

``VendorData`` resolves operations by:

1. checking whether the caller supplied a provider id as the first
   argument
2. otherwise using the active provider opened by ``open(provider_id)``
3. otherwise finding a single available provider that supports the
   capability
4. raising a clear ambiguity or unavailable-feature error

Optional Dependencies
---------------------

Core imports stay lightweight. Provider extras install SDKs:

- ``vendor-fabric[aws]``
- ``vendor-fabric[google]``
- ``vendor-fabric[github]``
- ``vendor-fabric[slack]``
- ``vendor-fabric[vault]``
- ``vendor-fabric[zoom]``
- ``vendor-fabric[meshy]``

Unavailable providers should appear as unavailable in the registry with
install guidance. Normal consumer code should not need repeated import
juggling.

Secret Sync
-----------

SecretSync execution semantics belong to ``jbcom/secrets-sync``. This
repository owns the Python facade over the gopy binding, credential
handoff, redaction, Extended Data-shaped payloads, and provider
capability metadata. Native Python helpers in this package are
transitional compatibility scaffolding and should not grow into a second
pipeline implementation.

Testing Package
---------------

``pytest-vendor-fabric`` is a sibling package in this repository. It
should cover provider fixtures, optional dependency markers, registry
assertions, credential guards, mocked provider responses, and live E2E
opt-in controls.

Agent runtime fixtures belong in ``pytest-agentic-fabric``, not here.

Validation Contract
-------------------

Every public behavior needs tests and docs in the same change. Python
3.11, 3.12, 3.13, and 3.14 must pass without skipped missing
interpreters.
