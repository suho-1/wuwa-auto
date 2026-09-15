import os
import sys
import json
import time
import shutil
from typing import TypedDict

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize
from PySide6.QtGui import (QPainter, QPen, QColor, QPixmap, QMouseEvent,
                           QKeyEvent, QBrush, QFont, QWheelEvent, QIcon, QImage, QCursor)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QSizePolicy, QFormLayout, QApplication, QSplitter,
                               QFileDialog, QListWidgetItem, QScrollArea, QFrame,
                               QInputDialog)
from qfluentwidgets import (PushButton, PrimaryPushButton, FluentIcon,
                             LineEdit, MessageBoxBase, SubtitleLabel, BodyLabel,
                             SpinBox, ComboBox, SearchLineEdit, ListWidget,
                             ToolButton, CardWidget, InfoBar, InfoBarPosition,
                             RoundMenu, Action, isDarkTheme, SplitTitleBar)
from ok.ui.qt.widget.BaseWindow import BaseWindow
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# Edge margins and handles for canvas box manipulation
EDGE_MARGIN = 8
HANDLE_NONE = 0
HANDLE_TOP = 1
HANDLE_BOTTOM = 2
HANDLE_LEFT = 3
HANDLE_RIGHT = 4
HANDLE_TL = 5
HANDLE_TR = 6
HANDLE_BL = 7
HANDLE_BR = 8

_COLOR_CACHE = {}


def get_high_contrast_color(ann_id: int):
    if ann_id in _COLOR_CACHE:
        return _COLOR_CACHE[ann_id]
    val = int(ann_id)
    hue = (val * 0.618033988749895) % 1.0
    if (0.0 <= hue <= 0.15) or (0.55 <= hue <= 0.65):
        hue = (hue + 0.25) % 1.0
    s = 0.75 + (val % 3) * 0.08
    v = 0.85 + (val % 2) * 0.1
    color = QColor.fromHsvF(hue, min(1.0, s), min(1.0, v))
    bg_color = QColor(color.red(), color.green(), color.blue(), 55)
    res = (color, bg_color)
    _COLOR_CACHE[ann_id] = res
    return res


def _detect_handle(pos: QPoint, rect: QRect, margin=EDGE_MARGIN):
    x, y = pos.x(), pos.y()
    rx, ry, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
    r_right = rx + rw
    r_bottom = ry + rh

    near_left = abs(x - rx) <= margin and ry - margin <= y <= r_bottom + margin
    near_right = abs(x - r_right) <= margin and ry - margin <= y <= r_bottom + margin
    near_top = abs(y - ry) <= margin and rx - margin <= x <= r_right + margin
    near_bottom = abs(y - r_bottom) <= margin and rx - margin <= x <= r_right + margin

    if near_top and near_left:
        return HANDLE_TL
    if near_top and near_right:
        return HANDLE_TR
    if near_bottom and near_left:
        return HANDLE_BL
    if near_bottom and near_right:
        return HANDLE_BR
    if near_top:
        return HANDLE_TOP
    if near_bottom:
        return HANDLE_BOTTOM
    if near_left:
        return HANDLE_LEFT
    if near_right:
        return HANDLE_RIGHT
    return HANDLE_NONE


def _cursor_for_handle(handle):
    if handle in (HANDLE_TL, HANDLE_BR):
        return Qt.SizeFDiagCursor
    if handle in (HANDLE_TR, HANDLE_BL):
        return Qt.SizeBDiagCursor
    if handle in (HANDLE_TOP, HANDLE_BOTTOM):
        return Qt.SizeVerCursor
    if handle in (HANDLE_LEFT, HANDLE_RIGHT):
        return Qt.SizeHorCursor
    return Qt.ArrowCursor


class TaskFolderManager:
    """Manages scene screenshots and COCO annotations grouped by task folder."""

    def __init__(self, root_dir="ok_templates"):
        self.root_dir = os.path.abspath(root_dir)
        self.tasks_dir = os.path.join(self.root_dir, "tasks")
        os.makedirs(self.tasks_dir, exist_ok=True)
        self._ensure_default_tasks()

    def _ensure_default_tasks(self):
        defaults = [
            "FarmEchoTask",
            "EnhanceEchoTask",
            "FiveToOneTask",
            "ChestExplorationTask",
            "DailyTask",
            "General"
        ]
        for t in defaults:
            p = os.path.join(self.tasks_dir, t)
            os.makedirs(p, exist_ok=True)
            coco_path = os.path.join(p, "coco_annotations.json")
            if not os.path.exists(coco_path):
                with open(coco_path, "w", encoding="utf-8") as f:
                    json.dump({"images": [], "annotations": [], "categories": []}, f, indent=2)

        # Migrate legacy ok_templates if present
        legacy_coco = os.path.join(self.root_dir, "coco_annotations.json")
        general_dir = os.path.join(self.tasks_dir, "General")
        if os.path.exists(legacy_coco):
            try:
                with open(legacy_coco, "r", encoding="utf-8") as f:
                    leg_data = json.load(f)
                if leg_data.get("images"):
                    for img in leg_data["images"]:
                        src_img = os.path.join(self.root_dir, img["file_name"])
                        dst_img = os.path.join(general_dir, img["file_name"])
                        if os.path.exists(src_img) and not os.path.exists(dst_img):
                            shutil.copy2(src_img, dst_img)
                    gen_coco = os.path.join(general_dir, "coco_annotations.json")
                    if os.path.exists(gen_coco):
                        with open(gen_coco, "r", encoding="utf-8") as f:
                            cur_gen = json.load(f)
                        if not cur_gen.get("images"):
                            with open(gen_coco, "w", encoding="utf-8") as f:
                                json.dump(leg_data, f, indent=2)
            except Exception:
                pass

    def list_tasks(self):
        tasks = [d for d in os.listdir(self.tasks_dir) if os.path.isdir(os.path.join(self.tasks_dir, d))]
        return sorted(tasks)

    def create_task(self, task_name):
        safe_name = "".join(c for c in task_name if c.isalnum() or c in ("_", "-")).strip()
        if not safe_name:
            raise ValueError("Invalid task name")
        path = os.path.join(self.tasks_dir, safe_name)
        os.makedirs(path, exist_ok=True)
        coco_path = os.path.join(path, "coco_annotations.json")
        if not os.path.exists(coco_path):
            with open(coco_path, "w", encoding="utf-8") as f:
                json.dump({"images": [], "annotations": [], "categories": []}, f, indent=2)
        return safe_name

    def get_task_path(self, task_name):
        return os.path.join(self.tasks_dir, task_name)

    def load_task_coco(self, task_name):
        path = os.path.join(self.get_task_path(task_name), "coco_annotations.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"images": [], "annotations": [], "categories": []}

    def save_task_coco(self, task_name, coco_data):
        path = os.path.join(self.get_task_path(task_name), "coco_annotations.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(coco_data, f, indent=2, ensure_ascii=False)

    def list_task_images(self, task_name):
        task_dir = self.get_task_path(task_name)
        valid_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        files = [f for f in os.listdir(task_dir) if os.path.isfile(os.path.join(task_dir, f)) and os.path.splitext(f)[1].lower() in valid_exts]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(task_dir, x)), reverse=True)
        return [os.path.join(task_dir, f) for f in files]

    def add_image_to_task(self, task_name, frame):
        import cv2
        task_dir = self.get_task_path(task_name)
        existing_indices = []
        for f in os.listdir(task_dir):
            base, ext = os.path.splitext(f)
            if ext.lower() == ".png" and base.isdigit():
                existing_indices.append(int(base))
        next_idx = max(existing_indices, default=-1) + 1
        img_name = f"{next_idx}.png"
        img_path = os.path.join(task_dir, img_name)
        cv2.imwrite(img_path, frame)
        h, w = frame.shape[:2]

        coco = self.load_task_coco(task_name)
        img_entry = next((i for i in coco["images"] if i["file_name"] == img_name), None)
        if not img_entry:
            next_id = max((i["id"] for i in coco["images"]), default=0) + 1
            coco["images"].append({
                "id": next_id,
                "file_name": img_name,
                "width": w,
                "height": h
            })
            self.save_task_coco(task_name, coco)
        return img_path


class BBoxCategoryDialog(MessageBoxBase):
    """Dialog for entering/editing category name and coordinates."""

    def __init__(self, parent, category="", x=0, y=0, w=0, h=0, known_categories=None):
        super().__init__(parent)
        self.known_categories = known_categories or []

        self.titleLabel = SubtitleLabel("Bounding Box Annotation", self)
        self.viewLayout.addWidget(self.titleLabel)

        form = QFormLayout()

        # Category selection / input
        cat_layout = QVBoxLayout()
        self.category_input = LineEdit(self)
        self.category_input.setText(category)
        self.category_input.setPlaceholderText("Enter or select category name (e.g. boss_check_mark)")
        cat_layout.addWidget(self.category_input)

        if self.known_categories:
            self.preset_combo = ComboBox(self)
            self.preset_combo.addItem("-- Select from Known Labels --")
            for cat in self.known_categories:
                self.preset_combo.addItem(cat)
            self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
            cat_layout.addWidget(self.preset_combo)

        form.addRow("Category:", cat_layout)

        self.x_input = SpinBox(self)
        self.x_input.setRange(0, 99999)
        self.x_input.setValue(int(round(x)))
        form.addRow("X Coordinate:", self.x_input)

        self.y_input = SpinBox(self)
        self.y_input.setRange(0, 99999)
        self.y_input.setValue(int(round(y)))
        form.addRow("Y Coordinate:", self.y_input)

        self.w_input = SpinBox(self)
        self.w_input.setRange(1, 99999)
        self.w_input.setValue(int(round(w)))
        form.addRow("Width (px):", self.w_input)

        self.h_input = SpinBox(self)
        self.h_input.setRange(1, 99999)
        self.h_input.setValue(int(round(h)))
        form.addRow("Height (px):", self.h_input)

        self.viewLayout.addLayout(form)
        self.yesButton.setText("Confirm")
        self.cancelButton.setText("Cancel")
        self.widget.setMinimumWidth(420)
        self.category_input.setFocus()

    def _on_preset_selected(self, text):
        if text and not text.startswith("--"):
            self.category_input.setText(text)

    def get_values(self):
        return (
            self.category_input.text().strip(),
            self.x_input.value(),
            self.y_input.value(),
            self.w_input.value(),
            self.h_input.value()
        )


class TaskAnnotationCanvas(QWidget):
    """Interactive canvas rendering image with zoom/pan and multiple bounding boxes."""

    annotations_changed = Signal()
    annotation_selected = Signal(int)

    MODE_NONE = 0
    MODE_DRAW = 1
    MODE_DELETE = 2

    def __init__(self, studio, parent=None):
        super().__init__(parent)
        self.studio = studio
        self.pixmap = None
        self._image = None
        self.scale = 1.0
        self._fit_scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.annotations = []  # list of {"id", "category", "x", "y", "w", "h"}
        self.mode = self.MODE_NONE
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.hovered_handle = HANDLE_NONE

        self.draw_start = None
        self.draw_preview = None

        self.dragging = False
        self.drag_start_pos = None
        self.drag_original_rect = None

        self.resizing = False
        self.resize_handle = HANDLE_NONE
        self.resize_start_pos = None
        self.resize_original_rect = None

        self.panning = False
        self.pan_start_pos = None
        self.pan_start_offset = None

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_image(self, image_path):
        if not image_path or not os.path.exists(image_path):
            self.pixmap = None
            self._image = None
            self.annotations = []
            self.update()
            return
        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            self._image = None
            self.annotations = []
            self.update()
            return
        self._image = self.pixmap.toImage()
        self.annotations = []
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.hovered_handle = HANDLE_NONE
        self._recalc_fit_scale()
        self.scale = self._fit_scale
        self._recalc_offset()
        self.update()

    def _recalc_fit_scale(self):
        if not self.pixmap or self.pixmap.isNull():
            self._fit_scale = 1.0
            return
        iw, ih = self.pixmap.width(), self.pixmap.height()
        ww, wh = max(1, self.width()), max(1, self.height())
        self._fit_scale = min(ww / iw, wh / ih)

    def _recalc_offset(self):
        if not self.pixmap or self.pixmap.isNull():
            self.offset_x, self.offset_y = 0, 0
            return
        iw, ih = self.pixmap.width(), self.pixmap.height()
        ww, wh = self.width(), self.height()
        sw = iw * self.scale
        sh = ih * self.scale

        if sw <= ww:
            self.offset_x = (ww - sw) / 2.0
        else:
            self.offset_x = min(0.0, max(ww - sw, self.offset_x))

        if sh <= wh:
            self.offset_y = (wh - sh) / 2.0
        else:
            self.offset_y = min(0.0, max(wh - sh, self.offset_y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_fit_scale()
        if self.scale < self._fit_scale:
            self.scale = self._fit_scale
        self._recalc_offset()
        self.update()

    def set_annotations(self, annotations):
        self.annotations = annotations
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.update()

    def select_annotation(self, index):
        if 0 <= index < len(self.annotations):
            self.selected_ann_index = index
        else:
            self.selected_ann_index = -1
        self.update()

    # Coordinate mapping between widget space and full image space
    def _img_to_widget(self, ix, iy):
        return int(ix * self.scale + self.offset_x), int(iy * self.scale + self.offset_y)

    def _widget_to_img(self, wx, wy):
        if self.scale <= 0:
            return 0.0, 0.0
        return (wx - self.offset_x) / self.scale, (wy - self.offset_y) / self.scale

    def _ann_to_widget_rect(self, ann):
        wx, wy = self._img_to_widget(ann["x"], ann["y"])
        ww = int(ann["w"] * self.scale)
        wh = int(ann["h"] * self.scale)
        return QRect(wx, wy, ww, wh)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw dark canvas background
        bg = QColor(24, 24, 27) if isDarkTheme() else QColor(240, 242, 245)
        painter.fillRect(self.rect(), bg)

        if not self.pixmap or self.pixmap.isNull():
            painter.setPen(QColor(140, 140, 140))
            painter.setFont(QFont("Segoe UI", 13))
            painter.drawText(self.rect(), Qt.AlignCenter, "No Screenshot Loaded in this Scene.\nClick 'Capture Game Frame' or 'Import Image' above.")
            return

        # Draw scaled image
        target_rect = QRect(int(self.offset_x), int(self.offset_y), int(self.pixmap.width() * self.scale), int(self.pixmap.height() * self.scale))
        painter.drawPixmap(target_rect, self.pixmap)

        # Draw all bounding boxes in this scene
        for idx, ann in enumerate(self.annotations):
            rect = self._ann_to_widget_rect(ann)
            color, bg_color = get_high_contrast_color(ann.get("id", idx + 1))
            is_selected = (idx == self.selected_ann_index)
            is_hovered = (idx == self.hovered_ann_index)

            # Box fill & outline
            painter.fillRect(rect, bg_color)
            pen = QPen(color, 2.5 if is_selected else 1.8)
            if is_selected:
                pen.setStyle(Qt.SolidLine)
            elif is_hovered:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Label badge pill
            cat_name = ann.get("category", "")
            if cat_name:
                badge_font = QFont("Segoe UI", 9, QFont.Bold)
                painter.setFont(badge_font)
                fm = painter.fontMetrics()
                text_w = fm.horizontalAdvance(cat_name) + 12
                text_h = fm.height() + 4
                badge_rect = QRect(rect.x(), max(0, rect.y() - text_h), text_w, text_h)
                painter.fillRect(badge_rect, color)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(badge_rect, Qt.AlignCenter, cat_name)

            # Draw resize handles if selected
            if is_selected:
                self._draw_handles(painter, rect, color)

        # Draw box preview if currently dragging new box
        if self.mode == self.MODE_DRAW and self.draw_preview:
            painter.setPen(QPen(QColor(0, 190, 255), 2, Qt.DashLine))
            painter.fillRect(self.draw_preview, QColor(0, 190, 255, 45))
            painter.drawRect(self.draw_preview)

    def _draw_handles(self, painter, rect, color):
        handle_size = 7
        half = handle_size // 2
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(color, 1.5))
        points = [
            rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight(),
            QPoint(rect.center().x(), rect.top()),
            QPoint(rect.center().x(), rect.bottom()),
            QPoint(rect.left(), rect.center().y()),
            QPoint(rect.right(), rect.center().y()),
        ]
        for p in points:
            painter.drawRect(QRect(p.x() - half, p.y() - half, handle_size, handle_size))

    # Mouse interactions
    def mousePressEvent(self, event: QMouseEvent):
        if not self.pixmap or self.pixmap.isNull():
            return

        # Panning with middle mouse or right mouse
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self.panning = True
            self.pan_start_pos = event.pos()
            self.pan_start_offset = (self.offset_x, self.offset_y)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            if self.mode == self.MODE_DRAW:
                ix, iy = self._widget_to_img(event.pos().x(), event.pos().y())
                self.draw_start = QPoint(int(round(ix)), int(round(iy)))
                self.draw_preview = None
            elif self.mode == self.MODE_DELETE:
                idx = self._find_annotation_at(event.pos())
                if idx >= 0:
                    self.studio.delete_annotation_index(idx)
            else:
                # Mode NONE: check resize handles first
                if self.selected_ann_index >= 0:
                    sel_rect = self._ann_to_widget_rect(self.annotations[self.selected_ann_index])
                    handle = _detect_handle(event.pos(), sel_rect)
                    if handle != HANDLE_NONE:
                        self.resizing = True
                        self.resize_handle = handle
                        self.resize_start_pos = event.pos()
                        ann = self.annotations[self.selected_ann_index]
                        self.resize_original_rect = QRect(int(ann["x"]), int(ann["y"]), int(ann["w"]), int(ann["h"]))
                        return

                # Check box selection or drag
                idx = self._find_annotation_at(event.pos())
                if idx >= 0:
                    self.selected_ann_index = idx
                    self.annotation_selected.emit(idx)
                    self.dragging = True
                    self.drag_start_pos = event.pos()
                    ann = self.annotations[idx]
                    self.drag_original_rect = QRect(int(ann["x"]), int(ann["y"]), int(ann["w"]), int(ann["h"]))
                else:
                    self.selected_ann_index = -1
                    self.annotation_selected.emit(-1)
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.panning and self.pan_start_pos:
            dx = event.pos().x() - self.pan_start_pos.x()
            dy = event.pos().y() - self.pan_start_pos.y()
            self.offset_x = self.pan_start_offset[0] + dx
            self.offset_y = self.pan_start_offset[1] + dy
            self._recalc_offset()
            self.update()
            return

        if self.mode == self.MODE_DRAW and self.draw_start:
            ix, iy = self._widget_to_img(event.pos().x(), event.pos().y())
            curr = QPoint(int(round(ix)), int(round(iy)))
            rect_img = QRect(self.draw_start, curr).normalized()
            wx, wy = self._img_to_widget(rect_img.x(), rect_img.y())
            self.draw_preview = QRect(wx, wy, int(rect_img.width() * self.scale), int(rect_img.height() * self.scale))
            self.update()
            return

        if self.resizing and self.selected_ann_index >= 0:
            ann = self.annotations[self.selected_ann_index]
            orig = self.resize_original_rect
            dx = (event.pos().x() - self.resize_start_pos.x()) / self.scale
            dy = (event.pos().y() - self.resize_start_pos.y()) / self.scale
            x, y, w, h = orig.x(), orig.y(), orig.width(), orig.height()

            if self.resize_handle in (HANDLE_TL, HANDLE_LEFT, HANDLE_BL):
                x += dx
                w -= dx
            if self.resize_handle in (HANDLE_TR, HANDLE_RIGHT, HANDLE_BR):
                w += dx
            if self.resize_handle in (HANDLE_TL, HANDLE_TOP, HANDLE_TR):
                y += dy
                h -= dy
            if self.resize_handle in (HANDLE_BL, HANDLE_BOTTOM, HANDLE_BR):
                h += dy

            if w >= 4 and h >= 4:
                ann["x"] = max(0, int(round(x)))
                ann["y"] = max(0, int(round(y)))
                ann["w"] = int(round(w))
                ann["h"] = int(round(h))
                self.update()
            return

        if self.dragging and self.selected_ann_index >= 0:
            ann = self.annotations[self.selected_ann_index]
            orig = self.drag_original_rect
            dx = (event.pos().x() - self.drag_start_pos.x()) / self.scale
            dy = (event.pos().y() - self.drag_start_pos.y()) / self.scale
            new_x = max(0, int(round(orig.x() + dx)))
            new_y = max(0, int(round(orig.y() + dy)))
            if self.pixmap:
                new_x = min(new_x, self.pixmap.width() - orig.width())
                new_y = min(new_y, self.pixmap.height() - orig.height())
            ann["x"] = new_x
            ann["y"] = new_y
            self.update()
            return

        # Update hover state
        if self.selected_ann_index >= 0:
            sel_rect = self._ann_to_widget_rect(self.annotations[self.selected_ann_index])
            handle = _detect_handle(event.pos(), sel_rect)
            if handle != HANDLE_NONE:
                self.setCursor(_cursor_for_handle(handle))
                return

        idx = self._find_annotation_at(event.pos())
        self.hovered_ann_index = idx
        if self.mode == self.MODE_DRAW:
            self.setCursor(Qt.CrossCursor)
        elif self.mode == self.MODE_DELETE:
            self.setCursor(Qt.ForbiddenCursor)
        elif idx >= 0:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)

        if self.resizing or self.dragging:
            self.resizing = False
            self.dragging = False
            self.annotations_changed.emit()
            self.update()
            return

        if self.mode == self.MODE_DRAW and self.draw_start:
            ix, iy = self._widget_to_img(event.pos().x(), event.pos().y())
            curr = QPoint(int(round(ix)), int(round(iy)))
            rect_img = QRect(self.draw_start, curr).normalized()
            self.draw_start = None
            self.draw_preview = None

            if rect_img.width() >= 6 and rect_img.height() >= 6:
                self.studio.on_box_drawn(rect_img.x(), rect_img.y(), rect_img.width(), rect_img.height())
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        idx = self._find_annotation_at(event.pos())
        if idx >= 0:
            self.studio.edit_annotation_index(idx)

    def wheelEvent(self, event: QWheelEvent):
        if not self.pixmap or self.pixmap.isNull():
            return
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        old_scale = self.scale
        new_scale = max(self._fit_scale, min(8.0, old_scale * factor))
        if new_scale == old_scale:
            return

        mouse_x = event.position().x()
        mouse_y = event.position().y()
        self.offset_x = mouse_x - (mouse_x - self.offset_x) * (new_scale / old_scale)
        self.offset_y = mouse_y - (mouse_y - self.offset_y) * (new_scale / old_scale)
        self.scale = new_scale
        self._recalc_offset()
        self.update()

    def _find_annotation_at(self, pos: QPoint):
        for idx in reversed(range(len(self.annotations))):
            rect = self._ann_to_widget_rect(self.annotations[idx])
            if rect.contains(pos):
                return idx
        return -1


class TaskAnnotationStudio(BaseWindow):
    """Full-featured GUI studio for task-based multi-scene template annotations."""

    def __init__(self, ok_instance=None, parent=None):
        # Guarantee og.app and og.app.icon are valid QIcon instances before BaseWindow.__init__
        from ok import og
        if not hasattr(og, 'app') or og.app is None:
            class DummyApp:
                icon = QIcon()
                debug = True
            og.app = DummyApp()

        if not getattr(og.app, 'icon', None) or not isinstance(og.app.icon, (QIcon, QPixmap)):
            if os.path.exists("wuwa-auto.ico"):
                og.app.icon = QIcon("wuwa-auto.ico")
            elif os.path.exists(os.path.join("icons", "wuwa-auto.ico")):
                og.app.icon = QIcon(os.path.join("icons", "wuwa-auto.ico"))
            else:
                og.app.icon = QIcon()

        super().__init__(parent)
        self.ok = ok_instance
        self.task_manager = TaskFolderManager()
        self.current_task = self.task_manager.list_tasks()[0] if self.task_manager.list_tasks() else "General"
        self.current_image_path = None
        self.current_coco = {"images": [], "annotations": [], "categories": []}

        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()
        self.setWindowTitle("wuwa-auto Task-Based Template Annotation Studio")
        self.setMinimumSize(1480, 880)

        self._init_ui()
        self._populate_task_combo()
        self._load_task(self.current_task)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2
            )

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 42, 8, 8)
        main_layout.setSpacing(6)

        # --- Top Header & Main Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Task Folder Selector
        task_label = BodyLabel("Task Folder:", self)
        toolbar.addWidget(task_label)

        self.task_combo = ComboBox(self)
        self.task_combo.setMinimumWidth(190)
        self.task_combo.currentTextChanged.connect(self._on_task_changed)
        toolbar.addWidget(self.task_combo)

        self.new_task_btn = PushButton(FluentIcon.ADD, "New Task", self)
        self.new_task_btn.clicked.connect(self._create_new_task)
        toolbar.addWidget(self.new_task_btn)

        toolbar.addSpacing(12)

        # Game Capture and Image Import
        self.capture_btn = PrimaryPushButton(FluentIcon.CAMERA, "Capture Game Frame", self)
        self.capture_btn.clicked.connect(self._capture_game_frame)
        toolbar.addWidget(self.capture_btn)

        self.import_btn = PushButton(FluentIcon.FOLDER, "Import Image", self)
        self.import_btn.clicked.connect(self._import_image_file)
        toolbar.addWidget(self.import_btn)

        toolbar.addSpacing(12)

        # Canvas mode toggles
        self.draw_btn = PushButton(FluentIcon.EDIT, "Draw Box (R)", self)
        self.draw_btn.setCheckable(True)
        self.draw_btn.clicked.connect(self._toggle_draw_mode)
        toolbar.addWidget(self.draw_btn)

        self.delete_btn = PushButton(FluentIcon.DELETE, "Delete Box (D)", self)
        self.delete_btn.setCheckable(True)
        self.delete_btn.clicked.connect(self._toggle_delete_mode)
        toolbar.addWidget(self.delete_btn)

        toolbar.addStretch(1)

        # Save and Export Buttons
        self.save_btn = PushButton(FluentIcon.SAVE, "Save Task", self)
        self.save_btn.clicked.connect(self._save_current_task)
        toolbar.addWidget(self.save_btn)

        self.test_btn = PushButton(FluentIcon.SEARCH, "Test Detection", self)
        self.test_btn.clicked.connect(self._test_current_detection)
        toolbar.addWidget(self.test_btn)

        self.export_assets_btn = PrimaryPushButton(FluentIcon.SHARE, "Export to Game Assets", self)
        self.export_assets_btn.clicked.connect(self._export_to_game_assets)
        toolbar.addWidget(self.export_assets_btn)

        main_layout.addLayout(toolbar)

        # --- 3-Column Splitter Layout ---
        splitter = QSplitter(Qt.Horizontal, self)

        # [Column 1] Left Panel: Scenes / Screenshots Browser
        left_card = CardWidget(self)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)

        self.scenes_header = SubtitleLabel("Task Scenes", left_card)
        left_layout.addWidget(self.scenes_header)

        self.scene_list = ListWidget(left_card)
        self.scene_list.currentRowChanged.connect(self._on_scene_selected)
        left_layout.addWidget(self.scene_list, 1)

        left_bottom = QHBoxLayout()
        self.delete_scene_btn = PushButton(FluentIcon.DELETE, "Delete Scene", left_card)
        self.delete_scene_btn.clicked.connect(self._delete_current_scene)
        left_bottom.addWidget(self.delete_scene_btn)
        left_layout.addLayout(left_bottom)

        left_card.setMinimumWidth(230)
        left_card.setMaximumWidth(320)
        splitter.addWidget(left_card)

        # [Column 2] Center Panel: Interactive Canvas
        center_widget = QWidget(self)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        self.canvas = TaskAnnotationCanvas(self, center_widget)
        self.canvas.annotations_changed.connect(self._on_canvas_annotations_changed)
        self.canvas.annotation_selected.connect(self._on_canvas_annotation_selected)
        center_layout.addWidget(self.canvas, 1)

        # Bottom Canvas Info Bar
        info_bar = QHBoxLayout()
        self.canvas_status = BodyLabel("Ready", center_widget)
        info_bar.addWidget(self.canvas_status)
        info_bar.addStretch(1)
        self.canvas_hint = BodyLabel("Scroll = Zoom | Middle/Right Drag = Pan | Double Click Box = Edit | Del = Delete", center_widget)
        self.canvas_hint.setStyleSheet("color: gray; font-size: 11px;")
        info_bar.addWidget(self.canvas_hint)
        center_layout.addLayout(info_bar)

        splitter.addWidget(center_widget)

        # [Column 3] Right Panel: Scene Annotations & Category Inspector
        right_card = CardWidget(self)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        self.anns_header = SubtitleLabel("Scene Annotations", right_card)
        right_layout.addWidget(self.anns_header)

        self.annotation_list = ListWidget(right_card)
        self.annotation_list.currentRowChanged.connect(self._on_annotation_row_selected)
        right_layout.addWidget(self.annotation_list, 1)

        # Annotation Quick Actions
        ann_actions = QHBoxLayout()
        self.edit_ann_btn = PushButton(FluentIcon.EDIT, "Edit", right_card)
        self.edit_ann_btn.clicked.connect(self._edit_selected_annotation)
        ann_actions.addWidget(self.edit_ann_btn)

        self.del_ann_btn = PushButton(FluentIcon.DELETE, "Delete", right_card)
        self.del_ann_btn.clicked.connect(self._delete_selected_annotation)
        ann_actions.addWidget(self.del_ann_btn)
        right_layout.addLayout(ann_actions)

        right_card.setMinimumWidth(260)
        right_card.setMaximumWidth(360)
        splitter.addWidget(right_card)

        # Set splitter proportions (Left 15%, Center 65%, Right 20%)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 8)
        splitter.setStretchFactor(2, 3)

        main_layout.addWidget(splitter, 1)

    def _populate_task_combo(self):
        tasks = self.task_manager.list_tasks()
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        for t in tasks:
            self.task_combo.addItem(t)
        if self.current_task in tasks:
            self.task_combo.setCurrentText(self.current_task)
        self.task_combo.blockSignals(False)

    def _on_task_changed(self, task_name):
        if not task_name:
            return
        self._save_current_task()
        self.current_task = task_name
        self._load_task(task_name)

    def _create_new_task(self):
        name, ok = QInputDialog.getText(self, "New Task Folder", "Enter task folder name (e.g. MyCustomTask):")
        if ok and name.strip():
            try:
                task_name = self.task_manager.create_task(name.strip())
                self._populate_task_combo()
                self.task_combo.setCurrentText(task_name)
                InfoBar.success(
                    title="Task Created",
                    content=f"Created task folder: {task_name}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                InfoBar.error(title="Error", content=str(e), orient=Qt.Horizontal, position=InfoBarPosition.TOP, parent=self)

    def _load_task(self, task_name):
        self.current_coco = self.task_manager.load_task_coco(task_name)
        images = self.task_manager.list_task_images(task_name)
        self.scenes_header.setText(f"Task Scenes ({len(images)})")

        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        for img_path in images:
            fname = os.path.basename(img_path)
            # Count annotations for this image
            img_entry = next((i for i in self.current_coco.get("images", []) if i["file_name"] == fname), None)
            ann_count = 0
            if img_entry:
                ann_count = sum(1 for a in self.current_coco.get("annotations", []) if a.get("image_id") == img_entry["id"])
            item = QListWidgetItem(f"{fname}  [{ann_count} labels]")
            self.scene_list.addItem(item)
        self.scene_list.blockSignals(False)

        if images:
            self.scene_list.setCurrentRow(0)
            self._load_scene(images[0])
        else:
            self.current_image_path = None
            self.canvas.set_image(None)
            self._refresh_annotations_list()
            self.canvas_status.setText(f"Task: {task_name} | No scenes loaded")

    def _on_scene_selected(self, row):
        images = self.task_manager.list_task_images(self.current_task)
        if 0 <= row < len(images):
            self._load_scene(images[row])

    def _load_scene(self, image_path):
        self.current_image_path = image_path
        self.canvas.set_image(image_path)
        fname = os.path.basename(image_path)

        # Load annotations for this image from current_coco
        img_entry = next((i for i in self.current_coco.get("images", []) if i["file_name"] == fname), None)
        cats_by_id = {c["id"]: c["name"] for c in self.current_coco.get("categories", [])}

        scene_anns = []
        if img_entry:
            for a in self.current_coco.get("annotations", []):
                if a.get("image_id") == img_entry["id"]:
                    x, y, w, h = a["bbox"]
                    scene_anns.append({
                        "id": a["id"],
                        "category": cats_by_id.get(a["category_id"], "Unknown"),
                        "x": x, "y": y, "w": w, "h": h
                    })

        self.canvas.set_annotations(scene_anns)
        self._refresh_annotations_list()

        res_str = f"{self.canvas.pixmap.width()}x{self.canvas.pixmap.height()}" if self.canvas.pixmap else "N/A"
        self.canvas_status.setText(f"Task: {self.current_task} | Scene: {fname} | Resolution: {res_str} | Labels: {len(scene_anns)}")

    def _refresh_annotations_list(self):
        self.annotation_list.blockSignals(True)
        self.annotation_list.clear()
        for idx, ann in enumerate(self.canvas.annotations):
            cat = ann.get("category", "Unknown")
            x, y, w, h = int(ann["x"]), int(ann["y"]), int(ann["w"]), int(ann["h"])
            item = QListWidgetItem(f"#{idx+1} {cat}  [{x}, {y}, {w}, {h}]")
            self.annotation_list.addItem(item)
        self.annotation_list.blockSignals(False)
        self.anns_header.setText(f"Scene Annotations ({len(self.canvas.annotations)})")

    def _on_annotation_row_selected(self, row):
        self.canvas.select_annotation(row)

    def _on_canvas_annotation_selected(self, idx):
        self.annotation_list.blockSignals(True)
        self.annotation_list.setCurrentRow(idx)
        self.annotation_list.blockSignals(False)

    def _on_canvas_annotations_changed(self):
        self._sync_canvas_to_coco()
        self._refresh_annotations_list()

    def _sync_canvas_to_coco(self):
        """Synchronizes canvas annotations back to self.current_coco for current image."""
        if not self.current_image_path:
            return
        fname = os.path.basename(self.current_image_path)
        img_entry = next((i for i in self.current_coco.get("images", []) if i["file_name"] == fname), None)
        if not img_entry:
            if not self.canvas.pixmap:
                return
            next_img_id = max((i["id"] for i in self.current_coco.get("images", [])), default=0) + 1
            img_entry = {
                "id": next_img_id,
                "file_name": fname,
                "width": self.canvas.pixmap.width(),
                "height": self.canvas.pixmap.height()
            }
            self.current_coco.setdefault("images", []).append(img_entry)

        # Remove existing annotations for this image
        self.current_coco["annotations"] = [a for a in self.current_coco.get("annotations", []) if a.get("image_id") != img_entry["id"]]

        cats = {c["name"]: c["id"] for c in self.current_coco.get("categories", [])}
        next_cat_id = max((c["id"] for c in self.current_coco.get("categories", [])), default=0) + 1
        next_ann_id = max((a["id"] for a in self.current_coco.get("annotations", [])), default=0) + 1

        for ann in self.canvas.annotations:
            cat_name = ann.get("category", "").strip()
            if not cat_name:
                continue
            if cat_name not in cats:
                new_cat = {"id": next_cat_id, "name": cat_name, "supercategory": ""}
                self.current_coco.setdefault("categories", []).append(new_cat)
                cats[cat_name] = next_cat_id
                next_cat_id += 1

            x, y, w, h = int(ann["x"]), int(ann["y"]), int(ann["w"]), int(ann["h"])
            self.current_coco["annotations"].append({
                "id": next_ann_id,
                "image_id": img_entry["id"],
                "category_id": cats[cat_name],
                "bbox": [x, y, w, h],
                "area": w * h,
                "iscrowd": 0
            })
            next_ann_id += 1

    def _save_current_task(self):
        self._sync_canvas_to_coco()
        self.task_manager.save_task_coco(self.current_task, self.current_coco)
        InfoBar.success(
            title="Saved",
            content=f"Saved annotations for task: {self.current_task}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=1500,
            parent=self
        )

    def on_box_drawn(self, x, y, w, h):
        """Called by canvas after user drags a new bounding box."""
        known = self._get_known_categories()
        dlg = BBoxCategoryDialog(self, "", x, y, w, h, known_categories=known)
        if dlg.exec():
            cat_name, rx, ry, rw, rh = dlg.get_values()
            if cat_name:
                next_id = max((a.get("id", 0) for a in self.canvas.annotations), default=0) + 1
                self.canvas.annotations.append({
                    "id": next_id,
                    "category": cat_name,
                    "x": rx, "y": ry, "w": rw, "h": rh
                })
                self.canvas.select_annotation(len(self.canvas.annotations) - 1)
                self._on_canvas_annotations_changed()
                self.end_draw_mode()

    def edit_annotation_index(self, idx):
        if not (0 <= idx < len(self.canvas.annotations)):
            return
        ann = self.canvas.annotations[idx]
        known = self._get_known_categories()
        dlg = BBoxCategoryDialog(self, ann["category"], ann["x"], ann["y"], ann["w"], ann["h"], known_categories=known)
        if dlg.exec():
            cat_name, rx, ry, rw, rh = dlg.get_values()
            if cat_name:
                ann["category"] = cat_name
                ann["x"] = rx
                ann["y"] = ry
                ann["w"] = rw
                ann["h"] = rh
                self._on_canvas_annotations_changed()

    def delete_annotation_index(self, idx):
        if 0 <= idx < len(self.canvas.annotations):
            del self.canvas.annotations[idx]
            self.canvas.selected_ann_index = -1
            self._on_canvas_annotations_changed()

    def _edit_selected_annotation(self):
        if self.canvas.selected_ann_index >= 0:
            self.edit_annotation_index(self.canvas.selected_ann_index)

    def _delete_selected_annotation(self):
        if self.canvas.selected_ann_index >= 0:
            self.delete_annotation_index(self.canvas.selected_ann_index)

    def _toggle_draw_mode(self):
        if self.draw_btn.isChecked():
            self.delete_btn.setChecked(False)
            self.canvas.mode = TaskAnnotationCanvas.MODE_DRAW
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.mode = TaskAnnotationCanvas.MODE_NONE
            self.canvas.setCursor(Qt.ArrowCursor)

    def _toggle_delete_mode(self):
        if self.delete_btn.isChecked():
            self.draw_btn.setChecked(False)
            self.canvas.mode = TaskAnnotationCanvas.MODE_DELETE
            self.canvas.setCursor(Qt.ForbiddenCursor)
        else:
            self.canvas.mode = TaskAnnotationCanvas.MODE_NONE
            self.canvas.setCursor(Qt.ArrowCursor)

    def end_draw_mode(self):
        self.draw_btn.setChecked(False)
        self.canvas.mode = TaskAnnotationCanvas.MODE_NONE
        self.canvas.setCursor(Qt.ArrowCursor)

    def _capture_game_frame(self):
        """Grabs screenshot from game and adds as a new scene in current task folder."""
        frame = None
        if self.ok and getattr(self.ok, 'device_manager', None):
            dm = self.ok.device_manager
            if hasattr(dm, 'capture_method') and dm.capture_method:
                try:
                    frame = dm.capture_method.get_frame()
                except Exception as e:
                    logger.error(f"Engine frame capture error: {e}")

        if frame is None:
            # Fallback: import image from disk
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Screenshot to Add to Task", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
            )
            if file_path and os.path.exists(file_path):
                import cv2
                frame = cv2.imread(file_path)

        if frame is None:
            InfoBar.warning(
                title="Capture Standby",
                content="Game is not actively captured. Please import an image file or run game window.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        new_path = self.task_manager.add_image_to_task(self.current_task, frame)
        self._load_task(self.current_task)
        # Select the newly added scene
        images = self.task_manager.list_task_images(self.current_task)
        if new_path in images:
            idx = images.index(new_path)
            self.scene_list.setCurrentRow(idx)

        InfoBar.success(
            title="Scene Captured",
            content=f"Added {os.path.basename(new_path)} to task {self.current_task}",
            orient=Qt.Horizontal,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def _import_image_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Screenshot into Task", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path and os.path.exists(file_path):
            import cv2
            frame = cv2.imread(file_path)
            if frame is not None:
                new_path = self.task_manager.add_image_to_task(self.current_task, frame)
                self._load_task(self.current_task)
                images = self.task_manager.list_task_images(self.current_task)
                if new_path in images:
                    idx = images.index(new_path)
                    self.scene_list.setCurrentRow(idx)
                InfoBar.success(title="Imported", content=f"Added scene to {self.current_task}", orient=Qt.Horizontal, parent=self)

    def _delete_current_scene(self):
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            return
        fname = os.path.basename(self.current_image_path)
        # Remove from disk
        try:
            os.remove(self.current_image_path)
        except Exception:
            pass
        # Remove from coco
        img_entry = next((i for i in self.current_coco.get("images", []) if i["file_name"] == fname), None)
        if img_entry:
            self.current_coco["images"] = [i for i in self.current_coco["images"] if i["id"] != img_entry["id"]]
            self.current_coco["annotations"] = [a for a in self.current_coco["annotations"] if a["image_id"] != img_entry["id"]]
            self.task_manager.save_task_coco(self.current_task, self.current_coco)
        self._load_task(self.current_task)

    def _test_current_detection(self):
        """Runs template matching on live frame using currently selected annotation."""
        if self.canvas.selected_ann_index < 0:
            InfoBar.warning(title="No Selection", content="Please select an annotation box to test first.", orient=Qt.Horizontal, parent=self)
            return

        ann = self.canvas.annotations[self.canvas.selected_ann_index]
        if not self.canvas.pixmap:
            return

        frame = None
        if self.ok and getattr(self.ok, 'device_manager', None):
            dm = self.ok.device_manager
            if hasattr(dm, 'capture_method') and dm.capture_method:
                try:
                    frame = dm.capture_method.get_frame()
                except Exception:
                    pass

        if frame is None:
            InfoBar.warning(title="Game Inactive", content="Live game frame not available. Ensure game window is open.", orient=Qt.Horizontal, parent=self)
            return

        import cv2
        ref_img = cv2.imread(self.current_image_path)
        if ref_img is None:
            return

        x, y, w, h = int(ann["x"]), int(ann["y"]), int(ann["w"]), int(ann["h"])
        crop = ref_img[y:y+h, x:x+w]
        if crop.shape[0] < 2 or crop.shape[1] < 2:
            return

        res = cv2.matchTemplate(frame, crop, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        cat = ann.get("category", "")
        if max_val >= 0.70:
            InfoBar.success(
                title=f"Match Confirmed: {cat}",
                content=f"Confidence: {max_val:.3f} (>= 0.70) at ({max_loc[0]}, {max_loc[1]})",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )
        else:
            InfoBar.warning(
                title=f"Not Detected: {cat}",
                content=f"Confidence: {max_val:.3f} (< 0.70 threshold). Feature not currently on screen.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )

    def _export_to_game_assets(self):
        """Compiles and merges all annotations from all task folders into production assets."""
        self._save_current_task()
        assets_dir = os.path.abspath("assets")
        assets_coco_path = os.path.join(assets_dir, "coco_annotations.json")
        if not os.path.exists(assets_coco_path):
            InfoBar.error(title="Error", content=f"Assets file not found: {assets_coco_path}", orient=Qt.Horizontal, parent=self)
            return

        with open(assets_coco_path, "r", encoding="utf-8") as f:
            assets_coco = json.load(f)

        cat_by_name = {c["name"]: c for c in assets_coco.get("categories", [])}
        next_cat_id = max((int(c["id"]) for c in assets_coco.get("categories", [])), default=0) + 1
        next_img_id = max((int(img["id"]) for img in assets_coco.get("images", [])), default=0) + 1
        next_ann_id = max((int(ann["id"]) for ann in assets_coco.get("annotations", [])), default=0) + 1

        total_merged = 0
        all_tasks = self.task_manager.list_tasks()

        for tname in all_tasks:
            task_coco = self.task_manager.load_task_coco(tname)
            task_path = self.task_manager.get_task_path(tname)
            if not task_coco.get("annotations"):
                continue

            # Map categories
            cat_map = {}
            for tc in task_coco.get("categories", []):
                name = tc["name"]
                if name in cat_by_name:
                    cat_map[tc["id"]] = cat_by_name[name]["id"]
                else:
                    new_c = {"id": next_cat_id, "name": name, "supercategory": ""}
                    assets_coco["categories"].append(new_c)
                    cat_by_name[name] = new_c
                    cat_map[tc["id"]] = next_cat_id
                    next_cat_id += 1

            # Copy images
            img_map = {}
            for timg in task_coco.get("images", []):
                src = os.path.join(task_path, timg["file_name"])
                if not os.path.exists(src):
                    continue
                dst_name = f"template_{tname}_{timg['file_name']}"
                rel_path = f"images/{dst_name}"
                dst_full = os.path.join(assets_dir, rel_path)
                os.makedirs(os.path.dirname(dst_full), exist_ok=True)
                shutil.copy2(src, dst_full)

                existing_entry = next((i for i in assets_coco["images"] if i.get("file_name") == rel_path), None)
                if existing_entry:
                    img_map[timg["id"]] = existing_entry["id"]
                else:
                    new_entry = {
                        "id": next_img_id,
                        "file_name": rel_path,
                        "width": timg.get("width", 0),
                        "height": timg.get("height", 0)
                    }
                    assets_coco["images"].append(new_entry)
                    img_map[timg["id"]] = next_img_id
                    next_img_id += 1

            # Add annotations
            for tann in task_coco.get("annotations", []):
                iid = img_map.get(tann["image_id"])
                cid = cat_map.get(tann["category_id"])
                if not iid or not cid:
                    continue
                exists = any(
                    a.get("image_id") == iid and a.get("category_id") == cid and a.get("bbox") == tann["bbox"]
                    for a in assets_coco["annotations"]
                )
                if not exists:
                    assets_coco["annotations"].append({
                        "id": next_ann_id,
                        "image_id": iid,
                        "category_id": cid,
                        "bbox": tann["bbox"],
                        "area": tann.get("area", tann["bbox"][2] * tann["bbox"][3]),
                        "iscrowd": 0
                    })
                    next_ann_id += 1
                    total_merged += 1

        # Write working assets
        with open(assets_coco_path, "w", encoding="utf-8") as f:
            json.dump(assets_coco, f, indent=4, ensure_ascii=False)

        # Synchronize to repo assets for byte-for-byte parity
        repo_assets_coco = os.path.abspath(os.path.join("data", "apps", "ok-ww", "repo", "assets", "coco_annotations.json"))
        if not os.path.exists(repo_assets_coco):
            repo_assets_coco = os.path.abspath(os.path.join("..", "repo", "assets", "coco_annotations.json"))
        if os.path.exists(os.path.dirname(repo_assets_coco)):
            shutil.copy2(assets_coco_path, repo_assets_coco)
            repo_images_dir = os.path.join(os.path.dirname(repo_assets_coco), "images")
            os.makedirs(repo_images_dir, exist_ok=True)
            for f in os.listdir(os.path.join(assets_dir, "images")):
                if f.startswith("template_"):
                    shutil.copy2(os.path.join(assets_dir, "images", f), os.path.join(repo_images_dir, f))

        # Clear feature cache in running engine
        if self.ok and hasattr(self.ok, 'feature_set') and self.ok.feature_set:
            try:
                with self.ok.feature_set.lock:
                    self.ok.feature_set.feature_dict.clear()
                    self.ok.feature_set.box_dict.clear()
                    self.ok.feature_set._processed_images.clear()
            except Exception:
                pass

        InfoBar.success(
            title="Export Succeeded",
            content=f"Merged {total_merged} template annotations into game assets and synchronized repo!",
            orient=Qt.Horizontal,
            position=InfoBarPosition.TOP,
            duration=3500,
            parent=self
        )

    def _get_known_categories(self):
        categories = set()
        try:
            from src.Labels import Labels
            for label in Labels:
                categories.add(label.value)
        except Exception:
            pass
        try:
            for cat in self.current_coco.get("categories", []):
                categories.add(cat.get("name", ""))
        except Exception:
            pass
        try:
            with open(os.path.join("assets", "coco_annotations.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
                for cat in data.get("categories", []):
                    categories.add(cat.get("name", ""))
        except Exception:
            pass
        return sorted([c for c in categories if c])


def launch_studio(ok_instance=None):
    """Entry point to launch the Task-Based Annotation Studio GUI."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Setup dummy og.app icon to prevent NoneType attribute errors in BaseWindow
    from ok import og
    if not hasattr(og, 'app') or og.app is None:
        class DummyApp:
            icon = QIcon()
            debug = True
        og.app = DummyApp()

    if not getattr(og.app, 'icon', None) or not isinstance(og.app.icon, (QIcon, QPixmap)):
        if os.path.exists("wuwa-auto.ico"):
            og.app.icon = QIcon("wuwa-auto.ico")
        elif os.path.exists(os.path.join("icons", "wuwa-auto.ico")):
            og.app.icon = QIcon(os.path.join("icons", "wuwa-auto.ico"))
        else:
            og.app.icon = QIcon()

    studio = TaskAnnotationStudio(ok_instance=ok_instance)
    studio.show()
    app.exec()
    return studio


if __name__ == "__main__":
    launch_studio()
