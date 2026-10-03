# Wuthering Waves (ok-ww) Vision Foundation Model: Training & Evaluation Pipeline

This guide details how to train, evaluate, and upgrade the unified vision model ("The Brain") for `ok-ww` using gameplay videos sourced from YouTube.

---

## 1. Architecture Overview

### Current State
* **Model**: Single-class YOLOv8 object detector (`assets/echo_model/echo.onnx`).
* **Input**: `[1, 3, 640, 640]` normalized RGB image.
* **Output**: `[1, 5, 8400]` (`[cx, cy, w, h, echo_score]`).
* **Limitation**: The model only detects dropped Echoes. The bot is blind to enemies, bosses, chests, prompts, and world objects, requiring brittle heuristics and OCR fallbacks for everything else.

### Upgraded Multi-Class Vision Foundation
By training on YouTube gameplay footage across diverse locations, lighting conditions, and combat scenarios, we turn the detector into a **unified perception engine** supporting:

| Class ID | Label Name | Usage in ok-ww Automations |
| :--- | :--- | :--- |
| `0` | `echo` | General echo drops (backward compatible) |
| `1` | `echo_gold` | 5-Star golden echoes (priority pickup) |
| `2` | `echo_purple` | 4-Star purple echoes |
| `3` | `echo_blue_green` | 2-Star / 3-Star low tier echoes |
| `4` | `target_boss` | Boss hitbox / entity tracking in combat |
| `5` | `target_mob` | Overworld common & elite monsters |
| `6` | `chest_supply` | Chest exploration route auto-farming |
| `7` | `interact_f_prompt` | Overworld interaction F prompt |
| `8` | `beacon_tactical` | Holograms, challenge totems, tacet field bulbs |
| `9` | `lockon_reticle` | In-game lock-on target reticle |

---

## 2. Environment Setup

For dataset extraction and video processing:
```bash
pip install yt-dlp opencv-python numpy
```

For YOLO model training and ONNX export (run on a machine with NVIDIA GPU):
```bash
pip install ultralytics torch torchvision
```

---

## 3. End-to-End Pipeline Workflow

### Step 1: Video Ingestion from YouTube
Target high-resolution (1080p60 or 4K) YouTube videos:
- **Echo Farming Routes**: Captures varied terrain, lighting, and drop drops.
- **Boss Fights & Hologram Challenges**: Captures boss hitboxes, combat effects, lock-on reticles.
- **Chest & 100% Exploration Guides**: Captures overworld chests, interaction prompts, and beacons.

Run the pipeline downloader:
```bash
python training/pipeline.py download --url "https://www.youtube.com/watch?v=VIDEO_ID" --out-dir ./raw_videos
```

### Step 2: Intelligent Keyframe Extraction & Deduplication
Instead of saving redundant sequential frames, `pipeline.py` uses 64-bit perceptual hashing (`dHash`) and brightness variance checks:
- Automatically filters out black loading screens and fade transitions.
- Skips static frames when characters are standing still or in dialogues.
- Extracts distinct keyframes at 1.0 - 2.0 FPS:

```bash
python training/pipeline.py extract --video ./raw_videos --out-dir ./extracted_frames --fps 1.5 --threshold 6
```

### Step 3: Annotation / Pseudo-Labeling
1. **Auto-labeling via Foundation Models**: Use zero-shot models (e.g. YOLO-World or Florence-2) or an existing checkpoint to generate pseudo-labels in YOLO format (`.txt` files).
2. **Review in Labeling Tool**: Open `./extracted_frames` in Label Studio, CVAT, or Roboflow for quick verification and edge-case correction.

### Step 4: Dataset Organization
Split extracted images and label files into standard 80/15/5 training splits:
```bash
python training/pipeline.py split --images-dir ./extracted_frames --labels-dir ./annotations --out-dir ./dataset
```

### Step 5: Training & Evaluation
Train YOLOv8s or YOLOv11s with data augmentations tuned for game particle effects and day/night transitions:
```bash
python training/train_export.py train --data training/dataset_config.yaml --base yolov8s.pt --epochs 50 --batch 16 --imgsz 640 --device 0
```

Validation metrics evaluate:
- **mAP@0.5**: Target $\ge 0.85$ across all classes.
- **mAP@0.5:0.95**: Target $\ge 0.65$.
- **Inference Latency**: Under 15 ms on DirectML GPU / Intel OpenVINO NPU.

### Step 6: Export & Live Deployment
The script automatically exports:
1. `assets/echo_model/echo.onnx`: The multi-class ONNX weights.
2. `assets/echo_model/labels.json`: The class ID mapping dictionary.
3. OpenVINO IR files (`echo.xml` / `echo.bin`) for high-speed NPU inference.

`ok-ww` automatically detects `labels.json` and loads the new multi-class brain with zero code modifications!

---

## 4. Character Guide Workflow (Rexlent "WuWa Guides" playlist)

Combat logic for individual resonators is driven by the Rexlent guide playlist
[`PLT669jfZO0z9sA1RCWuQfIpufrIkI3s3f`](https://www.youtube.com/playlist?list=PLT669jfZO0z9sA1RCWuQfIpufrIkI3s3f).
One character is processed at a time and each one produces the same four artefacts:

| Artefact | Path | Purpose |
| :--- | :--- | :--- |
| Transcript | `training/transcripts/<char>_<videoid>.en.txt` | Source text with the author's official chapter marks |
| Guide data | `training/char_guides/<char>.json` | Structured moves, rotations, build, teams, capture points |
| Combat logic | `src/char/<Char>.py` | The rotation, with the guide timestamp cited per phase |
| Team data | `configs/rexlent_teams.json` | Character entry plus meta teams, linked by `guide_url` |

### Step 1: Capture the guide knowledge
Pull the transcript and the chapter list from the video description. Chapter
marks are exact timestamps; anything in between is estimated by locating the
spoken cue inside its chapter and interpolating by word position. Record which
of the two it is in the `anchor` field (`chapter_exact` or `interpolated`).

### Step 2: Describe the capture points
Each entry in `capture_points` is a timestamp plus what is on screen, and is
tagged with a `purpose`:

* `verify_existing_template` - confirms a generic detector (e.g. `mouse_forte`)
  fires on this character's HUD.
* `candidate_template` - a character-specific cue that has no template yet.
  Name it in `candidate_category`.
* `negative_sample` - a near-miss frame, useful for threshold tuning.
* `reference` / `documentation` - cheat sheets and move demos for humans.

### Step 3: Extract and annotate frames
```bash
python training/capture_frames.py list     --guide training/char_guides/hsin.json
python training/capture_frames.py download --guide training/char_guides/hsin.json
python training/capture_frames.py capture  --guide training/char_guides/hsin.json
```
Interpolated points are sampled across a window (default 4s), black/fade frames
are discarded and the sharpest candidate is promoted. Every frame is written
twice: `<id>.png` (clean) and `<id>_annotated.png` (caption banner plus the
detector regions the bot actually searches, including the search variance
padding). Output goes to `training/captures/<char>/`, which is gitignored.

> **Templates must come from real game pixels.** A frame from a compressed
> YouTube upload is fine for *locating* a feature and for review, but a
> template that ships should be cropped from a clean in-game screenshot at the
> capture resolution. `capture_frames.py register` therefore only creates the
> COCO *categories* - it never invents bounding boxes.

### Step 4: Register and annotate new templates
```bash
python training/capture_frames.py register --guide training/char_guides/hsin.json
python tools/add_char_annotations.py --check
```
Then draw the boxes in the Annotation Studio, or pass explicit coordinates to
`tools/add_char_annotations.py`.

### Step 5: Implement and pin the rotation
Write the rotation in `src/char/<Char>.py`, citing the guide timestamp for each
phase, and add a test that pins the input order so later refactors cannot drift
from the guide. See `src/char/Hsin.py` and `tests/test_hsin_rotation.py`.

Prefer the existing generic detectors over new templates where the guide's cue
already maps onto one:

| Guide wording | Detector | Meaning |
| :--- | :--- | :--- |
| "the basic attack is glowing" | `mouse_forte` | Forte bar full, hold basic attack |
| "your E skill is shining" | `e_forte` | Enhanced Resonance Skill ready |

If a character has a player-selected mode that changes the rotation (Hsin's
Unison vs Electro Flare), expose it as a flag in `char_config_option` in
`config.py` rather than guessing it from the HUD.

### Progress
| # | Character | Video | Status |
| :--- | :--- | :--- | :--- |
| 1 | Hsin | [`-JiixPs82UI`](https://www.youtube.com/watch?v=-JiixPs82UI) | Guide data, rotation, teams and tests done. Frame capture pending a machine with YouTube access. |

---

## 5. Retraining on New Game Patches
When a new game patch drops with new areas, bosses, or mechanics:
1. Download 2-3 YouTube showcase walkthroughs of the new area.
2. Extract frames using `python training/pipeline.py extract`.
3. Add the new annotations to `./dataset/images/train`.
4. Run incremental fine-tuning:
   ```bash
   python training/train_export.py train --base runs/ww_brain/weights/best.pt --epochs 20
   ```
5. Export and replace `assets/echo_model/echo.onnx`.
