"""Read-only replay of a saved Nvoids batch; no providers or workbook writes."""
import argparse
import json
import sqlite3
from pathlib import Path
from core.outreach.job_fields import resolve_job_fields, render_subject


def replay(path, since):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        records = connection.execute(
            'SELECT title,payload_json,url FROM jobs WHERE source=? AND first_seen_at>=? ORDER BY first_seen_at',
            ('nvoids', since)).fetchall()
        result = []
        for old_title, payload, url in records:
            record = json.loads(payload)
            fields = resolve_job_fields(record.get('Original Title') or old_title,
                                        record.get('Description', ''), record.get('Location', ''))
            subject = ('HELD: ' + fields.review_reason if fields.review_reason else
                       render_subject('Application for {job_title} - {location} - [your configured name]', fields, {}))
            result.append((old_title, url, fields, subject))
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True, help='UTC ISO timestamp of batch start')
    parser.add_argument('--state-db', default='data/bot_state.db')
    parser.add_argument('--output', default='data/nvoids_latest_batch_preview.md')
    args = parser.parse_args()
    output = Path(args.output)
    if output.suffix.lower() != '.md':
        parser.error('Output must be a separate Markdown report')
    rows = replay(args.state_db, args.since)
    held = sum(bool(fields.review_reason) for _, _, fields, _ in rows)
    missing = sum(not fields.location and not fields.review_reason for _, _, fields, _ in rows)
    lines = ['# Nvoids saved-batch replay', '',
             'Saved-description replay only; no live pages or mailbox operations. Source records unchanged.',
             'Subjects below are previews, not recorded drafts. The configured name suffix is represented by a placeholder.',
             'Existing review-held records remain held even if this replay finds a role.', '',
             f'{len(rows)} records; {held} unresolved roles; {missing} resolved roles without a reliable location.', '']
    for old, url, fields, subject in rows:
        lines += [f'## {old}', '', f'- Source: {url}', f'- Resolved title: {fields.title or "Needs Review"}',
                  f'- Location: {fields.location or "Omitted"}', f'- Proposed subject: {subject}',
                  f'- Title evidence: {fields.title_evidence}', f'- Location evidence: {fields.location_evidence}',
                  f'- Note: {fields.review_reason or fields.location_issue or "None"}', '']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{len(rows)} records; {held} unresolved roles; {missing} unresolved locations. Report: {output}')


if __name__ == '__main__':
    main()
