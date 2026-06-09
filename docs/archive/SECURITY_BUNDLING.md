# Security Bundling

This repository uses `runtime/config/core_dependency_manifest.json` as the source of truth for built-in runtime dependencies.

Core components are part of the product. They must be bundled locally, verified offline and documented with license and checksum metadata before release.

Optional external connectors are not allowed to become hidden startup requirements.
