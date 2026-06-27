Internal API
============

These modules back the public surface but are hidden from the
auto-generated toctree because their names start with an underscore or
are CLI entry shims. They are importable and stable; this page keeps
them reachable from the docs navigation.

- :mod:`vendor_fabric._optional` — optional-dependency machinery
  (extra lookups, install guidance, availability probes) used by every
  connector.
- :mod:`vendor_fabric.secrets_sync._binding` — the SecretSync Python
  binding facade delegating to the ``secrets_sync`` import from
  ``secrets-sync-python-binding``.
- :mod:`vendor_fabric.secrets_sync.__main__` — the
  ``python -m vendor_fabric.secrets_sync`` entry shim.

.. toctree::
   :hidden:

   ../apidocs/vendor_fabric/vendor_fabric._optional
   ../apidocs/vendor_fabric/vendor_fabric.secrets_sync._binding
   ../apidocs/vendor_fabric/vendor_fabric.secrets_sync.__main__