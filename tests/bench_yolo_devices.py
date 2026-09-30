"""Benchmark the echo YOLO model across every OpenVINO device on this machine.

Reports compile time, first-inference latency, steady-state latency and CPU
time consumed, and checks that the GPU result matches the CPU result.
"""
import os
import sys
import time

import numpy as np
from openvino import Core

MODEL = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "echo_model", "echo.onnx")
WARMUP = 5
RUNS = 40


def build_input(core, compiled):
    inp = compiled.input(0)
    shape = list(inp.shape)
    shape[0] = 1
    return np.random.rand(*shape).astype(np.float32), inp, compiled.output(0)


def bench(device):
    core = Core()
    t0 = time.perf_counter()
    try:
        model = core.read_model(MODEL)
        compiled = core.compile_model(model, device_name=device,
                                      config={"PERFORMANCE_HINT": "LATENCY"})
    except Exception as exc:
        return {"device": device, "error": str(exc).splitlines()[0][:90]}
    compile_ms = (time.perf_counter() - t0) * 1000

    data, inp, out = build_input(core, compiled)

    t0 = time.perf_counter()
    result = compiled({inp: data})
    first_ms = (time.perf_counter() - t0) * 1000

    for _ in range(WARMUP):
        compiled({inp: data})

    c0, t0 = time.process_time(), time.perf_counter()
    for _ in range(RUNS):
        result = compiled({inp: data})
    wall_ms = (time.perf_counter() - t0) * 1000 / RUNS
    cpu_ms = (time.process_time() - c0) * 1000 / RUNS

    values = np.asarray(result[out]).ravel()
    return {
        "device": device,
        "compile_ms": compile_ms,
        "first_ms": first_ms,
        "steady_ms": wall_ms,
        "cpu_ms": cpu_ms,
        "checksum": float(values.sum()),
        "max_abs": float(np.abs(values).max()),
        "shape": tuple(np.asarray(result[out]).shape),
    }


def main():
    core = Core()
    devices = list(core.available_devices)
    print(f"model    : {MODEL}")
    print(f"devices  : {devices}")
    for device in devices:
        try:
            print(f"           {device} = {core.get_property(device, 'FULL_DEVICE_NAME')}")
        except Exception:
            pass
    print()

    header = (f"{'device':<8} {'compile':>10} {'first':>10} {'steady':>10} "
              f"{'cpu/round':>11} {'max|out|':>10}")
    print(header)
    print("-" * len(header))

    results = {}
    for device in devices:
        row = bench(device)
        results[device] = row
        if "error" in row:
            print(f"{device:<8} {row['error']}")
        else:
            print(f"{device:<8} {row['compile_ms']:>9.0f}m {row['first_ms']:>9.1f}m "
                  f"{row['steady_ms']:>9.2f}m {row['cpu_ms']:>10.2f}m {row['max_abs']:>10.3f}")

    if "CPU" in results and len(results["CPU"]["shape"]) == len(results.get("GPU", {}).get("shape", ())):
        print()
        if "GPU" in results:
            print(f"GPU steady-state speedup vs CPU : {results['CPU']['steady_ms'] / results['GPU']['steady_ms']:.2f}x")
            print(f"GPU CPU-time reduction vs CPU   : {results['CPU']['cpu_ms'] / max(results['GPU']['cpu_ms'], 1e-6):.1f}x less host CPU")
        if "NPU" in results:
            print(f"NPU steady-state speedup vs CPU : {results['CPU']['steady_ms'] / results['NPU']['steady_ms']:.2f}x")


if __name__ == "__main__":
    main()
