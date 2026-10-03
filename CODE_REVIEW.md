# Code Review — wuwa-auto

Scope: `src/`, `config.py`, `main.py`, `main_debug.py` (the vendored `ok/` framework was scanned
but intentionally left untouched). Review performed with manual inspection plus `ruff`
(`F`, `E`, `B`, `PLE`, `PLW` rule sets) and the Linux-runnable part of the test suite.
The follow-up hardening is covered by regression tests; full execution requires the pinned
runtime dependencies and Windows-specific capture/input packages.

---

## 1. Bugs found and FIXED

### 1.1 `src/OnnxYolo8Detect.py` — ONNX session never initialized (critical)
A `_load_labels` `@staticmethod` had been inserted in the middle of `__init__`, which cut the
constructor short. Everything after it — provider selection (DML/CUDA/CPU), the
`ort.InferenceSession` creation, `self.input_name` / `self.output_name` / model shape setup —
sat *after* the `return {0: 'echo'}` of `_load_labels` as unreachable dead code. Any
`OnnxYolo8Detect` instance was constructed without `self.session`, so the first inference call
crashed with `AttributeError`. The ONNX echo-detection backend was effectively dead
(only the OpenVINO path could have worked).

**Fix:** restored the full constructor body and moved `_load_labels` after `__init__` as a proper
static method. Also dropped the shadowed `import os` and unused `random` / `time` imports.

### 1.2 `src/char/Carlotta.py` — `==` where `=` was intended
```python
self._liberation_available == False   # no-op comparison, result discarded
self._resonance_available == False
```
These were meant to reset availability state inside `do_perform`; as comparisons they did
nothing, so Carlotta's rotation could act on stale "liberation/resonance available" state.
**Fix:** changed both to assignments.

### 1.3 `src/task/DiagnosisTask.py` — undefined `logger`
`choose_level()` calls `logger.info(...)` but the module never created a logger →
guaranteed `NameError` the moment the method runs.
**Fix:** added `logger = Logger.get_logger(__name__)`.

### 1.4 `src/task/ForgeryTask.py` — closure late-binding on loop variable
`teleport_once` captured `cand_serial` by reference inside the candidates loop (ruff B023).
It is currently invoked within the same iteration so behavior was correct *today*, but any
refactor that defers the callback (e.g. retry queues in `farm_domain_with_recovery_loop`)
would silently teleport to the wrong domain.
**Fix:** bound the value via a default argument (`serial_to_enter=cand_serial`).

### 1.5 `src/task/FarmEchoTask.py` — hot-loop waste in `click_boss_octagon`
Inside the contour-matching double loop (121 shift positions per contour):
* `cv2.contourArea(trapezoid_scaled)` (loop-invariant) was recomputed every iteration;
* `cnt.astype(np.float32)` was recomputed every iteration;
* a division by zero was possible if the scaled trapezoid degenerated at tiny resolutions.

**Fix:** hoisted both conversions out of the loops, added a guard raising a clear error for a
degenerate template, and removed the dead `best_mat` tracking. Same results, ~100× fewer
redundant `contourArea`/`astype` calls in that search.

### 1.6 `main_debug.py` — self-assignment
`config = config` (no-op). Removed.

### 1.7 Dead code / hygiene (auto-fixed with ruff, then hand-audited)
* ~60 unused imports removed across `src/` (e.g. `WWScene` re-imports in task modules,
  `find_boxes_by_name` / `mask_white` in `BaseWWTask`, PySide6 leftovers in
  `TaskAnnotationStudio`, `cv2`/`numpy` in `FiveToOneTask`, …).
* ~55 `f`-strings without placeholders downgraded to plain strings.
* Unused locals removed where the right-hand side was side-effect free
  (`Camellya.heavy_att/freeze_forte_*`, `Carlotta.last/res`, `Changli.outro`,
  `BaseWWTask.direction/original_mat`, `AutoPickTask.text_area`,
  `Rover`'s unused `has_char(Zani)` probe, `except ... as e` with unused `e`).
  Every removal was reviewed in the diff to confirm no side-effecting call was dropped.

---

## 2. Verified as false positives (left alone, documented here)

* `logger.error('msg', e)` in `CombatCheck`, `BaseCombatTask`, `FarmEchoTask`,
  `MouseResetTask` — ruff flags PLE1205, but `ok.Logger.error(message, exception)` is a custom
  wrapper that formats the exception's stack trace; these calls are correct.
* `raw time.sleep()` inside `Lucy`/`Rebecca`/`ShoreKeeper` rotations — intentional: those loops
  also pump `self.task.next_frame()`, and the timings are gameplay-tuned.
* `BaseCombatTask.time_elapsed_accounting_for_freeze` reassigns `freeze_time` in its loop
  (PLW2901) — intentional handling of the `-100` intro-freeze sentinel.
* `CharFactory` maps several template names onto one shared config dict — intentional aliasing
  for multi-form characters (canonical name is stored explicitly).

---

## 3. Follow-up hardening implemented

The review recommendations below were applied after the initial pass:

1. **Bounded FarmEcho recovery:** `FarmEchoTask.run` now retries popup recovery in an
   iterative state machine. The new `Recovery Retry Count` setting defaults to three and
   prevents recursive task setup or unbounded stack growth when a claim/monthly-card popup
   never clears.
2. **Combat detection diagnostics:** `CombatCheck.in_combat` tracks consecutive capture/OCR
   failures, resets the streak after a clean frame, and emits one actionable notification after
   the third failure while retaining the existing safe reset behavior.
3. **Executable discovery cache:** the two registry/UserAssist scans are cached per process,
   with `clear_pc_exe_path_cache()` for launchers that install or update the game at runtime.
   Running-client path resolution also searches ancestor layouts before using the legacy fallback.
4. **TUI data safety and layout validation:** `TaskConfigStore` now deep-copies nested values so
   callers cannot mutate cached multi-selection data accidentally. `src/tui/grid.py` validates
   column counts and positive widths, using strict zips to reject malformed rows instead of
   silently truncating them.
5. **Non-square detector support:** ONNX Runtime and OpenVINO preprocessing/postprocessing now
   pair height and width axes correctly for non-square model inputs.

The remaining platform limitation is Windows-only test coverage: several test modules still
cannot be collected off-Windows because `win32api`/`win32con` are imported at module scope in
framework dependencies. Guarding those imports is a separate portability change.

---

## 4. Verification

```
python -m compileall src config.py main.py main_debug.py tests
python -m unittest discover tests
```
The repository's test suite covers the new retry, detector-axis, combat-streak,
config-store, and grid validation paths. Full execution requires the pinned
runtime dependencies in `requirements.txt` and Windows for capture/input tests;
the current review sandbox does not have those optional packages installed.
