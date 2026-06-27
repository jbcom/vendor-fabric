SecretSync Binding Facade
=========================

``vendor_fabric.secrets_sync`` is the Python integration facade for the
SecretSync runtime owned by ``jbcom/secrets-sync``. Pipeline execution,
merge, sync, validation, and diff semantics should come from that
binding-backed runtime. The vendor layer converts binding payloads into
Extended Data-friendly structures, handles redaction, and exposes
provider capability metadata for downstream consumers.

.. code:: bash

   pip install "vendor-fabric[secrets-sync]"
   pip install secrets-sync-python-binding

.. code:: python

   from vendor_fabric.secrets_sync import SyncOptions, get_targets, run_pipeline

   result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True, compute_diff=True))
   targets = get_targets("pipeline.yaml")

   assert "success" in result
   assert "targets" in targets

The same binding-backed facade powers non-agentic Python calls and the
``vendor-fabric-secrets-sync`` CLI. Provider-backed capability functions
and metadata are available from ``vendor_fabric.secrets_sync.tools`` and
re-exported from ``vendor_fabric.secrets_sync``:

.. code:: python

   from vendor_fabric.secrets_sync import TOOL_DEFINITIONS, SyncOptions, run_pipeline

   tool_names = [definition["name"] for definition in TOOL_DEFINITIONS]
   result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True))

Agent runtime loops, crew discovery, and framework runner selection live
in ``agentic-fabric`` and should call this API through ``VendorData``
capabilities.

The upstream binding distribution is expected to install the
``secrets_sync`` import. If it is not yet available from PyPI, build and
install it from ``jbcom/secrets-sync`` before running SecretSync execution
paths. Local upstream references to ``secretssync`` are rename debt, not
the contract consumed here.

Capability Boundary
-------------------

- ``extended-data>=8.4.0`` owns generic data containers,
  ``ExtendedData``, local sync primitives, redaction, file decoding, and
  workflow composition.
- ``jbcom/secrets-sync`` owns the canonical SecretSync execution engine,
  Go runtime, CLI, pipeline semantics, GitHub Action, and gopy binding
  source.
- ``vendor-fabric`` owns the Python facade over those bindings, credential
  discovery, provider activation, redaction, data shaping, and capability
  metadata.
- ``vendor-fabric`` exposes provider capability functions and metadata
  over this native Python API. ``agentic-fabric`` owns the agent runtime
  that turns those capabilities into framework-visible tools.

Reconciliation Note
-------------------

This package still contains transitional Python pipeline helper classes
used by local tests and compatibility paths. They are not the target
architecture. Do not expand them into a long-term fork of SecretSync
pipeline semantics; move public execution through the binding facade
instead.
