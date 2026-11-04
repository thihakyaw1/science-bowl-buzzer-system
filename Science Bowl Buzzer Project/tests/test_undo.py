import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from science_bowl_buzzer.storage import Database
from science_bowl_buzzer.match import MatchController

class Reset:
    available=True
    def __init__(self): self.pulses=0
    def pulse(self): self.pulses+=1

class UndoTests(unittest.TestCase):
    def test_undo_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'test.db')
            try:
                reset=Reset();c=MatchController(db,reset_output=reset)
                first=db.active_round()['id']
                self.assertFalse(c.undo()['accepted'])
                c.buzz(1);c.correct()
                self.assertEqual(db.current_question()['question_number'],2)
                c.undo()
                self.assertEqual(db.current_question()['question_number'],1)
                self.assertEqual(db.game_payload()['attempts'],[])
                c.buzz(1);c.wrong();c.buzz(2);c.wrong()
                c.undo()
                self.assertEqual(db.current_question()['question_number'],1)
                self.assertEqual(len(db.game_payload()['attempts']),1)
                c.buzz(3);c.undo()
                self.assertIsNone(c.pending)
                self.assertEqual(len(db.game_payload()['attempts']),1)
                c.time_up();c.undo()
                self.assertEqual(db.current_question()['question_number'],1)
                before=reset.pulses;c.delete();self.assertEqual(reset.pulses,before+1)
                c.new_round('Second');second=db.active_round()['id']
                c.buzz(4)
                with self.assertRaises(ValueError):c.load_round(first)
                c.delete();c.load_round(first)
                self.assertEqual(db.active_round()['id'],first)
                self.assertEqual(db.game_payload(second)['attempts'],[])
            finally:db.close()

if __name__=='__main__':unittest.main()
