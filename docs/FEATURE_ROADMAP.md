# wuwa-auto feature audit and improvement roadmap

Audit date: **2026-10-03**
Target game version: **Wuthering Waves 3.7**
Runtime status: **Reported non-functional across multiple layers; no feature is considered working until it passes the recovery gates below.**

> The scores in this document describe implementation footprint, not verified functionality. They must not be read as reliability scores.

## Research policy

Use each source for what it is good at:

1. **Kuro Games patch notes** are authoritative for newly added systems, regions, bosses, Echoes, and UI changes.
2. **Prydwen** is the strategy source for combat mechanics, character rotations, teams, Echo sets, and resource priorities.
3. **The live game UI** is authoritative for Guidebook ordering, screen coordinates, translated labels, and unlock states. Web research must never be used to guess click coordinates.
4. Every destructive action (discarding, merging, consuming Waveplates, changing equipment) needs a preview or explicit opt-in and a regression test.

Primary references:

- [Prydwen beginner guide](https://www.prydwen.gg/wuthering-waves/guides/beginner-guide)
- [Prydwen game modes](https://www.prydwen.gg/wuthering-waves/guides/game-modes)
- [Prydwen Echoes explained](https://www.prydwen.gg/wuthering-waves/guides/echoes-explained)
- [Prydwen Echo sets](https://www.prydwen.gg/wuthering-waves/guides/echo-sets)
- [Prydwen current tier list](https://www.prydwen.gg/wuthering-waves/tier-list)
- [Kuro Games 3.7 update notice](https://wutheringwaves.kurogames.com/en/main/news/detail/5476)
- [Kuro Games 3.7 patch notes](https://wutheringwaves.kurogames.com/en/main/news/detail/5571)
- [Kuro Games 3.0 patch notes](https://wutheringwaves.kurogames.com/en/main/news/detail/3920)

## Detail scale

| Level | Meaning |
|---|---|
| 1 — shell | A button or stub exists, but it cannot complete a reliable workflow. |
| 2 — basic | One narrow happy path works; coverage and recovery are limited. |
| 3 — usable | Main workflow works with configuration and some recovery. |
| 4 — advanced | Broad coverage, state detection, recovery, and useful controls. |
| 5 — mature | Current-version coverage, safe previews, telemetry, tests, and graceful recovery. |

## Current implementation footprint

All rows currently have runtime status **BROKEN / UNVERIFIED**. A large amount of code exists, but code volume is not evidence that an end-to-end workflow works.

| Feature | Code depth | Evidence in the repository | Main gap | Target |
|---|---:|---|---|---:|
| Desktop control center | 4 | Native Qt capture, task, trigger, schedule, config, log, and notification screens | More wuwa-specific summaries and safer first-run guidance | 5 |
| Daily routine | 4 | Activity OCR, stamina domains, rewards, mail, battle pass, Nightmare Nest, Garden, merge, and follow-up tasks | Spending intent was ambiguous; Simulation omitted Echo EXP | 5 |
| Auto combat | 4 | Shared combat state machine plus 53 character modules, Forte/concerto checks, healer switching, revive handling | Validate every 3.7 rotation and resonance mode against current Prydwen guides | 5 |
| Team Advisor | 3 | Character aliases, predefined teams, fallbacks, Echo recommendations | T0–T4 tiers are not scored correctly by the old S/A weight map; resonance modes and quickswap skill levels need explicit modeling | 5 |
| 4-Cost Echo farming | 3 | Single boss, sweeps, Guidebook tracking, YOLO pickup, locked-area skip, bounded popup recovery | Explicit profiles cover 15 overworld and 5 weekly targets while 3.7 has a larger roster; Data Bank 27/30 behavior is not surfaced | 5 |
| Nightmare/Tacet Discord Nests | 4 | Dynamic OCR queue, normal/difficult targets, locked-area skip, capture-only mode, recovery | Add per-Sonata targeting, daily quota summaries, and 3.7 Nexus coverage validation | 5 |
| Tacet Suppression | 3 | Automated domain loop, double claims, death recovery, locked-field fallback | UI geometry anticipates 19 fields but only 9 are named in settings; current Sonata pairs are incomplete | 5 |
| Forgery Challenge | 3 | Domain selection, material capture, fallback, repeat claims | UI geometry anticipates 20 entries but only 6 are named; 3.x materials/domains are missing | 5 |
| Simulation Challenge | 4 | One run, double claim, 180 target, burn-all, recovery | Needed the fourth current reward type (Echo EXP) and clearer 180-vs-240 behavior | 5 |
| Echo enhancement | 3 | OCR substats, configurable valid stats, crit thresholds, auto-lock/discard | No character/build presets, main-stat gate, weighted roll score, or dry-run report | 5 |
| Echo merge/change | 3 | Automated merge and attribute selection | Needs inventory thresholds, protected-set rules, and a non-destructive preview | 5 |
| Chest exploration | 2 | One 51-stop Gorges of Spirits route and 19 playbook handlers | Only one region; route position recovery relies heavily on scripted actions | 4 |
| Auto pickup/dialog/login/travel | 4 | OCR allow/deny lists, dialogue confirmation, login and travel triggers | Add localization packs, per-trigger metrics, and false-positive review | 5 |
| Multi-account and scheduling | 3 | Account loop, scheduled tasks, exit behavior | Per-account plans, isolated failures, summaries, and credential-safe setup guidance | 5 |
| Diagnostics/annotation/training | 4 | Overlay, screenshots, annotation studio, YOLO/OpenVINO paths, training pipeline | Build repeatable fixture packs for every supported resolution and UI language | 5 |

## Recovery gates (must happen before feature enhancement)

Because startup, capture, and task execution are all reported broken, improvements must proceed through shared-foundation gates rather than by adding more task logic:

1. **Launch gate** — the Qt UI opens without an exception and displays all configured tasks.
2. **Window gate** — Wuthering Waves is discovered and the selected HWND remains stable.
3. **Capture gate** — ten consecutive non-black frames are captured at the actual client resolution; the aspect ratio and scaling are recorded.
4. **Input gate** — a harmless configured key reaches the game in foreground and background modes without a stuck key/button.
5. **Vision gate** — template matching and OCR pass against captured English fixtures at the user's exact resolution.
6. **State gate** — main-world, team, Guidebook, loading, popup, and domain states are recognized before any click automation runs.
7. **Daily smoke gate** — open Guidebook, read Activity/Waveplates, then return to the world without spending or claiming anything.
8. **Daily action gate** — run one explicitly selected Simulation claim and produce a step-by-step report.

The Daily settings now expose these gates directly through **Execution Mode**:

- **Read Only (Guidebook Check)** is the safe default and does not claim rewards or spend Waveplates.
- **One Simulation (40 Waveplates)** performs exactly one claim and verifies a 39–41 regular-Waveplate decrease while requiring reserve Waveplates to remain unchanged.
- **Full Daily Routine** remains opt-in; **Always Burn Waveplates** is disabled by default until the one-Simulation gate passes.

A failure at a gate blocks later gates. Each failure must save a screenshot, the selected capture/input backend, resolution, confidence values, and the final exception to the log.

### Log-driven recovery findings (2026-10-03)

The supplied Windows log came from `ok-ww.exe` **v3.6.7** with `gui: None` and `tui: True`, not from this recovery launcher's Qt-default source. It nevertheless established that the 1280×720 client was discovered, WGC capture started, OCR initialized, PostMessage input navigated the Guidebook, and the old Daily routine completed a Simulation claim. The old routine consumed 40 Waveplates and then printed `Daily Task Completed` without rereading the final Activity total.

The same log reproduced a standalone Nightmare Nest no-op: both configured tabs and their scrolled views were scanned, but no target was selected and no final reason was reported. The recovery source therefore now:

- emits a `WUWA-AUTO STARTUP` banner containing source/runtime version, Qt/TUI mode, source build, Git/build revision, working directory, and entrypoint;
- rereads Daily Activity state instead of reporting completion optimistically;
- logs the configured Nightmare Nest queue, matched counters, and unfiltered OCR text;
- saves the exact normalized Nightmare Nest scan region when no progress counter is recognized;
- returns an explicit “no eligible incomplete nest found” result instead of silently ending.

### Evidence required for the first recovery pass

- `logs/wuwa-auto.log`
- `logs/wuwa-auto_error.log`
- `logs/launcher.log` and `logs/launcher_error.log` when present
- exact client resolution, Windows display scaling, and window mode
- the last visible UI/game state before the failure

These files should contain no account password or token. If a future diagnostic ever encounters such a value, it must redact it before export.

## Improvement order after recovery

### 1. Daily routine and Waveplate policy — code complete, runtime unverified

Prydwen documents four Simulation rewards—Resonator EXP, Weapon EXP, Shell Credits, and Echo EXP—and distinguishes the 180-Waveplate daily activity from the 240 regular Waveplate cap. The policy code now:

- adds **Echo EXP (Sealed Tubes)** to Simulation and Daily settings;
- makes **Always Burn Waveplates** actually consume all regular Waveplates for Tacet, Forgery, and Simulation choices, but keeps it disabled by default;
- keeps reserve Waveplate Crystals untouched;
- provides read-only, one-Simulation, and full-routine execution modes in the desktop settings;
- verifies the one-Simulation gate from the observed regular/reserve Waveplate delta;
- rereads final Activity points and refuses to print a false completion result;
- retains the safe 180 objective when burn-all is disabled;
- centralizes and tests the 180/240 policy.

Next Daily pass after Windows evidence: replace remaining optimistic mail/Battle Pass/reward clicks with state-based result checks, then add weekly-boss planning.

### 2. Current-version activity catalogs

- Capture the 3.7 Guidebook ordering in English and Chinese.
- Expand named Tacet fields from 9 to the 19 entries already represented by layout geometry.
- Expand Forgery names/material families to every visible 3.7 entry.
- Expand boss profiles only after their live serial positions are captured.
- Store content metadata separately from click/navigation logic so future patches are data updates.

### 3. Combat rotations and Team Advisor

For each supported character:

- record Prydwen role, key mechanic, opener, standard loop, swap-cancel points, resonance modes, preferred partners, and failure recovery;
- translate the guide into a deterministic state diagram rather than a fixed sleep chain;
- add rotation trace fixtures and timing budgets;
- correct Team Advisor scoring for Prydwen's T0/T0.5/T1…T4 scale;
- model teams by mechanic tags such as Erosion, Frazzle, Flare, Unison, Coordinated Attack, Heavy Attack, and Echo damage.

### 4. Echo farming

- Bring weekly and overworld boss catalogs to 3.7.
- Display target Sonata and whether the target benefits from enhanced absorption.
- Account for Data Bank level 27 applying enhanced attempts to COST 1/3 and level 30 providing 20 weekly COST-4 enhanced attempts.
- Add stop conditions: drops captured, enhanced attempts spent, elapsed time, and inventory full.
- Add a session report with boss attempts, Echo detections, captures, skips, and recovery count.

### 5. Echo enhancement and inventory safety

- Add main-stat and Sonata gates before spending EXP.
- Ship editable Prydwen-inspired presets per damage profile, never hard-code one universal score.
- Add weighted substat scoring and roll-quality ranges.
- Add **dry run** as the default for discard/merge automation.
- Record every lock/discard decision with OCR text and a screenshot.

### 6. Nightmare Nests and resource domains

- Select nests by desired three-piece Sonata set.
- Distinguish standard/difficult nests and daily remaining enemies.
- Prefer free weekly Remnant Crystal claims before Waveplate spending when detectable.
- Add domain cost and expected resource type to the UI.

### 7. Exploration routes

- Define a versioned route schema with region, prerequisite, start anchor, movement action, verification target, and recovery anchor.
- Add regions incrementally, starting with short routes that can be visually verified.
- Never count a chest as collected without a disappearance/reward/interact-state check.
- Resume by verified anchor rather than only by stop number.

### 8. Utility triggers, multi-account, and diagnostics

- Add trigger hit/miss counters and a recent-decisions screen.
- Add per-account task plans and failure isolation without storing secrets in project files.
- Build screenshot fixtures for 1280×720 through 4K, ultrawide where supported, and all supported languages.

## Definition of done for each feature

A feature reaches level 5 only when it has:

1. current 3.7 content coverage;
2. explicit settings with descriptions and safe defaults;
3. state-based success detection, not only sleeps/click coordinates;
4. bounded retries and a known recovery state;
5. a user-visible completion/failure summary;
6. unit tests for policy logic and fixture tests for visual detection;
7. no destructive or premium-currency action without explicit opt-in;
8. source and last-verified version recorded beside data that can go stale.
