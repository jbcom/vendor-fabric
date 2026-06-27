# SecretSync Alignment

This file locks the intended SecretSync boundary for `vendor-fabric`.

## Canonical Stack

1. `jbcom/secrets-sync` owns the Go runtime, CLI, pipeline semantics, GitHub
   Action, and gopy binding source.
2. `jbcom/vendor-fabric` consumes that binding from Python.
3. `jbcom/agentic-fabric` turns vendor capabilities into framework-visible
   tools and runtime behavior.

## Binding Contract

- PyPI distribution: `secrets-sync-python-binding`
- Python import/module: `secrets_sync`
- Expected top-level binding surface includes functions such as
  `ValidateConfig`, `RunPipeline`, `DryRun`, `GetConfigInfo`, `GetTargets`, and
  `GetSources`, plus `DefaultSyncOptions`, `SyncOptions`, `SyncResult`, and
  operation/output-format constants.
- Local upstream scaffolding may still say `secretssync`; treat that as rename
  debt, not the contract.

## This Repository's Role

- Expose `vendor_fabric.secrets_sync` as the Python integration surface.
- Convert between `ExtendedData`/Python-friendly structures and the underlying
  `secrets_sync` binding contract.
- Handle credential discovery, provider activation, redaction, config loading,
  and capability metadata around the binding-backed runtime.
- Keep SecretSync access additive to `VendorData`, not separate from it.

## Required Direction

- Treat the Go/binding layer as the canonical execution engine for merge, diff,
  validation, and sync behavior.
- Prefer thin adapters, typed facades, and capability metadata over a second
  full implementation of pipeline semantics in Python.
- Keep AI-framework wrappers out of this repository; expose plain capabilities
  that `agentic-fabric` can wrap.

## Forbidden Drift

- Do not let `vendor_fabric.secrets_sync` become a long-term fork of SecretSync
  pipeline logic.
- Do not invent a different binding package name or import path downstream.
- Do not claim the gopy/binding layer was retired if Python still depends on
  SecretSync runtime behavior.
- Do not import CrewAI, LangChain, LangGraph, Strands, or MCP wrapper types
  into SecretSync modules here.

## Current Reconciliation Note

This repository currently contains native Python SecretSync modules. Treat that
as divergence to reconcile toward a binding-backed facade rather than as the
target architecture.
