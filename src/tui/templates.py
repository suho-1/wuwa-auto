"""Template capture, annotation, export and deletion.

This is the feature-heavy part of the TUI: it grabs frames off the live
capture pipeline, hands off to OpenCV or Qt for box selection, and merges
workspace annotations into the production assets.
"""

from __future__ import annotations

import json
import os
import shutil

from . import console, engine, logs

TEMPLATE_FOLDER = "ok_templates"
ASSETS_COCO = os.path.join("assets", "coco_annotations.json")
IMAGE_PAGE_SIZE = 12
ROI_MAX_WIDTH = 1600
ROI_MAX_HEIGHT = 900
MATCH_THRESHOLD = 0.70


def store():
    from ok.core.template_store import CocoTemplateStore

    return CocoTemplateStore(os.path.join(os.getcwd(), TEMPLATE_FOLDER))


def _image_label(item) -> str:
    categories = ", ".join(item.get("categories", [])) or "None"
    return f"{item['path'].name} [dim](Labels: {categories})[/dim]"


def choose_image(title: str, subtitle: str = "Pick a workspace screenshot"):
    """Paginate through workspace screenshots and return the chosen path."""
    images = store().list_images()
    if not images:
        console.print("\n[yellow]No screenshots in ok_templates. Capture one first![/yellow]")
        console.pause()
        return None

    console.banner(title, subtitle)
    page = 0
    pages = max(1, (len(images) + IMAGE_PAGE_SIZE - 1) // IMAGE_PAGE_SIZE)
    while True:
        window = images[page * IMAGE_PAGE_SIZE:(page + 1) * IMAGE_PAGE_SIZE]
        for offset, item in enumerate(window, 1):
            number = page * IMAGE_PAGE_SIZE + offset
            console.print(f"  [bold magenta]{number:>2}[/bold magenta]. {_image_label(item)}")
        if pages > 1:
            console.print(f"\n[dim]Page {page + 1}/{pages} - n for next, p for previous[/dim]")
        console.print(console.thin_rule(), style="dim")
        answer = console.ask("\n[bold cyan]Image number (Enter cancels):[/bold cyan] ").strip().lower()
        if not answer:
            return None
        if answer == "n" and pages > 1:
            page = (page + 1) % pages
            continue
        if answer == "p" and pages > 1:
            page = (page - 1) % pages
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(images):
            return str(images[int(answer) - 1]["path"])
        console.invalid(f"Enter a number between 1 and {len(images)}.")


# -- capture --------------------------------------------------------------

def capture_screenshot(bridge: engine.EngineBridge) -> None:
    console.banner("CAPTURE GAME SCREENSHOT")
    frame = bridge.capture_frame()

    if frame is None:
        console.print("[yellow]Live capture is not active or the game window is hidden.[/yellow]")
        if not console.confirm("Import an existing image from disk instead?", default=False):
            return
        path = console.ask("Path to the image (.png/.jpg): ").strip(" \"'")
        if not os.path.exists(path):
            console.invalid("File not found.")
            return
        import cv2

        frame = cv2.imread(path)
        if frame is None:
            console.invalid("Could not read that image file.")
            return

    try:
        from ok.util.blur import apply_blur_areas, get_blur_algorithm

        frame = apply_blur_areas(frame, bridge.ok.config.get("blur_area"),
                                 get_blur_algorithm(getattr(bridge.ok, "global_config", None)))
    except Exception:
        pass

    try:
        template_store = store()
        saved = template_store.save_frame(frame)
    except Exception as exc:
        console.report_exception("Could not save the screenshot", exc)
        return

    height, width = frame.shape[:2]
    logs.info(f"Captured screenshot: {saved.name} ({width}x{height})")
    console.success(f"Screenshot saved: {saved.name} ({width}x{height})")

    if console.confirm("Annotate it now with the visual ROI selector?", default=True):
        annotate_roi(bridge, str(saved))


# -- annotation -----------------------------------------------------------

def _clamp_box(x, y, box_width, box_height, width, height):
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    box_width = max(1, min(box_width, width - x))
    box_height = max(1, min(box_height, height - y))
    return x, y, box_width, box_height


def _display_scale(width: int, height: int) -> float:
    if width <= ROI_MAX_WIDTH and height <= ROI_MAX_HEIGHT:
        return 1.0
    return min(ROI_MAX_WIDTH / width, ROI_MAX_HEIGHT / height)


def _ask_category(known) -> str:
    while True:
        name = console.ask("\n[bold cyan]Category / label name (e.g. boss_check_mark):[/bold cyan] ")
        if name == "?":
            console.print(f"Known categories: [dim]{', '.join(known[:40])}[/dim]")
            continue
        if not name:
            return ""
        return name


def available_categories() -> list:
    categories = set()
    try:
        from src.Labels import Labels

        categories.update(label.value for label in Labels)
    except Exception:
        pass
    try:
        for category in store().load().get("categories", []):
            categories.add(category.get("name", ""))
    except Exception:
        pass
    try:
        with open(ASSETS_COCO, "r", encoding="utf-8") as stream:
            for category in json.load(stream).get("categories", []):
                categories.add(category.get("name", ""))
    except Exception:
        pass
    return sorted(name for name in categories if name)


def annotate_roi(bridge: engine.EngineBridge, target_image_path=None) -> None:
    import cv2

    template_store = store()
    if not target_image_path:
        target_image_path = choose_image("VISUAL ROI TEMPLATE SELECTOR")
        if not target_image_path:
            return

    image = cv2.imread(target_image_path)
    if image is None:
        console.invalid(f"Could not load image: {target_image_path}")
        return

    height, width = image.shape[:2]
    scale = _display_scale(width, height)
    if scale < 1.0:
        display = cv2.resize(image, (int(width * scale), int(height * scale)),
                             interpolation=cv2.INTER_AREA)
    else:
        display = image

    name = os.path.basename(target_image_path)
    console.print(f"\n[bold cyan]>>> ROI window: {name}[/bold cyan]")
    console.print("[dim]Drag a box, ENTER/SPACE confirms, C/ESC cancels.[/dim]")

    title = f"wuwa-auto ROI: {name}"
    try:
        cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
        rect = cv2.selectROI(title, display, showCrosshair=True, fromCenter=False)
    except Exception as exc:
        console.report_exception("ROI selection failed", exc)
        return
    finally:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    x, y, box_width, box_height = rect
    if box_width <= 0 or box_height <= 0:
        console.print("\n[yellow]Selection cancelled.[/yellow]")
        return

    x, y, box_width, box_height = _clamp_box(
        int(round(x / scale)), int(round(y / scale)),
        int(round(box_width / scale)), int(round(box_height / scale)),
        width, height,
    )
    console.print(f"\n[bold green]Bounding box:[/bold green] x={x} y={y} "
                   f"w={box_width} h={box_height} [dim](on {width}x{height})[/dim]")

    category = _ask_category(available_categories())
    if not category:
        console.print("[yellow]Category name cannot be empty. Nothing saved.[/yellow]")
        return

    existing = template_store.annotations_for(name).get("annotations", [])
    annotations = [{"category": item["category"], "bbox": list(item["bbox"])} for item in existing]
    annotations.append({"category": category, "bbox": [x, y, box_width, box_height]})
    try:
        template_store.replace_annotations(name, annotations)
    except Exception as exc:
        console.report_exception("Could not save the annotation", exc)
        return

    logs.info(f"Annotated {category} at [{x},{y},{box_width},{box_height}] on {name}")
    console.success(f"Saved template annotation: '{category}'")


def manual_annotate(bridge: engine.EngineBridge, target_image_path=None) -> None:
    import cv2

    template_store = store()
    if not target_image_path:
        target_image_path = choose_image("MANUAL COORDINATE ANNOTATION")
        if not target_image_path:
            return

    image = cv2.imread(target_image_path)
    if image is None:
        console.invalid("Could not load the image.")
        return
    height, width = image.shape[:2]

    category = _ask_category(available_categories())
    if not category:
        return

    console.print(f"\nImage resolution: [bold]{width}x{height}[/bold]")
    console.print("  pixels : 'x y w h'          e.g. '850 350 150 40'")
    console.print("  ratios : 'x1 y1 x2 y2' 0-1  e.g. '0.66 0.48 0.77 0.56'")
    tokens = console.ask("\n[bold cyan]Coordinates:[/bold cyan] ").split()
    if len(tokens) != 4:
        console.invalid("Coordinates must contain exactly 4 numbers.")
        return

    try:
        values = [float(token) for token in tokens]
    except ValueError:
        console.invalid("Coordinates must be numeric.")
        return

    try:
        if all(0.0 <= value <= 1.0 for value in values):
            x1, y1, x2, y2 = values
            x, y = int(round(x1 * width)), int(round(y1 * height))
            box_width, box_height = int(round((x2 - x1) * width)), int(round((y2 - y1) * height))
        else:
            x, y, box_width, box_height = (int(round(value)) for value in values)
        x, y, box_width, box_height = _clamp_box(x, y, box_width, box_height, width, height)
    except Exception as exc:
        console.report_exception("Could not parse the coordinates", exc)
        return

    name = os.path.basename(target_image_path)
    existing = template_store.annotations_for(name).get("annotations", [])
    annotations = [{"category": item["category"], "bbox": list(item["bbox"])} for item in existing]
    annotations.append({"category": category, "bbox": [x, y, box_width, box_height]})
    try:
        template_store.replace_annotations(name, annotations)
    except Exception as exc:
        console.report_exception("Could not save the annotation", exc)
        return

    logs.info(f"Annotated {category} at [{x},{y},{box_width},{box_height}] on {name}")
    console.success(f"Saved annotation: '{category}' at [{x}, {y}, {box_width}, {box_height}]")


# -- inventory ------------------------------------------------------------

def list_annotations(bridge: engine.EngineBridge) -> None:
    from rich.table import Table

    console.banner("TEMPLATE ANNOTATION INVENTORY")
    coco = store().load()
    annotations = coco.get("annotations", [])
    if not annotations:
        console.print("[dim]No annotations in the ok_templates workspace.[/dim]")
        console.pause()
        return

    categories = {item["id"]: item["name"] for item in coco.get("categories", [])}
    images = {item["id"]: item["file_name"] for item in coco.get("images", [])}

    table = Table(border_style="cyan", expand=True)
    table.add_column("ID", style="bold magenta", width=4, justify="center")
    table.add_column("Image File", style="bold white", ratio=12)
    table.add_column("Category", style="bold green", ratio=20)
    table.add_column("BBox [X, Y, W, H]", ratio=18)
    table.add_column("Area", style="dim", width=8, justify="right")
    for annotation in annotations:
        box = [int(round(value)) for value in annotation.get("bbox", [])]
        table.add_row(
            str(annotation.get("id", "")),
            images.get(annotation.get("image_id"), "N/A"),
            categories.get(annotation.get("category_id"), "Unknown"),
            str(box),
            str(int(annotation.get("area", 0))),
        )
    console.print(table)
    console.pause()


def delete_annotation(bridge: engine.EngineBridge) -> None:
    console.banner("DELETE TEMPLATE ANNOTATION")
    template_store = store()
    coco = template_store.load()
    annotations = coco.get("annotations", [])
    if not annotations:
        console.print("[dim]No annotations in the workspace.[/dim]")
        return

    categories = {item["id"]: item["name"] for item in coco.get("categories", [])}
    images = {item["id"]: item["file_name"] for item in coco.get("images", [])}
    for annotation in annotations:
        category = categories.get(annotation.get("category_id"), "Unknown")
        image = images.get(annotation.get("image_id"), "N/A")
        console.print(f"  [bold magenta]ID {annotation.get('id'):>3}[/bold magenta]  "
                       f"{category:<24} on {image} {annotation.get('bbox')}")
    console.print(console.thin_rule(), style="dim")

    answer = console.ask("\n[bold cyan]Annotation ID to delete (Enter cancels):[/bold cyan] ")
    if not answer.isdigit():
        return
    target = int(answer)
    if not any(annotation.get("id") == target for annotation in annotations):
        console.invalid(f"No annotation with ID {target}.")
        return
    coco["annotations"] = [item for item in annotations if item.get("id") != target]
    template_store.save(coco)
    logs.warn(f"Deleted annotation {target} from the workspace")
    console.success(f"Deleted annotation ID {target}.")


# -- live matching --------------------------------------------------------

def test_live(bridge: engine.EngineBridge) -> None:
    import cv2

    console.banner("TEST TEMPLATE DETECTION AGAINST THE GAME")
    frame = bridge.capture_frame()
    if frame is None:
        console.invalid("The game is not being captured. Focus the game window and retry.")
        console.pause()
        return

    coco = store().load()
    categories = [item["name"] for item in coco.get("categories", [])]
    if not categories:
        console.invalid("No categories annotated in the workspace yet.")
        return

    index = 0
    for position, name in enumerate(categories, 1):
        console.print(f"  [bold magenta]{position:>2}[/bold magenta]. {name}")
    console.print(console.thin_rule(), style="dim")
    answer = console.ask("\n[bold cyan]Category number or name:[/bold cyan] ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(categories):
        index = int(answer) - 1

    category_id = next((item["id"] for item in coco.get("categories", [])
                        if item["name"] == categories[index]), None)
    annotation = next((item for item in coco.get("annotations", [])
                       if item.get("category_id") == category_id), None)
    if annotation is None:
        console.invalid(f"No bounding box recorded for '{categories[index]}'.")
        return

    image_info = next((item for item in coco.get("images", []) if item["id"] == annotation["image_id"]), None)
    if image_info is None:
        console.invalid("The COCO image record is missing.")
        return

    reference = cv2.imread(os.path.join(os.getcwd(), TEMPLATE_FOLDER, image_info["file_name"]))
    if reference is None:
        console.invalid("Could not load the reference image.")
        return

    x, y, box_width, box_height = (int(round(value)) for value in annotation["bbox"])
    template = reference[y:y + box_height, x:x + box_width]
    if template.size == 0:
        console.invalid("The recorded bounding box is empty on the reference image.")
        return

    _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED))
    matched = score >= MATCH_THRESHOLD
    colour = "green" if matched else "red"

    console.clear()
    console.print(console.rule(), style="cyan")
    console.print(f"  Feature Name : [bold green]{categories[index]}[/bold green]")
    console.print(f"  Template Size: {box_width}x{box_height} px")
    console.print(f"  Match Score  : [bold {colour}]{score:.4f}[/bold {colour}] "
                   f"(threshold {MATCH_THRESHOLD:.2f})")
    console.print(f"  Best Match At: (x={location[0]}, y={location[1]})")
    console.print(f"  Result       : [bold {colour}]"
                   f"{'MATCH CONFIRMED ON THE GAME SCREEN' if matched else 'NOT DETECTED (not visible)'}"
                   f"[/bold {colour}]")
    console.print(console.rule(), style="cyan")
    console.pause()


# -- export ---------------------------------------------------------------

def find_repo_assets() -> str:
    """Locate the git-side assets directory.

    The old code tried ``data/apps/ok-ww/repo/assets`` relative to the working
    directory first, which never exists because the CWD is already
    ``.../working``.  Walking up from the CWD finds the real checkout in both
    the installed and the source layouts.
    """
    candidates = []
    directory = os.path.abspath(os.getcwd())
    while True:
        candidates.append(os.path.join(directory, "assets", "coco_annotations.json"))
        candidates.append(os.path.join(directory, "repo", "assets", "coco_annotations.json"))
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def _merge_coco(assets: dict, workspace: dict):
    """Merge workspace records into assets. Returns ``(added, new_coco)``."""
    by_name = {item["name"]: item for item in assets["categories"]}
    next_category = max((int(item["id"]) for item in assets["categories"]), default=0) + 1
    next_image = max((int(item["id"]) for item in assets["images"]), default=0) + 1
    next_annotation = max((int(item["id"]) for item in assets["annotations"]), default=0) + 1

    category_map = {}
    for item in workspace.get("categories", []):
        name = item["name"]
        if name in by_name:
            category_map[item["id"]] = by_name[name]["id"]
        else:
            record = {"id": next_category, "name": name, "supercategory": ""}
            assets["categories"].append(record)
            by_name[name] = record
            category_map[item["id"]] = next_category
            next_category += 1

    image_map = {}
    existing_images = {item.get("file_name"): item.get("id") for item in assets["images"]}
    for item in workspace.get("images", []):
        destination = f"images/template_{item['file_name']}"
        if destination in existing_images:
            image_map[item["id"]] = existing_images[destination]
        else:
            record = {
                "id": next_image,
                "file_name": destination,
                "width": item.get("width", 0),
                "height": item.get("height", 0),
            }
            assets["images"].append(record)
            existing_images[destination] = next_image
            image_map[item["id"]] = next_image
            next_image += 1

    # Set lookup instead of the previous O(n^2) scan over every existing box.
    seen = {(item.get("image_id"), item.get("category_id"), tuple(item.get("bbox") or ()))
            for item in assets["annotations"]}

    added = 0
    for item in workspace.get("annotations", []):
        image_id = image_map.get(item["image_id"])
        category_id = category_map.get(item["category_id"])
        if not image_id or not category_id:
            continue
        box = item.get("bbox") or []
        key = (image_id, category_id, tuple(box))
        if key in seen:
            continue
        seen.add(key)
        assets["annotations"].append({
            "id": next_annotation,
            "image_id": image_id,
            "category_id": category_id,
            "bbox": box,
            "area": item.get("area", (box[2] * box[3]) if len(box) == 4 else 0),
            "iscrowd": 0,
        })
        next_annotation += 1
        added += 1

    return added, assets


def export_to_assets(bridge: engine.EngineBridge) -> None:
    console.banner("MERGE & EXPORT TEMPLATES TO ASSETS")
    console.print("Source : " + os.path.join(TEMPLATE_FOLDER, "coco_annotations.json"))
    console.print("Target : " + ASSETS_COCO)
    repo_assets = find_repo_assets()
    if repo_assets:
        console.print("Sync   : " + repo_assets)
    if not console.confirm("Proceed with the export?", default=False):
        return

    template_store = store()
    workspace = template_store.load()
    if not workspace.get("annotations"):
        console.invalid("No workspace annotations to export.")
        return

    assets_path = os.path.abspath(ASSETS_COCO)
    if not os.path.isfile(assets_path):
        console.invalid(f"Assets file not found: {assets_path}")
        return

    try:
        with open(assets_path, "r", encoding="utf-8") as stream:
            assets = json.load(stream)
    except (OSError, ValueError) as exc:
        console.report_exception("Could not read the assets file", exc)
        return

    added, merged = _merge_coco(assets, workspace)
    assets_dir = os.path.dirname(assets_path)
    try:
        os.makedirs(os.path.join(assets_dir, "images"), exist_ok=True)
        copied = 0
        for item in workspace.get("images", []):
            source = os.path.join(TEMPLATE_FOLDER, item["file_name"])
            if not os.path.isfile(source):
                continue
            shutil.copy2(source, os.path.join(assets_dir, "images", f"template_{item['file_name']}"))
            copied += 1
        with open(assets_path, "w", encoding="utf-8") as stream:
            json.dump(merged, stream, indent=4, ensure_ascii=False)
    except (OSError, ValueError) as exc:
        console.report_exception("Export failed", exc)
        return

    if repo_assets:
        try:
            shutil.copy2(assets_path, repo_assets)
            repo_images = os.path.join(os.path.dirname(repo_assets), "images")
            os.makedirs(repo_images, exist_ok=True)
            for item in workspace.get("images", []):
                source = os.path.join(assets_dir, "images", f"template_{item['file_name']}")
                if os.path.isfile(source):
                    shutil.copy2(source, os.path.join(repo_images, os.path.basename(source)))
        except OSError as exc:
            console.warn(f"Repo sync failed: {exc}")

    bridge.clear_feature_cache()
    logs.info(f"Exported {added} annotations to assets ({copied} images)")
    console.success(f"Exported {added} new annotations and {copied} images.")
    console.notice("[dim]Runtime feature cache cleared; tasks pick the new templates up immediately.[/dim]")


# -- GUI handoffs ---------------------------------------------------------

def launch_studio(bridge: engine.EngineBridge) -> None:
    try:
        from PySide6.QtGui import QIcon

        from ok import og

        if getattr(og, "app", None) is None:
            class _StudioApp:
                icon = QIcon()
                debug = True

            og.app = _StudioApp()
        if not isinstance(getattr(og.app, "icon", None), QIcon):
            icon_path = "wuwa-auto.ico" if os.path.exists("wuwa-auto.ico") else os.path.join("icons", "wuwa-auto.ico")
            og.app.icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        from src.gui.TaskAnnotationStudio import launch_studio as run_studio

        console.notice("[bold green]>>> Launching the Task Annotation Studio...[/bold green]")
        run_studio(ok_instance=bridge.ok)
        console.notice("[bold green]>>> Task Annotation Studio closed.[/bold green]")
    except Exception as exc:
        console.report_exception("Could not launch the Task Annotation Studio", exc)


def launch_qt_markup(bridge: engine.EngineBridge, target_image_path=None) -> None:
    template_store = store()
    images = template_store.list_images()
    if not images:
        console.invalid("No screenshots in ok_templates. Capture one first.")
        return
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from ok import og
        from ok.ui.qt.tasks.MarkUpWindow import MarkUpWindow

        app = QApplication.instance() or QApplication([])
        if getattr(og, "app", None) is None:
            class _MarkupApp:
                icon = QIcon()
                debug = True

            og.app = _MarkupApp()
        window = MarkUpWindow(str(target_image_path or images[0]["path"]),
                              [str(item["path"]) for item in images])
        window.show()
        console.notice("[bold green]>>> Qt MarkUp Editor open. Close it when finished.[/bold green]")
        app.exec()
        console.notice("[bold green]>>> Qt MarkUp Editor closed. Workspace updated.[/bold green]")
    except Exception as exc:
        console.report_exception("Could not launch the Qt MarkUp editor", exc)
