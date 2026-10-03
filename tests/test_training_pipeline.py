"""Unit tests for the training pipeline and multi-class YOLO model support."""

import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from training.pipeline import (
    compute_perceptual_hash,
    hamming_distance,
    is_black_or_loading_screen,
    split_dataset,
)
from src.OpenVinoYolo8Detect import OpenVinoYolo8Detect
from src.OnnxYolo8Detect import OnnxYolo8Detect


class TestTrainingPipeline(unittest.TestCase):

    def test_perceptual_hash_and_hamming(self):
        """Verify perceptual hashing produces identical hash for identical images and different for dissimilar."""
        img1 = np.zeros((100, 100, 3), dtype=np.uint8)
        img1[20:80, 20:80] = 255

        img2 = img1.copy()
        img3 = 255 - img1

        h1 = compute_perceptual_hash(img1)
        h2 = compute_perceptual_hash(img2)
        h3 = compute_perceptual_hash(img3)

        self.assertEqual(h1, h2)
        self.assertEqual(hamming_distance(h1, h2), 0)
        self.assertGreater(hamming_distance(h1, h3), 0)

    def test_non_square_letterbox_targets_keep_height_and_width_axes(self):
        """Both detector backends should preserve NCHW axis order when letterboxing."""
        image = np.zeros((240, 480, 3), dtype=np.uint8)

        onnx_detector = OnnxYolo8Detect.__new__(OnnxYolo8Detect)
        onnx_detector.preprocess_target_h = 320
        onnx_detector.preprocess_target_w = 640
        letterboxed, _ = onnx_detector._preprocess(image)
        self.assertEqual(letterboxed.shape, (1, 3, 320, 640))

        openvino_detector = OpenVinoYolo8Detect.__new__(OpenVinoYolo8Detect)
        openvino_detector.input_height = 320
        openvino_detector.input_width = 640
        letterboxed, _ = openvino_detector._preprocess(image)
        self.assertEqual(letterboxed.shape, (1, 3, 320, 640))

    def test_black_or_loading_screen(self):
        """Verify blank/black screens are detected and normal gameplay frames pass."""
        black_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        self.assertTrue(is_black_or_loading_screen(black_frame))

        # Gameplay-like frame with textures and colors
        np.random.seed(42)
        game_frame = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)
        self.assertFalse(is_black_or_loading_screen(game_frame))

    def test_split_dataset(self):
        """Verify dataset splitting creates proper train/val/test partitions."""
        temp_dir = tempfile.mkdtemp()
        try:
            images_dir = os.path.join(temp_dir, "images")
            os.makedirs(images_dir, exist_ok=True)

            import cv2
            for i in range(20):
                dummy = np.full((50, 50, 3), i * 10, dtype=np.uint8)
                cv2.imwrite(os.path.join(images_dir, f"frame_{i:02d}.jpg"), dummy)

            out_root = os.path.join(temp_dir, "dataset")
            split_dataset(images_dir, out_root, train_ratio=0.7, val_ratio=0.2, test_ratio=0.1)

            train_files = os.listdir(os.path.join(out_root, "images", "train"))
            val_files = os.listdir(os.path.join(out_root, "images", "val"))
            test_files = os.listdir(os.path.join(out_root, "images", "test"))

            self.assertEqual(len(train_files), 14)
            self.assertEqual(len(val_files), 4)
            self.assertEqual(len(test_files), 2)
            self.assertEqual(len(train_files) + len(val_files) + len(test_files), 20)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_labels_loader_and_custom_dic(self):
        """Verify dynamic label discovery and custom dic_labels support."""
        custom_labels = {0: "echo", 1: "target_boss", 2: "chest_supply"}

        weights_path = os.path.join(REPO_ROOT, "assets", "echo_model", "echo.onnx")

        # Custom dic_labels passed directly
        detector = OpenVinoYolo8Detect(
            weights=weights_path,
            dic_labels=custom_labels,
        )
        self.assertEqual(detector.dic_labels[1], "target_boss")
        self.assertEqual(detector.dic_labels[2], "chest_supply")

        # Static _load_labels from directory
        temp_dir = tempfile.mkdtemp()
        try:
            dummy_weights = os.path.join(temp_dir, "model.onnx")
            open(dummy_weights, "w").close()

            # When no labels.json exists, default is {0: 'echo'}
            self.assertEqual(OpenVinoYolo8Detect._load_labels(dummy_weights), {0: "echo"})

            # When labels.json is created
            with open(os.path.join(temp_dir, "labels.json"), "w", encoding="utf-8") as f:
                json.dump({"0": "echo_gold", "1": "chest_supply"}, f)

            loaded = OpenVinoYolo8Detect._load_labels(dummy_weights)
            self.assertEqual(loaded[0], "echo_gold")
            self.assertEqual(loaded[1], "chest_supply")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_auto_labeler_frame(self):
        """Verify AutoLabeler processes an image and generates valid normalized bounding boxes."""
        from training.auto_label import AutoLabeler
        labeler = AutoLabeler()
        # Test image with bright center circle
        test_img = np.zeros((360, 640, 3), dtype=np.uint8)
        import cv2
        cv2.circle(test_img, (320, 180), 30, (255, 255, 255), 2)
        boxes = labeler.label_frame(test_img)
        self.assertIsInstance(boxes, list)
        for b in boxes:
            cls_id, conf, xc, yc, bw, bh = b
            self.assertTrue(0.0 <= xc <= 1.0)
            self.assertTrue(0.0 <= yc <= 1.0)
            self.assertTrue(0.0 < bw <= 1.0)
            self.assertTrue(0.0 < bh <= 1.0)

    def test_annotation_server_api(self):
        """Verify AnnotationServerHandler responds to /api/classes."""
        from http.server import HTTPServer
        import urllib.request
        from training.annotate_ui import AnnotationServerHandler
        import threading
        import time

        server = HTTPServer(("127.0.0.1", 8123), AnnotationServerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.2)
        try:
            req = urllib.request.urlopen("http://127.0.0.1:8123/api/classes")
            self.assertEqual(req.status, 200)
            data = json.loads(req.read().decode("utf-8"))
            self.assertIn("names", data)
            self.assertEqual(len(data["names"]), 10)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
