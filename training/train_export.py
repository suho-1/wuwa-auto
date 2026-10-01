"""YOLO Training, Evaluation, and ONNX/OpenVINO Export Runner for ok-ww.

This script trains a unified multi-class object detection model using Ultralytics
YOLOv8/YOLOv11, evaluates mAP and latency, and exports production-ready ONNX and
OpenVINO weights for ok-ww.
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Optional


def check_ultralytics_available():
    """Ensure ultralytics is available, or provide instructions."""
    try:
        import ultralytics
        return ultralytics
    except ImportError:
        print("[Error] The 'ultralytics' library is required to train and export YOLO models.")
        print("[Tip] Install it in your training environment via:")
        print("      pip install ultralytics")
        sys.exit(1)


def train_model(
    data_yaml: str,
    base_model: str = "yolov8s.pt",
    epochs: int = 50,
    batch_size: int = 16,
    imgsz: int = 640,
    device: str = "0",
    project: str = "./runs",
    name: str = "ww_brain",
) -> str:
    """Train YOLOv8/YOLOv11 multi-class model on the Wuthering Waves dataset."""
    ultralytics = check_ultralytics_available()
    from ultralytics import YOLO

    print(f"[Training] Loading base model: {base_model}")
    model = YOLO(base_model)

    print(f"[Training] Starting training on {data_yaml} for {epochs} epochs...")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        imgsz=imgsz,
        device=device,
        project=project,
        name=name,
        # Augmentations suited for in-game lighting and dynamic combat
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        save=True,
        save_period=10,
    )

    best_weights = os.path.join(project, name, "weights", "best.pt")
    print(f"[Training] Training completed. Best model saved to: {best_weights}")
    return best_weights


def evaluate_model(weights_path: str, data_yaml: str, device: str = "0"):
    """Evaluate trained model on the validation/test split and display metrics."""
    check_ultralytics_available()
    from ultralytics import YOLO

    print(f"[Evaluation] Validating model {weights_path} against {data_yaml}...")
    model = YOLO(weights_path)
    metrics = model.val(data=data_yaml, device=device, split="val")

    print("\n" + "=" * 55)
    print("           MODEL EVALUATION SUMMARY           ")
    print("=" * 55)
    print(f"  mAP@0.5      : {metrics.box.map50:.4f}")
    print(f"  mAP@0.5:0.95 : {metrics.box.map:.4f}")
    print(f"  Precision    : {metrics.box.mp:.4f}")
    print(f"  Recall       : {metrics.box.mr:.4f}")
    print("=" * 55)

    if hasattr(metrics.box, "maps") and metrics.box.maps is not None:
        print("\n  Per-Class mAP@0.5:0.95:")
        for idx, (cls_name, score) in enumerate(zip(model.names.values(), metrics.box.maps)):
            print(f"    - Class {idx} ({cls_name:<18}): {score:.4f}")
    print("=" * 55 + "\n")
    return metrics


def export_model(
    weights_path: str,
    output_dir: str = "../assets/echo_model",
    imgsz: int = 640,
    export_openvino: bool = True,
):
    """Export best weights to ONNX format and generate matching labels.json."""
    check_ultralytics_available()
    from ultralytics import YOLO

    os.makedirs(output_dir, exist_ok=True)
    model = YOLO(weights_path)

    # 1. Export to ONNX
    print(f"[Export] Exporting {weights_path} to ONNX (imgsz={imgsz})...")
    onnx_path = model.export(
        format="onnx",
        imgsz=imgsz,
        opset=12,
        dynamic=False,
        simplify=True,
    )

    # Copy / Move ONNX to destination
    dst_onnx = os.path.join(output_dir, "echo.onnx")
    if os.path.exists(onnx_path) and onnx_path != dst_onnx:
        import shutil
        shutil.copy2(onnx_path, dst_onnx)
        print(f"[Export] ONNX model deployed to: {dst_onnx}")

    # 2. Generate labels.json
    labels_path = os.path.join(output_dir, "labels.json")
    labels_dict = {str(k): v for k, v in model.names.items()}
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels_dict, f, indent=2)
    print(f"[Export] Class labels mapping saved to: {labels_path}")
    print(f"[Export] Labels: {labels_dict}")

    # 3. Optional OpenVINO IR Export
    if export_openvino:
        try:
            print("[Export] Exporting to OpenVINO IR format...")
            openvino_dir = model.export(format="openvino", imgsz=imgsz, half=True)
            print(f"[Export] OpenVINO model exported to: {openvino_dir}")
        except Exception as exc:
            print(f"[Export Warning] OpenVINO export failed (falling back to ONNX runtime): {exc}")

    print("\n[Export Complete] The new brain is ready for live automation in ok-ww!")


def main():
    parser = argparse.ArgumentParser(description="ok-ww YOLO Training and Deployment Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Train parser
    tr_parser = subparsers.add_parser("train", help="Train a new model")
    tr_parser.add_argument("--data", default="dataset_config.yaml", help="Path to dataset YAML file")
    tr_parser.add_argument("--base", default="yolov8s.pt", help="Pretrained model weights (e.g. yolov8s.pt, yolo11s.pt)")
    tr_parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    tr_parser.add_argument("--batch", type=int, default=16, help="Batch size")
    tr_parser.add_argument("--imgsz", type=int, default=640, help="Input image dimension")
    tr_parser.add_argument("--device", default="0", help="GPU device ID or 'cpu'")

    # Eval parser
    ev_parser = subparsers.add_parser("eval", help="Evaluate model performance")
    ev_parser.add_argument("--weights", required=True, help="Path to .pt weights file")
    ev_parser.add_argument("--data", default="dataset_config.yaml", help="Path to dataset YAML file")
    ev_parser.add_argument("--device", default="0", help="GPU device ID or 'cpu'")

    # Export parser
    ex_parser = subparsers.add_parser("export", help="Export weights to ONNX and OpenVINO")
    ex_parser.add_argument("--weights", required=True, help="Path to .pt weights file")
    ex_parser.add_argument("--out-dir", default="../assets/echo_model", help="Target assets directory")
    ex_parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    ex_parser.add_argument("--skip-openvino", action="store_true", help="Skip OpenVINO IR conversion")

    args = parser.parse_args()

    if args.command == "train":
        best_pt = train_model(
            data_yaml=args.data,
            base_model=args.base,
            epochs=args.epochs,
            batch_size=args.batch,
            imgsz=args.imgsz,
            device=args.device,
        )
        evaluate_model(best_pt, args.data, device=args.device)
        export_model(best_pt)
    elif args.command == "eval":
        evaluate_model(args.weights, args.data, device=args.device)
    elif args.command == "export":
        export_model(args.weights, output_dir=args.out_dir, imgsz=args.imgsz, export_openvino=not args.skip_openvino)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
