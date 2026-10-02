import unittest
from unittest.mock import MagicMock, call, patch

from src.task.BaseWWTask import BaseWWTask


class TestTurningAndNavigationLogic(unittest.TestCase):

    def setUp(self):
        self.task = BaseWWTask.__new__(BaseWWTask)
        self.task.send_key_down = MagicMock()
        self.task.send_key_up = MagicMock()
        self.task.send_key = MagicMock()
        self.task.mouse_down = MagicMock()
        self.task.mouse_up = MagicMock()
        self.task.middle_click = MagicMock()
        self.task.sleep = MagicMock()
        self.task.log_info = MagicMock()
        self.task.log_debug = MagicMock()
        self.task.turn_direction = MagicMock()

    def test_navigate_straight_ahead(self):
        # Angle within +/- 12 degrees
        direction, adjust, should_continue = self.task._navigate_based_on_angle(5, None, None)
        self.assertEqual(direction, 'w')
        self.assertIsNone(adjust)
        self.assertFalse(should_continue)
        self.task.send_key_down.assert_called_with('w')
        self.task.mouse_down.assert_called_with(key='right')

    def test_navigate_straight_ahead_cleans_up_adjust(self):
        direction, adjust, should_continue = self.task._navigate_based_on_angle(-3, 'w', 'a')
        self.assertEqual(direction, 'w')
        self.assertIsNone(adjust)
        self.assertFalse(should_continue)
        self.task.send_key_up.assert_called_with('a')

    def test_navigate_minor_curve_right(self):
        # Angle 25 degrees (between 12 and 40)
        direction, adjust, should_continue = self.task._navigate_based_on_angle(25, 'w', None)
        self.assertEqual(direction, 'w')
        self.assertEqual(adjust, 'd')
        self.assertFalse(should_continue)
        self.task.send_key_down.assert_called_with('d')
        self.task.middle_click.assert_called_with(down_time=0.05, interval=0.8)

    def test_navigate_minor_curve_left(self):
        # Angle -20 degrees (between -40 and -12)
        direction, adjust, should_continue = self.task._navigate_based_on_angle(-20, 'w', None)
        self.assertEqual(direction, 'w')
        self.assertEqual(adjust, 'a')
        self.assertFalse(should_continue)
        self.task.send_key_down.assert_called_with('a')
        self.task.middle_click.assert_called_with(down_time=0.05, interval=0.8)

    def test_navigate_major_turn_right(self):
        # Angle 75 degrees (> 40 and <= 130) -> should NOT be trapped in minor adjust!
        direction, adjust, should_continue = self.task._navigate_based_on_angle(75, 'w', 'd')
        self.assertEqual(direction, 'w')
        self.assertIsNone(adjust)
        self.assertFalse(should_continue)
        # Should clean up previous adjust and movement
        self.task.send_key_up.assert_has_calls([call('d'), call('w')], any_order=True)
        self.task.mouse_up.assert_called_with(key='right')
        # Should execute active turn
        self.task.turn_direction.assert_called_with('d')
        # Should resume forward sprint
        self.task.send_key_down.assert_called_with('w')
        self.task.mouse_down.assert_called_with(key='right')

    def test_navigate_major_turn_left(self):
        # Angle -90 degrees
        direction, adjust, should_continue = self.task._navigate_based_on_angle(-90, 'w', None)
        self.assertEqual(direction, 'w')
        self.assertIsNone(adjust)
        self.task.turn_direction.assert_called_with('a')

    def test_navigate_major_turn_around(self):
        # Angle 170 degrees (behind character)
        direction, adjust, should_continue = self.task._navigate_based_on_angle(170, 'w', None)
        self.assertEqual(direction, 'w')
        self.assertIsNone(adjust)
        self.task.turn_direction.assert_called_with('s')

    def test_stop_movement_releases_direction_and_adjust(self):
        self.task._stop_movement('w', 'd')
        self.task.mouse_up.assert_called_with(key='right')
        self.task.send_key_up.assert_has_calls([call('w'), call('d')])

    def test_turn_direction_active_holding(self):
        real_task = BaseWWTask.__new__(BaseWWTask)
        real_task.send_key_down = MagicMock()
        real_task.send_key_up = MagicMock()
        real_task.middle_click = MagicMock()
        real_task.sleep = MagicMock()
        real_task.center_camera = MagicMock()

        # Turn 'd'
        real_task.turn_direction('d')
        real_task.send_key_down.assert_called_with('d')
        real_task.middle_click.assert_called_with(down_time=0.08)
        real_task.send_key_up.assert_called_with('d')

        # Turn 's'
        real_task.send_key_down.reset_mock()
        real_task.send_key_up.reset_mock()
        real_task.middle_click.reset_mock()
        real_task.turn_direction('s')
        real_task.send_key_down.assert_called_with('s')
        real_task.middle_click.assert_called_with(down_time=0.08)
        real_task.send_key_up.assert_called_with('s')

        # Turn 'w'
        real_task.turn_direction('w')
        real_task.center_camera.assert_called_once()

    def test_yolo_find_echo_turns_quadrants_when_turn_true(self):
        real_task = BaseWWTask.__new__(BaseWWTask)
        real_task.pick_echo = MagicMock(return_value=False)
        real_task.box_of_screen = MagicMock()
        real_task.calculate_color_percentage = MagicMock(return_value=0.0)
        real_task.log_debug = MagicMock()
        real_task.log_info = MagicMock()
        real_task.turn_direction = MagicMock()
        real_task.center_camera = MagicMock()

        # No echos in all 4 quadrants
        real_task.find_echos = MagicMock(return_value=[])
        found, has_more = real_task.yolo_find_echo(turn=True)
        self.assertFalse(found)
        # Should have turned left 3 times to check quadrants 1, 2, 3
        self.assertEqual(real_task.turn_direction.call_count, 3)
        real_task.turn_direction.assert_has_calls([call('a'), call('a'), call('a')])
        real_task.center_camera.assert_called_once()


if __name__ == '__main__':
    unittest.main()
