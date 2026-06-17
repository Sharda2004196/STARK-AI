# 🤖 STARK AI (J.A.R.V.I.S)

### The Ultimate Cross-Platform Personal AI Assistant
**Developed by Sharda Vatsal Bhat (SVB)**

STARK AI (J.A.R.V.I.S) is a state-of-the-art, autonomous, multi-modal AI assistant. It bridges the gap between digital intent and real-world action by integrating high-fidelity voice, computer vision, and deep system-level automation.

![STARK AI Screenshot](assets/STARK_AI_Screenshot.png)

---

## 📖 Table of Contents
1. [Overview](#-overview)
2. [Architecture](#-architecture)
3. [Comprehensive Tool Module Documentation](#-comprehensive-tool-module-documentation)
4. [Getting Started & Configuration](#-getting-started--configuration)
5. [Advanced Setup Deep-Dive](#-advanced-setup-deep-dive)
6. [Security & Risk Disclaimer](#-security--risk-disclaimer)
7. [Support & Credits](#-support--credits)

---

## 🧐 Overview
STARK AI was built to serve as a unified interface for all digital tasks. Unlike traditional assistants that merely answer questions, J.A.R.V.I.S uses an **agentic architecture** to plan complex goals, execute multi-step tool sequences, and self-correct based on real-time feedback from your computer and mobile devices.

---

## 🏗️ Architecture

J.A.R.V.I.S is built on a modular agentic framework:
*   **The Brain (Gemini Live API):** Handles multimodal audio/text/image reasoning using the `google.genai` SDK.
*   **The Planner (`agent/planner.py`):** Parses complex goals into actionable tool sequences using semantic understanding.
*   **The Executor (`agent/executor.py`):** Sequentially invokes the correct action modules, managing concurrency and state.
*   **Error Handler (`agent/error_handler.py`):** Monitors execution, manages retries, and provides self-healing patterns for transient errors.
*   **Memory Manager (`memory/memory_manager.py`):** Maintains long-term context using JSON storage, allowing JARVIS to remember identity, preferences, and relationships.

---

## 🚀 Comprehensive Tool Module Documentation

J.A.R.V.I.S utilizes over 16 specialized automation modules:

### 📱 Mobile & Computer Control
*   **Mobile Control (`actions/mobile_control.py`):** Hybrid **UIAutomator2 + Vision** engine. Allows for wireless control over Android devices including app launching, messaging, calling, and system settings (volume/brightness). Uses MDNS auto-discovery for wireless ADB connections.
*   **Computer Control (`actions/computer_control.py`):** High-precision PC interaction using Windows-native UI tree parsing (`pywinauto`) for element identification by name, with Gemini 2.0 Flash vision as a fallback. Supports precise scrolling and pixel-accurate clicking.
*   **Desktop Control (`actions/desktop.py`):** Manages wallpapers, organizes files, and provides desktop statistics.

### ⚙️ Autonomous Engineering
*   **APK Builder (`actions/apk_builder.py`):** Architects, builds, and compiles native Android applications from natural language. It manages Gradle structures, manifest generation, and Kotlin code.
*   **Extension Builder (`actions/extension_builder.py`):** Generates structured browser extensions for Chrome/Edge from natural language descriptions.
*   **Frontend Builder (`actions/frontend_builder.py`):** Generates immersive UIs using Tailwind CSS, 3D (Three.js), and GSAP animations.
*   **Code Helper (`actions/code_helper.py`):** Writes, edits, explains, runs, and builds code files programmatically.
*   **Dev Agent (`actions/dev_agent.py`):** Builds complete multi-file projects, plans structure, installs dependencies, and manages errors.

### 🌐 Intelligence & Communication
*   **Web Search (`actions/web_search.py`):** Advanced web browsing and research.
*   **Browser Control (`actions/browser_control.py`):** Full browser orchestration: navigating, filling forms, extracting data, and managing sessions.
*   **Send Message (`actions/send_message.py`):** PC-based communication module for WhatsApp, Telegram, and Signal.
*   **Attention Monitor (`actions/attention_monitor.py`):** Proactively detects incoming communication (Zoom, Teams, Skype, WhatsApp) and injects announcements into the live session.
*   **Meeting Analyzer (`actions/meeting_analyzer.py`):** Real-time audio transcription and screen-based analysis during virtual meetings.

### 🛠️ Utilities
*   **File Controller (`actions/file_controller.py`):** Comprehensive local file management: CRUD operations, moving, copying, renaming, and finding files.
*   **File Processor (`actions/file_processor.py`):** Multi-modal file processing engine for OCR, summarization, PDF extraction, format conversion, and media analysis.
*   **Video Editing (`actions/video_editing.py`):** Advanced programmatic video editing capabilities, including trimming, merging, captioning, and beat-syncing.
*   **Game Updater (`actions/game_updater.py`):** Automated management for Steam and Epic Games libraries.
*   **Content Studio (`actions/content_studio.py`):** Studio for social media content creation (YouTube, Instagram).
*   **Prompt Optimizer (`actions/prompt_optimizer.py`):** Refines user requests for high-fidelity tool execution.

---

## 🛠️ Getting Started & Configuration

1. **System Prerequisites:**
   - **OS:** Windows 10/11
   - **Language:** Python 3.11
   - **Dependencies:** Android SDK/JDK 17 (Required for APK compilation)
2. **Installation:**
   ```bash
   git clone <repo-url>
   pip install -r requirements.txt
   ```
3. **API Configuration:**
   - Rename `config/api_keys.example.json` to `config/api_keys.json`.
   - **Gemini Key (Mandatory):** Obtain from [Google AI Studio](https://aistudio.google.com/).
   - **OpenCode/Composio Keys (Optional but Recommended):** 
     - **OpenCode:** Obtain from [OpenCode.ai](https://opencode.ai/). Highly recommended for superior Android code reasoning.
     - **Composio:** Obtain from [Composio.dev](https://composio.dev/). Required for advanced cloud-based automation (GitHub, Sheets, Notion).
4. **Execution:**
   - **Main Assistant:** Run the main.py file to launch the J.A.R.V.I.S UI and interactive session directly.

---

## ⚙️ Advanced Setup Deep-Dive

### 🖐️ AI Gesture Control (Vision Mode)
Transform your hand into a high-precision digital controller. Use the webcam to navigate your OS with low-latency tracking and AI-driven recognition.
*   **The Tech Stack:** Powered by `cvzone` and `MediaPipe` for 21-point hand landmark detection. It processes frames in a dedicated background thread, ensuring JARVIS remains responsive while you control the PC.
*   **High Precision & Smoothing:** Implements a snappy exponential moving average filter to eliminate cursor jitter, providing a "liquid" feel similar to a high-end trackpad.
*   **Tactical HUD Feedback:** JARVIS opens a dedicated "Gesture Vision" window with a real-time HUD. It draws a digital skeleton over your hand and provides visual color confirmation (Green/Blue glows) when clicks are registered.
*   **Full Gesture Mapping:**
    - **Cursor Movement:** Use your **Index Finger** as the pointer (the HUD will track the tip).
    - **Left Click:** Perform a **Pinch** gesture with your Index Finger and Thumb.
    - **Right Click:** Perform a **Pinch** gesture with your Middle Finger and Thumb.
    - **Smart Scroll:** Hold your **Index and Middle** fingers together and move your hand vertically to scroll through pages or lists.
    - **Instant Minimize (Fist):** Close your hand into a **Fist** to instantly minimize all open windows (`Win+D`). This is the fastest way to clear your screen without searching for the minimize button.

### 📱 Wireless Mobile Control (UIAutomator2)
The mobile control module provides structural, high-level interaction with your Android phone.
*   **Under the Hood:** J.A.R.V.I.S installs a lightweight ATX Agent on the phone (`uiautomator2`). This agent converts high-level Python commands (`click("Call")`) into UI actions, bypassing the need for manual coordinate guessing.
*   **Wireless Mechanism:** Uses **Wireless Debugging** (Android Developer Options). The setup uses MDNS for dynamic discovery; J.A.R.V.I.S automatically updates its connection whenever your WiFi IP/port changes.
*   **Setup:**
    1.  Enable *Wireless Debugging* in Android Developer Options.
    2.  Ensure *Install via USB* and *USB Debugging (Security Settings)* are ENABLED.
    3.  Run `py -3.11 -m uiautomator2 init` while connected to prime the driver.

### 🏗️ APK & Extension Compilation
These features harness AI-driven reasoning to generate complex project structures.
*   **APK Construction:** J.A.R.V.I.S generates the entire Kotlin/Gradle folder structure. To compile, the system automatically injects your `ANDROID_HOME` (SDK) and `JAVA_HOME` (JDK) paths to invoke Gradle and produce a production-ready `.apk`.
*   **Error Correction:** If compilation fails, the logs are automatically captured and fed back into the reasoning model to suggest code fixes or structural changes in the next iteration.

---

## 🛡️ Security & Risk Disclaimer

**Read carefully before use.** STARK AI is built for total system autonomy.

1. **Cloud Privacy:** Screen/Audio processed by Google Gemini Cloud API. Avoid sensitive data.
2. **Agentic Risk:** J.A.R.V.I.S has full control over your machine. AI hallucinations can lead to unintended actions.
3. **Always-On Mic:** Uses a background listening loop.
4. **Human-in-the-Loop (HITL):** A mandatory **🛡️ STARK SECURITY PROTOCOL** confirmation popup guards destructive actions (deleting files/system shutdown). **Do not bypass this security layer.**

---

## 🌟 Support
Built by **Sharda Vatsal Bhat (SVB)**.
⭐ **Star this repository** if you find it useful.
