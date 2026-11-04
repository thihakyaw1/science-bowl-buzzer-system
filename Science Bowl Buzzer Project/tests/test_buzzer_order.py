import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from science_bowl_buzzer.hardware import Mcp23017InputSource
from science_bowl_buzzer.match import MatchController
from science_bowl_buzzer.storage import Database


class BuzzerChanges(unittest.TestCase):
    def test_all_physical_channels(self):
        expected = {3:1,4:2,11:3,10:4,16:5,15:6,6:7,5:8,
                    1:9,2:10,12:11,9:12,13:13,14:14,8:15,7:16}
        source = Mcp23017InputSource.__new__(Mcp23017InputSource)
        source.address = 0x27
        source.enabled_players = set(range(1,17))
        for active_low in [True, False]:
            source.active_low = active_low
            for old, new in expected.items():
                mask = (0xffff ^ (1 << (old-1))) if active_low else (1 << (old-1))
                class Bus:
                    def read_byte_data(self, address, register):
                        return (mask >> (8 if register == source.GPIOB else 0)) & 255
                source.bus = Bus()
                self.assertEqual(source.read_active_players(), [new])

    def test_two_wrong_advance_with_or_without_timer(self):
        for timed in [False, True]:
            with tempfile.TemporaryDirectory() as directory:
                db = Database(Path(directory)/'test.db')
                try:
                    controller = MatchController(db)
                    if timed: controller.start_timer()
                    controller.buzz(1); controller.wrong()
                    self.assertEqual(db.current_question()['question_number'],1)
                    controller.buzz(2); controller.wrong()
                    self.assertEqual(db.current_question()['question_number'],2)
                    self.assertFalse(controller.timer.running)
                    self.assertIsNone(controller.pending)
                    payload = db.game_payload()
                    self.assertEqual(len(payload['attempts']),2)
                    self.assertEqual(payload['questions'][0]['final_result'],'Wrong')
                    self.assertEqual([a['interrupt'] for a in payload['attempts']],[not timed]*2)
                    controller.buzz(3)
                    self.assertEqual(controller.pending.player_id,3)
                    self.assertEqual(db.current_question()['question_number'],2)
                finally: db.close()

if __name__ == '__main__': unittest.main()
