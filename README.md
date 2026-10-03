<div align="center">
  <h1 align="center">
    <img src="icons/icon.png" width="200" alt="wuwa-auto logo"/>
    <br/>
    wuwa-auto
  </h1>

  <p>
    An image-recognition-based automation tool for <b>Wuthering Waves</b>, with background mode support, built on the <a href="https://github.com/ok-oldking/ok-script">ok-script</a> framework.
  </p>

  <p><i>Operates by simulating the Windows user interface — no memory reading, no file modification.</i></p>
</div>

<!-- Badges -->
<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/suho-1/wuwa-auto)](https://github.com/suho-1/wuwa-auto/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

---

## ⚠️ Disclaimer

This software is an external auxiliary tool designed to automate parts of the Wuthering Waves gameplay. It interacts with the game solely by simulating standard user interface actions, in compliance with relevant laws and regulations. This project aims to simplify repetitive user tasks and does not disrupt game balance or provide an unfair advantage. It will never modify any game files or data.

This software is open-source and free, intended for personal learning and communication purposes only. Do not use it for any commercial or profit-making activities.

Please note, according to Kuro Games' official Fair Play Declaration for Wuthering Waves:
> The use of any third-party tools to disrupt the game experience is strictly prohibited.
> We will take strict measures against the use of unauthorized tools such as cheats, speed hacks, cheat software, and macro scripts. This includes, but is not limited to, automated farming, skill acceleration, god mode, teleportation, and modification of game data.
> Once verified, we will impose penalties based on the severity and frequency of the violation, including but not limited to deducting illicit gains, and suspending or permanently banning the game account.

**By using this software, you acknowledge that you have read, understood, and agreed to the above statement, and you voluntarily assume all potential risks.**

## ✨ Features

*   **High-Resolution Support** — Runs smoothly on all 16:9 resolutions up to 4K (minimum 1280×720). Some features are also compatible with 21:9 ultrawide.
*   **Background Mode** — Supports running while the game window is minimized or obscured, so you can use your computer for other tasks.
*   **Intelligent Recognition** — Automatically identifies all characters with no manual skill-sequence configuration needed. One-click start.
*   **Auto-Mute** — Optionally mutes the game audio when running in the background.
*   **Auto Combat** — Intelligent rotational combat for all resonators with character-specific skill chains.
*   **Echo Farming** — Automated echo boss tracking with minimap navigation, locked-area skipping, and 360° camera scanning.
*   **Daily Routines** — One-click daily task runner: simulation, forgery, tacet fields, and waveplate management.
*   **TUI Dashboard** — Headless terminal interface for managing routines without a GUI.
*   **Chest Exploration** — Automated route playback for chest hunting across all regions.

## 🚀 Quick Start

1.  **Clone this repository**:
    ```bash
    git clone https://github.com/suho-1/wuwa-auto.git
    ```
2.  **Install dependencies** (Python 3.12 recommended):
    ```bash
    pip install -r requirements.txt --upgrade
    ```
3.  **Run**:
    ```bash
    python main.py
    ```
    Or use the included launcher:
    ```bash
    wuwa-auto.bat
    ```

## 🔧 Troubleshooting

If you encounter issues, please check the following before opening an issue:

1.  **Antivirus Software** — Add the installation directory to your antivirus whitelist (including Windows Defender) to prevent files from being blocked.
2.  **Display Settings**:
    *   In-game filters are fine, but disable GPU-level filters (NVIDIA Dynamic Vibrance, AMD sharpening).
    *   Use the game's default brightness.
    *   Disable overlays (MSI Afterburner, Fraps, etc.).
3.  **Custom Keybinds** — If you changed the default in-game keybinds, update them in the wuwa-auto settings. Only listed keybinds are supported.
4.  **Software Version** — Make sure you're on the latest version.
5.  **Game Performance** — The game must run stably at **60 FPS**. Lower graphics if needed.
6.  **Game Disconnections** — Enable "Close Launcher After Start" in settings, or run from source.
7.  **OpenVINO Error** — If you get `0x000005` on an Intel CPU with NPU, update to the latest Intel NPU driver.
8.  **Disable Auto Sprint** — Turn off Auto Sprint in the game settings.
9.  **Equip a Main Echo** — Every character in the team must have a main Echo equipped (the Echo Skill icon should appear in the bottom-right corner). Without one, Auto Combat may lock onto enemies without attacking.

---

## 💻 Developer Guide

### Running from Source

Python 3.12 is recommended. Python 3.10+ is required but other versions have not been fully tested.

```bash
# Install or update dependencies
pip install -r requirements.txt --upgrade

# Run Release version
python main.py

# Run Debug version
python main_debug.py
```

### Command-Line Arguments

```bash
# Run the first task automatically and exit when done
python main.py -t 1 -e
```

*   `-t` / `--task` — Automatically run the Nth task after launch. `1` = first task.
*   `-e` / `--exit` — Exit the program after the task completes.

### Running Tests

```bash
python -m unittest discover tests
```

---

## 🏗️ Project Structure

```
├── src/
│   ├── char/           # Character-specific combat rotations
│   ├── combat/         # Combat check and team advisor
│   ├── task/           # Automation tasks (echo, daily, dungeon, etc.)
│   ├── tui/            # Terminal UI dashboard
│   └── gui/            # Annotation studio
├── ok/                 # ok-script framework (upstream library)
├── assets/             # YOLO models, sprite atlases, templates
├── tests/              # Unit tests and benchmarks
├── training/           # Dataset pipeline and labeling tools
├── config.py           # Application configuration
├── main.py             # Entry point
└── requirements.txt    # Python dependencies
```

---

## ❤️ Credits & Acknowledgements

This project is a fork/derivative of [**ok-ww**](https://github.com/ok-oldking/ok-wuthering-waves) by [ok-oldking](https://github.com/ok-oldking). The original project and the [ok-script](https://github.com/ok-oldking/ok-script) framework it's built on made this work possible. Huge thanks to the original author and all contributors.

### Additional Thanks

*   [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script) — The automation framework powering this project
*   [ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves) — The original ok-ww project
*   [lazydog28/mc_auto_boss](https://github.com/lazydog28/mc_auto_boss)
*   [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
*   [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
*   [Toufool/AutoSplit](https://github.com/Toufool/AutoSplit)

---

## 📄 License

This project is open-source. See [LICENSE](LICENSE) for details.
