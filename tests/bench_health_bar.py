"""Cost of the real ``has_health_bar`` colour search, full-frame vs cropped.

``src/combat/CombatCheck.py`` used to call::

    find_color_rectangles(self.frame, enemy_health_color_red, min_width, min_height, ...)

with no ``box``, so ``ok/util/color.py:112-113`` ran ``cv2.inRange`` and
``cv2.findContours`` over the entire screen. The boss-bar search two lines below
was already scoped. This measures the old call against the crop now in use.
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ok import relative_box
from ok.util.color import find_color_rectangles
from src.combat.CombatCheck import HEALTH_BAR_REGION_BOTTOM

RUNS = 30


def timed(label, fn, runs=RUNS):
    fn()
    c0, t0 = time.process_time(), time.perf_counter()
    for _ in range(runs):
        fn()
    wall = (time.perf_counter() - t0) * 1000 / runs
    cpu = (time.process_time() - c0) * 1000 / runs
    print(f"  {label:<52} {wall:8.2f} ms wall  {cpu:8.2f} ms cpu")
    return wall


def main():
    for width, height, label in ((1920, 1080, "1080p"), (2560, 1440, "1440p")):
        print(f"\n=== screen {width}x{height} ({label}) ===")
        # A plausible combat frame: mostly dark, a red enemy health bar along
        # the top edge, some coloured UI, and enough noise that findContours
        # has real work to do.
        rng = np.random.default_rng(7)
        frame = rng.integers(0, 40, (height, width, 3), dtype=np.uint8)
        bar_y = height // 12
        frame[bar_y: bar_y + 9, width // 6: width // 6 + int(width / 3840 * 100)] = (40, 40, 220)
        for _ in range(40):
            x, y = rng.integers(0, width - 60), rng.integers(0, height - 40)
            frame[y:y + rng.integers(4, 30), x:x + rng.integers(10, 60)] = (30, 200, 60)

        min_width = max(1, int(width / 3840 * 100))
        min_height = max(1, int(height / 2160 * 9))

        # The real ranges, verbatim from src/combat/CombatCheck.py.
        enemy_red = {"r": (174, 225), "g": (35, 135), "b": (35, 135)}
        boss_red = {"r": (245, 255), "g": (35, 135), "b": (35, 135)}

        region = relative_box(width, height, 0, 0, 1.0, HEALTH_BAR_REGION_BOTTOM,
                              name="health_bar_region")
        boss_box = relative_box(width, height, 1269 / 3840, 58 / 2160, 2533 / 3840, 200 / 2160)

        old = timed("full frame (what has_health_bar used to do)",
                    lambda: find_color_rectangles(frame, enemy_red, min_width, min_height,
                                                  max_height=min_height * 3))
        new = timed("cropped to the health-bar region (current)",
                    lambda: find_color_rectangles(frame, enemy_red, min_width, min_height,
                                                  max_height=min_height * 3, box=region))
        timed("boss bar, already cropped (unchanged)",
              lambda: find_color_rectangles(frame, boss_red, min_width,
                                            min_height * 1.3, box=boss_box))

        # The crop must not change the answer for a bar that lives in it.
        found_old = find_color_rectangles(frame, enemy_red, min_width, min_height,
                                          max_height=min_height * 3)
        found_new = find_color_rectangles(frame, enemy_red, min_width, min_height,
                                          max_height=min_height * 3, box=region)
        same = [(b.x, b.y, b.width, b.height) for b in found_old] == \
               [(b.x, b.y, b.width, b.height) for b in found_new]
        print(f"  identical result for a bar inside the region: {same} "
              f"({len(found_old)} found, region covers "
              f"{region.width * region.height / (width * height):.0%} of the frame)")
        print(f"  -> {old / max(new, 1e-9):.1f}x faster "
              f"({old - new:.2f} ms saved per call)")
        print(f"  -> has_health_bar runs at least twice per combat tick, "
              f"and AutoCombatTask.py:17 allows 100 ms")


if __name__ == "__main__":
    main()
