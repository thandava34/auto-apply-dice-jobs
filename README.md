# AI Job Search Automation Suite

A desktop Python suite with two separate workflows:

1. **Dice Auto-Apply Bot** — searches Dice, filters roles, ranks configured resumes, completes supported Easy Apply forms, and records a confirmed outcome.
2. **Nvoids Cold-Outreach Bot** — collects or accepts job leads, extracts recruiter contact details, selects an exact or matched resume, and creates drafts or sends through a configured email provider.

The current build is designed to fail closed: missing resumes, required unanswered questions, uncertain submissions, invalid recipients, unverified attachments, duplicate outreach, and exceeded caps stop the external action instead of being treated as success.

**Latest code review — September 17, 2026:** see the
[loop and responsiveness report](docs/LOOP_AND_LAG_REVIEW.md) for confirmed fixes,
end-to-end flow findings, remaining bottlenecks and release limitations. This is
offline validation, not a claim that every live provider is fully verified.

> Use automation responsibly. Review Dice and email-provider terms, applicable employment/privacy rules, and anti-spam laws. Start with visible browser windows, low limits, and email `draft` mode.

### Dice interface and login updates

Dice's Analytics tab and its workbook-aggregation code have been removed. Existing
result files and logs are retained. The main screen now has one **Skipped** box
beside the other counters instead of four reason-specific boxes. It counts unique
jobs skipped during the current run, including filtered/excluded jobs, previously
processed jobs and manual skips; failed attempts are not automatically skips.
Detailed reasons remain in the existing logs and workbooks. Because pre-filtered
jobs are included, Skipped is not a subset of the displayed jobs-to-process count.

Cookie consent is checked as soon as Dice's login page opens and again on every
login-control readiness poll, covering banners that arrive after initial loading.
Only known consent controls or accept buttons inside cookie-labelled containers
on Dice domains are eligible. This does not bypass login, MFA or browser security.

## Contents

- [What is included](#what-is-included)
- [How the bots work](#how-the-bots-work)
- [Requirements](#requirements)
- [Quick setup](#quick-setup)
- [Configuration](#configuration)
- [Run the applications](#run-the-applications)
- [Safe first-run procedure](#safe-first-run-procedure)
- [Testing](#testing)
- [Operational data and statuses](#operational-data-and-statuses)
- [Security and GitHub checklist](#security-and-github-checklist)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [Readiness and roadmap](#readiness-and-roadmap)

## What is included

### Dice Auto-Apply Bot

- Multiple job queries and Dice search filters.
- Include/exclude keyword rules and explicit C2C/W2/full-time classification.
- Resume profiles with general, unique, and must-have skills.
- Layered resume ranking: keywords, title affinity, optional local semantic similarity, optional Groq scoring, and learning history.
- Absolute `minimum_ats_fit`; a weak “best of a bad set” result is rejected.
- Required-question and resume-upload gates before submission.
- Captured-question editing and user-approved local answer associations. There are no built-in legal, sponsorship, salary, relocation, employment, or experience claims.
- AI answer generation is off by default and is always blocked for sensitive questions.
- Confirmed outcome categories: `applied`, `already_applied`, `skipped`, `blocked`, `unconfirmed`, and `failed`.
- Pause, stop, skip, headless, screen-awake, batching, and application-limit controls.

### Nvoids Cold-Outreach Bot

- Nvoids job scraping with queries, age limit, result limit, keyword filters, and optional continuous cycles.
- **Jobs & Contacts**: searchable, paged jobs list with side-by-side details and a separate **Add Job** window.
- Recruiter email/phone extraction and blocked-domain/address filtering.
- Three complementary duplicate protections: exact job hash, content fingerprint, and recruiter/title cooldown.
- Exact fixed-resume selection or ATS-thresholded automatic matching.
- Template variables, multiple templates, optional AI-assisted content, and CC/BCC filtering.
- `draft` or `send` mode with daily and per-cycle caps.
- Zoho mail verifies To/CC/BCC, subject/body and completed résumé attachment before
  draft/send completion. Current BCC controls and the HTML upload modal are supported.
  Saved drafts close through their own tab; uncertain outcomes pause for review.
  See the [mail acceptance report](docs/MAIL_REMEDIATION_AND_LIVE_TESTS.md) for live
  test results, provider limitations and safe test commands with `--cc` / `--bcc`.
- Supported providers:

  - `outlook` — native Outlook desktop on Windows.
  - `outlook_web` — Outlook Web through Selenium.
  - `gmail_web` — Gmail Web through Selenium.
  - `gmail_api` — Gmail OAuth API; recommended for reliable Gmail drafts.
  - `zoho_web` — Zoho Mail through Selenium.

- Resume attachment required by default.
- AI-generated email can be sent automatically only with an explicit override; draft-first review is the default.
- Transactional SQLite outbox, cap reservation, dedup, run session, and audit state.
- Graceful worker shutdown and stale reservation recovery.
- Confirmed `Mark All Drafted` and `Mark All Sent` bookkeeping controls that synchronize Excel, SQLite, audit, and dedup state without contacting a provider.

## How the bots work

### Dice flow

```text
Queries + Dice filters
        ↓
Job card/detail extraction
        ↓
Include/exclude + employment rules
        ↓
Resume eligibility and ATS threshold
        ↓
Easy Apply form + exact resume upload
        ↓
Required-question validation
        ↓
Submit only when all gates pass
        ↓
Confirmation detection → typed outcome → SQLite/Excel/UI
```

The bot does not equate a click with a successful application. If Dice does not show a positive confirmation, the result is `unconfirmed`, not `applied`.

### Outreach flow

```text
Nvoids scrape or pasted job description
        ↓
Age/skill/title/email exclusion filters
        ↓
Exact hash + content dedup + cooldown
        ↓
Exact or thresholded resume selection
        ↓
Transactional daily/cycle reservation
        ↓
Validated recipient + subject + body + attachment
        ↓
Provider draft/send
        ↓
Confirmed result → state ledger → dedup → Excel export
```

SQLite is the operational source of truth. Excel is a readable export and manual work queue; it is not used as the only transaction boundary.

## Requirements

- Python **3.11** recommended. Later versions may work, but binary AI/browser dependencies are most predictable on 3.11.
- Google Chrome, Brave, or Chromium for browser-driven workflows.
- A valid Dice account for Dice automation.
- At least one PDF or DOCX resume profile.
- An email account/provider only if using outreach.
- Tkinter. It is included with normal Windows/macOS Python installers; Linux may require a separate OS package.

Optional services:

- One shared Groq API key for optional Dice ranking/question disambiguation and Nvoids title extraction/email generation. Enter it in Dice's API Key Manager or Nvoids **Email Config**; Nvoids also has **Check Groq connection**. The key is stored in Dice's local `config/settings.json` and reused by both bots. Keep this private file out of Git.
  Restart an already-running bot after changing the key in the other bot; its existing AI client may still hold the previous credential. Saving Nvoids Email Config migrates an older Nvoids-only key into the shared location and removes the redundant copy.
- Gemini API key where configured by the Dice UI.
- Gmail OAuth desktop credentials for `gmail_api`.

## Quick setup

### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\scripts\test.ps1
```

If `python` is not the desired interpreter:

```powershell
.\scripts\setup.ps1 -Python "C:\Path\To\Python311\python.exe"
```

### macOS or Linux

```bash
chmod +x scripts/setup.sh scripts/test.sh
./scripts/setup.sh
./scripts/test.sh
```

The setup script creates `.venv`, installs `requirements.txt`, and copies missing local configuration from the redacted examples. It never overwrites an existing `.env` or settings file.

### Manual setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then copy:

- `.env.example` → `.env`
- `config/settings.example.json` → `config/settings.json`
- `config/outreach_settings.example.json` → `config/outreach_settings.json`

## Configuration

### Keyword Suggestions: manual profile edits only

Dice's **Keyword Suggestions** tab replaces the previous Skill Gaps add-to-profile
controls. Job-description gaps, selected/all-résumé scans, matching-test gaps and
enabled scheduled scans save suggestions separately in
`data/keyword_suggestions.db` (private, ignored by Git).

1. Open **Keyword Suggestions**, then use **Search / Refresh** to load recent items.
2. Select a row to read the full keyword, profile name, source job/scan, company,
   reason and capture date. Use **Copy selected** or Ctrl+C
   to copy selected keywords.
3. Check the original résumé yourself. A job asking for a skill is not evidence
   that you have it; scanner output can also be incorrect.
4. Use **Mark reviewed** or **Dismiss** to organize suggestions. Filter to Reviewed,
   Dismissed or All to see them later; **Restore to pending** reverses that label.
5. Enter verified keywords manually in the existing résumé profile editor and
   save that profile yourself.

There is deliberately **no approve/add-to-profile button**. Saving, copying,
reviewing or dismissing a suggestion never changes profiles or ranking scores.
Repeated identical suggestions preserve their review status across restarts.
Lists show 100 records per page with full wrapped details below.

Legacy auto-attach settings are ignored even if previously enabled. Existing
profile keywords are left untouched: review and remove previously added keywords
manually if needed. Old session-only gap history cannot be recovered after the
old application has closed. Scheduled scans retain their existing API behavior
when enabled, but now save suggestions only; this change does not run a live scan.

Validation: **153 tests and 16 subtests passed**, including suggestion persistence,
review labels, legacy auto-attach protection and Tk copy/detail controls. Import,
compilation and dependency checks also passed; no live scans were used.

The GUIs can edit most settings. JSON examples are included for repeatable setup; local real settings are ignored by Git.

### Environment variables

```dotenv
DICE_USERNAME=your-dice-login
DICE_PASSWORD=your-dice-password
WEB_BROWSER_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
GROQ_API_KEY=
GEMINI_API_KEY=
```

`WEB_BROWSER_PATH` is optional. Detection checks normal install locations for the current user and system, then the executable search path. It does not recursively scan other users’ profiles.

### Dice settings

Start with [config/settings.example.json](config/settings.example.json). Important fields:

| Setting | Meaning | Safe default |
|---|---|---:|
| `search_queries` | Dice searches to run | Example role list |
| `job_application_limit` | Maximum jobs handled in one run | `25` in example |
| `filter_easy_apply` | Restrict to supported Easy Apply jobs | `true` in example |
| `filter_employment_type` | `ALL`, contract/C2C choice used by the UI | `ALL` |
| `minimum_ats_fit` | Absolute resume-fit floor from 0–100 | `25` |
| `profile_name_boost_mode` | `off`, `low`, `high`, or `exact` | `high` |
| `semantic_enabled` | Use local semantic matching | `true` |
| `auto_answer_questions` | Use explicitly configured answer patterns | `false` |
| `allow_ai_generated_application_answers` | AI for non-sensitive free text only | `false` |
| `auto_attach_missed_kws` | Obsolete; ignored and saved as false. Suggestions never update profiles. | `false` |

Resume profile shape:

```json
{
  "id": "data-engineer",
  "name": "Data Engineer",
  "file_path": "resumes/data-engineer.pdf",
  "keywords": ["Python", "SQL", "Airflow"],
  "unique_keywords": ["Databricks"],
  "must_have": ["Python"]
}
```

Use unique IDs and valid file paths. A profile missing any `must_have` term is excluded. If no eligible profile reaches `minimum_ats_fit`, the application is skipped.

Application answers are substring-pattern mappings and must be truthful for the operator:

```json
{
  "auto_answer_questions": true,
  "application_answers": {
    "preferred start date": "YOUR TRUTHFUL ANSWER",
    "desired salary": "YOUR TRUTHFUL ANSWER"
  }
}
```

No sample legal or protected-status answer is supplied intentionally. Even when AI answers are enabled, citizenship, authorization, visa, sponsorship, clearance, disability, veteran, demographic, conviction, background-check, and drug-test questions are not generated.

In the Dice Settings tab, choose a categorized question pattern, optionally choose a quick answer, or type a custom answer. Nothing is saved until **Save Explicit Answer** is clicked. Selecting a question never pre-fills a candidate claim.

### Browsing Jobs & Contacts

Open **Jobs & Contacts** in Nvoids. The left list includes all saved jobs, even
those without a phone number. Single-click a row (or use keyboard selection) to
read its **Overview**, **Job Description** and **Email Details** on the right.
Called jobs are hidden from the normal list after refresh, but stay in Excel.
Search by job title, company, recruiter, email or phone to find them again (even
in Needs Calling); the email-status filter still applies. Clear the search to
hide them again. Their call status appears in Overview, and completed calls are
excluded from further bulk call updates.
Drag the divider to resize the two panels. Double-click a row to open its job
website, or use **Open Job Link**. Invalid/missing links are disabled.

Use search, the email-status filter and Previous/Next to browse 50 records at a
time. Reads run in the background; selecting a loaded row does not reload Excel,
run AI, create a draft or send anything. Drafted and Sent are separate outcomes;
uncertain historical records show **Outcome unclear**. A configured send mode
alone is not evidence that a message was drafted or sent.

**Add Job** opens the existing paste/extract/save workflow in a reusable window.
Closing that window hides it and retains your text. Clearing it or exiting the
application asks before discarding unsaved edits. Saved jobs appear after refresh.

**Mark All as Called** is visible in both **All Jobs** and **Needs Calling**.
Choose **Needs Calling** for selected-contact call actions. **Mark All
as Called** includes eligible contacts across every page matching the current
search and email-status filter. Its confirmation shows the count and filter
scope; clear filters first if you want every eligible contact. **Mark Selected
Called** affects only your selection. All phone actions require confirmation and change only **Phone
Status**. Ambiguous or missing identifiers stop the update rather than modifying
several similar jobs. A locked workbook reports an error; it is not treated as a
successful update.

Missing fields display “Not recorded.” Existing Excel records do not contain the
exact email subject/body, and older descriptions may be truncated excerpts. Use
the provider mailbox or original job link for the original content. No new
dependencies, mailbox permissions or workbook migration are required.

The shared desktop appearance now applies to both bots. Each Jobs & Contacts list
entry uses two lines: job title, then email outcome/company/date. Long labels are
shortened to fit the divider position; select the record to read its complete
saved fields on the right. Resizing uses cached records and does not reload Excel.
Segoe UI 11 pt text and font-measured row heights keep the list readable.
Shared tokens live in `utils/desktop_tokens.py`; `utils/desktop_theme.py` applies
the coordinated appearance to both applications, including newly opened custom
dialogs. Dice uses blue primary actions, Nvoids uses teal; stop remains red.
Settings, résumé screens, AI tools, templates, results and logs keep their existing
controls and callbacks. Tabs use shorter text labels instead of decorative emoji.
Nvoids dashboard actions use two rows to reduce crowding. Toggle switches now
support Tab focus and Space/Enter activation. No new dependencies are required.

Restart each app when idle to load the appearance update. Native Windows file
pickers and message boxes retain their operating-system appearance. This is a
presentation update, not a change to provider workflows or automation outcomes;
actual on-monitor review of dense legacy forms is still recommended.
See [Desktop appearance](docs/DESKTOP_APPEARANCE.md) for scope, design decisions
and validation limitations.

Actions use consistent colours: teal for Add Job, green for called actions, amber
for skipping a call, and slate for navigation. Disabled controls remain dark with
muted text; they are unavailable, not broken. Select an eligible contact to enable
selected-call actions, and select a job with a valid URL to enable Open Job Link.
Empty results explain how to find previously called jobs through search.

Outlook Web startup now uses DOM-ready loading instead of waiting for every page
resource, and selects a visible enabled New Mail control even when hidden copies
exist. Logs separately report Chrome/driver startup and mailbox readiness times.
An existing live bot browser is reused. This does not reuse an unrelated personal
browser session, skip authentication, or remove attachment/draft-save waits.

### Outreach settings reference

Start with [config/outreach_settings.example.json](config/outreach_settings.example.json). Important controls:

| Setting | Meaning | Recommended start |
|---|---|---:|
| `email_provider` | One of the five provider IDs above | `gmail_api` for Gmail |
| `gmail_client_secret_path` | Google OAuth Desktop Client JSON path | `config/gmail_client_secret.json` |
| `gmail_token_path` | Local OAuth refresh-token path | `config/gmail_token.json` |
| `send_mode` | `draft` or `send` | `draft` |
| `require_resume_attachment` | Block action without a valid resume | `true` |
| `target_resume` | Exact profile name or `Auto-Match (AI)` | Explicitly review |
| `resume_minimum_ats_fit` | Automatic resume fit floor | `25` |
| `daily_cap` | Maximum confirmed drafts/sends per day | `25` or lower |
| `cycle_cap` | Maximum confirmed drafts/sends per scrape cycle | `10` or lower |
| `cooldown_hours` | Recruiter/title cooldown | `48` |
| `use_ai_email` | Generate or enhance email text | `false` |
| `allow_ai_email_auto_send` | Permit AI output in direct-send mode | `false` |
| `excluded_vendor_domains` | Domains never placed in To/CC/BCC | Required review |
| `excluded_email_addresses` | Exact addresses never contacted | Optional |

Template variables include `{recruiter_name}`, `{job_title}`, and `{company}`. Keep templates factual; generated text is untrusted until reviewed.

#### Gmail API setup

1. Create a Google Cloud project and enable the Gmail API.
2. Configure an OAuth consent screen.
3. In **Google Auth Platform → Clients**, click **Create client**, choose application type **Desktop app** (not **Web application**), and download the new JSON file. Desktop clients use Google's supported localhost callback automatically; do not configure a fixed redirect URI for this bot.
4. In **Email Config**, select `gmail_api` and use **Browse** to choose that OAuth Client JSON.
5. Keep the default token location or choose another ignored local JSON path.
6. Click **Check Configuration**, then **Connect / Re-authorize Gmail API**.
7. Complete Google consent in the browser. The application writes the refresh token to the selected local token file.
8. Keep `draft` mode enabled and run **Test Email** with an address you control.

Gmail mailbox access cannot be configured with a simple API key. The OAuth client secret identifies the application, and the locally generated refresh token authorizes the mailbox. The UI stores only the configured file paths in settings; it does not copy credential contents into the settings file.

Both OAuth files are ignored by Git and must never be committed.

#### Web and Outlook providers

- `outlook` requires installed Outlook desktop and `pywin32` on Windows.
- Web providers open a persistent Chromium profile and may require manual login/MFA on first use.
- A changed provider UI can break selectors. Re-run a one-message draft test after provider or browser updates.
- The provider test treats only a confirmed `Draft` or `Sent` as success and asks again before a live test in send mode.
- Gmail API requires a returned message ID. Gmail Web and Zoho Web require a saved-draft notification or a closed compose surface before reporting `Draft`.

## Run the applications

### Desktop workflow controls

- **Dice cookies:** login automatically accepts supported cookie-consent banners on Dice.
  It checks at login transitions and ignores unrelated Accept buttons. A changed or unsupported
  banner still needs manual handling. Login success requires account-specific UI evidence.
- **More precise answers:** exact question matches take precedence, then the longest specific
  pattern. Generic experience patterns no longer answer different skill-specific questions.
  Dropdown/radio answers must match the displayed choice. Empty/invalid fields detected after
  filling are queued for review. Question details now include captured choices and field type.
  The scanner now correctly receives saved answers and returns unanswered questions to Python;
  native radio groups prefer their question legend over individual answer labels.
- **Nvoids limits:** daily and per-batch/cycle limits have their own row. Zero means unlimited.
  Starting a batch/new cycle resets the persisted cycle budget after queued work finishes;
  daily limits continue to apply.
- **Batch outcomes:** normal email batches report drafted, sent, failed, skipped and deferred
  records. Confirmed and uncertain outcomes are excluded from automatic reprocessing.
- **Phone Status:** new phone actions use a separate column and preserve email outcomes.
  Historical Called statuses remain unchanged. Gmail API identifiers are recorded as
  `provider_receipt` events in the local state database for confirmed operations.

The staged migration plan and remaining work are in [docs/UPGRADE_PLAN.md](docs/UPGRADE_PLAN.md).
Existing app entry points and mail providers remain available; no new model or mandatory
third-party runtime has been installed for this release.

Activate `.venv` first, or call its Python directly.

### Dice

```bash
python run.py
```

### Outreach

```bash
python outreach_ui.py
```

Do not launch multiple copies against the same local data directory. SQLite protects transactions, but concurrent GUIs can still compete for browser sessions and Excel files.

## Safe first-run procedure

### Dice

1. Use one query, application limit `1`, visible browser mode, and Easy Apply only.
2. Add one resume profile and verify the file opens.
3. Keep AI answer generation disabled.
4. Review the match score and chosen resume.
5. Intentionally leave one required answer unmapped and confirm the bot blocks submission.
6. Add a truthful explicit answer and run the controlled application.
7. Confirm the UI, SQLite ledger, and export show the same terminal outcome.

### Outreach

1. Use an email address you control, `draft` mode, and caps of `1`.
2. Choose an exact resume profile.
3. Paste a synthetic job description.
4. Check To/CC/BCC, subject, body, and visible attachment in the resulting draft.
5. Retry the same record and confirm it is skipped.
6. Test a nonexistent resume and confirm no draft is created.
7. Enable `send` only after the selected provider passes these checks.

## Testing

The default suite is offline and deterministic. It never logs into Dice and never creates or sends a real email.

```powershell
# Windows
.\scripts\test.ps1
```

```bash
# macOS/Linux
./scripts/test.sh
```

Or directly:

```bash
python -m pytest -q
```

The test command runs:

- compilation checks;
- the unit/integration suite and provider dispatch subtests (one JavaScript rule test requires Node);
- both-GUI and core import smoke checks;
- dependency consistency via `pip check`.

`pytest.ini` collects only `tests/`. Historical root and `scratch/` scripts may open browsers, use real services, or expect local files; inspect them before running them manually.

See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for the exact coverage matrix and controlled live checklist.

For the latest audit scope and remaining limitations, use the
[September 17 review](docs/LOOP_AND_LAG_REVIEW.md). Earlier test reports are historical.
The September 17 offline run passed **149 tests and 16 subtests**, compilation,
import smoke checks and dependency checks. Five SWIG deprecation warnings remain.

### Responsiveness and long-running sessions

- Both live log panels retain approximately 2,000 visible lines. Dice's latest-log
  viewer loads at most 256 KiB; use **Open Log Folder** for the complete disk file.
  Existing files and saved outcomes are not truncated by these display limits.
- UI event processing yields between callbacks after a short time budget so
  bursts of updates do not consume an entire large callback batch at once.
- Nvoids coalesces job-list notifications and detects a stopped mail worker
  instead of endlessly waiting for queue space or the next cycle.
- **Pause**, continuous-cycle rests, daily/cycle caps and provider readiness
  checks can intentionally delay work. **Stop** waits for in-flight operations
  to return; it does not mean an immediate browser or network interruption.
- Keep Excel exports closed while running. A locked export is not a reason to
  send an email or submit an application again. Preserve **Unconfirmed / Needs
  Review** outcomes until independently checked.
- First local-model use can take longer than later cached matches. Do not reduce
  readiness/confirmation timeouts just to make the progress display move faster.

The [mail remediation and live-test report](docs/MAIL_REMEDIATION_AND_LIVE_TESTS.md)
documents attachment, recipient, draft-confirmation and formatting fixes, along
with account-specific live blockers. The nine original mail audit failures are
now passing regression tests. Unknown outcomes appear as **Needs review** and are
excluded from automatic retries to avoid duplicate mail. Gmail API needs a Desktop
app OAuth client; Google's automated-browser sign-in rejection is not bypassed.
Do not treat offline tests as approval for unattended sending.

## Operational data and statuses

Runtime data is stored under `data/` and ignored by Git:

- `bot_state.db` — jobs, application attempts, outreach lifecycle, capacity, dedup, runs, and audit events.
- `outreach_dedup.db` — legacy outreach hash/content/cooldown mirror.
- `outreach_jobs.xlsx` — human-readable outreach export and pending-work view.
- Dice Excel/JSON exports — UI reports; filenames depend on the workflow.
- learning/semantic caches — local ranking state.

Outreach reserves capacity before queuing. A confirmed `Draft` or `Sent` consumes capacity and creates dedup state. A failed or skipped action releases the reservation. Stale reservations are recovered on a later startup after the configured timeout.

The dashboard’s **Mark All Drafted** and **Mark All Sent** buttons are metadata corrections only. They never create or send messages. After confirmation, they update eligible rows with valid recipients and skip call-only, missing-email, skipped, and already matching records. Use them only after independently verifying the mailbox state.

Never edit SQLite files while a bot is running. Close Excel exports before operations that need to rewrite them.

## Security and GitHub checklist

The `.gitignore` excludes local credentials and runtime artifacts, including:

- `.env` and local settings;
- Gmail OAuth client/token files;
- browser profiles, cookies, sessions, and history;
- databases, spreadsheets, logs, screenshots, captured HTML, and model caches.
- local `backups/`, `scratch/` and `.claude/` directories.

Before pushing:

1. Confirm only `.example` configuration files are intended for publication.
2. Search the files being published for API keys, OAuth tokens, passwords, email addresses, resume paths, and candidate PII.
3. Do not publish `chrome_profile*`, `config/gmail_*.json`, local JSON settings, database files, spreadsheets, debug HTML, or screenshots.
4. If a secret was ever committed in an earlier repository history, rotate it; `.gitignore` cannot remove history.
5. Add the license you intend to use before making the repository public.
6. Run the complete test script from a clean virtual environment.

## Troubleshooting

### Browser not found

Install Chrome, Brave, or Chromium, or set an absolute `WEB_BROWSER_PATH` in `.env`. Edge, Firefox, and Safari are not supported by the current `webdriver.Chrome` implementation.

### Driver/browser version error

Update the browser, close all automation windows, and retry. `webdriver-manager` may need network access to obtain a compatible driver.

### Dice login, CAPTCHA, or MFA

Run with headless mode off. Complete any manual challenge. Avoid aggressive retry loops; account or site protections are not application defects.

### No eligible resume

Check the profile path, `must_have` list, title boost mode, and `minimum_ats_fit`. The bot intentionally returns no selection instead of attaching a weak or different resume.

### Required application questions remain

Detected unresolved wizard questions are saved automatically in `data/dice_questions.db`. In Dice **Settings → Application Wizard Answers → Review Unanswered Questions**, click **Refresh**, select a question, enter your truthful custom response, and click **Save Answer for Future Applications**. The full question, latest job title/link, and encounter count are retained across restarts; repeated questions share one entry. Saving removes it from the pending list and adds its answer to the existing answer editor. Enable auto-answer to reuse saved responses. If a response cannot fill a later form, the question returns for review.

Required unresolved questions still block submission. Saving an answer does not automatically retry a blocked application; retry it explicitly after reviewing the answer. The queue begins collecting on the next run and does not import historical logs. It covers questions detected by the Dice wizard; external application sites remain outside this flow. Sensitive questions must be answered explicitly; AI generation will not handle them.

### Outreach creates no message

Check the recipient format, exclusion lists, exact resume path, attachment requirement, duplicate/cooldown result, and cap status. The live log and SQLite/Excel status include the reason.

### Gmail API authentication fails

Verify the Gmail API is enabled, the OAuth client is a desktop client, the consent user is allowed, and `config/gmail_client_secret.json` is valid. If Google reports `invalid_grant` or says the token expired or was revoked, click **Connect / Re-authorize Gmail API**. The bot preserves the rejected token as an ignored `.revoked-<timestamp>.bak` file, opens a fresh Google consent flow, and writes a new token after consent succeeds. Normal draft/send runs never open an unexpected authorization browser; they stop with a reconnect instruction instead.

The downloaded `client_secret_....json` belongs in **OAuth Client JSON**. It must not be selected as **Generated Token File**. Keep the generated token at `config/gmail_token.json` (or another new local filename); the bot creates it after Connect / Re-authorize succeeds.

`Error 400: redirect_uri_mismatch` means a Web application client was selected. OAuth client types are not interchangeable: create a new **Desktop app** client, download its JSON, select it in the UI, and reconnect. If the consent app is in Testing, also add the Gmail account under **Google Auth Platform → Audience → Test users**.

### Excel permission error

Close the workbook in Excel. The exporter retries and may create a timestamped backup if the file remains locked.

### Slow first semantic match

The local embedding model may download and initialize on first use. Disable semantic matching if an offline keyword-only startup is preferred.

## Project structure

```text
.
├── run.py                         # Dice GUI entry point
├── app_tkinter.py                 # Dice GUI/orchestration
├── outreach_ui.py                 # Outreach GUI entry point
├── core/
│   ├── main_script.py             # Dice browser/application workflow
│   ├── matcher.py                 # Resume scoring and eligibility
│   ├── application_answers.py     # Explicit/sensitive answer policy
│   ├── application_outcome.py     # Typed outcome classification
│   ├── employment_classifier.py   # C2C/W2/full-time rules
│   ├── state_store.py             # Transactional operational ledger
│   └── outreach/
│       ├── nvoids_scraper.py      # Nvoids collection/filtering
│       ├── outreach_pipeline.py   # Queue, caps, lifecycle, dedup
│       ├── email_engine.py        # Five provider adapters
│       ├── resume_picker.py       # Outreach resume matching
│       ├── dedup_engine.py        # Legacy dedup/cooldown mirror
│       └── excel_store.py         # Human-readable export
├── utils/                         # Config, logging, timing, UI helpers
├── config/                        # Redacted examples + ignored local config
├── scripts/                       # Cross-platform setup/test commands
├── tests/                         # Offline deterministic test suite
├── docs/                          # Test report and roadmap
├── data/                          # Ignored runtime state
└── logs/                          # Ignored runtime logs
```

## Readiness and roadmap

### Nvoids job titles, locations and subjects

The follow-up batch fix recognizes `Title:` and colon-free `Role`/`Location`
labels, separates Nvoids' generated footer geography from recruiter fields,
preserves technical qualifiers after separators, and removes leftover recruiting
phrases and malformed schedule text. Wrapped values stop before unrelated prose.
Unknown locations remain omitted; ambiguous roles remain held. Restart Nvoids to
load code updates. Normal pending-mail processing resolves saved descriptions
again before preparing email; this does not bulk-repair Excel or release existing
Needs Review records.

For a read-only preview of a saved batch (use its UTC start timestamp):

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_nvoids_batch --since 2026-09-23T22:30:00+00:00
```

This writes `data/nvoids_latest_batch_preview.md`, showing proposed subjects with
a name placeholder, not actual drafts. The preview neither imports mail providers
nor changes the database/workbook. Review the source evidence for unclear listings.

New processing resolves job fields **before résumé matching and email preparation**.
Explicit JD fields (`Job Title`, `Position`, `Role`, `Location`, including wrapped
values) take precedence over website headings. Recruiting instructions, rates and
interview requirements are not role titles. Full compound/specialized titles are
retained instead of permanently truncating them at 55 characters.

Explicit JD locations outrank website-generated location labels. Multiple stated
locations remain visible; `Remote, Remote` becomes `Remote`. Missing or conflicting
locations are omitted from the subject rather than guessed. Your existing subject
template and name suffix remain in use. Empty dash separators are cleaned up;
unresolved placeholders and multiline subjects are blocked.

Groq extraction remains a fallback for ambiguous scraper titles. A suggested role
must occur in the source text; conflicting roles cannot be silently selected by AI.
Both bots use the configured `openai/gpt-oss-20b` model on Groq; retired model IDs
must not be reused. A successful key check verifies account/model access, not the
quality of a particular job or résumé match. Routine Nvoids processing can complete
without a Groq call when title extraction is unambiguous. The AI-generated email
body setting remains optional and off by default.
Unresolved titles or invalid subjects receive **Needs Review**, without drafting,
sending or consuming email capacity. These records stay excluded from pending-mail
batches until their source information is corrected and reviewed. There is no new
automatic release/retry action.

Existing workbook history, stored subjects and mailbox messages are not repaired.
Same-listing checks use the original Nvoids job ID across workbook, state and legacy
dedup records, so improved titles or changed URL `uid` values do not make an old
listing eligible again. Existing hashes and uncertain-outcome protections remain.
Future saved descriptions retain up to 30,000 characters; historical truncated
descriptions cannot be reconstructed without retrieving their source.

### Résumé selection in Dice and Nvoids

Both bots rank the same saved résumé profiles. A stated job occupation (for example,
Data Engineer versus Analyst or DevOps) is checked before comparing skills, and
generic keyword lists are capped so a profile with hundreds of terms cannot win
solely by volume. Exact-name priority requires a genuinely close title match;
cloud/vendor specializations without supporting job evidence receive a penalty.
This is a ranking improvement, not proof that a résumé contains every claimed skill.
Review profile names, manually maintained keywords, and the actual résumé files,
especially when no profile matches a niche role. The matcher does not add keywords
to profiles or change résumé documents automatically.

Generate the four-case, read-only before/after preview locally:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_nvoids_subjects
```

The report is written to `data/nvoids_subject_preview.md`. It uses saved descriptions
and recorded subjects from a read-only SQLite connection, never constructs email
workers and never modifies production records. It may contain your personal subject
suffix: review it before sharing. **Saved-description replay is not live-page
verification.** The original four pages were inaccessible during diagnosis.

Regression fixtures cover those same job IDs, wrapped and long titles, multiple
roles/locations, invalid AI output, subject validation, review holds and historical
duplicate protection. Scraper, Auto-Pilot and pending-batch checks use synthetic data
and fake providers; they do not certify a changing live listing or mailbox service.

Validation on 2026-09-23: the full offline suite passed **165 tests and 42 subtests**;
compilation, application imports and `pip check` passed. Five third-party SWIG
deprecation warnings remain. Concurrent-workbook testing also exposed and fixed a
Windows lock-file initialization race; file ownership is still OS-backed and no
age-based lock removal was introduced.

### Dice question matching: MiniLM first, Groq only for ambiguity

Open **Settings → Review Unanswered Questions**. Select a question and enter **Your answer**; the complete question is captured automatically, so there is no pattern to type. **Save answer** stores a user-confirmed answer version. Previously confirmed questions remain available in this window for editing. You can also copy a legacy/confirmed answer from the dropdown, then explicitly save it for the selected question.

Use **Find matching answer**, or **Find matches for existing questions**, to compare saved questions. The order is: approved association → normalized exact wording → local `all-MiniLM-L6-v2` similarity → Groq only for ambiguous candidates. MiniLM runs through the existing FastEmbed/ONNX stack, sharing a serialized model service and the model-aware embedding cache with résumé matching. No new model-training job or dependency is introduced.

- Local score at least **0.85**, with at least **0.08** separation from the next candidate: show a **Local MiniLM** suggestion.
- At least one compatible score of **0.65**, without a clear local winner: optionally ask Groq to choose among at most three saved questions.
- Lower scores, conflicting constraints or unavailable MiniLM: manual entry; no Groq fallback for a missing local model.

Scores rank wording similarity; they are not accuracy percentages. Every new association still requires **Approve match**. **Reject suggestion** persists the rejection. Saved suggestions and errors prevent repeated API calls for unchanged lookups. Library/model/setting changes invalidate the corresponding lookup key. A previously approved association is reused locally with **zero Groq calls**.

**Use Groq only for ambiguous matches** defaults on and can be disabled in the review window. Each lookup uses at most one request, a 12-second timeout, no automatic retries, and a maximum of 20 requests per bulk review. Groq receives question wording, field constraints and candidate question IDs—not saved answer values, résumés or recruiter details. It may select an existing question or return no match; it cannot create the answer used by this feature. No suggestion request is made merely by opening the editor or selecting a row.

Compensation periods/currencies, skill-specific experience, numeric thresholds, employment arrangements, negation and field choices must be compatible. Legal/authorization and location wording is deliberately conservative: changed wording requires a separately confirmed answer rather than inferred equivalence. Missing field context can likewise require manual confirmation. The copy-answer dropdown avoids retyping an existing answer in those cases.

Enable **auto-answer in Settings** to reuse approved answers in application forms. Unknown questions stay in the review queue. With the new `question_matching_enabled` setting enabled (default), unmatched wizard questions do not fall through to the older generated-answer path—even if that older generation option was enabled. AI suggestions do not submit applications. Use **Affected jobs / retry** to explicitly revalidate and retry eligible jobs.

The live Dice wizard now does **no MiniLM or Groq question lookup while filling a form**. It fills exact saved field/constraint answers and associations you approved in the review window; older explicit answer patterns in Settings continue to work as configured. A newly suggested semantic wording remains pending until **Approve match**; the application is blocked if a required field is still unanswered. This fixes the earlier session behavior that could use a suggestion before approval. The review inbox defaults to **Pending review** and can be filtered by category (pay, work authorization, experience, location, profile links, other) or switched to all/approved questions. Categories are organizational labels only; they never authorize an answer.

Optional **Review visible form before Submit** in Dice Settings pauses each application at the final Submit button. It displays current visible field values and attachment filenames in a resizable window, without storing those values in logs. Choose **Submit this application** to proceed, or **Skip this application** to leave it unsubmitted. Closing the review window or a review error skips the submission. The browser page remains available for inspection; custom controls and hidden fields may not appear in the summary, so verify the page itself. This setting is off by default to preserve unattended runs.

Editing a confirmed answer creates a new version and invalidates its other approved associations. Those affected questions return to pending review. Changes to field type/options/required status also prevent blind reuse. Legacy answers remain intact and do not automatically gain new semantic associations.

If a fact changes (for example your desired rate, location, availability or experience), switch the inbox to **All questions**, select the approved question and choose **Require re-confirmation**. This disables that answer version and its linked wording, keeps those questions blocked from older substring mappings, and returns recorded questions to Pending review. Enter a truthful replacement with **Save answer** or approve an appropriate existing answer. There is no automatic age-based expiry: older answer records do not reliably include a confirmation date, so the application does not guess when your circumstances changed.

Answer versions, associations and suggestions are stored locally in the question database using a transactional versioned extension. The first extension creates a `.question-memory-v1.bak` backup. Keep this database, its backup and embedding cache private and out of Git. “Learning” here means remembering your approved associations, not fine-tuning MiniLM.

Offline validation for this update: **142 tests and 16 subtests passed**, including the question editor and existing Tkinter regressions. Compilation and import checks passed. GUI tests require a session where Tcl/Tk can initialize; the restricted sandbox on this PC cannot load `init.tcl`, so the GUI suite was run outside it. Tests use synthetic questions and mocked model/provider responses, not live applications or Groq requests.

### Simplified controls and retained safety

The optional 8 GB modes, unfinished-run resume screens, manual export-retry buttons,
Nvoids readiness/history popup, failed-email-only action and prepared-email approval
workflow have been removed. Old settings for those features no longer control processing.
Use the normal draft/send actions, Jobs & Contacts and provider connection controls.
Dice's semantic matching setting, MiniLM question matching and answer-linked job retries remain.

Existing records, answer memory, approval snapshots and databases are not deleted.
Historical `Awaiting Review` emails remain held rather than being silently released for
sending. Existing `Unconfirmed` outcomes also remain excluded from automatic processing.

Internal OS/file locks, durable outcomes, duplicate prevention, bounded queues and safe
shutdown remain. Normal Nvoids processing still retries pending workbook exports without
repeating successful emails. If a Dice workbook save fails, its application outcomes remain
in the local ledger; do not resubmit applications to repair an export.

Older roadmap/delivery documents describe historical features, not the current controls.

Removal validation: the offline regression suite passes **143 tests and 16 subtests**,
including checks that retired controls are absent, normal workflow handlers remain and
historical approval holds cannot enter a processing batch. No live emails or applications
were used for this validation.

Automated local status as of 2026-09-10: 57 tests plus 3 provider dispatch subtests passed, compilation and both-application imports passed. Both GUIs were constructed in hidden test windows. An isolated Chrome form fixture passed cookie targeting, answer handoff, radio selection, and post-fill checks. Live login and provider behavior still require account-specific validation.

That does not certify changing third-party web interfaces. Complete the provider-specific live checklist before unattended use. The phased follow-up plan, acceptance criteria, CI recommendation, adapter isolation, and operational controls are documented in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).
