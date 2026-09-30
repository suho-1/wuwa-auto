"""Measure the real per-frame CPU hot path and test whether OpenCL helps.

OpenCV here is the CPU-only wheel (``cv2.cuda.getCudaEnabledDeviceCount() == 0``)
but it is built with ``OpenCL: YES (NVD3D11)``, so ``cv2.UMat`` can dispatch
some primitives to the NVIDIA driver.  This measures the operations the
executor actually runs per tick, plain ndarray vs UMat.
"""
import os
import sys
import time

import cv2
import numpy as np

WIDTH, HEIGHT = 1920, 1080
RUNS = 60


def timed(label, fn, runs=RUNS):
    fn()
    c0, t0 = time.process_time(), time.perf_counter()
    for _ in range(runs):
        fn()
    wall = (time.perf_counter() - t0) * 1000 / runs
    cpu = (time.process_time() - c0) * 1000 / runs
    print(f"  {label:<44} {wall:8.3f} ms wall  {cpu:8.3f} ms cpu")
    return wall, cpu


def main():
    print(f"opencv {cv2.__version__}  threads={cv2.getNumThreads()}  "
          f"cuda_devices={cv2.cuda.getCudaEnabledDeviceCount()}")
    info = cv2.getBuildInformation()
    for line in info.splitlines():
        if any(k in line for k in ("OpenCL", "Intel IPP:", "Parallel framework")):
            print("   ", line.strip())
    print()

    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    small = cv2.resize(frame, (240, 135), interpolation=cv2.INTER_LINEAR)
    template = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    umat_frame = cv2.UMat(frame)
    umat_small = cv2.UMat(small)
    umat_tpl = cv2.UMat(template)

    print("per-frame colour work (full 1920x1080):")
    lo = np.array([0, 0, 200], np.uint8)
    hi = np.array([80, 80, 255], np.uint8)
    timed("cv2.inRange", lambda: cv2.inRange(frame, lo, hi))
    mask = cv2.inRange(frame, lo, hi)
    timed("cv2.findContours", lambda: cv2.findContours(mask, cv2.RETR_LIST,
                                                        cv2.CHAIN_APPROX_SIMPLE))
    timed("connectedComponentsWithStats", lambda: cv2.connectedComponentsWithStats(mask, 8))
    timed("cv2.cvtColor BGR2GRAY (full frame)", lambda: cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    timed("cv2.cvtColor BGR2HSV (full frame)", lambda: cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
    print()

    print("template matching on a small local search area (240x135):")
    timed("cv2.matchTemplate TM_CCOEFF_NORMED",
          lambda: cv2.matchTemplate(small, template, cv2.TM_CCOEFF_NORMED))
    timed("cv2.matchTemplate (grayscale)",
          lambda: cv2.matchTemplate(gray_small, gray_tpl, cv2.TM_CCOEFF_NORMED))
    timed("cv2.matchTemplate Canny+tpl (grayscale)",
          lambda: cv2.matchTemplate(cv2.Canny(gray_small, 50, 150),
                                     cv2.Canny(gray_tpl, 50, 150),
                                     cv2.TM_CCOEFF_NORMED))
    print()

    print("template matching full frame (1920x1080):")
    timed("cv2.matchTemplate TM_CCOEFF_NORMED full",
          lambda: cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED), runs=10)
    print()

    print("UMat / OpenCL variants:")
    try:
        _ = cv2.UMat(np.zeros((8, 8, 3), np.uint8)).get()
        timed("UMat inRange + get",
              lambda: cv2.inRange(umat_frame, lo, hi).get(), runs=20)
        timed("UMat cvtColor + get",
              lambda: cv2.cvtColor(umat_frame, cv2.COLOR_BGR2GRAY).get(), runs=20)
        timed("UMat matchTemplate + get",
              lambda: cv2.matchTemplate(umat_small, umat_tpl,
                                        cv2.TM_CCOEFF_NORMED).get(), runs=20)
    except Exception as exc:
        print(f"  UMat unavailable: {exc}")
    print()

    print("residual / interpolation used by the rotation search (BaseWWTask):")
    one = rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)

    def rotate():
        m = cv2.getRotationMatrix2D((20, 20), -17, 1.0)
        return cv2.warpAffine(one, m, (40, 40))

    timed("getRotationMatrix2D + warpAffine (1 of 360)", rotate, runs=200)


if __name__ == "__main__":
    main()
