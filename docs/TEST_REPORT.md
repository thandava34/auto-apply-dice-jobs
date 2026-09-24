# Test and Readiness Report

## September 15 — compact layout, all-contact action and Outlook readiness

**96 tests and 3 provider subtests passed**; five existing SWIG warnings remain.
The UI now uses compact pixel-sized text, tighter tabs, less detail spacing and
non-collapsing list columns with horizontal scrolling. Mark All as Called covers
all eligible records across matching pages, with count/filter confirmation;
selected-contact actions remain separate. The regression test covers 63 matching
contacts across pages and excludes a differently filtered record.

Outlook Web uses eager page loading with a bounded initial navigation wait and
checks all matching New Mail controls for a visible enabled button. Offline tests
cover hidden-first matches, navigation timeout recovery and browser reuse.
Stage timing logs distinguish driver/browser setup from mailbox readiness.
Attachment and draft-save waits were retained. Live Outlook latency was not
measured, and no email was drafted or sent during these tests; these changes
address identified code-level delays, not a confirmed account-specific diagnosis.

## September 11 — Jobs & Contacts redesign

The full suite passed **93 tests and 3 provider subtests** after the redesign.
Compilation passed; the five existing SWIG deprecation warnings remain.

- Synthetic workbook tests cover paging, search/status/call filters, missing
  files, phone-less jobs, ambiguous historical email outcomes and invalid links.
- Phone updates are all-or-nothing, keyed by unique dedup hash or a unique exact
  phone-and-title pair. Tests verify ambiguous matches stop the entire update and
  email status remains unchanged.
- Actual Tk widget tests cover cached read-only selection, latest-filter-wins
  loading, double-click link opening, phone-action scope/confirmation, reusable
  Add Job construction, retained input and discard confirmation.
- Automated widget geometry checks passed at 1366×768 with Tk scaling equivalent
  to 125% and 150%. These checks cover the split, wrapping and usable panel space;
  they are not a screenshot-based certification of every Windows theme/monitor.
- One initial repeated-Tk-initialization test encountered a transient local Tcl
  file-read error. The file exists; a single shared test interpreter and fresh
  child windows passed the focused rerun and full suite. No Python installation
  files were modified.

No production workbook was used by these tests, no emails were sent, and mail
provider implementations were not changed for this UI work. Existing exact email
subject/body is not stored; the detail view explains this rather than inventing
content. README documents the new controls and limitations.

## Latest mail remediation / live testing

See [MAIL_REMEDIATION_AND_LIVE_TESTS.md](MAIL_REMEDIATION_AND_LIVE_TESTS.md) for the
provider-specific fixes and evidence. The suite now passes 81 tests plus 3 provider
subtests; the nine former expected failures have been converted to regression
tests. This is not blanket live certification: Gmail sign-in/OAuth and Outlook
Desktop have specific blockers, and Outlook Web was excluded by the user.

Zoho's first live test was received by the user. A second saved draft was verified
with approved To/CC/BCC, body, subject and synthetic DOCX, then Zoho confirmed Sent.
Receipt of the second test and recipient-side attachment validation remain pending.

## September 10 provider audit correction

The focused [Nvoids mail audit](NVOIDS_MAIL_AUDIT.md) found nine reproducible open
defects/verification gaps and additional code-inspection findings. Its new tests
explicitly mark known defects as expected failures, not passes. This supersedes
any earlier implication below that attachment completion, recipient exclusions,
or web draft confirmation are fully protected. Only Outlook Web has the user's
live confirmation; other adapters have not completed real-mailbox acceptance.

Report date: 2026-09-09  
Scope: Dice auto-apply bot and Nvoids cold-outreach bot  
Runtime used: Python 3.11 on Windows

The Windows test script was executed successfully with a process-scoped execution-policy bypass. The Bash scripts were reviewed, but Bash/WSL execution was denied by this Windows host, so macOS/Linux execution remains to be confirmed on those platforms.

## Executive assessment

September 10 compatibility release: 57 tests plus 3 provider subtests pass. Both GUIs were
constructed in isolated hidden windows. The offline Chrome fixture in
`scripts/test_dice_browser_fixture.py` passed cookie handling, answer-map transfer, specific
matching, radio choices, and post-fill validation. Run it with explicit `--browser` and
`--driver` executable paths using `python -m scripts.test_dice_browser_fixture`.
The counts and feature descriptions below document the earlier September 9 baseline;
see `UPGRADE_PLAN.md` for the new release and remaining migrations.

The deterministic code paths are healthy: compilation, imports, dependency consistency, 42 automated tests plus 3 provider dispatch subtests, and the existing safe regression scripts pass. The most dangerous prior failure modes have been closed: invented application answers, false application success, wrong-resume fallback, unconfirmed web-email sends, race-prone caps, premature outreach deduplication, and unrecoverable revoked Gmail OAuth tokens.

The repository is suitable for a controlled draft-first trial. It is not responsible to claim that every live Dice or webmail interaction is permanently verified because those UIs are external, session-dependent, and can change without a code release. A human must complete the live checklist below with dedicated test accounts before enabling unattended submission or email send mode.

## Automated results

| Check | Result | Coverage |
|---|---:|---|
| Python compilation | Pass | `core`, `utils`, `tests`, both GUIs, both entry points |
| Pytest suite | Pass: 42 + 3 subtests | Unit, safety, persistence, OAuth configuration and revoked-token recovery, decision-flow, provider contracts, and mocked outreach integration |
| Import smoke test | Pass | `app_tkinter`, `outreach_ui`, Dice core, outreach pipeline |
| Dependency consistency | Pass | `pip check` in project virtual environment |
| Existing dedup regression script | Pass | Legacy URL/content/cooldown behavior |
| Existing upgrade verification script | Pass | Matcher/scoring upgrade expectations |

The only automated warnings are SWIG deprecation warnings emitted by installed binary AI dependencies; they do not fail execution.

## Feature matrix

| Area | Automated evidence | Live validation still required |
|---|---|---|
| Dice employment filtering | C2C/W2/full-time negative-precedence tests | Confirm current Dice card/detail text extraction |
| Resume matching | Must-have exclusion, absolute ATS threshold, confidence and cache tests | Review chosen resume on a sample of real jobs |
| Application answers | Explicit-only normalization, blank categorized catalog, and sensitive-question AI block | Exercise current Easy Apply control types |
| Application outcome | Applied/already-applied/blocked/unconfirmed/failed classification | Confirm Dice success banner selectors |
| Application state | SQLite application-attempt tests | Verify spreadsheet/UI presentation after a controlled run |
| Outreach extraction/filtering | Email/domain filters and dedup tests | Confirm current Nvoids page selectors and date parsing |
| Resume attachment | Exact-path/profile resolution and missing-file fail-closed tests | Confirm attachment chip appears for each webmail provider |
| Outreach queue | Mocked job-to-draft lifecycle test | Create one real draft in the selected provider |
| Caps and dedup | Transactional state, daily cap, cycle cap, duplicate tests | Restart during a controlled batch and verify recovery |
| Gmail Web/API and Zoho | Validation (including rejection of Web OAuth clients), revoked-token recovery, routing, Gmail API response IDs, and web draft-confirmation contracts tested without sending | OAuth/login and one controlled mailbox draft per provider |
| Shutdown | Worker drain and state close exercised | Close each GUI during a small real draft batch |

## Issues corrected during review

### Critical and high priority

- Removed built-in legal, sponsorship, work-authorization, salary, relocation, employment, and experience answers from backend and GUI.
- Required unanswered application questions and failed resume uploads now block submission.
- A Dice application is successful only after a positive confirmation; “already applied” and unconfirmed submission are separate outcomes.
- Added negative-precedence employment classification so “no C2C” cannot be mistaken for C2C acceptance.
- Required a minimum absolute ATS fit and excluded profiles missing must-have skills.
- Removed fallback to the first resume when an explicit outreach profile is absent or matching fails.
- Required verified resume attachment by default and positive web-provider send confirmation.
- Prevented AI-generated outreach from direct send unless the user explicitly overrides draft-first protection.
- Made daily/cycle reservation and dedup state transactional in SQLite.
- Delayed dedup/contacted marking until draft/send succeeds.
- Added graceful queue draining and run-session finalization.
- Added confirmed bulk Drafted/Sent bookkeeping with Excel, state, audit, and dedup synchronization; it never contacts a provider.
- Required Gmail API response IDs and observable Gmail/Zoho web draft confirmation before reporting success.
- Added UI-based Gmail OAuth client/token path configuration, local credential validation, explicit authorization, connection status, cache isolation by credential paths, and recoverable `invalid_grant` handling that backs up rejected tokens before fresh consent.

### Reliability and maintainability

- Made settings writes atomic and validated.
- Added locks around local SQLite dedup access and fail-closed behavior on dedup read errors.
- Made temporary state, dedup, and Excel paths configurable for isolated tests.
- Removed recursive scanning of other Windows user profiles and shell-based browser discovery.
- Preserved CC/BCC after filtering and handled invalid/missing recipients explicitly.
- Invalidated learning and semantic caches correctly.
- Added DOCX table/header/footer/textbox extraction.
- Added prompt-injection boundaries and output validation around AI extractors/scorers.
- Excluded credentials, browser profiles, runtime databases, exports, debug captures, and model caches from future Git commits.

## Controlled live acceptance checklist

Use dedicated test accounts, one job, one resume, and `draft` mode first.

### Dice

1. Set `job_application_limit` to `1`, disable headless mode, and use one narrowly targeted query.
2. Confirm login and search filters are reflected in the actual results.
3. Verify W2-only/no-C2C jobs are skipped and a compatible contract job is accepted.
4. Confirm the displayed resume selection and ATS score are reasonable.
5. Use an application containing a required question not in `application_answers`; verify submission stops.
6. Add the truthful answer explicitly and retry.
7. Confirm a successful submission is recorded as `applied` only after Dice displays confirmation.
8. Close the application mid-run and verify the browser and keep-awake state are restored.

### Outreach

1. Select one provider, `draft` mode, daily/cycle cap `1`, and an exact resume profile.
2. Paste one synthetic job with an email address you control.
3. Confirm recipient, subject, body, CC/BCC filters, and the visible resume attachment.
4. Confirm exactly one draft exists and the SQLite/Excel status is `draft`/`Drafted`.
5. Retry the same job and verify it is skipped as duplicate.
6. Try a missing resume path and verify no draft or send is created.
7. Only if desired, change to `send` and send one message to your own address; verify the provider’s sent confirmation and cap.

## Remaining risks

- Dice, Nvoids, Outlook Web, Gmail Web, and Zoho Web selectors can change at any time.
- Browser automation can encounter CAPTCHA, MFA, anti-bot controls, rate limits, or account restrictions.
- Native Outlook automation is Windows-only; web providers need persistent authenticated browser profiles; Gmail API needs OAuth consent and token files.
- AI ranking and generation are probabilistic. Thresholds reduce risk but do not replace human review.
- Excel is an export/reporting layer, not the source of transactional truth; SQLite is authoritative for queue state.
- The repository does not currently include a license or CI workflow. Decide the intended license and add CI before a public release.

## Release recommendation

Proceed with a controlled, draft-first release after the live checklist passes in the target environment. Do not advertise unattended “all providers verified” support without repeating the provider-specific live checks after UI or browser updates.
