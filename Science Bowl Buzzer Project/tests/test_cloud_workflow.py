import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from science_bowl_buzzer.storage import Database
from science_bowl_buzzer.match import MatchController
from science_bowl_buzzer.jobs import BackgroundJobs
from science_bowl_buzzer.subject_infer import infer_subjects_from_pdf, infer_subjects_from_text


class CloudWorkflow(unittest.TestCase):
    def test_real_pdfs(self):
        fixtures = Path(__file__).parent / 'fixtures'
        first = infer_subjects_from_pdf(str(fixtures / 'round1.pdf'))
        second = infer_subjects_from_pdf(str(fixtures / 'RegionalHS_13A.pdf'))
        self.assertEqual(len(first), 25)
        self.assertEqual(first[25], 'Biology')
        expected = ['Biology','Energy','Math','Chemistry','Earth And Space Science','Physics',
                    'Energy','Biology','Chemistry','Math','Earth And Space Science','Physics',
                    'Biology','Earth And Space Science','Math','Chemistry','Physics',
                    'Earth And Space Science','Energy','Math','Physics','Biology','Chemistry']
        self.assertEqual(list(second.values()), expected)

    def test_duplicate_round_rejected_and_bonus_ignored(self):
        text = 'TOSS-UP 1) BIOLOGY Short Answer\nBONUS 1) CHEMISTRY Short Answer'
        self.assertEqual(infer_subjects_from_text(text), {1:'Biology'})
        with self.assertRaises(ValueError):
            infer_subjects_from_text(text + '\n' + text)

    def test_identity_snapshot_and_all_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / 'test.db')
            roster = [{'port':i,'person_id':f'person-{i}','name':f'Name {i}'} for i in range(1,17)]
            db.set_roster(roster)
            controller = MatchController(db)
            db.set_subjects({1:'Biology',2:'Math'})
            controller.buzz(1)
            roster[0]['name'] = 'Renamed'
            db.set_roster(roster)
            controller.wrong()
            controller.buzz(2); controller.wrong()
            self.assertEqual(db.current_question()['subject'], 'Math')
            controller.buzz(3); controller.correct()
            payload = db.game_payload()
            self.assertEqual(len(payload['attempts']), 3)
            self.assertEqual(payload['attempts'][0]['player_name'], 'Name 1')
            self.assertTrue(payload['attempts'][0]['interrupt'])
            self.assertEqual(payload['missing_subjects'], [])
            self.assertEqual(payload['game_key'], db.game_payload()['game_key'])
            first_round = payload['round_id']
            db.new_round('Next')
            self.assertEqual(db.game_payload(first_round)['attempts'], payload['attempts'])
            db.close()

    def test_network_completion_keeps_sqlite_on_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / 'test.db')
            jobs = BackgroundJobs()
            def work():
                time.sleep(.03)
                return 'done'
            job = jobs.start(work, lambda value: db.set_setting('completed',value))
            self.assertEqual(jobs.get(job['job_id'])['status'], 'running')
            with self.assertRaises(ValueError):
                jobs.start(work)
            deadline = time.monotonic()+2
            while jobs.get(job['job_id'])['status']=='running' and time.monotonic()<deadline:
                time.sleep(.005)
            self.assertEqual(jobs.get(job['job_id'])['status'], 'done')
            self.assertEqual(db.get_setting('completed'), 'done')
            jobs.close(); db.close()

if __name__ == '__main__':
    unittest.main()
