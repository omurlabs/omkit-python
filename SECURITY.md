# Security policy

> Status: pre-1.0. omkit ships primitives that downstream services
> rely on for tenant isolation, encryption-at-rest, auth, and rate
> limiting. Bugs that break any of those guarantees are in scope even
> while the API is unstable.

## Supported versions

Pre-1.0 we support the latest minor release line only. Security fixes
are issued as a patch on that line and announced in
[`CHANGELOG.md`](CHANGELOG.md).

| Version | Supported |
|---|---|
| 0.1.x | yes (current) |
| < 0.1 | no |

## Reporting a vulnerability

**Do not open a public GitHub issue.**

Report privately via
[GitHub Security Advisories](https://github.com/omurlabs/omkit-python/security/advisories/new).
This routes directly to the maintainer team and stays private until
disclosure is coordinated.

If GitHub is unavailable, email `vadim+omkit-security@yuzi.co` with
subject `[omkit-python security]`. PGP-encrypted reports are accepted;
key fingerprint will be published here once minted.

Please include:

- omkit version (`pip show omkit` output).
- Python version (`python --version`).
- A minimal reproduction (smallest viable program / SQL / config).
- Affected module — `crypto/`, `data/`, `dbpool`, `encryption`,
  `kms/`, `platform/`, `providers/`, `security/`, `sessions`,
  `tenant`, `transport/`, `valkey*`, or another.
- Impact assessment (what an attacker can read / write / corrupt /
  bypass).
- Suggested fix, if you have one.

## Response SLO

| Event | Target |
|---|---|
| Acknowledgement | within 5 business days |
| Triage and severity assessment | within 10 business days |
| Fix on the supported release line for severity ≥ high | within 30 days of triage |
| Fix on the supported release line for severity ≥ medium | within 90 days of triage |
| Public advisory + CVE (when applicable) | coordinated with reporter |

Pre-1.0 we operate as a small team. We will keep reporters informed
in writing and will not silently close reports.

## Scope

**In scope:**

- The `omkit` package on PyPI (`pip install omkit`) and any submodule
  imported at runtime by a downstream service.
- Cross-tenant leakage — any helper in `tenant.py`, `dbpool.py`, or
  `transport/` that fails to scope a query / cache / metric to the
  current tenant, or a code path that lets a request observe another
  tenant's data.
- Encryption envelope integrity — `crypto/` and `encryption.py`. IV
  reuse, AAD mishandling, downgrade between AES-256-GCM and the
  retired Fernet shape, key-material logging, plaintext leakage into
  errors / spans / metrics.
- KMS integration — `kms/`. DEK persistence outside the documented
  lifecycle, plaintext-key logging, wrong-key-id silent fallback.
- Auth / sessions / role gates — `sessions.py`, `security/`. Role
  escalation, session-token leakage, role-gate predicates that ignore
  the role list.
- Quota / rate-limit bypass — `quota.py`.
- Request / job context propagation — `jobqueue/`, `eventbus.py`,
  `events.py`. Cross-tenant context bleed across asyncio tasks or
  background workers.
- Dependency vulnerabilities reported by `pip-audit` that affect a
  runtime path.
- Documentation that misrepresents a security guarantee — a README
  or docstring claim that does not match runtime behaviour.

**Out of scope:**

- Postgres, Valkey/Redis, streaq, or other infrastructure consumed
  by omkit. Report those upstream.
- Vulnerabilities that require attacker access to the consumer's
  database, KMS, or service credentials — those are deployment
  concerns the consumer owns.
- Denial-of-service via unbounded payload size, unbounded fanout, or
  client-controlled cost. These are operator-tunable; consumers must
  put limits at their ingress.
- Test fixtures and the `scripts/` tree. Not on the runtime path.

## Coordinated disclosure

Default disclosure window: **90 days from triage**, extendable by
mutual agreement. We will publish a Security Advisory on GitHub
naming the reporter (with their consent), the affected versions,
the fix version, and the impact.

If a fix is not feasible within the window, we will disclose the
issue publicly anyway with documented mitigations. Silent fixes are
not the policy.

## Cross-SDK envelope

omkit and [`omkit-go`](https://github.com/omurlabs/omkit-go) share a
wire-compatible AES-256-GCM envelope and a shared job-queue envelope
(see `tests/test_crypto_envelope_interop.py` and the matching tests
in omkit-go). Reports of envelope incompatibility, version-downgrade,
or a code path that accepts an envelope it cannot verify are in scope
on **both** SDKs — please file on whichever SDK exhibits the bug;
we'll cross-link.

## Acknowledgements

Security researchers credited in past advisories will be listed here
once we have any to publish.
