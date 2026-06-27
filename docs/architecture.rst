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
``_data`` value owns the current extended shape. The facade owns a
``ConnectorFabric`` (created lazily when none is supplied), an optional
logger exposed as ``logging`` (falling back to the fabric's logger), a
declared-capability tuple, and an active-provider id available through
the read-only ``active_provider`` property.

.. code:: python

   from extended_data import ExtendedData
   from vendor_fabric.connectors import ConnectorFabric


   class VendorData(ExtendedData):
       def __new__(cls, value=None, *, fabric=None, logger=None,
                   capabilities=(), **fabric_kwargs):
           return object.__new__(cls)

       def __init__(self, value=None, *, fabric=None, logger=None,
                    capabilities=(), **fabric_kwargs):
           self._data = ExtendedData(value)
           self.fabric = fabric or ConnectorFabric(
               logger=logger, **fabric_kwargs)
           self.logging = logger or getattr(self.fabric, "logging", None)
           self._declared_capabilities = tuple(capabilities)
           self._capability_index = _index_capabilities(
               self._declared_capabilities)
           self._provider_capability_cache = {}
           self._providers = {}
           self._unavailable = {}
           self._active_provider = None

       @property
       def value(self):
           return self._data

       @property
       def active_provider(self):
           return self._active_provider

       def cast(self, value):
           self._data = ExtendedData(value)
           return self

This preserves the ``ExtendedData`` contract while letting the vendor
layer add provider-aware operations. Operations take the provider id as
their first positional argument and dispatch to the connector method
declared in the capability matrix, falling back to the active provider
when none is given:

.. code:: python

   from vendor_fabric.vendor_data import VendorData

   data = VendorData({"resource": "config"})
   data.open("aws")
   data.call("get_object", "aws", bucket="my-bucket", key="config.json")

   github = VendorData(fabric=fabric).open("github",
                                            github_owner="jbcom",
                                            github_repo="extended-data")
   github.call("get_repository_file", "github", file_path="README.md")

``VendorData`` also exposes two helpers for inspecting support: the
``capabilities(provider=None)`` method returns the full route set (or
one provider's routes), and ``capability_matrix()`` returns an
``operation -> provider -> route`` mapping. Use ``supports(provider,
operation)`` to query a single route. There is no ``__dir__`` override;
caller-side autocomplete reflects the static API plus whatever
``open_<provider>`` lambdas ``__getattr__`` synthesises.

Provider Capability Registry
----------------------------

Provider support should be declared on provider classes, not hardcoded
as a large repeated pass-through method matrix.

Use normal Python mechanisms:

- abstract base classes for common connector behavior
  (``vendor_fabric.base.ConnectorBase`` mixes in
  ``CapabilityProviderMixin``)
- a ``@capability(...)`` decorator on provider methods; decorated methods
  carry a ``_vendor_capabilities`` tuple of ``CapabilitySpec`` records
- ``CapabilityProviderMixin.__init_subclass__`` to collect decorated
  methods from the full method resolution order
- a ``capabilities`` mapping (``vendor_capabilities`` /
  ``vendor_capability_methods``) on provider classes for inspection and
  dispatch
- ``__getattr__`` on ``VendorData`` only as a thin convenience for the
  declared operations (``open_<provider>`` and the bare operation name)

Connectors may also declare a ``__supports__`` mapping on the class to
publish additional operation aliases that are not themselves decorated
methods (for example, mapping ``"get_file"`` to a concrete
``get_object`` method). ``VendorData.declare_supports`` attaches this
metadata; the ``_declared_supports`` helper reads it back. Use ordinary
metadata such as ``_vendor_capabilities`` on decorated methods and
``__supports__`` on provider classes.

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
