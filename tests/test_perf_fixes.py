"""Tests for the two performance fixes, without needing a running game.

Both are behavioural no-ops by construction, and that is exactly what needs
proving: the health-bar crop must not miss anything the full frame finds, and
the rotation cache must return the same angle as warping on every call.
"""

import os
import sys
import time
import types
import unittest

import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ok import relative_box
from ok.feature.Feature import Feature

import src.combat.CombatCheck as combat_check
from src.task.BaseWWTask import BaseWWTask


class HealthBarRegionTests(unittest.TestCase):
    def test_region_covers_the_known_boss_bar(self):
        """The crop must contain the boss bar, whose coordinates are known."""
        bottom = combat_check.HEALTH_BAR_REGION_BOTTOM
        self.assertGreater(bottom, 0.0)
        self.assertLessEqual(bottom, 1.0)
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            region = relative_box(width, height, 0, 0, 1.0, bottom)
            boss = relative_box(width, height, 1269 / 3840, 58 / 2160, 2533 / 3840, 200 / 2160)
            with self.subTest(resolution=f"{width}x{height}"):
                self.assertLessEqual(boss.y + boss.height, region.y + region.height)
                self.assertGreaterEqual(boss.y, region.y)

    def test_region_is_a_real_reduction(self):
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            region = relative_box(width, height, 0, 0, 1.0,
                                  combat_check.HEALTH_BAR_REGION_BOTTOM)
            with self.subTest(resolution=f"{width}x{height}"):
                self.assertLess(region.width * region.height / (width * height), 0.60)

    def test_region_spans_the_full_width(self):
        """Cropping vertically only avoids guessing where the bar sits in x."""
        for width, height in ((1920, 1080), (2560, 1440)):
            region = relative_box(width, height, 0, 0, 1.0,
                                  combat_check.HEALTH_BAR_REGION_BOTTOM)
            with self.subTest(resolution=f"{width}x{height}"):
                self.assertEqual(region.x, 0)
                self.assertEqual(region.width, width)


class _Recorder:
    """Captures find_color_rectangles calls made by has_health_bar."""

    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def __call__(self, frame, color_range, min_width, min_height, max_height=-1,
                 max_width=-1, threshold=0.5, box=None):
        self.calls.append(box)
        if box is None:
            return self.results.get("wide", [])
        return self.results.get("region", [])


class HealthBarVerifyTests(unittest.TestCase):
    """``verify_health_bar_region`` is the safety net for the crop constant."""

    def setUp(self):
        self.saved = combat_check.find_color_rectangles
        self.recorder = None
        self.addCleanup(self._restore)

    def _restore(self):
        combat_check.find_color_rectangles = self.saved

    def install(self, results=None):
        self.recorder = _Recorder(results or {})
        combat_check.find_color_rectangles = self.recorder

    def build(self, checked=0.0):
        task = types.SimpleNamespace()
        task.messages = []
        task.log_info = lambda message, *a, **k: task.messages.append(message)
        task.frame = np.zeros((1080, 1920, 3), np.uint8)
        task._health_bar_region_checked = checked
        task.verify_health_bar_region = (
            combat_check.CombatCheck.verify_health_bar_region.__get__(task))
        return task

    def test_returns_nothing_before_the_interval_elapses(self):
        self.install({"wide": [1, 2, 3]})
        task = self.build(checked=time.time())
        result = task.verify_health_bar_region(50, 4, 12)
        self.assertEqual(result, [])
        self.assertEqual(self.recorder.calls, [], "must not scan the full frame yet")

    def test_scans_and_reports_once_the_interval_elapsed(self):
        self.install({"wide": [1, 2, 3]})
        task = self.build(checked=0.0)
        result = task.verify_health_bar_region(50, 4, 12)
        self.assertEqual(result, [1, 2, 3])
        self.assertEqual(len(self.recorder.calls), 1)
        self.assertIsNone(self.recorder.calls[0], "the verification must scan the full frame")
        self.assertTrue(any("outside the search region" in m for m in task.messages),
                        task.messages)

    def test_stays_quiet_when_the_region_agrees(self):
        self.install({"wide": []})
        task = self.build(checked=0.0)
        result = task.verify_health_bar_region(50, 4, 12)
        self.assertEqual(result, [])
        self.assertEqual(task.messages, [])

    def test_the_interval_is_long_enough_to_be_cheap(self):
        self.assertGreaterEqual(combat_check.HEALTH_BAR_REGION_RECHECK, 60.0)


class RotatedTemplateTests(unittest.TestCase):
    def setUp(self):
        self.feature = Feature(np.random.default_rng(0).integers(
            0, 255, (16, 16, 3), dtype=np.uint8))

    def variants(self, step=1):
        return BaseWWTask.rotated_template_variants(self, self.feature, step)

    def test_produces_one_variant_per_step(self):
        self.assertEqual(len(self.variants(1)), 360)
        self.assertEqual(len(self.variants(24)), 15)
        self.assertEqual(len(self.variants(90)), 4)

    def test_caches_so_the_second_call_is_free(self):
        first = self.variants(1)
        again = self.variants(1)
        self.assertIs(again, first)
        self.assertIn(1, self.feature.rotation_cache)

    def test_cache_is_keyed_on_the_source_image(self):
        self.variants(1)
        original = self.feature.rotation_cache[1][1]
        replacement = np.zeros_like(self.feature.mat)
        self.feature.mat = replacement
        rebuilt = self.variants(1)
        self.assertIsNot(rebuilt, original)
        self.assertTrue(all(v.shape == replacement.shape for v in rebuilt))

    def test_cache_holds_a_reference_to_the_source(self):
        """Otherwise a freed template's id could be recycled onto a stale cache."""
        self.variants(1)
        source, _ = self.feature.rotation_cache[1]
        self.assertIs(source, self.feature.mat)

    def test_matches_warping_every_time(self):
        """The cache must be a pure optimisation: same angles, same scores."""
        mat = self.feature.mat
        height, width = mat.shape[:2]
        center = (width // 2, height // 2)
        search = np.random.default_rng(1).integers(0, 90, (60, 60, 3), dtype=np.uint8)
        variants = self.variants(1)
        for angle in (0, 37, 90, 180, 271, 359):
            fresh = cv2.warpAffine(mat, cv2.getRotationMatrix2D(center, -angle, 1.0),
                                    (width, height))
            self.assertTrue(np.array_equal(variants[angle], fresh), f"angle {angle}")

    def test_find_rotation_is_unchanged_by_the_cache(self):
        """End-to-end: the same angle is chosen with and without the cache."""
        rng = np.random.default_rng(3)
        mat = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
        mat[6:10, 7:9] = 250
        search = rng.integers(0, 90, (60, 60, 3), dtype=np.uint8)
        box = relative_box(60, 60, 0, 0, 1.0, 1.0, name="arrow")

        def best_angle(variants):
            scores = []
            for template in variants:
                result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
                np.nan_to_num(result, copy=False, nan=0, posinf=0, neginf=0)
                scores.append(cv2.minMaxLoc(result)[1])
            return int(np.argmax(scores))

        feature = Feature(mat)
        cached = best_angle(BaseWWTask.rotated_template_variants(self, feature, 1))

        height, width = mat.shape[:2]
        center = (width // 2, height // 2)
        rebuilt = [cv2.warpAffine(mat, cv2.getRotationMatrix2D(center, -a, 1.0), (width, height))
                   for a in range(360)]
        self.assertEqual(cached, best_angle(rebuilt))
        self.assertIsNotNone(box)


if __name__ == "__main__":
    unittest.main(verbosity=2)
