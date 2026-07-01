Ownership Map
=============

``vendor-fabric`` owns external API connector integrations and
vendor-backed sync capabilities for the Extended Data stack. Runtime
agent orchestration belongs in ``agentic-fabric``; this repository owns
provider-backed capability functions and metadata that ``agentic-fabric``
can call through ``VendorData``.

In This Package
---------------

+-----------------------------------+-----------------------------------+
| Surface                           | Current owner                     |
+===================================+===================================+
| Connector registry and adapter    | ``vendor_fabric.registry``        |
| metadata                          |                                   |
+-----------------------------------+-----------------------------------+
| Optional-dependency machinery     | ``vendor_fabric._optional``       |
| (extra lookups, install guidance, |                                   |
| availability probes)              |                                   |
+-----------------------------------+-----------------------------------+
| Shared connector base classes     | ``vendor_fabric.base``            |
+-----------------------------------+-----------------------------------+
| Capability declaration mechanism  | ``vendor_fabric.capabilities``    |
| (``@capability`` decorator,       |                                   |
| ``CapabilityProviderMixin``)      |                                   |
+-----------------------------------+-----------------------------------+
| Connector fabric                  | ``vendor_fabric.connectors``      |
+-----------------------------------+-----------------------------------+
| VendorData facade with capability | ``vendor_fabric.vendor_data``     |
| dispatch                          |                                   |
+-----------------------------------+-----------------------------------+
| Vendor CLI                        | ``vendor_fabric.cli``             |
+-----------------------------------+-----------------------------------+
| Cloud parameter adapters          | ``vendor_fabric.cloud_params``    |
+-----------------------------------+-----------------------------------+
| Payload surface introspection     | ``vendor_fabric.surface``         |
| for connector data methods        |                                   |
+-----------------------------------+-----------------------------------+
| AWS, Google, GitHub, Slack,       | ``vendor_fabric.*``               |
| Vault, Zoom, Anthropic, Cursor,   |                                   |
| and Meshy clients                 |                                   |
+-----------------------------------+-----------------------------------+
| Provider capability functions     | ``vendor_fabric.*.tools``         |
+-----------------------------------+-----------------------------------+
| SecretSync Python binding facade  | ``vendor_fabric.secrets_sync``    |
+-----------------------------------+-----------------------------------+
| Provider-backed capability        | ``vendor_fabric.*.tools``         |
| metadata for downstream runtimes  |                                   |
+-----------------------------------+-----------------------------------+

Outside This Package
--------------------

+-----------------------+--------------------------+----------------------------------------------------------------------+
| Surface               | Current repository       | Install target                                                       |
+=======================+==========================+======================================================================+
| Base data primitives, | ``jbcom/extended-data``  | ``extended-data``                                                    |
| generic containers,   |                          |                                                                      |
| local file sync,      |                          |                                                                      |
| inputs, logging, and  |                          |                                                                      |
| workflows             |                          |                                                                      |
+-----------------------+--------------------------+----------------------------------------------------------------------+
| Agent crew discovery, | ``jbcom/agentic-fabric`` | ``agentic-fabric``                                                   |
| runner selection,     |                          |                                                                      |
| runtime adapters, and |                          |                                                                      |
| agent test fixtures   |                          |                                                                      |
+-----------------------+--------------------------+----------------------------------------------------------------------+
| Standalone Go         | ``jbcom/secrets-sync``   | ``go install github.com/jbcom/secrets-sync/cmd/secrets-sync@latest`` |
| SecretSync binary, if |                          |                                                                      |
| retained              |                          |                                                                      |
+-----------------------+--------------------------+----------------------------------------------------------------------+

SecretSync pipeline semantics, the Go runtime, CLI, GitHub Action, and
gopy binding source belong in ``jbcom/secrets-sync``. The Python facade
belongs here because its useful Python shape is a vendor-backed sync
capability over Vault, AWS, S3, and future providers. Agent framework
packages, runtime adapters, and framework tool factories belong in
``agentic-fabric``; they compose vendor capabilities rather than being
provider implementations.
MCP bridges are agent-facing transports and belong in ``agentic-fabric``.
