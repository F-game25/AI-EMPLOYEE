# Offline Wheelhouse

Packaged enterprise builds populate this directory with platform-specific wheels:

`runtime/wheelhouse/<platform>/<python-version>/`

Startup and first-boot verification must not download core dependencies in offline mode. Build jobs should install from this wheelhouse with `--no-index --find-links`.
