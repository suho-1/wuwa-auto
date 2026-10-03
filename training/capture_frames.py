"""Guide-driven frame capture and annotation for ok-ww character work.

A character guide (``training/char_guides/<name>.json``) carries a
``capture_points`` list: each entry is a timestamp in the source video plus a
description of what is on screen and which detector it relates to. This tool
turns that list into reviewed, annotated PNGs and can register the resulting
template categories into ``assets/coco_annotations.json``.

Why a window instead of a single frame: only the author's chapter marks are
exact timestamps. Everything else is interpolated from the transcript, so each
capture point is sampled across a few seconds and the sharpest candidate is
promoted to ``<id>.png``. Blur and fade frames are rejected automatically.

Typical use
-----------
Inspect what would be captured (no video needed)::

    python training/capture_frames.py list --guide training/char_guides/hsin.json

Download the source video (needs yt-dlp and network access)::

    python training/capture_frames.py download --guide training/char_guides/hsin.json

Capture and annotate every point::

    python training/capture_frames.py capture --guide training/char_guides/hsin.json

Capture a single point with a wider search window::

    python training/capture_frames.py capture --guide training/char_guides/hsin.json \
        --only hsin_mouse_forte_glow --window 8

Register the candidate template categories into the COCO file::

    python training/capture_frames.py register --guide training/char_guides/hsin.json

IMPORTANT: template matching in ok-ww compares pixel crops of the real game
HUD. Frames taken from a compressed YouTube upload are fine for *reviewing* and
for *locating* a feature, but a template that will be shipped should be cropped
from a clean in-game screenshot at the capture resolution. ``register`` only
creates the category entries; it never invents bounding boxes.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COCO_PATH = os.path.join(REPO_ROOT, "assets", "coco_annotations.json")

# Relative HUD regions, derived from the annotated 4K/1080p templates already in
# assets/coco_annotations.json. (x1, y1, x2, y2) as fractions of the frame.
# The *_VARIANCE values mirror the search padding used by BaseCombatTask.
HUD_REGIONS: Dict[str, Dict[str, object]] = {
    "mouse_forte": {
        "rel": (0.59427, 0.90556, 0.60521, 0.93241),
        "variance": (0.025, 0.015),
        "label": "mouse_forte (basic attack glow)",
        "color": (0, 215, 255),
    },
    "e_forte": {
        "rel": (0.59349, 0.92315, 0.59922, 0.93426),
        "variance": (0.025, 0.0),
        "label": "e_forte (E skill shine)",
        "color": (0, 255, 170),
    },
    "box_resonance": {
        "rel": (0.82943, 0.86898, 0.86458, 0.92130),
        "variance": (0.0, 0.0),
        "label": "box_resonance (E)",
        "color": (255, 170, 0),
    },
    "box_echo": {
        "rel": (0.87786, 0.86898, 0.91302, 0.92315),
        "variance": (0.0, 0.0),
        "label": "box_echo",
        "color": (255, 120, 60),
    },
    "box_liberation": {
        "rel": (0.93021, 0.86898, 0.96302, 0.92130),
        "variance": (0.0, 0.0),
        "label": "box_liberation (R)",
        "color": (200, 120, 255),
    },
    # Coarse areas used for orientation only - not detector regions.
    "hud_forte_gauge": {
        "rel": (0.555, 0.885, 0.625, 0.945),
        "variance": (0.0, 0.0),
        "label": "forte gauge",
        "color": (120, 200, 120),
    },
    "hud_skill_bar": {
        "rel": (0.800, 0.855, 0.975, 0.935),
        "variance": (0.0, 0.0),
        "label": "skill bar",
        "color": (120, 200, 120),
    },
}


# --------------------------------------------------------------------------- #
# guide helpers
# --------------------------------------------------------------------------- #

def load_guide(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def default_video_dir(guide: dict) -> str:
    return os.path.join(REPO_ROOT, "training", "raw_videos")


def default_out_dir(guide: dict) -> str:
    return os.path.join(REPO_ROOT, "training", "captures", guide["character"])


def find_video(guide: dict, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    vid = guide["source"]["video_id"]
    for pattern in (f"*{vid}*.mp4", f"*{vid}*.mkv", f"*{vid}*.webm"):
        hits = sorted(glob.glob(os.path.join(default_video_dir(guide), pattern)))
        if hits:
            return hits[0]
    return None


def fmt_ts(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


# --------------------------------------------------------------------------- #
# frame quality
# --------------------------------------------------------------------------- #

def sharpness(image: np.ndarray) -> float:
    """Variance of the Laplacian - higher means crisper."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_transition(image: np.ndarray, min_brightness: float = 18.0) -> bool:
    """Reject black frames, fades and flat cuts."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray)) < min_brightness or float(np.std(gray)) < 5.0


# --------------------------------------------------------------------------- #
# annotation drawing
# --------------------------------------------------------------------------- #

def _draw_region(frame: np.ndarray, name: str, show_variance: bool = True) -> None:
    spec = HUD_REGIONS.get(name)
    if not spec:
        return
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = spec["rel"]  # type: ignore[misc]
    color = spec["color"]  # type: ignore[assignment]
    px = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))

    if show_variance:
        hv, vv = spec["variance"]  # type: ignore[misc]
        if hv or vv:
            sx1 = max(0, int((x1 - hv) * w))
            sy1 = max(0, int((y1 - vv) * h))
            sx2 = min(w - 1, int((x2 + hv) * w))
            sy2 = min(h - 1, int((y2 + vv) * h))
            cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), color, 1, cv2.LINE_AA)

    cv2.rectangle(frame, (px[0], px[1]), (px[2], px[3]), color, 2, cv2.LINE_AA)

    label = str(spec["label"])
    scale = max(0.4, w / 2400.0)
    thick = max(1, int(round(scale * 2)))
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    ty = px[1] - 8 if px[1] - 8 - th > 0 else px[3] + th + 8
    tx = min(max(0, px[0] - tw // 3), w - tw - 4)
    cv2.rectangle(frame, (tx - 4, ty - th - 4), (tx + tw + 4, ty + 4), (0, 0, 0), -1)
    cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def annotate_frame(frame: np.ndarray, guide: dict, point: dict, actual_ts: float) -> np.ndarray:
    """Draw the caption banner and any detector regions this point refers to."""
    out = frame.copy()
    h, w = out.shape[:2]

    for region in point.get("annotate", []) or []:
        _draw_region(out, region)

    scale = max(0.45, w / 2200.0)
    thick = max(1, int(round(scale * 2)))
    line_h = int(34 * scale) + 10

    anchor = point.get("anchor", "interpolated")
    anchor_txt = "exact chapter mark" if anchor == "chapter_exact" else "interpolated (+/- a few s)"
    lines = [
        f"{guide['display_name']}  |  {point['id']}",
        f"t={fmt_ts(actual_ts)} ({actual_ts:.2f}s)  [{anchor_txt}]  chapter: {point.get('chapter', '-')}",
        f"{point.get('what', '')}",
    ]
    cue = point.get("cue")
    if cue:
        lines.append(f'cue: "{cue}"')
    note = point.get("note")
    if note:
        lines.append(f"note: {note}")
    lines.append(f"purpose: {point.get('purpose', '-')}   src: {guide['source']['video_id']}")

    banner_h = line_h * len(lines) + 16
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.62, out, 0.38, 0, out)

    y = line_h
    for i, text in enumerate(lines):
        color = (255, 255, 255) if i == 0 else (190, 220, 255)
        cv2.putText(out, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
        y += line_h
    return out


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_list(args) -> int:
    guide = load_guide(args.guide)
    points = guide.get("capture_points", [])
    print(f"{guide['display_name']} <- {guide['source']['url']}")
    print(f"{len(points)} capture points\n")
    print(f"{'id':<34}{'time':>8}  {'anchor':<16}{'purpose':<26}annotate")
    print("-" * 118)
    for p in points:
        print(f"{p['id']:<34}{fmt_ts(p['seconds']):>8}  "
              f"{p.get('anchor', ''):<16}{p.get('purpose', ''):<26}"
              f"{','.join(p.get('annotate', []) or []) or '-'}")
    return 0


def cmd_download(args) -> int:
    guide = load_guide(args.guide)
    url = guide["source"]["url"]
    out_dir = args.out_dir or default_video_dir(guide)
    os.makedirs(out_dir, exist_ok=True)
    template = os.path.join(out_dir, "%(title).60s [%(id)s].%(ext)s")
    fmt = f"bestvideo[height<={args.quality}][ext=mp4]+bestaudio/best[height<={args.quality}]/best"
    for cmd in ([sys.executable, "-m", "yt_dlp"], ["yt-dlp"]):
        try:
            subprocess.run(cmd + ["--format", fmt, "--no-playlist", "-o", template, url], check=True)
            break
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            last = exc
    else:
        print(f"[capture] yt-dlp failed: {last}\n[capture] install it with: pip install yt-dlp")
        return 1
    found = find_video(guide, None)
    print(f"[capture] downloaded: {found}")
    return 0 if found else 1


def _candidates_for(cap: cv2.VideoCapture, centre: float, window: float,
                    step: float) -> List[Tuple[float, np.ndarray]]:
    half = window / 2.0
    start = max(0.0, centre - half)
    out: List[Tuple[float, np.ndarray]] = []
    t = start
    while t <= centre + half:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if ok and frame is not None and not is_transition(frame):
            out.append((t, frame))
        t += step
    return out


def cmd_capture(args) -> int:
    guide = load_guide(args.guide)
    video = find_video(guide, args.video)
    if not video:
        print("[capture] No source video found.")
        print(f"[capture] Expected something matching *{guide['source']['video_id']}* in "
              f"{default_video_dir(guide)}")
        print("[capture] Fetch it with:  python training/capture_frames.py download "
              f"--guide {args.guide}")
        return 1

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        print(f"[capture] Could not open {video}")
        return 1

    out_dir = args.out_dir or default_out_dir(guide)
    raw_dir = os.path.join(out_dir, "candidates")
    os.makedirs(out_dir, exist_ok=True)
    if args.keep_candidates:
        os.makedirs(raw_dir, exist_ok=True)

    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None
    points = [p for p in guide.get("capture_points", [])
              if wanted is None or p["id"] in wanted]
    if not points:
        print("[capture] No capture points matched.")
        return 1

    window = args.window if args.window is not None else \
        float(guide.get("capture_notes", {}).get("recommended_window_seconds", 4))

    print(f"[capture] source : {os.path.basename(video)}")
    print(f"[capture] output : {out_dir}")
    print(f"[capture] points : {len(points)}  window={window}s step={args.step}s\n")

    written = 0
    for p in points:
        # Exact chapter marks need no search; interpolated ones do.
        win = 0.0 if (p.get("anchor") == "chapter_exact" and not args.force_window) else window
        cands = _candidates_for(cap, float(p["seconds"]), win, args.step)
        if not cands:
            print(f"  ! {p['id']:<34} no usable frame near {fmt_ts(p['seconds'])}")
            continue

        best_ts, best = max(cands, key=lambda tf: sharpness(tf[1]))

        if args.keep_candidates:
            for ts, fr in cands:
                cv2.imwrite(os.path.join(raw_dir, f"{p['id']}_{ts:07.2f}.png"), fr)

        cv2.imwrite(os.path.join(out_dir, f"{p['id']}.png"), best)
        annotated = annotate_frame(best, guide, p, best_ts)
        cv2.imwrite(os.path.join(out_dir, f"{p['id']}_annotated.png"), annotated)
        written += 1
        flag = "=" if win == 0 else "~"
        print(f"  {flag} {p['id']:<34} {fmt_ts(best_ts)} ({best_ts:7.2f}s)  "
              f"{len(cands):>2} cand  sharp={sharpness(best):8.1f}")

    cap.release()

    manifest = {
        "character": guide["character"],
        "source": guide["source"],
        "window_seconds": window,
        "points": [{"id": p["id"], "seconds": p["seconds"], "anchor": p.get("anchor"),
                    "purpose": p.get("purpose"), "annotate": p.get("annotate", [])}
                   for p in points],
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\n[capture] wrote {written} frame(s) + annotated copies to {out_dir}")
    print("[capture] review the *_annotated.png files, then crop shippable templates "
          "from a clean in-game screenshot.")
    return 0


def cmd_register(args) -> int:
    """Create COCO categories for the guide's candidate templates (no bboxes)."""
    guide = load_guide(args.guide)
    wanted = []
    for p in guide.get("capture_points", []):
        cat = p.get("candidate_category")
        if cat and cat not in wanted:
            wanted.append(cat)
    if not wanted:
        print("[register] guide declares no candidate_category entries.")
        return 0

    with open(COCO_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    existing = {c["name"]: c["id"] for c in data["categories"]}
    next_id = max(c["id"] for c in data["categories"]) + 1
    added = []
    for name in wanted:
        if name in existing:
            print(f"  = {name} (already id={existing[name]})")
            continue
        data["categories"].append({"id": next_id, "name": name, "supercategory": ""})
        added.append((name, next_id))
        print(f"  + {name} (id={next_id})")
        next_id += 1

    if not added:
        print("[register] nothing to do.")
        return 0
    if args.dry_run:
        print("[register] dry run, not writing.")
        return 0

    with open(COCO_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)
    print(f"[register] added {len(added)} categor(y/ies) to {COCO_PATH}")
    print("[register] they have no annotations yet - draw boxes with the Annotation "
          "Studio or tools/add_char_annotations.py.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Guide-driven frame capture and annotation for ok-ww")
    sub = ap.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="show the capture points in a guide")
    p_list.add_argument("--guide", required=True)

    p_dl = sub.add_parser("download", help="download the guide's source video with yt-dlp")
    p_dl.add_argument("--guide", required=True)
    p_dl.add_argument("--out-dir", default=None)
    p_dl.add_argument("--quality", default="1080", choices=["2160", "1440", "1080", "720"])

    p_cap = sub.add_parser("capture", help="extract and annotate frames for a guide")
    p_cap.add_argument("--guide", required=True)
    p_cap.add_argument("--video", default=None, help="explicit video path")
    p_cap.add_argument("--out-dir", default=None)
    p_cap.add_argument("--only", default=None, help="comma separated capture point ids")
    p_cap.add_argument("--window", type=float, default=None,
                       help="seconds to search around each interpolated timestamp")
    p_cap.add_argument("--step", type=float, default=0.5, help="sampling step inside the window")
    p_cap.add_argument("--keep-candidates", action="store_true",
                       help="also keep every sampled frame")
    p_cap.add_argument("--force-window", action="store_true",
                       help="search a window even around exact chapter marks")

    p_reg = sub.add_parser("register", help="add candidate template categories to the COCO file")
    p_reg.add_argument("--guide", required=True)
    p_reg.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "download":
        return cmd_download(args)
    if args.command == "capture":
        return cmd_capture(args)
    if args.command == "register":
        return cmd_register(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
