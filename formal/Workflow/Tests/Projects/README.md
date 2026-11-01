# Aiken test projects

Runnable Aiken projects for manual workflow and generated-output inspection.
These projects can support several property scenarios. Check-specific harnesses
and pinned regression inputs remain in their existing scenario folders.

- [vault-demo](vault-demo/README.md): normal and deliberately faulty
  unparameterized vaults for inspecting UP-001 sources and results.

Build a project's blueprint before invoking `plutus-upv run`. Generated
blueprints/build caches are local; workflow run files stay under `formal/output/`.
