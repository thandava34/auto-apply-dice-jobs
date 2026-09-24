"""Read-only saved-description replay. No providers, pipeline or workbook imports.

Run: python -m scripts.preview_nvoids_subjects
Only the requested Markdown report is written; local source data is opened read-only.
"""
import argparse
import json
import re
import sqlite3
from pathlib import Path
from core.outreach.job_fields import resolve_job_fields, render_subject

IDS = ('3703592', '3703219', '3703724', '3702571')


def replay(db_path, subject_template):
    found = {}
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        for subject, payload in connection.execute('SELECT subject,payload_json FROM outreach_messages ORDER BY updated_at DESC'):
            record = json.loads(payload)
            description = record.get('Description', '')
            match = re.search(r'https://jobs\.nvoids\.com/job_details\.jsp\?id=(' + '|'.join(IDS) + r')\b[^\s]*', description)
            if not match or match[1] in found:
                continue
            fields = resolve_job_fields(record.get('Job Title', ''), description, record.get('Location', ''))
            values = {'company':record.get('Company',''), 'company_name':record.get('Company',''),
                      'keywords':record.get('Keywords',''), 'recruiter_name':record.get('Recruiter Name','')}
            try:
                proposed = render_subject(subject_template, fields, values)
            except ValueError as exc:
                proposed = 'NEEDS REVIEW: ' + str(exc)
            found[match[1]] = {'url':match[0], 'old_subject':subject, 'new_subject':proposed, **fields.__dict__}
    finally:
        connection.close()
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-db', default='data/bot_state.db')
    parser.add_argument('--settings', default='config/outreach_settings.json')
    parser.add_argument('--output', default='data/nvoids_subject_preview.md')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.suffix.lower() != '.md' or output in {Path(args.state_db).resolve(), Path(args.settings).resolve()}:
        parser.error('Output must be a separate Markdown report')
    config = json.loads(Path(args.settings).read_text(encoding='utf-8-sig'))
    results = replay(args.state_db, config.get('subject_template', 'Application for {job_title}'))
    lines = ['# Nvoids subject preview', '', '**Saved-description replay — not live-page verified.**',
             'The four links were inaccessible to the web reader during diagnosis. No mailbox actions or source-record edits were performed.', '',
             'This local report contains your configured subject suffix. Do not publish it without reviewing personal information.', '']
    for key in IDS:
        row = results.get(key)
        lines += ['## Job ' + key, '']
        if not row:
            lines += ['No saved evidence found; not tested.', '']
            continue
        for label, field in [('Original URL','url'), ('Recorded subject','old_subject'), ('Proposed subject','new_subject'),
                             ('Resolved title','title'), ('Resolved location','location'), ('Title evidence','title_evidence'),
                             ('Location evidence','location_evidence'), ('Review reason','review_reason'), ('Location note','location_issue')]:
            lines += [f"- {label}: {str(row[field]).replace(chr(10), ' ') or 'None'}"]
        lines += ['']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Saved-description replay: {len(results)}/4 cases. Report: {output}')


if __name__ == '__main__':
    main()
