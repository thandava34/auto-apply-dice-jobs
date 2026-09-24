# Desktop upgrade plan (8 GB RAM)

The existing Tkinter applications remain the supported entry points. Preserve local settings,
resumes, workbooks, and history. Migrate components incrementally; do not replace working
provider adapters without contract tests and an account-specific live trial.

## Delivery sequence

1. Reliability: Dice cookie-banner acceptance; stricter login confirmation; specific
   question matching and post-fill validation; richer unanswered-question context;
   consistent cycle accounting; email preflight and structured batch results.
2. Low-memory operation: optional keyword-only matching, bounded browser concurrency,
   visible resource/limit controls. No additional local model is required.
3. Operator workflow: failed-only retries, queue preview, separate phone/email history,
   provider result identifiers and evidence. Keep automatic sending under existing controls.
4. Integrations: independently tested Microsoft Graph and Zoho OAuth adapters. Their live
   activation requires user-owned OAuth clients/account consent. Keep existing web adapters.
5. Optional migration pilots: Playwright against sanitized fixtures, then a controlled Dice
   trial; Qt desktop shell only after the existing application services are isolated.
   Benchmark reranking before introducing another local model.

## Acceptance

- Existing deterministic suite passes; new boundary/recovery cases covered.
- Failed login cannot be reported as success merely because the URL contains /dashboard/login.
- Consent clicks are limited to cookie controls on dice.com.
- Failed or ambiguous form answers stay in the question queue and block submission.
- A new completed outreach cycle gets a fresh persisted budget; unfinished work cannot
  silently reset the cycle. Day limits remain enforced.
- A batch summary accounts for every selected row. Configuration problems stop before
  creating messages. Preview and failed-only retry are distinct operations.
- No extra heavy dependencies or models in the default installation.
- Live cookies/login/provider behavior and RAM usage must be measured with the user's
  running browser before calling the migration production-verified.

## Migration policy

Database extensions must be additive. New optional settings must have explicit UI controls.
Do not relabel an internal relevance score as an employer ATS score. Do not import old
outreach errors as successes. Keep an unknown outcome separate from a confirmed failure.

## Delivered in the September 10 compatibility release

- Cookie acceptance with Dice-only targeting; login requires account UI evidence.
- Specific answer matching, exact choices, post-fill empty/invalid detection, queue field metadata.
- Persisted cycle reset, local preflight, structured batch summaries, failed-only batch retry.
- Visible limits and optional 8 GB controls; sequential CLI search retains every query.
- Read-only paginated queue/recruiter history; separate phone status; Gmail receipt audit events.
- Test runner now stops immediately when compilation, tests, or imports fail.

Verification: 57 deterministic tests and 3 provider subtests; Python compilation and imports;
hidden-window construction of both applications. An isolated headless Chrome fixture passed
cookie-control targeting, saved-answer-map handoff, specific matching, exact radio selection,
and post-fill validation. This also corrected two older defects: the scanner's JavaScript
function was not receiving/returning values correctly, and native radio option labels were
mistaken for question labels. Fixtures do not prove the current production banner selector.
No messages/applications were sent during validation.

## Still to implement / validate

- Editable frozen-message preview/approval, reply ingestion, follow-up scheduling, structured
  candidate profile with per-skill evidence, versioned application evidence and ranking benchmarks.
- Microsoft Graph/Zoho API adapters and account setup; current Gmail/Web adapters stay available.
- Browser migration and optional Qt shell remain separate pilots, not part of this release.
- End-to-end memory measurements with the actual user sessions and controlled live provider checks.
