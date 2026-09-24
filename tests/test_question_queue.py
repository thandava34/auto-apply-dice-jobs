import tempfile
import unittest
from pathlib import Path
from core.question_queue import QuestionQueue


class QuestionQueueTests(unittest.TestCase):
    def test_persistent_capture_dedup_resolution_and_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.db'
            queue = QuestionQueue(path)
            field = 'input: "How many years of Python experience?"'
            queue.capture([field, field], 'Engineer', 'https://example.test/1')
            queue = QuestionQueue(path)
            queue.capture([field], 'Senior Engineer', 'https://example.test/2')
            rows = queue.pending()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['occurrences'], 2)
            self.assertEqual(rows[0]['job_title'], 'Senior Engineer')
            queue.resolve(rows[0]['pattern'])
            self.assertEqual(QuestionQueue(path).pending(), [])
            queue.capture([field])
            self.assertEqual(len(queue.pending()), 1)

    def test_mismatched_answer_is_not_part_of_question_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = QuestionQueue(Path(directory) / 'queue.db')
            question = 'Are you authorized to work in the country where this position is based, without further restrictions?'
            queue.capture([f'radio (no match): "{question}" → "Yes"'])
            row = queue.pending()[0]
            self.assertEqual(row['question'], question)
            self.assertEqual(row['pattern'], question.lower())

    def test_separate_connections_preserve_distinct_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.db'
            first, second = QuestionQueue(path), QuestionQueue(path)
            first.capture(['select: "Preferred location?"'])
            second.capture(['input: "Start date?"'])
            self.assertEqual(len(first.pending()), 2)
