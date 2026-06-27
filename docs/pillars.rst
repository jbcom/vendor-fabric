Pillars
=======

These pillars define what belongs in ``vendor-fabric``.

Providers Are Data Extensions
-----------------------------

Every provider should feel like an extension of ``ExtendedData``, not a
separate utility island. Provider inputs and outputs should be promoted
into extended containers wherever doing so helps callers transform,
redact, export, sync, or inspect results.

Capability-Driven Dispatch
--------------------------

The fabric should dispatch by capabilities declared by providers.
Repeated hardcoded pass-through methods should be avoided when a
provider can declare support once and the facade can route generically.

Optional Means Discoverable
---------------------------

Optional provider dependencies are normal for this package. Missing
extras should be visible through registry state and clear install
guidance, not through unexpected import failures in ordinary package
imports.

Sync Is A First-Class Capability
--------------------------------

File sync and secret sync are provider capabilities. They should compose
``extended-data`` primitives for merge, redaction, encoding, decoding,
and file handling while delegating provider IO to the right connector.

Agent Runtime Is Out Of Scope
-----------------------------

Agent orchestration, crew discovery, framework selection, and agent
runner fixtures belong in ``agentic-fabric``. This package can expose
provider-backed tools, but it should not own agent runtimes.

Tests Define Provider Contracts
-------------------------------

Unit tests, mocked provider tests, optional dependency tests, and opt-in
E2E tests are part of the public contract. ``pytest-vendor-fabric``
should make it straightforward for downstream projects to test code
built on this package.
