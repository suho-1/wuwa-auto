"""YouTube Video Ingestion & Smart Dataset Extraction Pipeline for ok-ww.

This tool extracts high-quality, non-redundant training keyframes from YouTube
gameplay videos or local MP4 captures, applies perceptual deduplication, and
prepares YOLO-formatted training splits.
"""

import argparse
import glob
import math
import os
import shutil
import subprocess
import sys
from typing import List, Tuple

import cv2
import numpy as np


def compute_perceptual_hash(image: np.ndarray, hash_size: int = 8) -> int:
    """Compute a 64-bit perceptual hash (dHash) to detect visually similar frames."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    hash_val = 0
    for bit in diff.flatten():
        hash_val = (hash_val << 1) | int(bit)
    return hash_val


def hamming_distance(h1: int, h2: int) -> int:
    """Return the number of differing bits between two 64-bit hashes."""
    x = h1 ^ h2
    return bin(x).count("1")


def is_black_or_loading_screen(image: np.ndarray, min_brightness: float = 22.0) -> bool:
    """Check if the frame is a black loading screen or transition fade."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    # If the frame has very low average brightness or extremely low variance (flat screen)
    return mean_val < min_brightness or std_val < 5.0


def download_youtube_video(url: str, output_dir: str, format_spec: str = "bestvideo[height<=1080][ext=mp4]/best[height<=1080][ext=mp4]/best") -> str:
    """Download gameplay video from YouTube using yt-dlp."""
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(title).50s [%(id)s].%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--format", format_spec,
        "--no-playlist",
        "-o", output_template,
        url,
    ]
    print(f"[Pipeline] Downloading YouTube video from {url}...")
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Try running yt-dlp directly if installed as a standalone CLI tool
        try:
            cmd = ["yt-dlp", "--format", format_spec, "--no-playlist", "-o", output_template, url]
            subprocess.run(cmd, check=True)
        except Exception as exc:
            print(f"[Pipeline Error] Failed to run yt-dlp: {exc}")
            print("[Tip] Ensure yt-dlp is installed via: pip install yt-dlp")
            raise

    # Find the downloaded video file
    video_files = sorted(
        glob.glob(os.path.join(output_dir, "*.mp4")) +
        glob.glob(os.path.join(output_dir, "*.mkv")) +
        glob.glob(os.path.join(output_dir, "*.webm")),
        key=os.path.getmtime,
        reverse=True
    )
    if not video_files:
        raise FileNotFoundError(f"No video file found in {output_dir} after download.")
    downloaded = video_files[0]
    print(f"[Pipeline] Download completed: {downloaded}")
    return downloaded


def extract_keyframes(
    video_path: str,
    output_dir: str,
    fps: float = 1.0,
    hash_threshold: int = 6,
    max_frames: int = 5000,
) -> int:
    """Extract diverse, informative keyframes from a gameplay video.

    Args:
        video_path: Path to the input video file.
        output_dir: Directory where extracted JPEG/PNG frames are stored.
        fps: Target sampling rate (frames per second).
        hash_threshold: Minimum bit difference in dHash to consider a frame new.
        max_frames: Maximum number of frames to save.

    Returns:
        Number of saved frames.
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_interval = max(1, int(round(video_fps / max(0.1, fps))))

    print(f"[Pipeline] Processing video: {os.path.basename(video_path)}")
    print(f"[Pipeline] Video FPS: {video_fps:.1f}, Total Frames: {total_frames}, Sampling interval: every {frame_interval} frames")

    saved_count = 0
    frame_idx = 0
    last_hash = None
    base_name = os.path.splitext(os.path.basename(video_path))[0][:30]

    while cap.isOpened() and saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            if not is_black_or_loading_screen(frame):
                curr_hash = compute_perceptual_hash(frame)
                if last_hash is None or hamming_distance(curr_hash, last_hash) >= hash_threshold:
                    frame_filename = f"{base_name}_f{frame_idx:06d}.jpg"
                    save_path = os.path.join(output_dir, frame_filename)
                    cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    saved_count += 1
                    last_hash = curr_hash

                    if saved_count % 50 == 0:
                        print(f"[Pipeline] Extracted {saved_count} frames (video progress: {frame_idx}/{total_frames})...")

        frame_idx += 1

    cap.release()
    print(f"[Pipeline] Extraction finished: saved {saved_count} unique frames into {output_dir}")
    return saved_count


def split_dataset(
    images_dir: str,
    output_root: str,
    train_ratio: float = 0.80,
    val_ratio: float = 0.15,
    test_ratio: float = 0.05,
    labels_dir: str = None,
):
    """Split extracted frames and label files into standard YOLO train/val/test folders."""
    all_images = sorted(glob.glob(os.path.join(images_dir, "*.[jJ][pP][gG]")) + glob.glob(os.path.join(images_dir, "*.[pP][nN][gG]")))
    total = len(all_images)
    if total == 0:
        print(f"[Pipeline Error] No images found in {images_dir} to split.")
        return

    np.random.seed(42)
    np.random.shuffle(all_images)

    n_train = int(total * train_ratio)
    n_val = int(total * val_ratio)

    splits = {
        "train": all_images[:n_train],
        "val": all_images[n_train:n_train + n_val],
        "test": all_images[n_train + n_val:],
    }

    for split_name, img_paths in splits.items():
        img_out = os.path.join(output_root, "images", split_name)
        lbl_out = os.path.join(output_root, "labels", split_name)
        os.makedirs(img_out, exist_ok=True)
        os.makedirs(lbl_out, exist_ok=True)

        for src_img in img_paths:
            dst_img = os.path.join(img_out, os.path.basename(src_img))
            shutil.copy2(src_img, dst_img)

            # Copy corresponding .txt label if it exists
            if labels_dir:
                base_txt = os.path.splitext(os.path.basename(src_img))[0] + ".txt"
                src_txt = os.path.join(labels_dir, base_txt)
                if os.path.exists(src_txt):
                    shutil.copy2(src_txt, os.path.join(lbl_out, base_txt))
                else:
                    # Create an empty label file if no annotations exist yet
                    open(os.path.join(lbl_out, base_txt), "a").close()

    print(f"[Pipeline] Dataset organized in {output_root}:")
    print(f"  - Train: {len(splits['train'])} frames")
    print(f"  - Val:   {len(splits['val'])} frames")
    print(f"  - Test:  {len(splits['test'])} frames")


def main():
    parser = argparse.ArgumentParser(description="ok-ww Video Dataset Ingestion and Preprocessing Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    # Download sub-command
    dl_parser = subparsers.add_parser("download", help="Download a YouTube video")
    dl_parser.add_argument("--url", required=True, help="YouTube video or playlist URL")
    dl_parser.add_argument("--out-dir", default="./raw_videos", help="Directory to save downloaded video")
    dl_parser.add_argument("--quality", choices=["1080", "720", "480"], default="720", help="Video resolution quality (default: 720)")
    dl_parser.add_argument("--format", default=None, help="Custom format selector for yt-dlp")

    # Extract sub-command
    ext_parser = subparsers.add_parser("extract", help="Extract diverse keyframes from video")
    ext_parser.add_argument("--video", required=True, help="Path to video file or directory of videos")
    ext_parser.add_argument("--out-dir", default="./extracted_frames", help="Output directory for frames")
    ext_parser.add_argument("--fps", type=float, default=1.0, help="Sampling frequency (frames per second)")
    ext_parser.add_argument("--threshold", type=int, default=6, help="dHash Hamming distance threshold")

    # Split sub-command
    split_parser = subparsers.add_parser("split", help="Split extracted images into train/val/test")
    split_parser.add_argument("--images-dir", required=True, help="Path to folder containing extracted images")
    split_parser.add_argument("--labels-dir", default=None, help="Path to folder containing YOLO .txt annotations")
    split_parser.add_argument("--out-dir", default="./dataset", help="Output root for YOLO dataset")

    # Run-all sub-command
    all_parser = subparsers.add_parser("run_all", help="Download, extract, and organize dataset in one step")
    all_parser.add_argument("--url", required=True, help="YouTube video URL")
    all_parser.add_argument("--out-dir", default="./dataset", help="Output dataset root")
    all_parser.add_argument("--fps", type=float, default=1.0, help="Frames per second")
    all_parser.add_argument("--quality", choices=["1080", "720", "480"], default="720", help="Video resolution quality (default: 720)")

    args = parser.parse_args()

    if args.command == "download":
        fmt = args.format or f"bestvideo[height<={args.quality}][ext=mp4]/best[height<={args.quality}][ext=mp4]/best"
        download_youtube_video(args.url, args.out_dir, format_spec=fmt)
    elif args.command == "extract":
        if os.path.isdir(args.video):
            vids = glob.glob(os.path.join(args.video, "*.mp4")) + glob.glob(os.path.join(args.video, "*.mkv"))
            for v in vids:
                extract_keyframes(v, args.out_dir, fps=args.fps, hash_threshold=args.threshold)
        else:
            extract_keyframes(args.video, args.out_dir, fps=args.fps, hash_threshold=args.threshold)
    elif args.command == "split":
        split_dataset(args.images_dir, args.out_dir, labels_dir=args.labels_dir)
    elif args.command == "run_all":
        fmt = f"bestvideo[height<={args.quality}][ext=mp4]/best[height<={args.quality}][ext=mp4]/best"
        video_path = download_youtube_video(args.url, "./raw_videos", format_spec=fmt)
        frames_dir = "./extracted_frames"
        extract_keyframes(video_path, frames_dir, fps=args.fps)
        split_dataset(frames_dir, args.out_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
