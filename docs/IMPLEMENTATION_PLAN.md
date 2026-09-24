# Implementation Plan and Roadmap

This roadmap separates completed stabilization from the work recommended before broader unattended use.

## Phase 1 — Safety invariants (completed)

- Explicit-only application answers; sensitive questions never receive AI-generated answers.
- Required unanswered fields, failed uploads, and missing resumes fail closed.
- Positive confirmation required before recording a Dice application or webmail send.
- Exact resume selection; no “first profile” fallback.
- Negative-precedence C2C/W2/full-time classification.

Acceptance evidence: safety, email, matching, and decision-flow tests pass.

## Phase 2 — Transactional state and lifecycle (completed)

- SQLite ledger for jobs, application attempts, outreach messages, outbox reservations, caps, dedup keys, run sessions, and audit events.
- Capacity reserved before asynchronous work and released or completed transactionally.
- Outreach dedup written only after confirmed draft/send.
- Graceful queue drain, stale-reservation recovery, and UI shutdown.

Acceptance evidence: state concurrency and mocked outreach lifecycle/cap/dedup tests pass.

## Phase 3 — Configuration and matching integrity (completed)

- Atomic validated configuration writes.
- Absolute ATS threshold, must-have exclusion, distinct absolute confidence and relative rank.
- Cache invalidation and cache schema/model identity.
- User-only browser detection with no recursive profile scanning or shell invocation.
- Safe defaults for AI answer generation, automatic keyword learning, attachments, and email send mode.

Acceptance evidence: configuration, matching, import, and dependency checks pass.

## Phase 4 — Testable packaging and documentation (completed)

- Isolated `pytest` suite that does not collect live browser scripts.
- Mocked end-to-end decision and outreach integration coverage.
- Cross-platform setup and test scripts.
- Redacted example configuration and environment templates.
- GitHub-ready README, test report, release checklist, and expanded `.gitignore`.
- Categorized explicit-answer UI, bulk verified-mailbox bookkeeping, and Gmail/Zoho provider confirmation contracts.
- Gmail OAuth client/token selection, configuration validation, authorization workflow, and account-safe service caching.

Acceptance evidence: `scripts/test.ps1`/`scripts/test.sh` run compile, tests, imports, and dependency checks.

## Phase 5 — Controlled live certification (next)

Priority: P0 before unattended operation.

1. Build provider-specific test accounts and test recipients.
2. Execute the live checklists in `docs/TEST_REPORT.md` for Dice and each supported email provider.
3. Save selector fixtures (sanitized HTML only) and convert failures into deterministic tests.
4. Record browser, provider, OS, and date in a certification matrix.
5. Keep `draft` as the recommended mode until the selected provider passes certification.

Acceptance criteria:

- One controlled Dice application correctly records each terminal outcome.
- One draft with correct recipient/content/attachment is produced by every claimed provider.
- Send mode, if enabled, records success only after observable provider confirmation.
- No duplicate action occurs after restart or retry.

## Phase 6 — Continuous integration and quality gates (recommended)

Priority: P1 for public collaboration.

1. Add a CI workflow for Python 3.11 on Windows and Linux.
2. Run compile, pytest, import smoke, dependency audit, and secret scanning on every pull request.
3. Add formatter/linter configuration and gradually address existing style debt without large unrelated rewrites.
4. Add coverage reporting, targeting decision/state modules first.
5. Add a sanitized selector-fixture test suite for Dice and Nvoids parsers.

Acceptance criteria: required CI checks are green, no credentials are detected, and core safety/state coverage is at least 85%.

## Phase 7 — Adapter isolation and observability (recommended)

Priority: P1/P2 depending on usage volume.

1. Move Dice, Nvoids, and every email provider behind explicit adapter interfaces.
2. Replace free-form status strings with typed enums across UI, Excel, and SQLite.
3. Add correlation IDs and structured JSON logs with automatic secret/PII redaction.
4. Add retry categories: transient network, authentication required, selector changed, validation blocked, and permanent provider rejection.
5. Add a dead-letter/review queue instead of silently retrying terminal failures.

Acceptance criteria: adapters can be contract-tested without a browser, every action has a traceable lifecycle, and retries are bounded/idempotent.

## Phase 8 — Operational controls (recommended before scale)

Priority: P1 before high-volume use.

1. Add per-domain throttles, quiet hours, exponential backoff, and global kill switch.
2. Add preview/approval queues for applications and AI-generated outreach.
3. Add database backup/retention controls and an export-only cleanup command.
4. Add health indicators for authentication, browser/driver compatibility, API quota, disk locks, and stale reservations.
5. Document applicable site terms, anti-spam rules, privacy obligations, and retention policy for the operator’s jurisdiction.

Acceptance criteria: a user can preview, pause, recover, audit, and safely stop every external action.

## Suggested issue order

1. Run and document controlled live certification.
2. Add CI plus secret scanning.
3. Add selector fixtures and adapter contract tests.
4. Introduce typed statuses and structured/redacted logging.
5. Add approval queue and operational throttles.
6. Decide license and contribution policy before public release.
