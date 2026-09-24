# Nvoids mail provider audit — September 10, 2026

> Historical pre-fix audit. The [remediation and live-test report](MAIL_REMEDIATION_AND_LIVE_TESTS.md)
> supersedes its implementation status and expected-failure counts. The original
> findings below are retained for traceability, not as the current test result.

## Verdict

**Not all providers are verified or ready for unattended sending.** Outlook Web has
the user's live confirmation. The other providers have code-level and offline
contract checks, not a completed real-mailbox acceptance test. A successful API
response, COM call, or browser click is not proof of delivery to a recipient.

This audit changes tests and documentation only. It does not change provider code,
mail settings, credentials, resumes, or production history. No email was sent or
drafted in a real account during this audit.

## What actually exists and what was tested

| Provider | Offline evidence | Remaining limitation |
|---|---|---|
| Outlook Web | Existing safety tests and code inspection; user reports live success | Attachment completion, BCC, and durable draft confirmation still have code gaps |
| Outlook Desktop (`outlook`) | Mocked COM draft/send: To, CC, BCC, subject, exact plain body, absolute resume path, Save versus Send, COM cleanup | No actual Outlook session tested; uses `mail.Body`, not styled HTML; no saved-item readback or delivery check |
| Gmail API (`gmail_api`) | Decode generated MIME for draft/send; verify recipients, Unicode subject/body, blank lines, escaped HTML, configured font, attachment bytes, ordinary filename, returned IDs | Live OAuth/account access and mailbox rendering not tested; Unicode filename defect below |
| Gmail Web (`gmail_web`) | Mocked control contract for To, subject, body, resume; stops when attachment helper explicitly fails | Does not establish real editor persistence or upload completion; draft-discard and BCC defects below |
| Zoho Web (`zoho_web`) | Mocked control contract for To, CC, subject, escaped body with line breaks, resume; stops when helper explicitly fails | Real editor/iframe state, upload modal, save persistence, and account/session not tested |
| Outlook API / Zoho API / Gmail or Zoho desktop | Not implemented as separate adapters | Do not interpret provider selection as support for these integrations |

The common template test also verifies replacement of recruiter name, job title,
company/company_name, location, and keywords in body and subject, with AI disabled.
It does not establish that source job data or user-supplied personal facts are correct.

## Findings and implementation priority

Locations refer to `core/outreach/email_engine.py` in the audited code.

| Priority | Finding | Evidence / effect | Required change |
|---|---|---|---|
| P1 | Gmail draft fallback includes a discard control | Line 986 includes `@alt='Discard draft'` in a save/close selector | Remove destructive/ambiguous fallbacks; scope to the current compose and verify the saved draft |
| P1 | File-input acceptance is reported as a completed attachment | `_attach_file`, lines 394–438, returns True after typing a path and a fixed delay without checking completion | Wait for the exact attachment in the current compose, no upload progress or error, then verify saved attachment |
| P1 | Zoho upload can report success after dialog failure | `_attach_file_zoho`, lines 604–647, sets `attached=True` after modal actions even when native dialog helper fails | Respect helper results; require exact filename and completed upload before allowing send |
| P1 | Excluded CC/BCC can be restored | Shared filter empties blocked fields; desktop/Gmail API/Gmail Web/Zoho Web then use unfiltered configured fallback (for supported fields) | Resolve, validate, filter, and freeze all effective recipients once; adapters must not add recipients |
| P1 | Draft confirmation can be a false positive | `_wait_for_draft_confirmation`, lines 347–384, accepts an empty page/no matching compose; Outlook Web returns Draft without readback at line 820 | Require evidence tied to this message; navigation, discard, and missing selectors must remain unconfirmed |
| P2 | BCC is not filled by any web adapter | BCC assignment exists only in desktop and Gmail API paths; Gmail Web omission reproduced | Implement compose-scoped BCC or reject configured BCC on unsupported adapters |
| P2 | CC failures can be silent; invalid CC/BCC syntax is not checked | Web CC exceptions log warnings and continue; shared validation checks To only | Validate every recipient and require all intended recipient chips to match before save/send |
| P2 | Optional resume is silently omitted by web adapters | Attachment helpers are called only when `require_resume_attachment=True` (lines 758, 940, 1325) | Attach a supplied file regardless of whether an attachment is mandatory; fail if the requested upload fails |
| P2 | Gmail MIME Unicode filename round-trip fails | Hand-built Content-Disposition at line 1588 changes `Resume José.pdf` on parsing | Use standards-aware MIME filename parameters; test ASCII, spaces, Unicode, and long filenames |
| P2 | Formatting and persistence differ between adapters | Desktop assigns plain Body; Gmail API builds HTML; browser paths inject text/HTML without saved-message readback | Define a common content contract, preserve paragraphs/signature, and compare actual saved contents |

Nine focused tests currently reproduce known defects and are explicitly marked
`expectedFailure` (shown as `xfailed`). **These are unresolved failures, not passing
safety checks.** The table also includes additional code-inspection findings not
individually reproduced by those nine tests. No product fixes are claimed here.

## Implementation sequence

1. **Prevent loss and unintended recipients.** Fix Gmail discard fallback and
   normalize/validate/exclude effective To/CC/BCC exactly once. Fail closed on
   incomplete recipient fields. Keep current Outlook Web behavior covered by tests.
2. **Make attachment and draft status trustworthy.** Use current-compose-scoped
   upload checks, explicit upload errors/timeouts, and durable saved-message evidence.
   Preserve uncertain outcomes for reconciliation instead of automatically retrying
   a potentially successful send and creating a duplicate.
3. **Unify content handling.** Fix MIME filename encoding, optional attachments,
   BCC support, and formatting contracts. Validate supported template placeholders;
   warn or block unresolved required details. Do not invent candidate facts.
4. **Run controlled live acceptance.** One provider at a time, draft-first, using
   a dedicated test recipient and an approved sample resume. Only after draft
   inspection should an explicitly approved self-addressed send be tested.
5. **Enable unattended batches only after acceptance.** Remove expected-failure
   markers as fixes land; retain negative tests and a provider-specific readiness
   checklist. These changes can use the existing stack and do not require a new
   browser fleet, model, or background service on the 8 GB PC.

## Live acceptance checklist (not performed)

For each supported provider:

- Confirm the sender account; create one uniquely labelled draft to the approved
  test recipient, with approved test CC/BCC addresses only.
- Reopen it from Drafts. Compare To/CC/BCC, subject, recruiter/company/role/location,
  paragraphs, Unicode, signature, and absence of unresolved placeholders.
- Download the draft attachment and compare its filename, size, and SHA-256 to
  the selected source resume. Confirm that there is exactly one requested attachment.
- Test an invalid path, delayed/failed upload, missing editor, session expiry,
  and save failure. None may produce a confirmed Draft/Sent result.
- With separate approval, send only to the test inbox. Check receipt, rendered
  contents and attachment again, then reconcile the provider receipt with history.
- Verify retry behavior does not create duplicate drafts or sends.

## Reproduce offline checks

Results from this audit run:

- Full suite: **67 passed, 9 expected failures, 3 provider subtests passed**.
- Focused audit: **10 passed, 9 expected failures**. Re-running with
  `--runxfail` reports those nine checks as failures (exit code 1), as intended.
- Compilation, import smoke test, and dependency consistency check passed.
- Five SWIG deprecation warnings were emitted by existing dependencies.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_email_provider_audit.py -q -rx
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1
```

To make the known defects fail the command during remediation (remove each
`expectedFailure` decorator to expose its underlying assertion traceback):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_email_provider_audit.py --runxfail -q
```

The fixtures replace provider services and browser/COM objects. They do not launch
mail clients, load production credentials, call Gmail, or verify actual UI rendering.
