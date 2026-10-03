"""
Annotation Helper for Missing Characters
=========================================
This script adds placeholder categories for char_hsin, char_jingran, and
char_suoming to coco_annotations.json. Once you take a game screenshot with
these characters in your party HUD and drop it into assets/images/, run this
script with the screenshot filename to auto-register the image + annotations.

Usage:
  # Step 1: Take a 3840x2160 (or any res) screenshot in-game with Hsin, Jingran,
  #         and/or Suoming visible in your party sidebar (right side).
  #         Save it to assets/images/ (e.g., assets/images/48.png).

  # Step 2: Open the Annotation Studio to draw bboxes:
  #   ..\\python\\python.exe -c "from src.gui.TaskAnnotationStudio import TaskAnnotationStudio; TaskAnnotationStudio.launch()"
  #
  #   OR run this script in auto mode if you know the bbox coordinates:
  #   ..\\python\\python.exe tools/add_char_annotations.py 48.png char_hsin 3545 455 80 80
  #   ..\\python\\python.exe tools/add_char_annotations.py 48.png char_jingran 3545 725 80 80
  #   ..\\python\\python.exe tools/add_char_annotations.py 48.png char_suoming 3545 990 80 80

  # Step 3 (optional): Add box_resonance_cd on a combat screenshot:
  #   ..\\python\\python.exe tools/add_char_annotations.py 1.png box_resonance_cd 3185 1877 135 60

Run with --check to see the current annotation status.
"""

import json
import sys
import os
from pathlib import Path

ANNO_FILE = Path(__file__).resolve().parent.parent / 'assets' / 'coco_annotations.json'

MISSING_CHARS = ['char_hsin', 'char_jingran', 'char_suoming']
MISSING_BOXES = ['box_resonance_cd']


def load_coco():
    with open(ANNO_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_coco(data):
    with open(ANNO_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Saved {ANNO_FILE}")


def check_status():
    data = load_coco()
    cats = {c['name']: c['id'] for c in data['categories']}
    ann_cat_ids = {a['category_id'] for a in data['annotations']}

    print("=== Missing Feature Status ===\n")
    all_missing = MISSING_CHARS + MISSING_BOXES
    for name in all_missing:
        if name not in cats:
            print(f"  {name:25s}  CATEGORY MISSING (not in annotations file)")
        elif cats[name] not in ann_cat_ids:
            print(f"  {name:25s}  Category exists (id={cats[name]}) but NO ANNOTATION")
        else:
            ann = next(a for a in data['annotations'] if a['category_id'] == cats[name])
            print(f"  {name:25s}  OK (ann_id={ann['id']}, bbox={ann['bbox']})")

    print(f"\n  Total categories: {len(cats)}")
    print(f"  Total annotations: {len(data['annotations'])}")
    print(f"  Total images: {len(data['images'])}")


def ensure_categories(data):
    """Add missing category entries if they don't exist yet."""
    cats = {c['name']: c['id'] for c in data['categories']}
    max_id = max(c['id'] for c in data['categories'])

    added = []
    for name in MISSING_CHARS + MISSING_BOXES:
        if name not in cats:
            max_id += 1
            entry = {"id": max_id, "name": name, "supercategory": ""}
            data['categories'].append(entry)
            cats[name] = max_id
            added.append(name)

    if added:
        print(f"Added categories: {added}")
    return cats


def ensure_image(data, filename):
    """Add image entry if it doesn't exist. Returns the image id."""
    for img in data['images']:
        if img['file_name'] == filename or img['file_name'] == f"images/{filename}":
            return img['id'], img

    # Need to determine image dimensions
    img_path = ANNO_FILE.parent / 'images' / filename
    if not img_path.exists():
        img_path = ANNO_FILE.parent / filename
    if not img_path.exists():
        print(f"ERROR: Image not found at {img_path}")
        sys.exit(1)

    from PIL import Image
    with Image.open(img_path) as im:
        w, h = im.size

    max_id = max(i['id'] for i in data['images']) if data['images'] else 0
    new_id = max_id + 1
    entry = {
        "id": new_id,
        "file_name": f"images/{filename}",
        "width": w,
        "height": h,
        "license": 0,
        "url": None,
        "date_captured": None
    }
    data['images'].append(entry)
    print(f"Added image: {entry}")
    return new_id, entry


def add_annotation(data, cats, image_id, cat_name, x, y, w, h):
    """Add a bounding box annotation."""
    cat_id = cats[cat_name]

    # Check if this category already has an annotation
    existing = [a for a in data['annotations'] if a['category_id'] == cat_id]
    if existing:
        print(f"WARNING: {cat_name} already has annotation(s): {existing}")
        print("Skipping. Remove existing annotation first if you want to replace it.")
        return

    max_id = max(a['id'] for a in data['annotations']) if data['annotations'] else 0
    ann = {
        "id": max_id + 1,
        "image_id": image_id,
        "category_id": cat_id,
        "bbox": [x, y, w, h],
        "area": w * h,
        "iscrowd": 0,
        "ignore": 0,
        "segmentation": []
    }
    data['annotations'].append(ann)
    print(f"Added annotation: {cat_name} -> bbox=[{x}, {y}, {w}, {h}] (ann_id={ann['id']})")


def main():
    if len(sys.argv) < 2 or sys.argv[1] == '--check':
        check_status()
        return

    if sys.argv[1] == '--add-categories':
        data = load_coco()
        ensure_categories(data)
        save_coco(data)
        return

    # Usage: script.py <image_filename> <category_name> <x> <y> <w> <h>
    if len(sys.argv) != 7:
        print("Usage: add_char_annotations.py <image.png> <category_name> <x> <y> <w> <h>")
        print("       add_char_annotations.py --check")
        print("       add_char_annotations.py --add-categories")
        sys.exit(1)

    filename = sys.argv[1]
    cat_name = sys.argv[2]
    x, y, w, h = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])

    data = load_coco()
    cats = ensure_categories(data)
    img_id, _ = ensure_image(data, filename)
    add_annotation(data, cats, img_id, cat_name, x, y, w, h)
    save_coco(data)
    print("Done!")


if __name__ == '__main__':
    main()
