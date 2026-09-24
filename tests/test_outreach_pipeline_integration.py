import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.outreach.outreach_pipeline import OutreachPipeline


class _FakeEmailEngine:
    def __init__(self, result="Draft"):
        self.result = result
        self.calls = []
        self.logs = []

    def send_email(self, job_record, resume_path, email_body, subject):
        self.calls.append({
            "job": dict(job_record),
            "resume_path": resume_path,
            "body": email_body,
            "subject": subject,
        })
        return self.result

    def log(self, message):
        self.logs.append(str(message))


class OutreachPipelineIntegrationTests(unittest.TestCase):
    def _make_pipeline(self, directory, daily_cap=10):
        resume_path = os.path.join(directory, "data-engineer.pdf")
        with open(resume_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n% deterministic test resume\n")

        config = {
            "target_resume": "Data Engineer",
            "send_mode": "draft",
            "email_provider": "gmail_api",
            "daily_cap": daily_cap,
            "cycle_cap": 10,
            "cooldown_hours": 48,
            "require_resume_attachment": True,
            "state_db_path": os.path.join(directory, "state.db"),
            "dedup_db_path": os.path.join(directory, "dedup.db"),
            "outreach_excel_path": os.path.join(directory, "outreach.xlsx"),
            "subject_template": "Application: {job_title}",
            "template": "Hello {recruiter_name}, applying for {job_title} at {company}.",
        }
        pipeline = OutreachPipeline(
            config,
            [{
                "id": "data",
                "name": "Data Engineer",
                "file_path": resume_path,
                "keywords": ["python", "etl"],
                "unique_keywords": ["airflow"],
            }],
        )
        fake = _FakeEmailEngine()
        pipeline.email_engine = fake
        return pipeline, fake, resume_path

    @staticmethod
    def _job(suffix="1"):
        return {
            "Job Title": f"Data Engineer {suffix}",
            "Company": "Example Corp",
            "Location": "Remote",
            "URL": f"https://jobs.example.test/{suffix}",
            "Recruiter Name": "Recruiter",
            "Recruiter Email": f"recruiter{suffix}@example.test",
            "Description": "Contract data engineering role using Python, Airflow and ETL.",
        }

    def test_job_to_draft_records_exact_resume_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, resume_path = self._make_pipeline(directory)
            try:
                self.assertEqual(pipeline.process_job(self._job()), "Queued for Background Draft")
                pipeline.email_queue.join()
                self.assertEqual(len(fake.calls), 1)
                self.assertEqual(fake.calls[0]["resume_path"], resume_path)

                conn = sqlite3.connect(pipeline.state.db_path)
                try:
                    row = conn.execute(
                        "SELECT status,resume_path FROM outreach_messages"
                    ).fetchone()
                finally:
                    conn.close()
                self.assertEqual(row, ("draft", resume_path))
                self.assertEqual(pipeline.process_job(self._job()), "Skipped (Duplicate)")
            finally:
                pipeline.shutdown()

    def test_daily_cap_defers_second_unique_message(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory, daily_cap=1)
            try:
                self.assertEqual(pipeline.process_job(self._job("1")), "Queued for Background Draft")
                pipeline.email_queue.join()
                self.assertEqual(pipeline.process_job(self._job("2")), "Pending (Daily Cap)")
                self.assertEqual(len(fake.calls), 1)
            finally:
                pipeline.shutdown()

    def test_new_extraction_in_autopilot_and_pending_batch(self):
        import json
        from pathlib import Path
        cases = json.loads((Path(__file__).parent / 'fixtures/nvoids_subject_cases.json').read_text())
        for batch in (False, True):
            with self.subTest(batch=batch), tempfile.TemporaryDirectory() as directory:
                pipeline, fake, _ = self._make_pipeline(directory)
                pipeline.config['email_provider'] = 'outlook_web'
                try:
                    for case in cases:
                        job = self._job(case['id'])
                        job.update({'Job Title':case['old_title'], 'Description':case['description'],
                                    'Original Title':case['headline'], 'URL':case['url']})
                        pipeline.process_job(job, skip_email=batch)
                    if batch:
                        pipeline.excel.flush()
                        pipeline.process_pending_emails()
                    else:
                        pipeline.email_queue.join()
                    self.assertEqual(len(fake.calls), 4)
                    self.assertEqual({c['job']['Job Title'] for c in fake.calls}, {c['title'] for c in cases})
                finally:
                    pipeline.shutdown()

    def test_bad_role_and_subject_never_reach_provider_or_consume_capacity(self):
        for bad_template in (False, True):
            with self.subTest(template=bad_template), tempfile.TemporaryDirectory() as directory:
                pipeline, fake, _ = self._make_pipeline(directory)
                try:
                    job = self._job('review')
                    if bad_template:
                        pipeline.config['subject_template'] = 'Apply {unknown}'
                    else:
                        job['Job Title'] = 'Only'
                    self.assertTrue(pipeline.process_job(job).startswith('Needs Review:'))
                    self.assertEqual(fake.calls, [])
                    self.assertEqual(pipeline._today_reserved, 0)
                    pipeline.excel.flush()
                    self.assertEqual(pipeline.process_pending_emails().selected, 0)
                finally:
                    pipeline.shutdown()

    def test_same_old_listing_with_changed_title_uid_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            try:
                job = self._job('old')
                job.update({'URL':'https://jobs.nvoids.com/job_details.jsp?id=123&uid=old',
                            'Job Title':'Locals Only', 'Dedup Hash':'legacy', 'Status':'Draft', 'Email Sent?':'Drafted'})
                pipeline.excel.export_record(job)
                updated = dict(job, **{'URL':'https://jobs.nvoids.com/job_details.jsp?id=123&uid=new', 'Job Title':'Machine Learning Engineer'})
                self.assertEqual(pipeline.process_job(updated), 'Skipped (Duplicate)')
                self.assertEqual(fake.calls, [])
                pipeline.state.upsert_job('state-only', 'nvoids', {'URL':'https://jobs.nvoids.com/job_details.jsp?id=456&uid=old'})
                updated['URL'] = 'https://jobs.nvoids.com/job_details.jsp?id=456&uid=new'
                self.assertEqual(pipeline.process_job(updated), 'Skipped (Duplicate)')
                pipeline.dedup.log_sent_job('legacy@example.test', 'Example', 'Rate', '', 'https://jobs.nvoids.com/job_details.jsp?id=789&uid=old')
                updated['URL'] = 'https://jobs.nvoids.com/job_details.jsp?id=789&uid=new'
                self.assertEqual(pipeline.process_job(updated), 'Skipped (Duplicate)')
            finally:
                pipeline.shutdown()

    def test_scraper_uses_jd_fields_before_pipeline_without_ai_for_clear_roles(self):
        import json
        from pathlib import Path
        from unittest.mock import Mock
        from core.outreach.nvoids_scraper import NvoidsScraper
        cases = json.loads((Path(__file__).parent / 'fixtures/nvoids_subject_cases.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            try:
                scraper = NvoidsScraper.__new__(NvoidsScraper)
                scraper.pipeline, scraper.driver = pipeline, Mock()
                scraper._ai = Mock()
                scraper._dedup_db = scraper._skill_ranker = None
                scraper.skip_flag = scraper.skip_email = False
                scraper._effective_max_hours = 24
                scraper.excluded_vendor_domains = scraper.exclude_keywords = []
                scraper.my_core_skills = []
                scraper.min_match_score = 0
                scraper.phone_callback = None
                scraper.log = scraper._safe_get = Mock()
                scraper._extract_company = lambda _: 'Example Corp'
                for case in cases:
                    scraper.driver.find_element.return_value.text = case['description'] + '\n\nEmail: recruiter@example.test'
                    with patch('core.outreach.nvoids_scraper._is_fresh', return_value=True), patch('core.outreach.nvoids_scraper._human_read_scroll'):
                        status = scraper._process_job_page(case['headline'], case['url'], set())
                    self.assertEqual(status, 'Queued for Background Draft', scraper.log.call_args_list)
                pipeline.email_queue.join()
                self.assertEqual(len(fake.calls), 4)
                self.assertEqual({c['job']['Job Title'] for c in fake.calls}, {c['title'] for c in cases})
                scraper._ai.extract.assert_not_called()
            finally:
                pipeline.shutdown()

    def test_dead_email_worker_stops_producer_before_queue_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            try:
                with patch.object(pipeline.email_thread, 'is_alive', return_value=False):
                    with self.assertRaisesRegex(RuntimeError, 'Email worker stopped'):
                        pipeline.process_job(self._job('dead-worker'))
                self.assertEqual(fake.calls, [])
                self.assertEqual(pipeline.email_queue.unfinished_tasks, 0)
            finally:
                pipeline.shutdown()

    def test_missing_fixed_profile_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _ = self._make_pipeline(directory)
            try:
                pipeline.target_resume_name = "Profile That Does Not Exist"
                self.assertIsNone(pipeline._pick_profile("Data Engineer", "Python"))
            finally:
                pipeline.shutdown()

    def test_cycle_reset_updates_persisted_budget_and_keeps_daily_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory, daily_cap=2)
            pipeline.cycle_cap = 1
            try:
                pipeline.process_job(self._job('1'))
                pipeline.email_queue.join()
                old_run = pipeline.run_id
                self.assertEqual(pipeline.process_job(self._job('2')), 'Pending (Cycle Cap)')
                pipeline.start_new_cycle()
                self.assertNotEqual(old_run, pipeline.run_id)
                self.assertEqual(pipeline.process_job(self._job('3')), 'Queued for Background Draft')
                pipeline.email_queue.join()
                pipeline.start_new_cycle()
                self.assertEqual(pipeline.process_job(self._job('4')), 'Pending (Daily Cap)')
                self.assertEqual(len(fake.calls), 2)
            finally:
                pipeline.shutdown()

    def test_preflight_blocks_batch_without_changing_pending_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            try:
                pipeline.process_job(self._job('1'), skip_email=True)
                pipeline.excel.flush()
                with patch.object(pipeline, 'preflight', return_value=['Account not connected']):
                    result = pipeline.process_pending_emails(log_ui=lambda *_: None)
                self.assertEqual((result.selected, result.deferred, result.failed), (1, 1, 0))
                self.assertEqual(fake.calls, [])
            finally:
                pipeline.shutdown()

    def test_phone_updates_preserve_email_success(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _ = self._make_pipeline(directory)
            try:
                pipeline.process_job(self._job())
                pipeline.email_queue.join()
                pipeline.excel.flush()
                before = pd.read_excel(pipeline.excel.filepath)
                key = before.iloc[0]['Dedup Hash']
                pipeline.excel.update_phone_status(key, 'Called (test)')
                after = pd.read_excel(pipeline.excel.filepath)
                self.assertEqual(after.iloc[0]['Status'], 'Draft')
                self.assertEqual(after.iloc[0]['Email Sent?'], 'Drafted')
                self.assertEqual(after.iloc[0]['Phone Status'], 'Called (test)')
            finally:
                pipeline.shutdown()

    def test_removed_review_workflow_does_not_release_historical_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            pipeline.config['review_before_processing'] = True  # Legacy saved setting
            try:
                record = self._job('held')
                record.update({'Dedup Hash': 'historical-held',
                               'Status': 'Awaiting Review', 'Email Sent?': 'No'})
                pipeline.excel.export_record(record)
                self.assertEqual(pipeline.process_pending_emails().selected, 0)
                self.assertEqual(fake.calls, [])
            finally:
                pipeline.shutdown()

    def test_batch_retry_counts_and_dedup(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            pipeline.config['email_provider'] = 'outlook_web'
            pipeline.cycle_cap = 1
            try:
                pipeline.process_job(self._job('1'), skip_email=True)
                pipeline.process_job(self._job('2'), skip_email=True)
                pipeline.excel.flush()
                result = pipeline.process_pending_emails(log_ui=lambda *_: None)
                self.assertEqual((result.selected, result.drafted, result.deferred), (2, 1, 1))
                result = pipeline.process_pending_emails(log_ui=lambda *_: None)
                self.assertEqual((result.selected, result.drafted), (1, 1))
                self.assertEqual(len(fake.calls), 2)
                self.assertEqual(pipeline.process_pending_emails().selected, 0)
            finally:
                pipeline.shutdown()

    def test_uncertain_batch_stops_and_is_excluded_from_automatic_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, fake, _ = self._make_pipeline(directory)
            pipeline.config["email_provider"] = "outlook_web"
            fake.result = "Unconfirmed: provider response lost"
            try:
                pipeline.process_job(self._job("review"), skip_email=True)
                pipeline.excel.flush()
                result = pipeline.process_pending_emails()
                self.assertEqual(result.unconfirmed, 1)
                self.assertEqual(result.sent + result.drafted, 0)
                self.assertEqual(pipeline.process_pending_emails().selected, 0)
                self.assertEqual(len(fake.calls), 1)
            finally:
                pipeline.shutdown()

    def test_bulk_mark_drafted_and_sent_synchronizes_excel_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _ = self._make_pipeline(directory)
            try:
                self.assertEqual(pipeline.process_job(self._job("bulk"), skip_email=True), "Pending Sending")
                changed, failures = pipeline.mark_all_email_status("draft")
                self.assertEqual((changed, failures), (1, 0))

                conn = sqlite3.connect(pipeline.state.db_path)
                try:
                    status = conn.execute("SELECT status FROM outreach_messages").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(status, "draft")

                self.assertEqual(pipeline.mark_all_email_status("draft"), (0, 0))
                self.assertEqual(pipeline.mark_all_email_status("sent"), (1, 0))

                import pandas as pd
                frame = pd.read_excel(pipeline.excel.filepath, engine="openpyxl")
                self.assertEqual(frame.iloc[0]["Status"], "Sent")
                self.assertEqual(frame.iloc[0]["Email Sent?"], "Yes")
            finally:
                pipeline.shutdown()


if __name__ == "__main__":
    unittest.main()
