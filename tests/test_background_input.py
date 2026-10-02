import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import win32con

from ok.device.interaction_methods.post_message import PostMessageInteraction


class TestBackgroundInput(unittest.TestCase):

    def setUp(self):
        self.mock_capture = MagicMock()
        self.mock_capture.width = 1920
        self.mock_capture.height = 1080
        self.mock_hwnd_window = MagicMock()
        self.mock_hwnd_window.hwnd = 12345
        self.mock_hwnd_window.top_hwnd = 12345
        self.mock_hwnd_window.is_foreground.return_value = False
        self.mock_hwnd_window.get_top_window_cords.side_effect = lambda x, y: (x, y)
        self.mock_hwnd_window.hwnds = []

    def tearDown(self):
        pass

    @patch('ok.device.interaction_methods.post_message.win32gui.PostMessage')
    @patch('ok.device.interaction_methods.post_message.win32gui.IsWindow', return_value=True)
    def test_post_message_held_keys_and_heartbeat(self, mock_is_window, mock_post_message):
        interaction = PostMessageInteraction(self.mock_capture, self.mock_hwnd_window)
        try:
            # Key down
            interaction.send_key_down('w')
            self.assertIn('w', interaction.held_keys)

            # Check that initial WM_KEYDOWN was posted
            calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_KEYDOWN]
            self.assertTrue(len(calls) >= 1)

            # Wait for heartbeat to tick (heartbeat runs every 80ms)
            time.sleep(0.2)

            # Heartbeat should have posted WM_SETFOCUS and WM_KEYDOWN with repeat bit
            focus_calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_SETFOCUS]
            self.assertTrue(len(focus_calls) >= 1)

            # Key up
            interaction.send_key_up('w')
            self.assertNotIn('w', interaction.held_keys)
        finally:
            interaction.stop()

    @patch('ok.device.interaction_methods.post_message.win32gui.ClientToScreen', return_value=(500, 600))
    @patch('ok.device.interaction_methods.post_message.win32gui.ScreenToClient', return_value=(500, 600))
    @patch('ok.device.interaction_methods.post_message.win32gui.PostMessage')
    @patch('ok.device.interaction_methods.post_message.win32gui.IsWindow', return_value=True)
    @patch('ok.device.interaction_methods.post_message.ctypes.windll.user32.ClipCursor')
    def test_post_message_mouse_down_and_up_bg(self, mock_clip_cursor, mock_is_window, mock_post_message, mock_s2c, mock_c2s):
        interaction = PostMessageInteraction(self.mock_capture, self.mock_hwnd_window)
        try:
            interaction.mouse_down(500, 600, key='right')
            self.assertIn('right', interaction.held_mouse_buttons)
            self.assertEqual(interaction.held_mouse_buttons['right'], (500, 600))

            # Should post WM_MOUSEACTIVATE in background
            activate_calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_MOUSEACTIVATE]
            self.assertTrue(len(activate_calls) >= 1)

            # Mouse up
            interaction.mouse_up(key='right')
            self.assertNotIn('right', interaction.held_mouse_buttons)

            # ClipCursor(None) should have been called
            mock_clip_cursor.assert_called_with(None)
        finally:
            interaction.stop()

    @patch('ok.device.interaction_methods.post_message.win32gui.PostMessage')
    @patch('ok.device.interaction_methods.post_message.win32gui.IsWindow', return_value=True)
    def test_try_activate_throttling_and_foreground_skip(self, mock_is_window, mock_post_message):
        interaction = PostMessageInteraction(self.mock_capture, self.mock_hwnd_window)
        try:
            # When foreground, try_activate should return immediately without posting
            self.mock_hwnd_window.is_foreground.return_value = True
            mock_post_message.reset_mock()
            interaction.try_activate()
            activate_calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_ACTIVATE]
            self.assertEqual(len(activate_calls), 0)

            # When background, first call should activate
            self.mock_hwnd_window.is_foreground.return_value = False
            interaction._last_activate_time = 0.0
            interaction.try_activate()
            activate_calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_ACTIVATE]
            self.assertEqual(len(activate_calls), 1)

            # Immediate second call should be throttled
            mock_post_message.reset_mock()
            interaction.try_activate()
            activate_calls = [call for call in mock_post_message.call_args_list if call[0][1] == win32con.WM_ACTIVATE]
            self.assertEqual(len(activate_calls), 0)
        finally:
            interaction.stop()

    @patch('ok.device.interaction_methods.post_message.win32gui.PostMessage')
    def test_activate_and_deactivate_messages(self, mock_post_message):
        interaction = PostMessageInteraction(self.mock_capture, self.mock_hwnd_window)
        try:
            mock_post_message.reset_mock()
            interaction.activate(hwnd=12345)
            # Should post WM_ACTIVATE, WM_SETFOCUS, WM_NCACTIVATE
            msg_types = [call[0][1] for call in mock_post_message.call_args_list]
            self.assertIn(win32con.WM_ACTIVATE, msg_types)
            self.assertIn(win32con.WM_SETFOCUS, msg_types)
            self.assertIn(win32con.WM_NCACTIVATE, msg_types)

            mock_post_message.reset_mock()
            interaction.deactivate(hwnd=12345)
            msg_types = [call[0][1] for call in mock_post_message.call_args_list]
            self.assertIn(win32con.WM_ACTIVATE, msg_types)
            self.assertIn(win32con.WM_KILLFOCUS, msg_types)
            self.assertIn(win32con.WM_NCACTIVATE, msg_types)
        finally:
            interaction.stop()

    def test_make_lparam_repeat(self):
        interaction = PostMessageInteraction(self.mock_capture, self.mock_hwnd_window)
        try:
            normal = interaction.make_lparam(0x57, is_up=False, is_repeat=False)
            repeat = interaction.make_lparam(0x57, is_up=False, is_repeat=True)
            self.assertTrue(repeat & (1 << 30))
            self.assertFalse(normal & (1 << 30))
        finally:
            interaction.stop()

    @patch('win32api.SetCursorPos')
    def test_combat_check_ensure_levitator_background_no_set_cursor_pos(self, mock_set_cursor):
        from src.combat.CombatCheck import CombatCheck

        task = CombatCheck.__new__(CombatCheck)
        task.config = {'Check Levitator': True}
        task.key_config = {'Wheel Key': 'tab'}
        task.log_info = MagicMock()
        task.log_debug = MagicMock()
        task.box_of_screen = MagicMock(return_value=None)
        task.has_char = MagicMock(return_value=False)
        task.find_one = MagicMock(return_value=False)
        task.is_open_world_auto_combat = MagicMock(return_value=False)

        mock_hwnd = MagicMock()
        mock_hwnd.is_foreground.return_value = False

        with patch.object(task, 'in_team', return_value=(False, None)), \
             patch.object(task, 'wait_feature', side_effect=[MagicMock(x=100, y=100), MagicMock()]), \
             patch.object(task, 'move') as mock_move, \
             patch.object(task, 'send_key_down'), \
             patch.object(task, 'send_key_up'), \
             patch.object(task, 'sleep'), \
             patch.object(task, 'target_enemy', return_value=True), \
             patch.object(CombatCheck, 'hwnd', new_callable=PropertyMock, return_value=mock_hwnd):

            result = task.ensure_levitator()
            self.assertTrue(result)
            mock_move.assert_called_with(100, 100)
            mock_set_cursor.assert_not_called()

    @patch('ctypes.windll.user32.ClipCursor')
    @patch('win32api.GetCursorPos', return_value=(500, 500))
    def test_mouse_reset_task_releases_clip_cursor(self, mock_get_pos, mock_clip_cursor):
        from src.task.MouseResetTask import MouseResetTask

        task = MouseResetTask.__new__(MouseResetTask)
        task.is_browser = MagicMock(return_value=False)
        task.mouse_pos = None
        task.post_mouse_reset = MagicMock()

        mock_hwnd = MagicMock()
        mock_hwnd.exists = True
        mock_hwnd.visible = False  # in background

        with patch.object(MouseResetTask, 'hwnd', new_callable=PropertyMock, return_value=mock_hwnd), \
             patch.object(MouseResetTask, 'enabled', new_callable=PropertyMock, return_value=True):
            task.mouse_reset()
            mock_clip_cursor.assert_called_with(None)
            task.post_mouse_reset.assert_called_with(0.05)


if __name__ == '__main__':
    unittest.main()
