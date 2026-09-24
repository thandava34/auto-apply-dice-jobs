import json
from pathlib import Path
import unittest

from core.outreach.job_fields import clean_title, resolve_job_fields, render_subject, listing_identity

CASES = json.loads((Path(__file__).parent / 'fixtures/nvoids_subject_cases.json').read_text())


class JobFieldTests(unittest.TestCase):
    def test_latest_batch_formats_and_footer_provenance(self):
        cases = [
            ('Job Openings for Data Snowflake Engineer', 'Role Data Snowflake Engineer\nLocation Austin, TX(Remote for EST zone)', 'Data Snowflake Engineer', 'Austin, TX (Remote for EST zone)'),
            ('Lead Data Engineer in Remote', 'Location: Remote', 'Lead Data Engineer', 'Remote'),
            ('Senior Informatica ETL/Data Engineer (Locals Only)', 'Title: Senior Informatica ETL/Data Engineer (Locals Only)\nLocation: Austin, TX (Hybrid)', 'Senior Informatica ETL/Data Engineer', 'Austin, TX (Hybrid)'),
            ('Machine Learning Evaluation Engineer required in CA', 'POSITION\nTitle: Machine Learning Evaluation Engineer\nLocation: Cupertino CA', 'Machine Learning Evaluation Engineer', 'Cupertino CA'),
            ('Agentic AI Engineer', 'Location: New York (\n5 Days Onsite from Day 1)', 'Agentic AI Engineer', 'New York (Onsite)'),
            ('Java Developer', 'Job Title: Java Developer\nLocation: Houston, TX\nContract\nJAVA MICROSERVICES\nPRINCIPAL ARCHITECT', 'Java Developer', 'Houston, TX'),
            ('AI Engineer', 'Role: AI Engineer\nLocation: Corona, CA (Onsite)\nOnly and\nNeed someone with experience', 'AI Engineer', 'Corona, CA (Onsite)'),
            ('Full Stack AI Engineer, Charlotte NC Onsite', '', 'Full Stack AI Engineer', 'Charlotte NC'),
            ('Data Engineer', 'Location: onsite - Irvine ,CA', 'Data Engineer', 'Irvine, CA (Onsite)'),
        ]
        for headline, body, title, location in cases:
            with self.subTest(headline=headline):
                fields = resolve_job_fields(headline, body + '\n\nTo remove this job post send "job_kill"\nLocation: Wrong, State')
                self.assertEqual((fields.title, fields.location, fields.review_reason), (title, location, ''))

    def test_specializations_and_cleanup_are_stable(self):
        for original, expected in [
            ('Data Engineer - MDM (Profisee Must to have)', 'Data Engineer - MDM (Profisee Must to have)'),
            ('Data Integration Engineer - Alteryx / AWS Glue', 'Data Integration Engineer - Alteryx / AWS Glue'),
            ('Senior Data Engineer - (Machine Learning + MLOps) - W2', 'Senior Data Engineer - (Machine Learning + MLOps)'),
            ('IT Software Engineer - AI / GenAI / Java / AWS (NO )', 'IT Software Engineer - AI / GenAI / Java / AWS'),
            ('AI - Devops Engineer', 'AI - Devops Engineer'),
            ('Senior/Lead AI/ML & Java Engineer (No )', 'Senior/Lead AI/ML & Java Engineer'),
        ]:
            with self.subTest(original=original):
                self.assertEqual(clean_title(original), expected)
                self.assertEqual(clean_title(expected), expected)

    def test_same_four_listing_fixtures(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                fields = resolve_job_fields(case['headline'], case['description'], 'Remote, Remote')
                self.assertFalse(fields.review_reason)
                self.assertEqual(fields.title, case['title'])
                self.assertEqual(fields.location, case['location'])
                self.assertEqual(render_subject('Application for {job_title} - {location} - Test Candidate', fields, {}),
                                 f"Application for {case['title']} - {case['location']} - Test Candidate")

    def test_full_compound_and_specialized_titles_are_idempotent(self):
        for title in ['Agentic AI - Forward deployed engineer', 'ML Engineer / Architect with GCP',
                      'Senior Information Protection & AI Governance Engineer',
                      'Principal Distributed Systems and Generative AI Platform Infrastructure Engineer',
                      'AI Engineer (Databricks Background)', 'Polyglot Software Developer Azure (AI focus)']:
            with self.subTest(title=title):
                self.assertEqual(clean_title(title), title)
                self.assertEqual(clean_title(clean_title(title)), title)

    def test_invalid_and_multiple_roles_stay_pending(self):
        for title in ['Rate', 'Locals Only', '2 Round F2F Interview', '$43/hr C2C', 'Only',
                      'Data Engineer | QA Analyst', 'Principal Data Engineer...']:
            with self.subTest(title=title):
                self.assertTrue(resolve_job_fields(title).review_reason)
        self.assertTrue(resolve_job_fields('Engineer', 'Job Title: Data Engineer\n\nRole: QA Analyst').review_reason)

    def test_location_conflicts_unknown_and_multiple_locations(self):
        fields = resolve_job_fields('Senior AI Native Engineer', 'Role Name: Senior AI Native Engineer\n\nLocation:\nArlington, VA or New York, NY or St. Louis, MO (Hybrid)', 'York, South Carolina')
        self.assertEqual(fields.location, 'Arlington, VA or New York, NY or St. Louis, MO (Hybrid)')
        fields = resolve_job_fields('Data Engineer', 'Location: Austin, TX\n\nLocation: Boston, MA')
        self.assertEqual(fields.location, '')
        self.assertIn('Conflicting', fields.location_issue)
        fields = resolve_job_fields('Data Engineer', 'Home\nData Engineer at Protection, Kansas, USA', 'Protection, Kansas')
        self.assertEqual(fields.location, '')
        self.assertEqual(render_subject('Application for {job_title} - {location} - Test Candidate', fields, {}), 'Application for Data Engineer - Test Candidate')
        self.assertEqual(resolve_job_fields('Data Engineer', location='Remote, Remote').location, 'Remote')
        self.assertEqual(resolve_job_fields('Data Engineer', 'Location: Austin, TX (Hybrid) or Boston, MA').location,
                         'Austin, TX (Hybrid) or Boston, MA')
        self.assertEqual(resolve_job_fields('Rate', 'Job Title:\nSenior Data Engineer\nMust skills: Python').title,
                         'Senior Data Engineer')

    def test_ai_cannot_invent_roles_or_resolve_explicit_conflicts(self):
        for candidate in [None, [], {'job_title': ['Engineer']}, {'job_title': 'Chief AI Engineer'}, {'job_title': 'Engineer\nBCC: stranger@example.test'}]:
            with self.subTest(candidate=candidate):
                self.assertTrue(resolve_job_fields('Only', 'Skills: Python', ai_candidate=candidate).review_reason)
        self.assertTrue(resolve_job_fields('Roles', 'Role: Data Engineer\n\nRole: QA Analyst', ai_candidate={'job_title':'Data Engineer'}).review_reason)
        self.assertTrue(resolve_job_fields('Data Engineer | QA Analyst', ai_candidate={'job_title':'Data Engineer'}).review_reason)

    def test_replay_is_read_only_and_does_not_create_providers(self):
        import sqlite3
        import tempfile
        from scripts.preview_nvoids_subjects import replay
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE outreach_messages(subject,payload_json,updated_at)')
            for case in CASES:
                record = {'Job Title':case['old_title'], 'Description':case['url'] + '\n' + case['description']}
                db.execute('INSERT INTO outreach_messages VALUES(?,?,?)', (case['old_title'], json.dumps(record), '2026-09-23'))
            db.commit()
            db.close()
            before = path.read_bytes()
            rows = replay(path, 'Application for {job_title} - {location} - Test Candidate')
            self.assertEqual(len(rows), 4)
            self.assertEqual(path.read_bytes(), before)

    def test_subject_placeholders_and_linebreaks_are_rejected(self):
        fields = resolve_job_fields('Data Engineer')
        for template in ['Application {unknown}', 'Application\n{job_title}']:
            with self.assertRaises(ValueError):
                render_subject(template, fields, {})
        with self.assertRaises(ValueError):
            render_subject('{job_title} {company}', fields, {'company': 'Example\r\nBCC: bad'})

    def test_uid_does_not_change_listing_identity(self):
        self.assertEqual(listing_identity(CASES[0]['url']), listing_identity('https://jobs.nvoids.com/job_details.jsp?id=3703592&uid=changed'))
