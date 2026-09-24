# Reliability delivery notes — 2026-09-15

## Implemented

The current update adds OS-backed launch/workbook locks; backed-up transactional reliability migrations; a Tk-owned worker callback queue; bounded automatic email queue; shutdown waiting; durable outcome/export tasks; optional versioned email approval with restricted attachment snapshots; read-only provider observations; checkpoint-based recovery selection; and many-to-many Dice question/job links.

`PreparedMessage`, `ProviderHealth`, `RunItemCheckpoint` and `UiEvent` are small supporting contracts. Existing provider send methods remain in place; an adapter supplies approved content and frozen formatting. No external email/application action is performed by an export retry, health check, answer save or approval button.

Approved versions persist sensitive message content in the operational database and snapshot directory. These local artifacts and migration backups must not be committed or included in diagnostic bundles. Attachment snapshots receive a restricted current-user ACL on Windows; permission failures block preparation. The preview displays text and supported font settings without scripts or remote resources. It is not a pixel-identical preview of every provider's web editor.

## Safety rules

- Only pending/preparing checkpoints are candidates for recovery. Missing account/file evidence blocks Nvoids recovery. Uncertain boundaries stay for human review; elapsed time does not make them safe to retry.
- Email outcome and its export task commit together. Failed exports do not roll back successful provider work. Primary Dice outcome records can commit a per-job export task with the attempt.
- Email exports preserve independently changed phone status. Ambiguous workbook keys stop export.
- Provider receipts are retained when supplied. Their presence is not permission to repeat an action.
- Exact-email review remains off unless explicitly enabled. Existing unattended processing retains its validation, exclusions, attachment and capacity checks.

## Automated validation

Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1` from the repository. It compiles Python, runs offline pytest tests, imports both bots and checks installed dependency compatibility.

Latest run: **123 tests and 3 subtests passed**; compilation, both-application import smoke checks and dependency checks passed. Five existing SWIG deprecation warnings remain. No live mail, application submission or production workbook mutation was used as a test.

Added synthetic tests exercise process-lock exclusion and crash release, migration backup and rollback, locked-file export recovery, idempotent Dice/Nvoids exports, immutable attachment/content versions, account/exclusion changes, repeated questions across jobs, read-only health, queue capacity, resources retained during unfinished shutdown, closed-window event queues and stale/cancelled readiness checks. Existing regression and hidden-Tk tests remain part of the suite.

## Not yet fully accepted

This is an incremental implementation, **not certification that the entire proposed plan is finished**:

1. Readiness checks now cover common mail controls and compose-scoped uploads, and redundant Gmail/Zoho compose and Dice login pauses were removed. Some legacy provider-specific sleeps and Outlook Web upload/confirmation behavior remain; they need targeted fixtures and separately approved live checks before replacement.
2. Recovery is conservative. Automatic reconciliation of uncertain items against provider/application evidence is not implemented; these items remain blocked. Historical checkpoint-free records cannot safely resume. Existing auxiliary/learning databases retain their previous schema management.
3. The event pump routes worker `root.after` callbacks and log updates. A complete audit/migration of every legacy direct Tk read/write and every child-dialog lifecycle is still required. New dialog layout/keyboard behavior needs manual verification at 125–150% Windows scaling.
4. Dice's legacy full-frame export paths use atomic locked writes, while primary application outcomes have durable per-job export tasks. Not every legacy scrape/export/delete path has been converted to a transactional per-record export operation; cross-process read/modify/write stress coverage must be expanded.
5. The mail preview preserves plain text and API/Desktop font settings, not the exact visual rendering of all web editors. Provider account evidence can be unavailable; review/recovery fails closed in that case. Health information is a dialog, not a continuously monitored account dashboard.
6. There is no automated provider/account reconciliation UI, comprehensive crash-injection suite around every boundary, or live provider certification in this delivery. Queue/shutdown coverage should be extended to prolonged producer/provider contention.

Do not remove these limitations merely because the offline suite passes. Finish the listed checks before treating every acceptance criterion as met. Live mail or application tests require separate explicit permission and confirmed targets. Nothing was pushed to GitHub.
