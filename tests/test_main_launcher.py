"""Tests for the desktop-first wuwa-auto launcher."""

import sys
import types
import unittest
from unittest.mock import patch

import main


class MainLauncherTests(unittest.TestCase):
    def test_desktop_ui_is_the_default_and_logs_identity(self):
        calls = []
        expected_config = {
            "gui": {"type": "qt"},
            "gui_title": "wuwa-auto",
            "version": "v-test",
        }

        config_module = types.ModuleType("config")
        config_module.config = expected_config
        config_module.version = "v-test"
        ok_module = types.ModuleType("ok")

        class FakeOK:
            def __init__(self, supplied_config):
                calls.append(("init", supplied_config))

            def start(self):
                calls.append(("start",))

        class FakeLogger:
            @staticmethod
            def get_logger(_name):
                return types.SimpleNamespace(info=lambda message: calls.append(("log", message)))

        ok_module.OK = FakeOK
        ok_module.Logger = FakeLogger

        with patch.dict(sys.modules, {"config": config_module, "ok": ok_module}), \
                patch.object(sys, "argv", ["main.py"]), \
                patch.dict("os.environ", {"WUWA_AUTO_BUILD_ID": "test-build"}, clear=False):
            main.main()

        self.assertEqual(calls[0], ("init", expected_config))
        self.assertEqual(calls[-1], ("start",))
        banner = calls[1][1]
        self.assertIn("WUWA-AUTO STARTUP", banner)
        self.assertIn("source_version=v-test", banner)
        self.assertIn("ui_mode=qt-desktop", banner)
        self.assertIn("source_build=recovery-20261003.1", banner)
        self.assertIn("revision=test-build", banner)

    def test_tui_remains_an_explicit_compatibility_mode(self):
        calls = []
        tui_module = types.ModuleType("src.tui")
        tui_module.run_tui = lambda: calls.append(tuple(sys.argv))
        config_module = types.ModuleType("config")
        config_module.config = {"version": "v-test"}
        config_module.version = "v-test"
        ok_module = types.ModuleType("ok")

        class FakeLogger:
            @staticmethod
            def get_logger(_name):
                return types.SimpleNamespace(info=lambda message: calls.append(message))

        ok_module.Logger = FakeLogger

        with patch.dict(
                sys.modules,
                {"config": config_module, "ok": ok_module, "src.tui": tui_module}), \
                patch.object(sys, "argv", ["main.py", "--tui"]), \
                patch.dict("os.environ", {"WUWA_AUTO_BUILD_ID": "test-build"}, clear=False):
            main.main()

        self.assertIn("ui_mode=legacy-tui", calls[0])
        self.assertEqual(calls[1], ("main.py",))

    def test_banner_contains_working_directory_and_entrypoint(self):
        with patch.dict("os.environ", {"WUWA_AUTO_BUILD_ID": "abc123"}, clear=False):
            banner = main.startup_banner({"version": "runtime"}, "source", "qt-desktop")

        self.assertIn("runtime_version=runtime", banner)
        self.assertIn("revision=abc123", banner)
        self.assertIn("cwd=", banner)
        self.assertIn("entry=", banner)


if __name__ == "__main__":
    unittest.main()
