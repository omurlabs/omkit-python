# Contributing to omkit

> Status: pre-1.0 — the public Python API may break across minor
> versions. Breaking changes are marked in
> [`CHANGELOG.md`](CHANGELOG.md). The v0.x → v0.y bump is the
> semver-major signal on the v0 line.

omkit is the Python-side SDK in the omurlabs SaaS-scaffolding pair
([`omkit-go`](https://github.com/omurlabs/omkit-go) is the Go
counterpart). The two share a wire-compatible AES-256-GCM envelope
and a shared job-queue envelope.

## Contribution stance

**Open with guardrails.** We welcome:

- Bug fixes against documented behaviour.
- Documentation fixes and additions.
- Tests (unit and integration).
- New modules that fit the SaaS-scaffolding shape (multi-tenant
  isolation, encryption-at-rest, observability, async eventing).

For these we accept PRs without prior discussion.

We require **maintainer pre-approval before code lands** for:

- Breaking changes to any public module — even on the v0 line.
  These bump the minor version.
- Changes to the AES-256-GCM envelope or to job-queue envelope
  serialisation. Both must stay wire-compatible with `omkit-go`.
- New cross-SDK contracts (anything that the Go side also has to
  understand on the wire).
- Anything that touches `omkit/crypto/`, `omkit/encryption.py`,
  `omkit/kms/`, or the tenant-isolation primitives in
  `omkit/tenant.py` / `omkit/dbpool.py`.

For these, please open an issue first (or a draft PR) so we can
align on the design before code review.

## Getting started

### Prerequisites

- Python 3.12+ (CI matrix is 3.12 + 3.14).
- Docker (or Podman) for the integration test compose stack —
  Postgres 16 + Valkey 8.

### Local setup

```bash
git clone https://github.com/omurlabs/omkit-python.git
cd omkit-python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,tracing,metrics]"
pytest
mypy omkit
```

Integration tests that touch Postgres / Valkey expect
`TEST_POSTGRES_DSN`, `TEST_REDIS_ADDR`, `VALKEY_URL`. The
[`scripts/test-with-postgres.sh`](scripts/test-with-postgres.sh)
helper brings up an ephemeral docker-compose stack and runs the suite
against it.

## Coding standards

| Concern | Tool | Scope |
|---|---|---|
| Tests | `pytest` | `tests/` |
| Type-check | `mypy` | `omkit/` |
| Coverage | `pytest --cov=omkit` | `omkit/` |
| Vuln scan | `pip-audit --strict` | declared deps |
| Secrets | `gitleaks` | full history |

CI runs all of the above. mypy `--strict` is aspirational; the
codebase ships `py.typed` but predates strict typing — tighten
gradually rather than blocking on a full annotation pass.

### Style notes

- Public modules document *why*, not *what*. Identifiers should
  already describe what.
- Every helper that touches tenant data takes the tenant scope
  explicitly; there is no implicit fallback in runtime paths.
- `structlog` is the structured-logging surface. No module logs to a
  global logger; consumers inject a logger or rely on the
  per-process default.
- Async-first: the public Python API is `async def`. Sync wrappers
  are added only when an adapter genuinely needs them.

## Workflow

### Branch + PR shape

- Branch per feature; one feature per PR.
- PR title: `<area>: <imperative description>` (e.g.
  `crypto: rotate AES-256-GCM key id`).
- Every PR includes test changes, or an explicit `no-test-needed:`
  rationale in the PR body.
- Breaking changes use `!` after the type/scope and bump the minor
  version (e.g. `feat(crypto)!: change envelope serialisation`).

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

- `feat(area): …` — new behaviour
- `fix(area): …` — bug fix
- `docs: …`, `chore: …`, `ci: …`, `test: …`, `refactor: …`,
  `perf: …`, `build: …`, `revert: …`

Body explains *why*. The diff shows *what*. Reference issues when
relevant.

### Tests

```bash
pytest -v --tb=short
pytest --cov=omkit --cov-report=term-missing
```

Unit tests live in `tests/`. Integration tests that need Postgres /
Valkey are guarded by the `TEST_POSTGRES_DSN` / `TEST_REDIS_ADDR` /
`VALKEY_URL` envs and skip cleanly when unset.

## Cross-SDK envelope

When changing `omkit/crypto/`, `omkit/encryption.py`, or any
`omkit/jobqueue/` envelope:

1. Mirror the change in
   [`omkit-go`](https://github.com/omurlabs/omkit-go) in the same
   release cycle.
2. Update `tests/test_crypto_envelope_interop.py` and the matching
   Go-side interop test.
3. Call out the wire-compat impact in the PR body. We do not ship
   envelope-incompatible releases.

## Releases

Tag-driven, OIDC-published to PyPI via the `pypi-publish.yml`
workflow. Most contributors don't need to know it; the maintainer
cuts releases. Push a `v*` tag to fire publish; rc tags
(`v*-rc.*`) route to TestPyPI.

## Reporting bugs and asking questions

- **Bug reports**: open an issue against this repo.
- **Security vulnerabilities**: do not open a public issue. See
  [`SECURITY.md`](SECURITY.md) for the private disclosure path.

## License

By contributing you agree your contributions are licensed under
[Apache-2.0](LICENSE) (inbound = outbound). No CLA is required.
