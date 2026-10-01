"""Automated Pseudo-Labeling Engine for ok-ww Vision Foundation Model.

Generates initial candidate bounding boxes in standard YOLO format for:
- Dropped Echoes (General, Gold 5-star, Purple 4-star)
- Active Boss / Elite targets
- In-game Lock-on Reticle
- Floating 'F' Interaction Prompts
"""

import glob
import os
import sys
from typing import List, Tuple, Dict, Any

import cv2
import numpy as np

# Ensure workspace root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.OpenVinoYolo8Detect import OpenVinoYolo8Detect


CLASS_MAP = {
    0: "echo",
    1: "echo_gold",
    2: "echo_purple",
    3: "echo_blue_green",
    4: "target_boss",
    5: "target_mob",
    6: "chest_supply",
    7: "interact_f_prompt",
    8: "beacon_tactical",
    9: "lockon_reticle",
}


class AutoLabeler:
    """Multi-heuristic and model-assisted pseudo-labeling engine."""

    def __init__(self, yolo_weights: str = None):
        self.detector = None
        if yolo_weights and os.path.exists(yolo_weights):
            try:
                self.detector = OpenVinoYolo8Detect(weights=yolo_weights)
            except Exception as exc:
                print(f"[AutoLabeler Warning] Could not load YOLO detector: {exc}")
        elif os.path.exists(os.path.join(REPO_ROOT, "assets", "echo_model", "echo.onnx")):
            try:
                weights = os.path.join(REPO_ROOT, "assets", "echo_model", "echo.onnx")
                self.detector = OpenVinoYolo8Detect(weights=weights)
            except Exception as exc:
                print(f"[AutoLabeler Warning] Could not load default YOLO detector: {exc}")

    def detect_echo_drops(self, image: np.ndarray, threshold: float = 0.35) -> List[Tuple[int, float, float, float, float, float]]:
        """Detect echo drops using YOLO detector and classify by color tier.

        Returns:
            List of (class_id, conf, x_center, y_center, width, height) normalized 0.0-1.0.
        """
        results = []
        if self.detector is None:
            return results

        h, w = image.shape[:2]
        boxes = self.detector.detect(image, threshold=threshold)
        for b in boxes:
            bw_val = getattr(b, "width", getattr(b, "w", 0))
            bh_val = getattr(b, "height", getattr(b, "h", 0))
            x1 = int(max(0, b.x))
            y1 = int(max(0, b.y))
            x2 = int(min(w, b.x + bw_val))
            y2 = int(min(h, b.y + bh_val))
            if x2 <= x1 or y2 <= y1:
                continue

            crop = image[y1:y2, x1:x2]
            class_id = 0  # default echo

            # Analyze color tier inside crop
            if crop.size > 0:
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                # Gold mask (yellow/gold)
                gold_mask = cv2.inRange(hsv, (15, 120, 180), (35, 255, 255))
                # Purple mask
                purple_mask = cv2.inRange(hsv, (125, 100, 150), (160, 255, 255))

                gold_ratio = np.count_nonzero(gold_mask) / float(crop.shape[0] * crop.shape[1])
                purple_ratio = np.count_nonzero(purple_mask) / float(crop.shape[0] * crop.shape[1])

                if gold_ratio > 0.08:
                    class_id = 1  # echo_gold
                elif purple_ratio > 0.08:
                    class_id = 2  # echo_purple

            xc = (b.x + bw_val / 2.0) / float(w)
            yc = (b.y + bh_val / 2.0) / float(h)
            norm_w = bw_val / float(w)
            norm_h = bh_val / float(h)
            results.append((class_id, float(b.confidence), xc, yc, norm_w, norm_h))

        return results

    def detect_lockon_reticle(self, image: np.ndarray) -> List[Tuple[int, float, float, float, float, float]]:
        """Detect the game's target lock-on reticle in the central screen region."""
        h, w = image.shape[:2]
        # Focus on central fighting screen area
        cy1, cy2 = int(h * 0.20), int(h * 0.80)
        cx1, cx2 = int(w * 0.20), int(w * 0.80)
        center_roi = image[cy1:cy2, cx1:cx2]

        gray = cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY)
        # Search for bright circular or symmetric bracket structures
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=100,
            param1=100,
            param2=38,
            minRadius=15,
            maxRadius=65,
        )

        results = []
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for c in circles[0, :2]:  # at most top 2 candidates
                x, y, r = c[0] + cx1, c[1] + cy1, c[2]
                box_w = r * 2.4
                box_h = r * 2.4
                xc = float(x) / float(w)
                yc = float(y) / float(h)
                bw = float(box_w) / float(w)
                bh = float(box_h) / float(h)
                results.append((9, 0.75, xc, yc, bw, bh))  # class 9: lockon_reticle

        return results

    def detect_interact_prompt(self, image: np.ndarray) -> List[Tuple[int, float, float, float, float, float]]:
        """Detect in-game floating 'F' interact prompt square button."""
        h, w = image.shape[:2]
        # Look in the central interaction corridor
        y1, y2 = int(h * 0.35), int(h * 0.75)
        x1, x2 = int(w * 0.40), int(w * 0.65)
        roi = image[y1:y2, x1:x2]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Threshold for white UI element
        _, thresh = cv2.threshold(gray, 225, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            # F prompt button is roughly square (16x16 to 45x45 at 720p)
            aspect = float(rw) / float(rh) if rh > 0 else 0
            if 0.75 <= aspect <= 1.30 and 14 <= rw <= 50 and 14 <= rh <= 50:
                abs_x = rx + x1
                abs_y = ry + y1
                xc = (abs_x + rw / 2.0) / float(w)
                yc = (abs_y + rh / 2.0) / float(h)
                bw = float(rw) / float(w)
                bh = float(rh) / float(h)
                results.append((7, 0.70, xc, yc, bw, bh))  # class 7: interact_f_prompt

        return results

    def detect_combat_boss(self, image: np.ndarray, lockon_boxes: List[Any]) -> List[Tuple[int, float, float, float, float, float]]:
        """Infer boss / elite target bounding box anchored near the lock-on reticle or center-upper arena."""
        h, w = image.shape[:2]
        results = []

        # If a lock-on reticle exists, anchor the boss entity around the reticle
        if lockon_boxes:
            for lk in lockon_boxes:
                _, _, xc, yc, bw, bh = lk
                # Boss body extends above and around the lock-on point
                boss_w = min(0.45, max(0.18, bw * 2.8))
                boss_h = min(0.60, max(0.25, bh * 3.2))
                boss_yc = max(boss_h / 2.0, min(1.0 - boss_h / 2.0, yc - boss_h * 0.15))
                results.append((4, 0.65, xc, boss_yc, boss_w, boss_h))  # class 4: target_boss
        return results

    def label_frame(self, image: np.ndarray) -> List[Tuple[int, float, float, float, float, float]]:
        """Run all detectors on a single frame and return combined bounding boxes."""
        boxes = []
        # 1. Echo drops
        boxes.extend(self.detect_echo_drops(image))

        # 2. Lock-on reticles
        lockons = self.detect_lockon_reticle(image)
        boxes.extend(lockons)

        # 3. Boss entities
        if lockons:
            boxes.extend(self.detect_combat_boss(image, lockons))

        # 4. Interact prompts
        boxes.extend(self.detect_interact_prompt(image))

        return boxes


def run_pseudo_labeling(
    frames_dir: str,
    output_labels_dir: str,
    yolo_weights: str = None,
) -> int:
    """Generate YOLO format .txt annotations for all images in frames_dir."""
    os.makedirs(output_labels_dir, exist_ok=True)
    images = sorted(glob.glob(os.path.join(frames_dir, "*.[jJ][pP][gG]")) + glob.glob(os.path.join(frames_dir, "*.[pP][nN][gG]")))

    labeler = AutoLabeler(yolo_weights=yolo_weights)
    total_boxes = 0
    annotated_frames = 0

    print(f"[AutoLabeler] Processing {len(images)} frames from {frames_dir}...")

    for idx, img_path in enumerate(images):
        img = cv2.imread(img_path)
        if img is None:
            continue

        boxes = labeler.label_frame(img)
        txt_filename = os.path.splitext(os.path.basename(img_path))[0] + ".txt"
        txt_path = os.path.join(output_labels_dir, txt_filename)

        with open(txt_path, "w", encoding="utf-8") as f:
            for cls_id, conf, xc, yc, bw, bh in boxes:
                # Standard YOLO format: <class_id> <x_center> <y_center> <width> <height>
                f.write(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")

        if boxes:
            total_boxes += len(boxes)
            annotated_frames += 1

        if (idx + 1) % 50 == 0 or (idx + 1) == len(images):
            print(f"[AutoLabeler] Progress: {idx + 1}/{len(images)} frames ({annotated_frames} frames with candidates, {total_boxes} total boxes)")

    print(f"[AutoLabeler] Completed! Annotated {annotated_frames}/{len(images)} frames with {total_boxes} candidate boxes.")
    return total_boxes


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ok-ww Automated Pseudo-Labeling Engine")
    parser.add_argument("--frames-dir", default="training/extracted_frames", help="Directory of frames to label")
    parser.add_argument("--labels-dir", default="training/annotations", help="Directory to save YOLO .txt labels")
    parser.add_argument("--weights", default=None, help="Optional YOLO weights path")
    args = parser.parse_args()

    run_pseudo_labeling(args.frames_dir, args.labels_dir, yolo_weights=args.weights)
