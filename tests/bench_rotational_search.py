"""Cost of the 360-step rotational template search in ``rotate_arrow_and_find``.

``src/task/BaseWWTask.py:827-841`` warps the arrow template through 360 integer
angles and runs a full ``find_one`` per angle.  This measures that honestly and
compares it against a coarse-to-fine search over the same angle range, which
costs ~1/15 of the matches and resolves to 1 degree after refinement.
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RUNS = 3
COARSE_STEP = 24


def timed(label, fn, runs=RUNS):
    fn()
    c0, t0 = time.process_time(), time.perf_counter()
    for _ in range(runs):
        result = fn()
    wall = (time.perf_counter() - t0) * 1000 / runs
    cpu = (time.process_time() - c0) * 1000 / runs
    print(f"  {label:<50} {wall:9.1f} ms  {cpu:9.1f} ms cpu")
    return wall, result


def main():
    rng = np.random.default_rng(3)
    # A minimap-sized search area and a small arrow template, as the code uses.
    search = rng.integers(0, 90, (60, 60, 3), dtype=np.uint8)
    template = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    template[6:10, 7:9] = 250
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    gray_search = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    h, w = template.shape[:2]
    center = (w // 2, h // 2)

    def score_at(angle):
        m = cv2.getRotationMatrix2D(center, -angle, 1.0)
        warped = cv2.warpAffine(template, m, (w, h))
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray_search, warped_gray, cv2.TM_CCOEFF_NORMED)
        np.nan_to_num(result, copy=False, nan=0, posinf=0, neginf=0)
        return float(cv2.minMaxLoc(result)[1])

    def brute_force():
        best, best_angle = -1.0, 0
        for angle in range(360):
            value = score_at(angle)
            if value > best:
                best, best_angle = value, angle
        return best_angle, best

    def coarse_to_fine():
        best, best_angle = -1.0, 0
        for angle in range(0, 360, COARSE_STEP):
            value = score_at(angle)
            if value > best:
                best, best_angle = value, angle
        # Refine +/- COARSE_STEP degrees at 1 degree resolution.
        for angle in range(best_angle - COARSE_STEP, best_angle + COARSE_STEP + 1):
            angle %= 360
            value = score_at(angle)
            if value > best:
                best, best_angle = value, angle
        return best_angle, best

    print("mini-map arrow rotational search (360 x matchTemplate)")
    brute_ms, brute = timed("brute force, 360 angles (current code)", brute_force)
    fine_ms, fine = timed(f"coarse-to-fine, {360 // COARSE_STEP}+{2 * COARSE_STEP + 1} angles",
                          coarse_to_fine)
    print()
    print(f"  speedup                    : {brute_ms / fine_ms:.1f}x")
    print(f"  brute-force best angle     : {brute[0]}")
    print(f"  coarse-to-fine best angle  : {fine[0]}   (error {abs(brute[0] - fine[0])} deg)")
    print(f"  score retained             : {fine[1] / max(brute[1], 1e-9):.4f}x")
    print()
    print("  note: the two searches are not equivalent in general - a template with")
    print("  180-degree symmetry, or several local maxima, can defeat a coarse pass.")


if __name__ == "__main__":
    main()
