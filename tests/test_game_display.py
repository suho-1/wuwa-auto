"""Tests for the game display profile.

These run against copies of a real ``GameUserSettings.ini`` so the parsing and
editing behaviour is proven against the actual file format, while the
player's own settings are never touched.
"""

import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.tui import game_display as gd

#: A trimmed but structurally faithful copy of the file this build writes.
REAL_SETTINGS = """[ScalabilityGroups]
sg.ResolutionQuality=100.000000
sg.ViewDistanceQuality=2
sg.AntiAliasingQuality=2
sg.ShadowQuality=0
sg.PostProcessQuality=2
sg.TextureQuality=3
sg.EffectsQuality=3
sg.FoliageQuality=2
sg.ShadingQuality=3
sg.KuroRenderQuality=0
sg.KuroLocalRenderQuality=0
sg.RayTracingQuality=0

[/Script/Engine.GameUserSettings]
bUseVSync=False
bUseDynamicResolution=False
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1920
LastUserConfirmedResolutionSizeY=1080
WindowPosX=-1
WindowPosY=-1
FullscreenMode=0
GameQualitySettingLevel=2
LastConfirmedFullscreenMode=0
PreferredFullscreenMode=1
Version=5
AudioQualityLevel=0
LastConfirmedAudioQualityLevel=0
FrameRateLimit=0.000000
FramePace=0
DesiredScreenWidth=1920
bUseDesiredScreenHeight=False
DesiredScreenHeight=1080
LastUserConfirmedDesiredScreenWidth=1920
LastUserConfirmedDesiredScreenHeight=1080
LastRecommendedScreenWidth=-1.000000
LastRecommendedScreenHeight=-1.000000
LastCPUBenchmarkResult=-1.000000
LastGPUBenchmarkResult=-1.000000
LastGPUBenchmarkMultiplier=1.000000
bUseHDRDisplayOutput=False
HDRDisplayOutputNits=1000

[ShaderPipelineCache.CacheFile]
LastOpened=Client

[Internationalization]
Culture=en
"""


class IniDocumentTests(unittest.TestCase):
    def document(self, text=REAL_SETTINGS):
        return gd.IniDocument(text)

    def test_reads_a_value_from_a_named_section(self):
        document = self.document()
        self.assertEqual(document.get(gd.SETTINGS_SECTION, "ResolutionSizeX"), "1920")
        self.assertEqual(document.get(gd.SCALABILITY_SECTION, "sg.TextureQuality"), "3")

    def test_does_not_read_a_key_from_the_wrong_section(self):
        document = self.document()
        self.assertIsNone(document.get(gd.SCALABILITY_SECTION, "ResolutionSizeX"))
        self.assertIsNone(document.get(gd.SETTINGS_SECTION, "sg.TextureQuality"))

    def test_missing_key_and_section_return_the_default(self):
        document = self.document()
        self.assertEqual(document.get("NoSuchSection", "k", "fallback"), "fallback")
        self.assertIsNone(document.get(gd.SETTINGS_SECTION, "NoSuchKey"))

    def test_set_replaces_in_place_without_moving_the_key(self):
        document = self.document()
        before = document.chunks.index("ResolutionSizeX=1920\n")
        document.set(gd.SETTINGS_SECTION, "ResolutionSizeX", "1280")
        after = document.chunks.index("ResolutionSizeX=1280\n")
        self.assertEqual(before, after)

    def test_set_reports_whether_it_changed_anything(self):
        document = self.document()
        self.assertTrue(document.set(gd.SETTINGS_SECTION, "ResolutionSizeX", "1280"))
        self.assertFalse(document.set(gd.SETTINGS_SECTION, "ResolutionSizeX", "1280"))

    def test_set_inserts_a_missing_key_into_its_section(self):
        document = self.document()
        document.set(gd.SETTINGS_SECTION, "BrandNewKey", "7")
        self.assertEqual(document.get(gd.SETTINGS_SECTION, "BrandNewKey"), "7")
        # It must land inside the section, before the next one.
        index = document.chunks.index("BrandNewKey=7\n")
        header = document.chunks.index(f"[{gd.SETTINGS_SECTION}]\n")
        following = document.chunks.index("[ShaderPipelineCache.CacheFile]\n")
        self.assertGreater(index, header)
        self.assertLess(index, following)

    def test_set_creates_a_missing_section(self):
        document = self.document()
        document.set("BrandNewSection", "Key", "1")
        self.assertEqual(document.get("BrandNewSection", "Key"), "1")

    def test_round_trip_preserves_unrelated_content(self):
        document = self.document()
        before = document.render()
        document.set(gd.SETTINGS_SECTION, "ResolutionSizeX", "1280")
        after = document.render()
        for line in ("[ShaderPipelineCache.CacheFile]", "LastOpened=Client",
                     "[Internationalization]", "Culture=en",
                     "AudioQualityLevel=0", "FrameRateLimit=0.000000",
                     "HDRDisplayOutputNits=1000", "Version=5"):
            with self.subTest(line=line):
                self.assertIn(line, after)
        self.assertEqual(before.count("\n"), after.count("\n") - 0)

    def test_render_keeps_a_trailing_newline(self):
        self.assertTrue(self.document().render().endswith("\n"))

    def test_round_trip_is_byte_exact_for_crlf(self):
        """The engine writes CRLF; rewriting as LF would be a gratuitous change."""
        crlf = REAL_SETTINGS.replace("\n", "\r\n")
        self.assertEqual(gd.IniDocument(crlf).render(), crlf)
        self.assertEqual(gd.IniDocument(crlf).newline, "\r\n")

    def test_round_trip_is_byte_exact_without_a_trailing_newline(self):
        self.assertEqual(gd.IniDocument("a=1").render(), "a=1")

    def test_editing_preserves_crlf_everywhere(self):
        document = gd.IniDocument(REAL_SETTINGS.replace("\n", "\r\n"))
        document.set(gd.SETTINGS_SECTION, "ResolutionSizeX", "1280")
        document.set(gd.SETTINGS_SECTION, "InsertedLater", "1")
        rendered = document.render()
        self.assertIn("ResolutionSizeX=1280\r\n", rendered)
        self.assertIn("InsertedLater=1\r\n", rendered)
        # No bare LF may survive once the CRLFs are accounted for.
        self.assertNotIn("\n", rendered.replace("\r\n", ""))


from unittest.mock import patch


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "GameUserSettings.ini")
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write(REAL_SETTINGS)
        self._patcher = patch.object(gd, "is_game_running", return_value=False)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def apply(self, profile=None, **kwargs):
        return gd.apply_profile(profile or gd.DEFAULT_PROFILE, path=self.path, **kwargs)

    def state(self):
        return gd.read_state(self.path)

    def test_default_profile_is_1280x720_windowed_lowest(self):
        profile = gd.DEFAULT_PROFILE
        self.assertEqual((profile.width, profile.height), (1280, 720))
        self.assertEqual(profile.window_mode, gd.WINDOW_MODE_WINDOWED)
        self.assertEqual(profile.quality, 0)
        self.assertEqual(profile.scale_levels, 0)
        # Internal render scale stays sharp: the app matches templates against
        # the captured image, so a soft render would cost accuracy.
        self.assertEqual(profile.resolution_quality, 100)

    def test_apply_reports_success(self):
        ok, message = self.apply()
        self.assertTrue(ok, message)

    def test_apply_sets_the_resolution_in_every_mirror_key(self):
        self.apply()
        state = self.state()
        self.assertEqual(state["width"], 1280)
        self.assertEqual(state["height"], 720)
        document = gd.IniDocument.load(self.path)
        for key in gd.RESOLUTION_KEYS:
            self.assertEqual(document.get(gd.SETTINGS_SECTION, key), "1280", key)
        for key in gd.RESOLUTION_HEIGHT_KEYS:
            self.assertEqual(document.get(gd.SETTINGS_SECTION, key), "720", key)

    def test_apply_sets_every_window_mode_key_to_windowed(self):
        self.apply()
        document = gd.IniDocument.load(self.path)
        for key in gd.MODE_KEYS:
            self.assertEqual(document.get(gd.SETTINGS_SECTION, key), "2", key)
        self.assertEqual(self.state()["window_mode"], gd.WINDOW_MODE_WINDOWED)

    def test_apply_drops_every_scalability_group_to_zero(self):
        self.apply()
        levels = self.state()["scalability"]
        self.assertTrue(levels)
        for key, value in levels.items():
            if key == "sg.ResolutionQuality":
                # Internal render scale is a percentage and is left sharp by
                # default so template matching keeps a clear image.
                self.assertEqual(value, 100)
                continue
            self.assertEqual(value, 0, f"{key} is still {value}")
        self.assertEqual(gd.summarise_state(self.state()),
                         "1280x720 windowed, preset 0")

    def test_soft_render_profile_lowers_the_render_scale(self):
        soft = gd.DisplayProfile(1280, 720, gd.WINDOW_MODE_WINDOWED, 0, 0, 70)
        ok, message = gd.apply_profile(soft, path=self.path)
        self.assertTrue(ok, message)
        self.assertEqual(self.state()["scalability"]["sg.ResolutionQuality"], 70)
        self.assertIn("render scale 70%", gd.summarise_state(self.state()))

    def test_apply_lowers_the_quality_preset(self):
        self.apply()
        self.assertEqual(self.state()["quality"], 0)

    def test_apply_keeps_the_desired_screen_height_flag(self):
        self.apply()
        document = gd.IniDocument.load(self.path)
        self.assertEqual(document.get(gd.SETTINGS_SECTION, gd.DESIRED_HEIGHT_FLAG), "False")

    def test_apply_does_not_invent_scalability_keys(self):
        """Only groups the file already declares may be written."""
        before = set(gd.IniDocument.load(self.path).keys(gd.SCALABILITY_SECTION))
        self.apply()
        after = set(gd.IniDocument.load(self.path).keys(gd.SCALABILITY_SECTION))
        self.assertEqual(before, after)

    def test_apply_leaves_non_display_settings_alone(self):
        self.apply()
        document = gd.IniDocument.load(self.path)
        self.assertEqual(document.get(gd.SETTINGS_SECTION, "AudioQualityLevel"), "0")
        self.assertEqual(document.get(gd.SETTINGS_SECTION, "FrameRateLimit"), "0.000000")
        self.assertEqual(document.get(gd.SETTINGS_SECTION, "Version"), "5")
        self.assertEqual(document.get("Internationalization", "Culture"), "en")

    def test_apply_is_idempotent(self):
        self.apply()
        with open(self.path, encoding="utf-8") as stream:
            first = stream.read()
        ok, message = self.apply()
        self.assertTrue(ok)
        self.assertIn("Already at", message)
        with open(self.path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), first)

    def test_apply_takes_a_backup(self):
        self.apply()
        backups = gd.list_backups(self.path)
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith(self.path + gd.BACKUP_SUFFIX))
        # The backup must hold the pre-change content.
        with open(backups[0], encoding="utf-8") as stream:
            self.assertIn("ResolutionSizeX=1920", stream.read())

    def test_restore_reverts_the_last_change(self):
        self.apply()
        self.assertEqual(self.state()["width"], 1280)
        name = gd.restore_backup(self.path)
        self.assertTrue(name)
        self.assertEqual(self.state()["width"], 1920)

    def test_backups_are_capped(self):
        for _ in range(gd.MAX_BACKUPS + 4):
            document = gd.IniDocument.load(self.path)
            document.set(gd.SETTINGS_SECTION, "FramePace", "1")
            document.set(gd.SETTINGS_SECTION, "FrameRateLimit", "60.0")
            with open(self.path, "w", encoding="utf-8") as stream:
                stream.write(document.render())
            time_stamp = gd.backup_path(self.path)
            shutil.copy2(self.path, time_stamp)
        self.assertLessEqual(len(gd.list_backups(self.path)), gd.MAX_BACKUPS)

    def test_missing_file_is_reported_not_raised(self):
        ok, message = gd.apply_profile(gd.DEFAULT_PROFILE,
                                       path=os.path.join(self._tmp.name, "nope.ini"))
        self.assertFalse(ok)
        self.assertIn("not found", message)

    def test_refuses_while_the_game_is_running(self):
        running = gd.is_game_running
        gd.is_game_running = lambda: True
        try:
            ok, message = self.apply()
        finally:
            gd.is_game_running = running
        self.assertFalse(ok)
        self.assertIn("running", message)
        # And the file must be untouched.
        with open(self.path, encoding="utf-8") as stream:
            self.assertIn("ResolutionSizeX=1920", stream.read())

    def test_force_overrides_the_running_check(self):
        running = gd.is_game_running
        gd.is_game_running = lambda: True
        try:
            ok, message = self.apply(force=True)
        finally:
            gd.is_game_running = running
        self.assertTrue(ok, message)
        self.assertEqual(self.state()["width"], 1280)

    def test_broken_file_is_reported_not_raised(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("not an ini at all\n")
        ok, message = self.apply()
        self.assertTrue(ok, message)
        # A file with no sections still gets the keys it needs.
        self.assertEqual(self.state()["width"], 1280)

    def test_other_profiles_work(self):
        profile = gd.DisplayProfile(1920, 1080, gd.WINDOW_MODE_BORDERLESS, 0, 0, 100)
        ok, message = gd.apply_profile(profile, path=self.path)
        self.assertTrue(ok, message)
        state = self.state()
        self.assertEqual((state["width"], state["height"]), (1920, 1080))
        self.assertEqual(state["window_mode"], gd.WINDOW_MODE_BORDERLESS)


class RhiTests(unittest.TestCase):
    def test_dx11_passes_the_flags_the_engine_shipped_with(self):
        args = gd.rhi_args(gd.RHI_DX11)
        self.assertIn("-dx11", args)
        self.assertIn("-force-d3d11", args)

    def test_dx12_passes_the_matching_flags(self):
        args = gd.rhi_args(gd.RHI_DX12)
        self.assertIn("-dx12", args)
        self.assertNotIn("-dx11", args)

    def test_default_passes_nothing(self):
        self.assertEqual(gd.rhi_args(gd.RHI_DEFAULT), [])

    def test_unknown_rhi_passes_nothing_and_launch_refuses(self):
        self.assertEqual(gd.rhi_args("vulkan"), [])
        running = gd.is_game_running
        gd.is_game_running = lambda: False
        try:
            ok, message = gd.launch("vulkan")
        finally:
            gd.is_game_running = running
        self.assertFalse(ok)
        self.assertIn("Unknown RHI", message)

    def test_launch_refuses_when_the_game_is_already_up(self):
        running = gd.is_game_running
        gd.is_game_running = lambda: True
        try:
            ok, message = gd.launch(gd.RHI_DX11)
        finally:
            gd.is_game_running = running
        self.assertFalse(ok)
        self.assertIn("already running", message)


class DiscoveryTests(unittest.TestCase):
    def test_install_root_is_derived_from_the_shipping_exe(self):
        exe = os.path.join("D:", "Games", "Wuthering Waves", "Wuthering Waves Game",
                           "Client", "Binaries", "Win64", "Client-Win64-Shipping.exe")
        root = gd.install_root_from_exe(exe)
        self.assertTrue(root.endswith("Wuthering Waves Game"), root)
        self.assertFalse(root.endswith("Client"), root)

    def test_settings_file_is_found_under_an_install_root(self):
        with tempfile.TemporaryDirectory() as base:
            config = os.path.join(base, "Client", "Saved", "Config", "WindowsNoEditor")
            os.makedirs(config)
            expected = os.path.join(config, "GameUserSettings.ini")
            with open(expected, "w", encoding="utf-8") as stream:
                stream.write(REAL_SETTINGS)
            self.assertEqual(gd.find_settings_file(base), expected)

    def test_any_platform_folder_is_accepted(self):
        with tempfile.TemporaryDirectory() as base:
            config = os.path.join(base, "Client", "Saved", "Config", "Windows")
            os.makedirs(config)
            expected = os.path.join(config, "GameUserSettings.ini")
            with open(expected, "w", encoding="utf-8") as stream:
                stream.write(REAL_SETTINGS)
            self.assertEqual(gd.find_settings_file(base), expected)

    def test_missing_install_reports_nothing(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(gd.find_settings_file(base), "")

    def test_read_state_of_a_missing_file_is_empty(self):
        self.assertEqual(gd.read_state(os.path.join(tempfile.gettempdir(), "no-such-file.ini")), {})


class SummaryTests(unittest.TestCase):
    def test_summary_mentions_groups_above_zero(self):
        state = {"width": 1280, "height": 720, "window_mode": 2, "quality": 0,
                 "scalability": {"sg.TextureQuality": 3, "sg.ShadowQuality": 0}}
        summary = gd.summarise_state(state)
        self.assertIn("1280x720", summary)
        self.assertIn("windowed", summary)
        self.assertIn("1/2 sg groups above 0", summary)

    def test_render_scale_is_not_counted_as_a_quality_level(self):
        state = {"width": 1280, "height": 720, "window_mode": 2, "quality": 0,
                 "scalability": {"sg.ResolutionQuality": 100.0, "sg.TextureQuality": 0}}
        self.assertEqual(gd.summarise_state(state), "1280x720 windowed, preset 0")

    def test_soft_render_scale_is_reported(self):
        state = {"width": 1280, "height": 720, "window_mode": 2, "quality": 0,
                 "scalability": {"sg.ResolutionQuality": 70.0}}
        self.assertIn("render scale 70%", gd.summarise_state(state))

    def test_summary_of_nothing(self):
        self.assertEqual(gd.summarise_state({}), "settings file not found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
