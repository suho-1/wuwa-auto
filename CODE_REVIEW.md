# Code Review — wuwa-auto

Scope: `src/`, `config.py`, `main.py`, `main_debug.py` (the vendored `ok/` framework was scanned
but intentionally left untouched). Review performed with manual inspection plus `ruff`
(`F`, `E`, `B`, `PLE`, `PLW` rule sets) and the Linux-runnable part of the test suite
(149 tests + 978 subtests, all passing before and after the changes).

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

## 3. Recommendations (not changed — behavior-affecting, need owner judgment)

1. **`FarmEchoTask.run` retries via recursion** (`self.run()` after
   `handle_claim_button()/handle_monthly_card()`): unbounded if a claim popup keeps
   reappearing, and it re-executes `WWOneTimeTask.run` setup each time. Consider a bounded
   `for attempt in range(N)` loop instead.
2. **`CombatCheck.in_combat` swallows all exceptions** and implicitly returns `None`
   (falsy → "not in combat"). Deliberate resilience, but a counter + escalation after N
   consecutive failures would surface genuine capture/OCR breakage faster.
3. **`config.py` registry scan** (`_find_most_recently_run_pc_exe`) walks every UserAssist GUID
   on startup; caching the result per session would shave cold-start time on machines with
   large registries.
4. **Windows-only test coverage**: 5 test modules can't even be collected off-Windows because
   `win32api`/`win32con` are imported at module scope in `src` deps. Guarding those imports
   (as `CombatCheck` consumers do at runtime) would let CI run the logic tests on Linux.
5. **`src/tui/grid.py`** uses `zip()` on sequences assumed equal-length; `strict=True`
   (Python ≥ 3.10) would turn silent column truncation into a loud error.

---

## 4. Verification

```
python -m compileall src          # clean
ruff check src --select F,E9,PLE  # only the 4 documented Logger false positives remain
pytest tests/test_game_display.py tests/test_tui.py \
       tests/test_tui_frame.py tests/test_turning_logic.py
# 149 passed, 978 subtests passed — identical to pre-change baseline
```
(The remaining test modules require Windows `pywin32`/`openvino` and cannot run in this sandbox.)

---

## 4. Second pass — broken task behaviour (Daily / Nightmare Nest / Tacet / Forgery / Team Advisor)

### 4.1 `BaseWWTask.get_locked_keywords` — "Unlocked" matched the `locked` keyword (critical)
The lock keyword list contained bare substring patterns (`locked`, `area.*unlocked`,
`not available`, …). `re.compile('locked', re.I)` matches inside **"Unlocked"**, which the game
shows constantly ("Area Unlocked", "Resonator Unlocked"). Combined with
`is_area_or_beacon_locked()` doing a **full-frame OCR**, almost any screen could be reported as
"locked", so Nightmare Nest skipped every nest and Tacet/Forgery/Daily bailed out or wandered to
an unrelated domain.
**Fix:** precise, anchored patterns (`(?<!un)\block(?:ed)?\b`, `\bnot\s+unlocked\b`, …), dropped
the vague ones, and `is_area_or_beacon_locked()` now scans only the tooltip/toast regions
(full-frame OCR is opt-in via `full_screen=True`).

### 4.2 `Skip Locked Areas = False` was ignored
`config.get('Skip Locked Areas', True) or config.get('Skip Locked Area', True)` is always truthy
when the user disables the option (the second lookup falls back to `True`). Replaced by
`BaseWWTask.skip_locked_areas()`.

### 4.3 `NightmareNestTask`
* `_is_incomplete_nest` accepted **any** `x/y` counter with `10 <= y <= 100`, so unrelated
  guidebook rows (bosses, quests) were clicked as if they were nests. Restricted to the real
  nest counters (24/36/41/48).
* The `run()` / `run_capture_mode()` loops caught bare `Exception`, swallowing
  `TaskDisabledException` → the task could not be stopped. Now re-raised.
* No attempt limit per nest: a nest whose counter never advances was retried forever.
  Added `MAX_ATTEMPTS_PER_NEST = 3`.
* `self._capture_success = dropped` reset an already successful capture back to `False`.
* Dropped the lock probe fired immediately after clicking a row (the panel is still loading →
  false "locked" skips); the map-level checks remain.

### 4.4 `DailyTask.claim_daily` — only the first milestone chest was claimed
The five milestone chests are clicked back-to-back, but each claim opens a reward overlay, so
clicks 2-5 landed on the overlay. Added `dismiss_reward_popup()` between clicks.

### 4.5 `TacetTask` / `ForgeryTask` — unbounded "try another domain" fallback
On a (often false) lock detection the tasks iterated over *every* serial in the F2 list —
19 Tacet fields / 20 Forgery entries, far beyond the 9/6 named options — farming random content.
Serials are now range-checked and at most 3 alternatives are attempted.

### 4.6 `TeamAdvisor` — tier scoring did not understand the current database
The roster sync moved the data to Prydwen tiers (`T0` … `T4`) while the code still weighted
`S+/S/A`, so **every** team scored the default 70 and the ranking was meaningless; dynamic team
synthesis also returned nothing for rosters without a dedicated healer.
**Fix:** `TeamAdvisor.tier_score()` (T-tiers + legacy letters + unknown labels), healer fallback
in `_synthesize_team`, and `AutoTeamTask`'s dead `Min Tier` option now uses T-tiers and is
actually applied.

Tests: stale expectations in `tests/test_team_advisor.py` updated, new regression tests for the
keyword false positives, the config flag, the nest counter filter, the attempt cap and tier
ordering. Full Linux-runnable suite: 207 tests + 986 subtests passing.
