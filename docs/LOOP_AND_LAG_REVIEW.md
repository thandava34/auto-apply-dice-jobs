# Dice and Nvoids: loop, responsiveness and release review

Review date: September 17, 2026. Scope: the current local source tree, not only the
last Git commit. There are existing unpublished changes in this checkout.

## Executive summary

Both applications keep their principal automation in background workers. Their
long-lived loops are not automatically defects: paused runs, continuous scraping,
mail-queue consumers and Tk event polling must wait for work or user input.
The important distinction is whether they yield, can be stopped, and report a
failure instead of silently waiting forever.

This review fixed concrete queue-stall, UI-work and diagnostic problems without
changing provider send implementations or application-answer rules. It does not
certify every live website, account or network condition. No real applications,
drafts, emails, authorization requests or model/API downloads were performed.

## Findings and changes

| Area | Problem / impact | Change | Status |
| --- | --- | --- | --- |
| Both live log panels | Text accumulated indefinitely during long runs, increasing Tk memory and layout work. | Retain roughly the newest 2,000 visible lines. Existing disk files are not modified. | Fixed |
| Dice log viewer | Reading and rendering an entire large log on the UI thread could freeze the window. | Read at most the last 256 KiB, with a visible notice directing users to the complete file. | Fixed; disk read remains synchronous but bounded |
| Shared UI event pump | A batch of 200 expensive callbacks could monopolize Tk before processing input. | Yield between callbacks after a 12 ms time budget as well as the existing count limit. Pending callbacks remain queued. | Fixed; one slow callback cannot be preempted |
| Nvoids producer | A full queue could wait indefinitely if the consumer thread had died. | Check worker liveness before each timed enqueue attempt; preserve the pending record and stop with an actionable error. | Fixed |
| Nvoids cycle transition | Waiting for unfinished mail could never finish after consumer failure. | Detect a stopped worker before resetting the cycle budget. | Fixed |
| Nvoids export bookkeeping | An exception outside the provider handler could skip `task_done`, leaving queue accounting stuck. | Always finish that queue task, stop production on bookkeeping failure, retain durable outcomes; never resend to repair an export. | Fixed |
| Shutdown | Wall-clock changes could distort the queue-drain deadline; a dead worker could consume the whole wait unnecessarily. | Use a monotonic deadline and check worker liveness. | Fixed; active provider calls still need to return |
| Nvoids job-list refresh | Several messages per email could trigger repeated workbook scans and clear/reload the list. | Coalesce notifications into one scheduled refresh per 350 ms window. Manual search/refresh remains available. | Fixed |
| Dice error feedback | Delayed callbacks referenced an exception variable Python clears after the `except` block. | Capture the error text when scheduling the callback. | Fixed for auto-fill and login-test errors |
| Windows setup | Native Python/pip failures could be followed by a misleading “Setup complete”. | Check each native exit code and stop with a specific setup error. | Fixed |
| Publication hygiene | Local backups, scratch scripts and assistant workspace notes were not excluded. | Ignore those directories without deleting their contents. | Improved; manual publication review still required |

Implementation locations: `utils/log_view.py`, `utils/ui_events.py`,
`app_tkinter.py`, `outreach_ui.py`, `core/outreach/outreach_pipeline.py`,
`core/outreach/nvoids_scraper.py`, `scripts/setup.ps1`, `.gitignore`.

## End-to-end flow review

### Dice

1. **Startup/configuration:** imports and settings loading precede the GUI;
   optional model initialization can add first-use latency. The existing shared
   embedding service serializes work and caches model-aware vectors.
2. **Login:** browser readiness and cookie-consent checks are bounded. MFA,
   CAPTCHA, login failures and browser startup remain external dependencies.
3. **Search:** query/page loops and navigation retries are finite. More queries
   and requested pages necessarily take longer. CLI multi-query search may use
   several browser processes; this is not the same path as sequential GUI search.
4. **Filtering/ranking:** extraction, résumé ranking and optional AI calls run
   within the automation workflow. First model use and provider timeouts can
   dominate a job's duration; a warm-cache test does not prove cold-start speed.
5. **Forms/questions:** wizard steps have attempt limits. Unknown factual answers
   must stay pending. Approved MiniLM associations remain local; this audit does
   not broaden matches or enable generated answers.
6. **Submission/retry:** confirmation and uncertain-outcome protections remain.
   The CLI retry pass is bounded to one additional attempt per eligible job;
   do not add retries after an uncertain submission merely to improve speed.
7. **Persistence/UI:** workbook writes and log rendering can contribute to lag.
   The log changes limit visible history, not job outcomes or saved questions.
8. **Pause/stop:** pause loops yield with sleeps. Stop is cooperative, not an
   immediate interruption of an in-flight browser/network call.

### Nvoids

1. **Configuration:** normal scraper, batch-mail and Auto-Pilot paths reuse a
   pipeline when its configuration matches. Changing settings can rebuild it.
2. **Scraping:** continuous mode deliberately performs repeated cycles with a
   configured rest interval. Pauses, cooldowns and request pacing remain intact.
3. **Extraction/matching:** filter and dedup gates run before dispatch. Large
   descriptions, many profiles and optional AI calls can add processing time.
4. **Queue:** one provider consumer and a 50-item buffer provide backpressure.
   A full buffer means production waits; it is not permission to drop messages
   or create another sender. Dead-worker waits now fail explicitly.
5. **Mail providers:** Outlook Desktop, Outlook Web, Gmail Web, Gmail API and
   Zoho retain their existing paths. Recipient/attachment/draft/send checks are
   safety work, not expendable delays. Provider readiness is covered offline,
   not re-certified against live accounts in this review.
6. **Outcomes/exports:** provider results are recorded separately from Excel.
   Export errors must never repeat an external action. Unconfirmed outcomes and
   historical approval holds remain excluded from automatic processing.
7. **Jobs & Contacts:** pages display 50 cached records; selection itself does
   not reload Excel. Filtering still scans the workbook to calculate totals.
   Worker generation checks discard obsolete responses. Notification coalescing
   reduces redundant refresh requests without adding a data cache.
8. **Shutdown:** resources must remain open while their worker is active.
   A pending shutdown is not success; inspect the reported operation before
   considering a force-close. Do not delete locks or databases to speed it up.

## Remaining limitations and prioritized follow-up

These were identified by source inspection, not measured as live-account latency.

1. **Medium — Excel scaling:** searches count matches by scanning the workbook;
   exports can read/write the whole workbook per outcome. Large or locked files
   will remain slow. Next step: benchmark synthetic 1k/10k/50k datasets and then
   consider a read index or batched export design, preserving phone edits and
   external-edit compatibility. No caching/database-source migration was made.
2. **Medium — fixed waits:** Dice and mail/scraper helpers still contain short
   sleeps and intentional throttling. Replace only waits with a trustworthy
   operation-specific readiness signal; retain cooldowns/backoff. The Nvoids
   page-ready helper can continue after a readiness timeout, so downstream
   selectors and fail-closed checks remain important.
3. **Medium — UI-thread utility work:** manual résumé scans, some settings and
   maintenance operations may still perform disk/CPU work on Tk's thread. Move
   them behind single-flight workers if representative profiling shows delays.
4. **Medium — cooperative cancellation:** Selenium, OS dialogs and remote API
   calls cannot all be interrupted immediately. Audit timeouts per provider and
   test stalled calls before promising a maximum Stop-to-idle duration.
5. **Medium — event pressure:** callbacks now yield on a time budget, but the
   shared event queue is not size-bounded. A sustained producer faster than Tk
   can render may still accumulate events. Prefer coalescing counters/status
   events; do not silently drop outcomes, failures or persistence work.
6. **Low — first-use model costs:** model loading, first download when enabled,
   and disk cache misses are different from a processing loop. Keep truthful
   initialization messages and separate cold/warm measurements in future tests.

## Validation and reproducibility

Final local result: **149 tests passed, 16 subtests passed**, in 24.77 seconds
for pytest. Source compilation, both-entry-point import smoke checks and
`pip check` also passed. Five existing SWIG deprecation warnings were emitted.
Test duration is not a benchmark of live automation throughput.

`git diff --check` still reports trailing whitespace in the existing cumulative
changes, including Dice source files. Those unrelated formatting changes were
not mass-rewritten. Local Git also warned that the global ignore file was not
readable; repository ignore checks nevertheless confirmed the new private-folder
rules and real settings exclusions, while example settings remain publishable.

Run from the repository root on Windows:

```powershell
.\scripts\test.ps1
```

The script compiles source, runs the default `tests/` suite, imports both entry
points and core modules, and runs `pip check`. The suite includes Tk checks,
local SQLite/workbook fixtures, process locks, provider mocks, form matching and
question-learning safeguards. It does not run the historical root/scratch scripts.

New regressions in `tests/test_responsiveness.py` and the pipeline integration
suite cover bounded log reads, bounded visible text, event-pump yielding without
loss, coalesced refreshes, export-bookkeeping failure without repeated dispatch,
and a stopped mail consumer. Existing tests cover queue saturation, shutdown,
locked-file/export behavior, duplicate outcomes and provider readiness failures.

Not performed: live account sign-in, mail delivery, application submission,
full-day soak, fresh-machine installation, manual DPI/keyboard walkthrough, or
separate standalone browser-fixture scripts. Passing mocks cannot establish that
a changed provider website still accepts its selectors. Existing historical live
reports must not be presented as new live validation.

## Before publishing

- Review the complete diff; this checkout contains changes from earlier work.
- Keep real settings, OAuth tokens, browser profiles, résumés, contacts, logs,
  workbooks, databases and backups private. Ignoring a file does not untrack it
  if it was committed earlier, nor erase old Git history.
- Only publish synthetic fixtures and redacted example configuration. A limited
  source/example scan found no common Groq/OpenAI/Google key-shaped strings;
  this is not a comprehensive secret or personal-data audit.
- Inspect staged filenames and content manually, run the tests, and review the
  limitations above before publishing. No commit or push was performed here.
