# Mail remediation and live acceptance — September 10, 2026

## Scope and current status

This is the follow-up to `NVOIDS_MAIL_AUDIT.md`. Unlike the original read-only
audit, this work includes provider fixes and controlled live testing. Outlook Web
was excluded from further testing at the user's request; its existing compose,
save and upload workflow was restored and retained. Shared recipient validation
still applies before dispatch to any provider.

| Provider | Evidence | Status |
|---|---|---|
| Outlook Web | User reports working; further test attempts stopped on request | Excluded, not newly certified |
| Outlook Desktop | Mocked COM tests cover recipients, HTML/plain body, attachment count, recipient resolution, Save/Send and returned draft ID | Live blocked: classic Outlook COM registration not found on this PC |
| Gmail API | Offline MIME round-trip, Unicode filename, exact attachment bytes, To/CC/BCC and saved-draft readback checks | Live deferred: selected/downloaded OAuth client is a Web application client, not Desktop app |
| Gmail Web | Offline adapter contracts and real Chromium fixture for common safety helpers | Live blocked by Google's browser security sign-in rejection; no bypass attempted |
| Zoho Web | Live test exposed updated recipient controls, iframe editor, split filename display and HTML upload modal; these paths were corrected | Live draft fields and attachment verified; see final outcome below |

No production recruiter messages were intentionally sent. Test content uses a
synthetic role/company and a generated DOCX, not the user's personal resumes.
Only explicitly approved test recipients are used; production CC/BCC and AI
generation are disabled in the live harness. Optional `--cc` / `--bcc` arguments
allow separately approved test copies. Production settings and workbooks
are not used as test outputs. Evidence under `data/mail_tests/` is private runtime
data and is excluded from Git.

## Implemented changes

- Effective CC/BCC are resolved once, validated, deduplicated and filtered before
  dispatch. An explicitly empty or filtered field cannot fall back to a blocked
  configured recipient. The caller's job dictionary is not mutated.
- Header line breaks, invalid modes, empty/missing requested files and unresolved
  supported template placeholders stop processing. A requested attachment is not
  silently omitted merely because attachments are optional.
- Gmail API uses encoded MIME filename parameters. Saved API drafts are fetched
  and checked against the intended recipients, subject, plain body and attachment
  bytes before returning a verified Draft result. Draft IDs are retained.
- Outlook Desktop adds styled HTML alongside the text body, checks attachment
  count and recipient resolution, and records a saved item ID. A COM Send return
  means submission to Outlook, not independently confirmed inbox delivery.
- Gmail Web no longer uses discard/minimize controls or a guessed keyboard
  shortcut to save. A missing compose is not proof of a saved draft.
- Gmail/Zoho checks isolate the current compose, fill requested CC/BCC, and compare
  the actual recipients, subject and body. An already-open compose is preserved
  rather than silently overwritten.
- Zoho recognizes the observed `To Recipients`, `CC Recipients` and iframe editor
  controls. Generic first-text-input recipient selection was removed. Controlled
  subject fields are verified after blur and corrected if they lose a character.
- Zoho's current `Add Bcc recipients` role-button is supported. Copy addresses
  are committed with Enter and already-present recipient chips are not re-added.
  Both CC and BCC were verified in the live saved compose before sending.
- Saved Zoho drafts close only through the tab linked to that compose's panel;
  missing/failed close controls stop processing for review. Unrelated tabs are
  no longer closed as cleanup. This close change has unit coverage; a complete
  consecutive-draft live batch remains a separate acceptance check.
- Zoho's attachment modal is handled through its file input and Attach button.
  No background Windows Open-dialog watcher is used. Upload and final compose
  checks recognize a filename split across stem/extension spans, and reject
  visible progress or upload errors.
- Unknown outcomes become `Unconfirmed` / `Review`, not ordinary retryable errors.
  Batch processing stops; automatic retries exclude those rows and persistent
  reservations prevent another send. Unknown outcomes conservatively consume a
  capacity slot. The UI summary and history filter expose these records.
- Provider calls are serialized around the shared browser/service; no new model,
  browser fleet, desktop framework or heavy runtime was installed.

## Test evidence

The final full suite passed **81 tests and 3 provider subtests**, with no expected-failure
markers remaining in the mail audit tests. Compilation, import smoke checks and
`pip check` passed. Existing SWIG dependency deprecation warnings remain.

The offline Chromium fixture passed compose isolation, CC/BCC, Unicode body,
attachment selection, exact filename matching, progress/error checks, recipient
mismatch rejection and saved-draft checks. These are real DOM interactions on a
synthetic page, not a substitute for a provider account test.

Live Zoho testing verified one synthetic DOCX in the compose, the exact approved
recipient with no CC/BCC, subject/body, and the provider's saved-draft indicator.
An upload-stage false negative and a truncated subject were found during the live
test and corrected. Partial test drafts were retained rather than deleted.

### Final live outcome

- Initial test `20260910T171630Z-4bb691`: saved compose verified, sent once,
  and receipt explicitly confirmed by the user.
- Fresh production-adapter draft `20260910T174057Z-55bac3`: returned Draft with
  synthetic DOCX. The same draft was then updated with the approved CC and BCC;
  exact To/CC/BCC, subject/body, attachment presence and saved state were verified.
  Zoho confirmed Sent after one explicit send. Recipient receipt of these copies
  is pending confirmation. The subject ends in `zoho_web draft` because the
  verified draft was subsequently sent; this is not an unsent-message status.
- Opening the downloaded attachment, byte-level recipient-side comparison and
  BCC privacy checks remain pending. A provider Sent notice is not inbox delivery.

## Reproduce safely

Run from the repository root in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1

# Readiness only; opens the provider but does not create a message.
.\.venv\Scripts\python.exe -m scripts.test_mail_live --provider zoho_web --recipient you@example.com --mode probe

# One test draft; a synthetic DOCX is generated automatically.
.\.venv\Scripts\python.exe -m scripts.test_mail_live --provider zoho_web --recipient you@example.com --mode draft --login-wait 120 --hold

# Optional approved test copies; never use real campaign recipients here.
.\.venv\Scripts\python.exe -m scripts.test_mail_live --provider zoho_web --recipient you@example.com --cc owned-copy@example.com --bcc owned-private@example.com --mode draft --hold
```

Use `--mode send` only with an approved test address after verifying a draft. The
script never reads production Excel rows or sends a campaign. Each invocation
creates a unique run directory and records intent before any external action.
Do not retry a run whose result is uncertain until checking the mailbox. Login,
MFA and account consent must be completed by the operator.

The real DOM fixture takes explicit installed browser/driver paths:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_mail_browser_fixture --browser "C:\path\to\chrome.exe" --driver "C:\path\to\chromedriver.exe"
```

## What remains before unattended operation

1. Connect Gmail API with a Desktop app OAuth client and repeat the live
   draft/readback/send tests. Google documents system-browser authorization for
   [installed desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app).
2. Do not work around Google's browser rejection. Google describes restrictions
   on [unsupported sign-in browsers](https://support.google.com/accounts/answer/7675428).
3. Confirm receipt of the additional Zoho CC/BCC test and open its downloaded
   attachment. Complete a consecutive-draft batch and a direct send-mode live
   regression; the verified draft-to-send flow is not proof of every batch path.
4. Test classic Outlook on a PC with its automation interface installed, if desktop
   Outlook is needed. Outlook API and Zoho API are still separate future work.
5. Review Unconfirmed rows against the actual mailbox before marking anything
   Draft/Sent. Do not bulk-mark these rows just to clear a warning. A dedicated
   per-row reconciliation UI for confirmed-not-created outcomes remains follow-up work.

These results are a bounded assessment of the tested code and account state, not
a guarantee that external providers can never change or reject an operation.
