# Changelog

## v0.1.2 — 2026-05-18

### Changed

- **packaging**: Bump `Development Status` classifier `3 - Alpha → 4 - Beta`.
- **packaging**: Add `Programming Language :: Python :: 3.14` classifier to match CI matrix.

## v0.1.1 — 2026-05-18

### Fixed

- **packaging**: Drop the legacy `License :: OSI Approved :: Apache Software License` classifier. Modern setuptools rejected it as conflicting with the PEP 639 `license = "Apache-2.0"` SPDX expression, which blocked sdist builds and caused the v0.1.0 PyPI publish to fail. No code changes vs v0.1.0.

## v0.1.0 — 2026-05-17

### Changed

- **encryption**: Replace Fernet with AES-256-GCM. Wire-compatible envelope shared with `omkit-go` (see `omkit.crypto` and `tests/test_crypto_envelope_interop.py`).

### Added

- `pypi-publish.yml` workflow using PyPI Trusted Publishing.
- README module index and quickstart.

### Internal

- `mypy --strict`-clean baseline; best-effort tracing propagator setup.
- CI matrix py3.12 + py3.14; actions pinned then later un-pinned to version tags.

## v0.0.2 — 2026-05-17

Initial release.
