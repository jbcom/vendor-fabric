Ownership Map
=============

``vendor-fabric`` owns external API connector integrations and
vendor-backed sync capabilities for the Extended Data stack. Runtime
agent orchestration belongs in ``agentic-fabric``; this repository only
owns provider-backed tools that ``agentic-fabric`` can call through
``VendorData``.

In This Package
---------------

+-----------------------------------+-----------------------------------+
| Surface                           | Current owner                     |
+===================================+===================================+
| Connector registry and adapter    | ``vendor_fabric.registry``        |
| metadata                          |                                   |
+-----------------------------------+-----------------------------------+
| Shared connector base classes     | ``vendor_fabric.base``            |
+-----------------------------------+-----------------------------------+
| Connector fabric                  | ``vendor_fabric.connectors``      |
+-----------------------------------+-----------------------------------+
| Vendor CLI                        | ``vendor_fabric.cli``             |
+-----------------------------------+-----------------------------------+
| MCP bridge                        | ``vendor_fabric.mcp``             |
+-----------------------------------+-----------------------------------+
| AWS, Google, GitHub, Slack,       | ``vendor_fabric.*``               |
| Vault, Zoom, Anthropic, Cursor,   |                                   |
| and Meshy clients                 |                                   |
+-----------------------------------+-----------------------------------+
| Vendor tool adapters              | ``vendor_fabric.*.tools``         |
+-----------------------------------+-----------------------------------+
| Native vendor secret and file     | ``vendor_fabric.secrets_sync``    |
| sync                              |                                   |
+-----------------------------------+-----------------------------------+
| Provider-backed tool capabilities | ``vendor_fabric.*.tools``         |
| for agents                        |                                   |
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

SecretSync for Python belongs here because its useful Python shape is a
vendor-backed sync capability over Vault, AWS, S3, and future providers.
Agent framework packages belong in ``agentic-fabric``; they compose
vendor capabilities rather than being provider implementations.
