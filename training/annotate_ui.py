"""Interactive Human Verification & Annotation UI for ok-ww Vision Model.

A local, zero-dependency browser-based bounding box verification and annotation tool.
Enables inspecting auto-labeled candidate boxes, drawing/resizing boxes, reclassifying
entities, and verifying ground-truth training data with keyboard shortcuts.
"""

import argparse
import glob
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any

# Root paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.path.join(SCRIPT_DIR, "extracted_frames")
ANNOTATIONS_DIR = os.path.join(SCRIPT_DIR, "annotations")
VERIFIED_INDEX = os.path.join(SCRIPT_DIR, "verified.json")

CLASS_NAMES = {
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

CLASS_COLORS = {
    0: "#3b82f6",  # Blue (general echo)
    1: "#eab308",  # Gold (echo_gold)
    2: "#a855f7",  # Purple (echo_purple)
    3: "#06b6d4",  # Cyan (echo_blue_green)
    4: "#ef4444",  # Red (target_boss)
    5: "#f97316",  # Orange (target_mob)
    6: "#10b981",  # Green (chest_supply)
    7: "#ec4899",  # Pink (interact_f_prompt)
    8: "#8b5cf6",  # Indigo (beacon_tactical)
    9: "#e11d48",  # Rose (lockon_reticle)
}


def load_verified_index() -> Dict[str, bool]:
    if os.path.exists(VERIFIED_INDEX):
        try:
            with open(VERIFIED_INDEX, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_verified_index(data: Dict[str, bool]):
    with open(VERIFIED_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WUWA Vision Studio - Annotation & Verification</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --panel-border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --primary: #38bdf8;
      --accent: #22c55e;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      user-select: none;
    }
    /* Header */
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--panel-border);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 56px;
    }
    .brand { display: flex; align-items: center; gap: 12px; font-weight: 700; font-size: 16px; letter-spacing: 0.5px; }
    .badge {
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
    }
    .header-center { display: flex; align-items: center; gap: 16px; font-size: 14px; color: var(--muted); }
    .header-actions { display: flex; align-items: center; gap: 10px; }
    button {
      background: #334155;
      color: var(--text);
      border: 1px solid var(--panel-border);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    button:hover { background: #475569; }
    button.primary { background: #0284c7; border-color: #38bdf8; }
    button.primary:hover { background: #0369a1; }
    button.success { background: #15803d; border-color: #22c55e; }
    button.success:hover { background: #166534; }
    button.danger { background: #b91c1c; border-color: #ef4444; }
    button.danger:hover { background: #991b1b; }

    /* Layout */
    .workspace {
      display: flex;
      flex: 1;
      height: calc(100vh - 120px);
      overflow: hidden;
    }
    .canvas-container {
      flex: 1;
      background: #090d16;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    #stage {
      position: relative;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      border-radius: 4px;
      overflow: hidden;
      cursor: crosshair;
    }
    #image-canvas, #overlay-canvas {
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
    }

    /* Sidebar */
    .sidebar {
      width: 320px;
      background: var(--panel);
      border-left: 1px solid var(--panel-border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .sidebar-section {
      padding: 14px;
      border-bottom: 1px solid var(--panel-border);
    }
    .section-title {
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--muted);
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
    }
    .class-palette {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .class-btn {
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 5px;
      border: 1px solid rgba(255,255,255,0.08);
      background: #0f172a;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      text-align: left;
    }
    .class-btn.active {
      border-color: var(--primary);
      background: #1e3a5f;
    }
    .color-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .box-list {
      flex: 1;
      overflow-y: auto;
      padding: 10px;
    }
    .box-item {
      background: #0f172a;
      border: 1px solid var(--panel-border);
      padding: 8px 10px;
      border-radius: 6px;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      cursor: pointer;
    }
    .box-item:hover, .box-item.selected {
      border-color: var(--primary);
      background: #1a2744;
    }
    .del-btn {
      background: none;
      border: none;
      color: var(--danger);
      font-size: 14px;
      cursor: pointer;
      padding: 2px 6px;
    }
    .del-btn:hover { color: #f87171; }

    /* Footer Scrubber */
    footer {
      height: 64px;
      background: var(--panel);
      border-top: 1px solid var(--panel-border);
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 12px;
    }
    .filmstrip {
      flex: 1;
      display: flex;
      align-items: center;
      gap: 4px;
      overflow-x: auto;
      height: 48px;
      padding: 0 4px;
    }
    .filmstrip::-webkit-scrollbar { height: 4px; }
    .filmstrip::-webkit-scrollbar-thumb { background: #475569; border-radius: 2px; }
    .strip-item {
      min-width: 32px;
      height: 36px;
      background: #0f172a;
      border: 1px solid var(--panel-border);
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      color: var(--muted);
      cursor: pointer;
      position: relative;
    }
    .strip-item:hover { border-color: var(--primary); }
    .strip-item.current { border-color: var(--primary); background: #0369a1; color: #fff; font-weight: 700; }
    .strip-item.verified::after {
      content: "";
      position: absolute;
      top: 3px; right: 3px;
      width: 6px; height: 6px;
      border-radius: 50%;
      background: var(--accent);
    }
    .strip-item.has-boxes::before {
      content: "";
      position: absolute;
      bottom: 3px; left: 3px;
      width: 4px; height: 4px;
      border-radius: 50%;
      background: #f59e0b;
    }
    .toast {
      position: fixed;
      bottom: 80px;
      left: 50%;
      transform: translateX(-50%);
      background: #0284c7;
      color: white;
      padding: 8px 18px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease;
      z-index: 999;
    }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>Wuthering Waves Vision Studio</span>
      <span class="badge" id="badge-version">v1.0</span>
    </div>
    <div class="header-center">
      <span id="frame-counter">Frame 0 / 0</span>
      <span id="verified-status" style="font-weight:600;">Status: Unverified</span>
    </div>
    <div class="header-actions">
      <button onclick="prevFrame()" title="Hotkey: A or Left Arrow">&lt; Prev</button>
      <button onclick="nextFrame()" title="Hotkey: D or Right Arrow">Next &gt;</button>
      <button id="verify-btn" class="success" onclick="toggleVerify()" title="Hotkey: Space">Mark Verified</button>
      <button class="primary" onclick="saveAnnotations()" title="Hotkey: Ctrl+S">Save</button>
    </div>
  </header>

  <div class="workspace">
    <div class="canvas-container" id="canvas-container">
      <div id="stage">
        <canvas id="image-canvas"></canvas>
        <canvas id="overlay-canvas"></canvas>
      </div>
    </div>

    <div class="sidebar">
      <div class="sidebar-section">
        <div class="section-title">
          <span>Class Palette</span>
          <span style="font-size:10px; color:#64748b;">Keys [0-9]</span>
        </div>
        <div class="class-palette" id="class-palette"></div>
      </div>

      <div class="sidebar-section" style="flex:1; display:flex; flex-direction:column; overflow:hidden;">
        <div class="section-title">
          <span>Detected Entities</span>
          <span id="box-count-badge" style="color:var(--primary);">0 boxes</span>
        </div>
        <div class="box-list" id="box-list"></div>
      </div>
    </div>
  </div>

  <footer>
    <div style="font-size:12px; color:var(--muted); font-weight:600; min-width:80px;" id="verified-summary">
      0 / 0 Verified
    </div>
    <div class="filmstrip" id="filmstrip"></div>
  </footer>

  <div class="toast" id="toast">Saved annotations successfully!</div>

  <script>
    let frames = [];
    let currentIndex = 0;
    let currentBoxes = []; // [{class_id, xc, yc, bw, bh, conf}]
    let selectedBoxIndex = -1;
    let activeClassId = 4; // default target_boss
    let classes = {};
    let colors = {};
    let imgNaturalW = 1280;
    let imgNaturalH = 720;
    let stageScale = 1.0;

    // Interaction states
    let isDrawing = false;
    let startX = 0, startY = 0;
    let dragMode = "none"; // "create", "move", "resize"
    let dragHandle = -1;
    let dragBoxOrig = null;

    const stage = document.getElementById("stage");
    const imgCanvas = document.getElementById("image-canvas");
    const overlayCanvas = document.getElementById("overlay-canvas");
    const imgCtx = imgCanvas.getContext("2d");
    const overlayCtx = overlayCanvas.getContext("2d");
    const toast = document.getElementById("toast");

    function showToast(msg) {
      toast.innerText = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 1200);
    }

    async function init() {
      // 1. Fetch classes
      const cRes = await fetch("/api/classes");
      const cData = await cRes.json();
      classes = cData.names;
      colors = cData.colors;
      renderPalette();

      // 2. Fetch frames
      await loadFrames();

      // Event listeners
      window.addEventListener("resize", fitStage);
      window.addEventListener("keydown", handleKeydown);

      overlayCanvas.addEventListener("mousedown", onMouseDown);
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    }

    function renderPalette() {
      const container = document.getElementById("class-palette");
      container.innerHTML = "";
      for (const [idStr, name] of Object.entries(classes)) {
        const id = parseInt(idStr);
        const col = colors[id] || "#fff";
        const btn = document.createElement("div");
        btn.className = `class-btn ${id === activeClassId ? 'active' : ''}`;
        btn.id = `class-btn-${id}`;
        btn.innerHTML = `<span class="color-dot" style="background:${col};"></span><span>[${id}] ${name}</span>`;
        btn.onclick = () => selectClass(id);
        container.appendChild(btn);
      }
    }

    function selectClass(id) {
      activeClassId = id;
      document.querySelectorAll(".class-btn").forEach(b => b.classList.remove("active"));
      const target = document.getElementById(`class-btn-${id}`);
      if (target) target.classList.add("active");
      if (selectedBoxIndex >= 0 && selectedBoxIndex < currentBoxes.length) {
        currentBoxes[selectedBoxIndex].class_id = id;
        renderOverlay();
        renderBoxList();
      }
    }

    async function loadFrames() {
      const res = await fetch("/api/frames");
      frames = await res.json();
      if (frames.length > 0) {
        updateFilmstrip();
        await loadFrame(currentIndex);
      }
    }

    async function loadFrame(idx) {
      if (idx < 0 || idx >= frames.length) return;
      currentIndex = idx;
      selectedBoxIndex = -1;
      const f = frames[idx];

      document.getElementById("frame-counter").innerText = `Frame ${idx + 1} / ${frames.length} (${f.name})`;
      const vStatus = document.getElementById("verified-status");
      const vBtn = document.getElementById("verify-btn");
      if (f.verified) {
        vStatus.innerText = "Status: ✓ Verified";
        vStatus.style.color = "var(--accent)";
        vBtn.innerText = "Unmark Verified";
        vBtn.className = "";
      } else {
        vStatus.innerText = "Status: ⚠ Unverified";
        vStatus.style.color = "#f59e0b";
        vBtn.innerText = "Mark Verified";
        vBtn.className = "success";
      }

      // Load Image
      const img = new Image();
      img.src = `/api/image/${encodeURIComponent(f.name)}`;
      img.onload = () => {
        imgNaturalW = img.naturalWidth || 1280;
        imgNaturalH = img.naturalHeight || 720;
        fitStage();
        imgCtx.drawImage(img, 0, 0, imgCanvas.width, imgCanvas.height);
      };

      // Load Annotations
      const aRes = await fetch(`/api/annotation/${encodeURIComponent(f.name)}`);
      currentBoxes = await aRes.json();
      renderOverlay();
      renderBoxList();
      updateFilmstrip();
    }

    function fitStage() {
      const container = document.getElementById("canvas-container");
      const cW = container.clientWidth - 40;
      const cH = container.clientHeight - 40;
      stageScale = Math.min(cW / imgNaturalW, cH / imgNaturalH);

      const renderW = Math.round(imgNaturalW * stageScale);
      const renderH = Math.round(imgNaturalH * stageScale);

      stage.style.width = renderW + "px";
      stage.style.height = renderH + "px";

      imgCanvas.width = renderW;
      imgCanvas.height = renderH;
      overlayCanvas.width = renderW;
      overlayCanvas.height = renderH;

      renderOverlay();
    }

    function renderOverlay() {
      overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
      const rW = overlayCanvas.width;
      const rH = overlayCanvas.height;

      currentBoxes.forEach((b, idx) => {
        const x = (b.xc - b.bw / 2) * rW;
        const y = (b.yc - b.bh / 2) * rH;
        const w = b.bw * rW;
        const h = b.bh * rH;
        const col = colors[b.class_id] || "#fff";
        const isSel = idx === selectedBoxIndex;

        // Box border
        overlayCtx.strokeStyle = col;
        overlayCtx.lineWidth = isSel ? 3 : 2;
        overlayCtx.strokeRect(x, y, w, h);

        // Fill background
        overlayCtx.fillStyle = isSel ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.2)";
        overlayCtx.fillRect(x, y, w, h);

        // Tag label
        const labelText = `[${b.class_id}] ${classes[b.class_id] || 'unknown'}`;
        overlayCtx.font = "bold 11px sans-serif";
        const textW = overlayCtx.measureText(labelText).width + 8;
        overlayCtx.fillStyle = col;
        overlayCtx.fillRect(x, y - 18 > 0 ? y - 18 : y, textW, 18);
        overlayCtx.fillStyle = "#000";
        overlayCtx.fillText(labelText, x + 4, (y - 18 > 0 ? y - 5 : y + 13));

        // Corner handles if selected
        if (isSel) {
          overlayCtx.fillStyle = "#fff";
          const hs = 6;
          overlayCtx.fillRect(x - hs/2, y - hs/2, hs, hs);
          overlayCtx.fillRect(x + w - hs/2, y - hs/2, hs, hs);
          overlayCtx.fillRect(x - hs/2, y + h - hs/2, hs, hs);
          overlayCtx.fillRect(x + w - hs/2, y + h - hs/2, hs, hs);
        }
      });
    }

    function renderBoxList() {
      const list = document.getElementById("box-list");
      list.innerHTML = "";
      document.getElementById("box-count-badge").innerText = `${currentBoxes.length} boxes`;

      currentBoxes.forEach((b, idx) => {
        const item = document.createElement("div");
        item.className = `box-item ${idx === selectedBoxIndex ? 'selected' : ''}`;
        const col = colors[b.class_id] || "#fff";
        item.innerHTML = `
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="color-dot" style="background:${col};"></span>
            <span style="font-weight:600;">[${b.class_id}] ${classes[b.class_id] || 'item'}</span>
          </div>
          <button class="del-btn" onclick="deleteBox(event, ${idx})" title="Delete box">&times;</button>
        `;
        item.onclick = (e) => {
          if (!e.target.classList.contains("del-btn")) {
            selectedBoxIndex = idx;
            selectClass(b.class_id);
            renderOverlay();
            renderBoxList();
          }
        };
        list.appendChild(item);
      });
    }

    function deleteBox(e, idx) {
      e.stopPropagation();
      currentBoxes.splice(idx, 1);
      selectedBoxIndex = -1;
      renderOverlay();
      renderBoxList();
      saveAnnotations(false);
    }

    function updateFilmstrip() {
      const strip = document.getElementById("filmstrip");
      strip.innerHTML = "";
      let verifiedCount = 0;

      frames.forEach((f, i) => {
        if (f.verified) verifiedCount++;
        const item = document.createElement("div");
        item.className = `strip-item ${i === currentIndex ? 'current' : ''} ${f.verified ? 'verified' : ''} ${f.has_boxes ? 'has-boxes' : ''}`;
        item.innerText = i + 1;
        item.onclick = async () => {
          await saveAnnotations(false);
          await loadFrame(i);
        };
        strip.appendChild(item);
      });

      document.getElementById("verified-summary").innerText = `${verifiedCount} / ${frames.length} Verified`;
      const curItem = strip.children[currentIndex];
      if (curItem) curItem.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    async function saveAnnotations(showFeedback = true) {
      if (!frames[currentIndex]) return;
      const f = frames[currentIndex];
      await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: f.name, boxes: currentBoxes }),
      });
      f.has_boxes = currentBoxes.length > 0;
      if (showFeedback) showToast("Saved annotations!");
    }

    async function toggleVerify() {
      if (!frames[currentIndex]) return;
      const f = frames[currentIndex];
      f.verified = !f.verified;
      await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: f.name, verified: f.verified }),
      });
      await saveAnnotations(false);
      loadFrame(currentIndex);
    }

    async function prevFrame() {
      if (currentIndex > 0) {
        await saveAnnotations(false);
        loadFrame(currentIndex - 1);
      }
    }

    async function nextFrame() {
      if (currentIndex < frames.length - 1) {
        await saveAnnotations(false);
        loadFrame(currentIndex + 1);
      }
    }

    function onMouseDown(e) {
      const rect = overlayCanvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const rW = overlayCanvas.width;
      const rH = overlayCanvas.height;

      // Check if clicking inside an existing box (reverse to check top-most first)
      let hit = -1;
      for (let i = currentBoxes.length - 1; i >= 0; i--) {
        const b = currentBoxes[i];
        const bx = (b.xc - b.bw / 2) * rW;
        const by = (b.yc - b.bh / 2) * rH;
        const bw = b.bw * rW;
        const bh = b.bh * rH;
        if (clickX >= bx && clickX <= bx + bw && clickY >= by && clickY <= by + bh) {
          hit = i;
          break;
        }
      }

      if (hit >= 0) {
        selectedBoxIndex = hit;
        selectClass(currentBoxes[hit].class_id);
        renderOverlay();
        renderBoxList();
      } else {
        // Start creating a new box
        isDrawing = true;
        startX = clickX;
        startY = clickY;
        selectedBoxIndex = -1;
      }
    }

    function onMouseMove(e) {
      if (!isDrawing) return;
      const rect = overlayCanvas.getBoundingClientRect();
      const curX = Math.max(0, Math.min(overlayCanvas.width, e.clientX - rect.left));
      const curY = Math.max(0, Math.min(overlayCanvas.height, e.clientY - rect.top));

      renderOverlay();
      overlayCtx.strokeStyle = colors[activeClassId] || "#38bdf8";
      overlayCtx.lineWidth = 2;
      overlayCtx.strokeRect(
        Math.min(startX, curX),
        Math.min(startY, curY),
        Math.abs(curX - startX),
        Math.abs(curY - startY)
      );
    }

    function onMouseUp(e) {
      if (!isDrawing) return;
      isDrawing = false;
      const rect = overlayCanvas.getBoundingClientRect();
      const endX = Math.max(0, Math.min(overlayCanvas.width, e.clientX - rect.left));
      const endY = Math.max(0, Math.min(overlayCanvas.height, e.clientY - rect.top));
      const rW = overlayCanvas.width;
      const rH = overlayCanvas.height;

      const x1 = Math.min(startX, endX);
      const y1 = Math.min(startY, endY);
      const w = Math.abs(endX - startX);
      const h = Math.abs(endY - startY);

      // Only save if meaningful size (at least 8px)
      if (w >= 8 && h >= 8) {
        const newBox = {
          class_id: activeClassId,
          xc: (x1 + w / 2) / rW,
          yc: (y1 + h / 2) / rH,
          bw: w / rW,
          bh: h / rH,
          conf: 1.0,
        };
        currentBoxes.push(newBox);
        selectedBoxIndex = currentBoxes.length - 1;
        saveAnnotations(false);
      }
      renderOverlay();
      renderBoxList();
    }

    function handleKeydown(e) {
      // Numbers 0-9 to select class
      if (e.key >= '0' && e.key <= '9') {
        selectClass(parseInt(e.key));
        return;
      }
      if (e.key === 'a' || e.key === 'A' || e.key === 'ArrowLeft') {
        prevFrame();
      } else if (e.key === 'd' || e.key === 'D' || e.key === 'ArrowRight') {
        nextFrame();
      } else if (e.code === 'Space') {
        e.preventDefault();
        toggleVerify();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedBoxIndex >= 0) {
          currentBoxes.splice(selectedBoxIndex, 1);
          selectedBoxIndex = -1;
          renderOverlay();
          renderBoxList();
          saveAnnotations(false);
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        saveAnnotations(true);
      }
    }

    window.onload = init;
  </script>
</body>
</html>
"""


class AnnotationServerHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Silence normal HTTP access logs for clean console
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/classes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = json.dumps({"names": CLASS_NAMES, "colors": CLASS_COLORS})
            self.wfile.write(payload.encode("utf-8"))
            return

        if path == "/api/frames":
            verified = load_verified_index()
            images = sorted(glob.glob(os.path.join(FRAMES_DIR, "*.[jJ][pP][gG]")) + glob.glob(os.path.join(FRAMES_DIR, "*.[pP][nN][gG]")))
            frames_meta = []
            for img in images:
                name = os.path.basename(img)
                base = os.path.splitext(name)[0]
                lbl_path = os.path.join(ANNOTATIONS_DIR, base + ".txt")
                has_boxes = os.path.exists(lbl_path) and os.path.getsize(lbl_path) > 0
                frames_meta.append({
                    "name": name,
                    "has_boxes": has_boxes,
                    "verified": verified.get(name, False),
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(frames_meta).encode("utf-8"))
            return

        if path.startswith("/api/image/"):
            img_name = urllib.parse.unquote(path[len("/api/image/"):])
            img_path = os.path.join(FRAMES_DIR, img_name)
            if os.path.exists(img_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Image not found")
            return

        if path.startswith("/api/annotation/"):
            img_name = urllib.parse.unquote(path[len("/api/annotation/"):])
            base = os.path.splitext(img_name)[0]
            txt_path = os.path.join(ANNOTATIONS_DIR, base + ".txt")
            boxes = []
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            cls_id = int(parts[0])
                            xc, yc, bw, bh = (float(p) for p in parts[1:5])
                            boxes.append({
                                "class_id": cls_id,
                                "xc": xc,
                                "yc": yc,
                                "bw": bw,
                                "bh": bh,
                                "conf": 1.0,
                            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(boxes).encode("utf-8"))
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        data = json.loads(body) if body else {}

        if parsed.path == "/api/save":
            img_name = data.get("name")
            boxes = data.get("boxes", [])
            if img_name:
                base = os.path.splitext(img_name)[0]
                os.makedirs(ANNOTATIONS_DIR, exist_ok=True)
                txt_path = os.path.join(ANNOTATIONS_DIR, base + ".txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    for b in boxes:
                        f.write(f"{b['class_id']} {b['xc']:.6f} {b['yc']:.6f} {b['bw']:.6f} {b['bh']:.6f}\n")

                # Also update corresponding dataset split label if it exists
                for split in ["train", "val", "test"]:
                    split_txt = os.path.join(SCRIPT_DIR, "dataset", "labels", split, base + ".txt")
                    if os.path.exists(split_txt) or os.path.exists(os.path.join(SCRIPT_DIR, "dataset", "images", split, img_name)):
                        os.makedirs(os.path.dirname(split_txt), exist_ok=True)
                        with open(split_txt, "w", encoding="utf-8") as f:
                            for b in boxes:
                                f.write(f"{b['class_id']} {b['xc']:.6f} {b['yc']:.6f} {b['bw']:.6f} {b['bh']:.6f}\n")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            return

        if parsed.path == "/api/verify":
            img_name = data.get("name")
            is_verified = bool(data.get("verified", False))
            if img_name:
                v_index = load_verified_index()
                v_index[img_name] = is_verified
                save_verified_index(v_index)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            return

        self.send_error(404, "Not found")


def launch_server(port: int = 8088, auto_open: bool = True):
    server = HTTPServer(("127.0.0.1", port), AnnotationServerHandler)
    url = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 65)
    print(f"  [WUWA Vision Studio] Verification UI is active at: {url}")
    print("  Press Ctrl+C in terminal to stop server.")
    print("=" * 65 + "\n")
    if auto_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WUWA Vision Studio] Server stopped.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WUWA Vision Studio - Annotation & Verification UI")
    parser.add_argument("--port", type=int, default=8088, help="Port to run local server (default: 8088)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch default browser")
    args = parser.parse_args()

    launch_server(port=args.port, auto_open=not args.no_browser)
