# ──────────────────────────────────────────────────────────────────────────────
#  ui.py — STARK Holographic Intelligence Interface
#  J.A.R.V.I.S. — Just A Rather Very Intelligent System
#  Operator: Sharda Vatsal Bhat  ·  SVB
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

try:
    import winsound
    _WINSOUND_OK = True
except ImportError:
    _WINSOUND_OK = False

try:
    import keyboard
    _KEYBOARD_OK = True
except ImportError:
    _KEYBOARD_OK = False


from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtMultimedia import QSoundEffect

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

# ── Path helpers ──────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1200, 780
_MIN_W,     _MIN_H     = 960, 640
_LEFT_W  = 260
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# ── Font loading ──────────────────────────────────────────────────────────────

_FONT_HDR  = "Segoe UI Semibold" # fallback
_FONT_DATA = "Consolas"         # fallback
_FONTS_LOADED = False


def _init_fonts():
    """Load custom fonts from fonts/ dir, then choose best available."""
    global _FONT_HDR, _FONT_DATA, _FONTS_LOADED
    if _FONTS_LOADED:
        return
    _FONTS_LOADED = True

    fonts_dir = BASE_DIR / "fonts"
    if fonts_dir.is_dir():
        for ext in ("*.ttf", "*.otf"):
            for fp in fonts_dir.glob(ext):
                QFontDatabase.addApplicationFont(str(fp))

    available = set(QFontDatabase.families())

    # Preference order for Tactical HUD look
    for candidate in ("Orbitron", "Exo 2", "Exo2", "Rajdhani", "Share Tech Mono", "Chakra Petch", "Segoe UI Semibold"):
        if candidate in available:
            _FONT_HDR = candidate
            break

    for candidate in ("Fira Code", "FiraCode", "Cascadia Code", "JetBrains Mono", "Roboto Mono", "Consolas"):
        if candidate in available:
            _FONT_DATA = candidate
            break


# ── Audio SFX Manager ─────────────────────────────────────────────────────────

class SFXManager(QObject):
    """UI sound effects — boot via QSoundEffect, clicks via winsound (Win32 native)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        sfx_dir = BASE_DIR / "sfx"

        # Boot sound → QSoundEffect (plays before voice starts, no conflict)
        self._boot = QSoundEffect()
        boot_path = sfx_dir / "startup.wav"
        if boot_path.exists():
            self._boot.setSource(QUrl.fromLocalFile(str(boot_path)))
        else:
            mp3s = list(sfx_dir.glob("*.mp3"))
            if mp3s:
                self._boot.setSource(QUrl.fromLocalFile(str(mp3s[0])))
        self._boot.setVolume(0.9)

        # Click / error → winsound (native Win32 API — completely separate audio
        # subsystem from both Qt Multimedia and PortAudio, so no device conflicts)
        self._click_path = str(sfx_dir / "click.wav")
        self._error_path = str(sfx_dir / "error.wav")

    def play(self, name: str):
        if name == "startup":
            self._boot.play()
        elif name == "click" and _WINSOUND_OK:
            try:
                winsound.PlaySound(
                    self._click_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NOSTOP,
                )
            except Exception:
                pass
        elif name == "error" and _WINSOUND_OK:
            try:
                winsound.PlaySound(
                    self._error_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NOSTOP,
                )
            except Exception:
                pass

_SFX = None

def play_sfx(name: str):
    global _SFX
    if _SFX:
        _SFX.play(name)


# ── Color palette ─────────────────────────────────────────────────────────────

class C:
    """Stark Holographic Intelligence colour constants."""
    BG       = "#010a14"
    PANEL    = "#01121d"
    PANEL2   = "#021a2b"
    BORDER   = "#0c3b54"
    BORDER_B = "#145c85"
    BORDER_A = "#0f4060"
    PRI      = "#00f2ff"  # Vibrant Aqua
    PRI_DIM  = "#0088aa"
    PRI_GHO  = "#002b3d"
    ACC      = "#ff8c00"
    ACC2     = "#ffcc00"
    VIOLET   = "#c084fc"
    VIOLET_B = "#d8b4fe"
    GREEN    = "#00ff88"
    GREEN_D  = "#00aa55"
    RED      = "#ff3355"
    MUTED_C  = "#ff2266"
    TEXT     = "#a3ffff"
    TEXT_DIM = "#45a3b5"
    TEXT_MED = "#63ccdf"
    WHITE    = "#e0fbff"
    DARK     = "#000c14"
    BAR_BG   = "#021f30"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c


# ── SHIELD Logo Widget ───────────────────────────────────────────────────────

class ShieldLogo(QWidget):
    """Custom drawn SHIELD / Stark tactical logo."""
    def __init__(self, size: int = 40, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W/2, H/2
        r = min(W, H) * 0.45

        # Draw outer circle
        p.setPen(QPen(qcol(C.PRI), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Draw inner Eagle/Shield geometry (stylized)
        p.setBrush(QBrush(qcol(C.PRI, 180)))
        p.setPen(Qt.PenStyle.NoPen)
        
        path = QPainterPath()
        path.moveTo(cx, cy - r*0.7) # Top
        path.lineTo(cx + r*0.6, cy - r*0.3)
        path.lineTo(cx + r*0.5, cy + r*0.5)
        path.lineTo(cx, cy + r*0.8) # Bottom
        path.lineTo(cx - r*0.5, cy + r*0.5)
        path.lineTo(cx - r*0.6, cy - r*0.3)
        path.closeSubpath()
        p.drawPath(path)

        # Inset line
        p.setPen(QPen(qcol(C.DARK, 200), 1))
        p.drawLine(QPointF(cx, cy - r*0.6), QPointF(cx, cy + r*0.7))
        p.end()


# ── System metrics (background thread) ───────────────────────────────────────

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self.cpu_cores: list[float] = []
        self._lock = threading.Lock()
        self._last_net   = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        cpu = sum(cpu_cores) / len(cpu_cores) if cpu_cores else 0.0
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            net = ((nc.bytes_sent - self._last_net.bytes_sent) +
                   (nc.bytes_recv - self._last_net.bytes_recv)) / dt / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp
            self.cpu_cores = cpu_cores

    # ── GPU utilisation ──
    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2,
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2,
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass
        return -1.0

    # ── Temperature ──
    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"):
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(["osx-cpu-temp"], capture_output=True,
                                   text=True, timeout=2)
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass
        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature "
                     "-Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3,
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass
        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu, "mem": self.mem, "net": self.net,
                "gpu": self.gpu, "tmp": self.tmp,
                "cores": list(self.cpu_cores),
            }


_metrics = _SysMetrics()


# ── JarvisCore — Dynamic Liquid Blob ─────────────────────────────────────────

_BLOB_HARMONICS = [
    {"amp": 12.0, "freq": 2,  "phase": 0.0,  "speed":  0.70},
    {"amp":  8.0, "freq": 3,  "phase": 1.20, "speed": -0.90},
    {"amp":  5.0, "freq": 5,  "phase": 2.50, "speed":  1.30},
    {"amp":  3.5, "freq": 7,  "phase": 0.70, "speed": -0.70},
    {"amp":  6.0, "freq": 4,  "phase": 3.10, "speed":  0.50},
    {"amp":  2.0, "freq": 8,  "phase": 1.80, "speed":  1.10},
    {"amp":  4.0, "freq": 6,  "phase": 4.20, "speed": -1.20},
    {"amp":  1.5, "freq": 11, "phase": 0.30, "speed":  1.80},
]

_STATE_COLORS = {
    "LISTENING":    (0,   229, 255),
    "THINKING":     (168,  85, 247),
    "SPEAKING":     (255, 170,   0),
    "IDLE":         (0,    85, 119),
    "MUTED":        (255,  34,  85),
    "INITIALISING": (0,   120, 160),
    "PROCESSING":   (168,  85, 247),
}

_STATE_AMP = {
    "LISTENING": 1.0, "THINKING": 2.8, "SPEAKING": 1.9,
    "IDLE": 0.35, "MUTED": 0.18, "INITIALISING": 0.5, "PROCESSING": 2.5,
}
_STATE_SPEED = {
    "LISTENING": 1.0, "THINKING": 3.2, "SPEAKING": 1.6,
    "IDLE": 0.4, "MUTED": 0.25, "INITIALISING": 0.6, "PROCESSING": 2.8,
}


class JarvisCore(QWidget):
    """Central Arc Reactor with full HUD overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

        self._state   = "INITIALISING"
        self._muted   = False
        self._speaking = False

        self._time = 0.0

        # smooth interpolation state
        self._cr, self._cg, self._cb = 0.0, 242.0, 255.0
        self._tr, self._tg, self._tb = 0.0, 242.0, 255.0
        self._amp_mult   = 0.5
        self._t_amp      = 0.5
        self._speed_mult = 0.6
        self._t_speed    = 0.6

        # Rotation angles for rings
        self._rot_outer = 0.0
        self._rot_mid = 0.0
        self._rot_inner = 0.0

        # pulse rings
        self._pulses: list[float] = [0.0, 45.0, 90.0]

        # blink
        self._blink      = True
        self._blink_tick = 0

        # breathing offset
        self._breath = 0.0

        # 60 fps timer
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def set_state(self, state: str):
        self._state    = state
        self._speaking = (state == "SPEAKING")
        self._muted    = (state == "MUTED")
        rgb = _STATE_COLORS.get(state, (0, 242, 255))
        self._tr, self._tg, self._tb = float(rgb[0]), float(rgb[1]), float(rgb[2])
        self._t_amp   = _STATE_AMP.get(state, 1.0)
        self._t_speed = _STATE_SPEED.get(state, 1.0)

    def _step(self):
        dt = 0.016
        self._time += dt * self._speed_mult

        sp = 0.06
        self._cr += (self._tr - self._cr) * sp
        self._cg += (self._tg - self._cg) * sp
        self._cb += (self._tb - self._cb) * sp

        self._amp_mult   += (self._t_amp   - self._amp_mult)   * 0.04
        self._speed_mult += (self._t_speed - self._speed_mult) * 0.04

        rot_base = 0.8 * self._speed_mult
        self._rot_outer = (self._rot_outer + rot_base * 0.5) % 360
        self._rot_mid = (self._rot_mid - rot_base * 1.2) % 360
        self._rot_inner = (self._rot_inner + rot_base * 2.0) % 360

        self._breath += 0.03 if self._speaking else 0.015

        fw = min(self.width(), self.height())
        lim = fw * 0.40
        p_sp = 3.5 if self._speaking else 1.5
        self._pulses = [r + p_sp for r in self._pulses if r + p_sp < lim]
        rate = 0.06 if self._speaking else 0.02
        if len(self._pulses) < 3 and random.random() < rate:
            self._pulses.append(0.0)

        self._blink_tick += 1
        if self._blink_tick >= 30:
            self._blink = not self._blink
            self._blink_tick = 0

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0
        fw = min(W, H)
        
        cr, cg, cb = int(self._cr), int(self._cg), int(self._cb)
        col_hex = f"#{cr:02x}{cg:02x}{cb:02x}"

        # ── 1. Grid Background ──
        p.setPen(QPen(qcol(C.PRI_GHO, 40), 1))
        for gx in range(0, W, 40):
            for gy in range(0, H, 40):
                p.drawPoint(gx, gy)

        # ── 2. Tactical Text Overlays ──
        p.setFont(QFont(_FONT_DATA, 7))
        p.setPen(QPen(qcol(C.PRI_DIM, 110), 1))
        p.drawText(QRectF(10, 8, 280, 14), Qt.AlignmentFlag.AlignLeft, "100_CONN : A_TEN ALGORITHM")
        p.drawText(QRectF(10, 22, 280, 14), Qt.AlignmentFlag.AlignLeft, "STARK_MODULE : 6 BASE TACFIN")
        p.drawText(QRectF(W - 290, 8, 280, 14), Qt.AlignmentFlag.AlignRight, f"RES_ARM : {W}x{H} MASTER_SYSTEM")
        p.drawText(QRectF(W - 290, 22, 280, 14), Qt.AlignmentFlag.AlignRight, f"STATES: {self._state} // GEN: UPGRADED")

        # ── 3. Corner Brackets ──
        bl = 30
        bc = qcol(col_hex, 160)
        hl, hr = cx - fw // 2 + 10, cx + fw // 2 - 10
        ht, hb = cy - fw // 2 + 10, cy + fw // 2 - 10
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl, ht, 1, 1), (hr, ht, -1, 1), (hl, hb, 1, -1), (hr, hb, -1, -1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # ── Arc Reactor Drawing Logic ──
        p.translate(cx, cy)

        # Ring 1: Outer Segmented HUD Ring
        r_out = fw * 0.42
        p.rotate(self._rot_outer)
        p.setPen(QPen(qcol(col_hex, 90), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0,0), r_out, r_out)
        
        p.setPen(QPen(qcol(col_hex, 180), 4))
        for i in range(0, 360, 30):
            p.drawArc(QRectF(-r_out, -r_out, r_out*2, r_out*2), int(i * 16), int(15 * 16))
            
        # Outer Ticks
        p.setPen(QPen(qcol(col_hex, 140), 1))
        t_in, t_out = r_out + 4, r_out + 12
        for deg in range(0, 360, 5):
            rad = math.radians(deg)
            if deg % 45 == 0:
                p.setPen(QPen(qcol(col_hex, 200), 2))
                t_o = t_out + 4
            else:
                p.setPen(QPen(qcol(col_hex, 100), 1))
                t_o = t_out
            p.drawLine(QPointF(t_in * math.cos(rad), t_in * math.sin(rad)),
                       QPointF(t_o * math.cos(rad), t_o * math.sin(rad)))
        p.rotate(-self._rot_outer)

        # Ring 2: Mid Dashed Data-Stream Ring
        r_mid = fw * 0.35
        p.rotate(self._rot_mid)
        pen_dashed = QPen(qcol(col_hex, 130), 2)
        pen_dashed.setDashPattern([4, 4])
        p.setPen(pen_dashed)
        p.drawEllipse(QPointF(0,0), r_mid, r_mid)
        
        p.setPen(QPen(qcol(C.ACC if self._speaking else col_hex, 200), 3))
        p.drawArc(QRectF(-r_mid, -r_mid, r_mid*2, r_mid*2), 0, int(60 * 16))
        p.drawArc(QRectF(-r_mid, -r_mid, r_mid*2, r_mid*2), int(180 * 16), int(60 * 16))
        p.rotate(-self._rot_mid)

        # Ring 3: Inner Frequency Pulse Ring
        r_in = fw * 0.28 + (math.sin(self._breath * 3.0) * 4 * self._amp_mult)
        p.rotate(self._rot_inner)
        p.setPen(QPen(qcol(col_hex, 160), 3))
        for i in range(0, 360, 15):
            h_len = 6 + (self._amp_mult * 4) if i % 90 != 0 else 12 + (self._amp_mult * 6)
            rad = math.radians(i)
            p.drawLine(QPointF(r_in * math.cos(rad), r_in * math.sin(rad)),
                       QPointF((r_in - h_len) * math.cos(rad), (r_in - h_len) * math.sin(rad)))
        p.rotate(-self._rot_inner)

        # Pulse Rings Emissions
        lim = fw * 0.40  # Maximum radius for pulse rings
        for pr in self._pulses:
            a = max(0, int(150 * (1.0 - pr / lim)))
            p.setPen(QPen(qcol(col_hex, a), 2))
            p.drawEllipse(QPointF(0,0), pr, pr)

        # Ring 4: The Core (Solid Layered Glow)
        r_core = fw * 0.22 + (math.sin(self._breath * 4.0) * 5 * self._amp_mult)
        grad = QRadialGradient(0, 0, r_core)
        grad.setColorAt(0.0, QColor(255, 255, 255, 200))
        grad.setColorAt(0.3, QColor(min(255, cr+80), min(255, cg+80), min(255, cb+80), 180))
        grad.setColorAt(0.7, QColor(cr, cg, cb, 100))
        grad.setColorAt(1.0, QColor(cr, cg, cb, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0,0), r_core, r_core)
        
        # Hard Outline for Core
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(col_hex, 220), 2))
        p.drawEllipse(QPointF(0,0), r_core * 0.8, r_core * 0.8)

        # Centre Label
        p.setPen(QPen(qcol(col_hex, 255), 1))
        p.setFont(QFont(_FONT_HDR, 16, QFont.Weight.Bold))
        p.drawText(QRectF(-80, -12, 160, 24), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")

        p.translate(-cx, -cy)

        # ── 16. status text ──
        sy = cy + fw * 0.45
        if self._muted:
            txt, scol = "⊘  MODULATION: MUTED", qcol(C.MUTED_C)
        elif self._speaking:
            txt, scol = "●  MODULATION: SPEAKING", qcol(C.ACC)
        elif self._state == "THINKING" or self._state == "PROCESSING":
            sym = "◈" if self._blink else "◇"
            txt = f"{sym}  MODULATION: {self._state}"
            scol = qcol(C.VIOLET_B)
        elif self._state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, scol = f"{sym}  MODULATION: LISTENING", qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, scol = f"{sym}  MODULATION: {self._state}", qcol(col_hex)

        p.setPen(QPen(scol, 1))
        p.setFont(QFont(_FONT_DATA, 10, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 22), Qt.AlignmentFlag.AlignCenter, txt)

        # ── 17. waveform bars ──
        wy = sy + 26
        N_bars, bw = 36, 8
        wx0 = (W - N_bars * bw) / 2
        for i in range(N_bars):
            if self._muted:
                hgt, bcol = 2, qcol(C.MUTED_C, 120)
            elif self._speaking:
                hgt = random.randint(3, 22)
                bcol = qcol(col_hex) if hgt > 14 else qcol(col_hex, 140)
            else:
                hgt = int(3 + 2 * math.sin(self._time * 6 + i * 0.6))
                bcol = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 22 - hgt, bw - 1, hgt), bcol)

        # ── 18. bottom readouts ──
        by = H - 22
        p.setFont(QFont(_FONT_DATA, 7))
        p.setPen(QPen(qcol(C.PRI_DIM, 120), 1))
        p.drawText(QRectF(10, by, W // 2, 14), Qt.AlignmentFlag.AlignLeft, f"MXS_ARM : XX MASTER_SYSTEM")
        conn_txt = "CONN_LIVE_GRID: COHERING" if self._state != "MUTED" else "CONN_LIVE_GRID: SUSPENDED"
        p.drawText(QRectF(W // 2, by, W // 2 - 10, 14), Qt.AlignmentFlag.AlignRight, conn_txt)

        p.end()

# ── MetricBar ─────────────────────────────────────────────────────────────────

class MetricBar(QWidget):
    """Ultra-thin neon progress bar with label and value."""

    def __init__(self, label: str, icon: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon  = icon
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self.setFixedHeight(42)
        self.setMinimumWidth(100)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # background
        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER, 80), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        # icon + label
        p.setFont(QFont(_FONT_DATA, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(self._color, 180), 1))
        p.drawText(QRectF(8, 5, 16, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._icon)
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(22, 5, W - 60, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._label)

        # value
        if self._value > 85:
            val_col = qcol(C.RED)
        elif self._value > 65:
            val_col = qcol(C.ACC)
        else:
            val_col = qcol(self._color) if self._text != "--" else qcol(C.TEXT_DIM)

        p.setFont(QFont(_FONT_DATA, 9, QFont.Weight.Bold))
        p.setPen(QPen(val_col, 1))
        p.drawText(QRectF(0, 4, W - 8, 16),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   self._text)

        # segmented bar
        bar_h  = 4
        bar_y  = H - bar_h - 7
        bar_x  = 8
        bar_w  = W - 16
        
        # Draw background track (dim dashed or segmented)
        num_segments = 25
        seg_w = (bar_w / num_segments) - 1.5
        
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(num_segments):
            sx = bar_x + i * (seg_w + 1.5)
            # determine if segment is active based on value
            is_active = (i / num_segments) * 100 <= self._value
            
            if is_active:
                bar_col = (qcol(C.RED) if self._value > 85 else
                           qcol(C.ACC) if self._value > 65 else
                           qcol(self._color))
                p.setBrush(QBrush(bar_col))
                # Add a tiny glow behind active segments
                glow_col = qcol(self._color if self._value <= 65 else
                                (C.ACC if self._value <= 85 else C.RED), 30)
                p.fillRect(QRectF(sx, bar_y - 2, seg_w, bar_h + 4), glow_col)
            else:
                p.setBrush(QBrush(qcol(C.BAR_BG)))
                
            p.drawRect(QRectF(sx, bar_y, seg_w, bar_h))

        p.end()


# ── CoreLoadWidget ────────────────────────────────────────────────────────────

class _CoreLoadWidget(QWidget):
    """Mini per-core CPU bar chart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._cores: list[float] = []

    def set_cores(self, cores: list[float]):
        self._cores = cores
        self.update()

    def paintEvent(self, _):
        if not self._cores:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        n = len(self._cores)
        gap = 2
        bar_w = max(3, (W - (n - 1) * gap) // n)
        total_w = n * bar_w + (n - 1) * gap
        x0 = (W - total_w) // 2

        for i, val in enumerate(self._cores):
            x = x0 + i * (bar_w + gap)
            bar_h = max(2, int((H - 6) * val / 100))
            y = H - bar_h - 3

            # dimmed background
            p.fillRect(QRectF(x, 3, bar_w, H - 6), qcol(C.BAR_BG))

            # filled portion
            if val > 85:
                col = qcol(C.RED)
            elif val > 60:
                col = qcol(C.ACC, 200)
            else:
                col = qcol(C.PRI, 160)
            p.fillRect(QRectF(x, y, bar_w, bar_h), col)

        p.end()


# ── LogWidget ─────────────────────────────────────────────────────────────────

class LogWidget(QTextEdit):
    """Terminal-style scrolling readout with typewriter animation."""
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(_FONT_DATA, 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._queue: list[str] = []
        self._typing = False
        self._text   = ""
        self._pos    = 0
        self._tag    = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        ts = time.strftime("%H:%M:%S")
        stamped = f"[{ts}] {text}"
        self._queue.append(stamped)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   "you:" in tl:           self._tag = "you"
        elif "jarvis:" in tl:        self._tag = "ai"
        elif "file:" in tl:          self._tag = "file"
        elif "err" in tl:            
            self._tag = "err"
            play_sfx("error")
        else:                        self._tag = "sys"
        self._tmr.start(5)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(15, self._next)


# ── File helpers ──────────────────────────────────────────────────────────────

_FILE_ICONS = {
    "image": ("🖼", "#00e5ff"), "video": ("🎬", "#ff8c00"),
    "audio": ("🎵", "#c084fc"), "pdf":   ("📄", "#ff4444"),
    "word":  ("📝", "#4488ff"), "excel": ("📊", "#44bb44"),
    "code":  ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":  ("📊", "#ff6622"), "text":  ("📃", "#aaaaaa"),
    "data":  ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"], "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"], "audio"),
    **dict.fromkeys(["pdf"], "pdf"),
    **dict.fromkeys(["doc","docx"], "word"),
    **dict.fromkeys(["xls","xlsx","ods"], "excel"),
    **dict.fromkeys(["ppt","pptx"], "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"], "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"], "archive"),
    **dict.fromkeys(["txt","md","rst","log"], "text"),
    **dict.fromkeys(["csv","tsv","json","xml"], "data"),
}


def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")


def _fmt_size(size: int) -> str:
    if   size < 1024:      return f"{size} B"
    elif size < 1024 ** 2: return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3: return f"{size / 1024 ** 2:.1f} MB"
    else:                  return f"{size / 1024 ** 3:.1f} GB"


# ── FileDropZone ──────────────────────────────────────────────────────────────

class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(105)
        self._current_file: str | None = None
        self._hovering   = False
        self._drag_over  = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                play_sfx("click")
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            play_sfx("click")
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg = qcol("#001a24" if z._drag_over else
                  ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:
            border_col = qcol(C.GREEN, 200)
        elif z._drag_over:
            border_col = qcol(C.PRI, 230)
        elif z._hovering:
            border_col = qcol(C.BORDER_B, 200)
        else:
            border_col = qcol(C.BORDER, 140)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:
            self._paint_file(p, W, H)
        elif z._drag_over:
            self._paint_drag(p, W, H)
        else:
            self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI if hover else C.PRI_DIM)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # upload arrow
        p.drawLine(QPointF(cx, cy - 16), QPointF(cx, cy + 2))
        p.drawLine(QPointF(cx - 8, cy - 8), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx + 8, cy - 8), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx - 14, cy + 2), QPointF(cx + 14, cy + 2))

        p.setFont(QFont(_FONT_HDR, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT if hover else C.PRI_DIM), 1))
        p.drawText(QRectF(0, cy + 10, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "DROP TACTICAL COMPONENT DATA")
        p.setFont(QFont(_FONT_DATA, 6))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 12), Qt.AlignmentFlag.AlignCenter,
                   "DRAG, DROP OR CLICK TO BROADCAST BINARY")

    def _paint_drag(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont(_FONT_DATA, 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32),
                   Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont(_FONT_DATA, 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, cy + 12, W, 16),
                   Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        try:
            size_str = _fmt_size(path.stat().st_size)
        except Exception:
            size_str = "?"
        ext_str = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 55
        p.setFont(QFont("Segoe UI Emoji", 20) if _OS == "Windows"
                  else QFont("Arial", 20))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H),
                   Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 8
        tw = W - tx - 36

        p.setFont(QFont(_FONT_DATA, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 32 else path.name[:29] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   name)

        p.setFont(QFont(_FONT_DATA, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont(_FONT_DATA, 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 40:
            par = "…" + par[-39:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   par)

        # close button
        p.setFont(QFont(_FONT_DATA, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 32, 0, 26, H),
                   Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 32:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ── SetupOverlay ──────────────────────────────────────────────────────────────

class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 8, 16, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(8)

        def _lbl(txt, size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(_FONT_HDR, size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.",
                              9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont(_FONT_DATA, 10))
        self._key_input.setFixedHeight(34)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS",
                    "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8,
                              color=C.ACC2,
                              align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout()
        os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows", "⊞  Windows"),
                           ("mac", "  macOS"),
                           ("linux", "🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(_FONT_DATA, 9, QFont.Weight.Bold))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(_FONT_HDR, 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(38)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {
            "windows": (C.PRI,   "#001a22"),
            "mac":     (C.ACC2,  "#1a1400"),
            "linux":   (C.GREEN, "#001a0d"),
        }
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 4px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d14; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        color: {C.TEXT}; border: 1px solid {C.BORDER_B};
                    }}
                """)

    def _submit(self):
        play_sfx("click")
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


# ── MainWindow ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)
    _hotkey_mute_sig = pyqtSignal()  # F4 hotkey only (triggers tray popup)
    _mute_ai_sig = pyqtSignal(bool)   # AI voice-command mute toggle (thread-safe)

    def __init__(self, face_path: str):
        super().__init__()
        
        # Initialize Audio
        global _SFX
        if _SFX is None:
            _SFX = SFXManager(self)
            
        self.setWindowTitle("J.A.R.V.I.S — STARK INDUSTRIES")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self.core = JarvisCore()
        self.core.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Expanding)
        body.addWidget(self.core, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # timers
        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        # thread-safe signals
        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._hotkey_mute_sig.connect(self._on_hotkey_mute)
        self._mute_ai_sig.connect(self._on_ai_mute)

        # setup overlay
        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        # shortcuts
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

        if _KEYBOARD_OK:
            try:
                keyboard.add_hotkey('f4',
                                    lambda: self._hotkey_mute_sig.emit())
            except Exception as e:
                print(f"[UI] ⚠️ Global hotkey registration failed: {e}")

        # ── System Tray Icon ──────────────────────────────────────────────
        self._init_tray()

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(
            f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(18, 0, 18, 0)

        # left — STARK brand + Shield Logo
        left_col = QHBoxLayout()
        left_col.setSpacing(12)
        
        self._shield = ShieldLogo(size=42)
        left_col.addWidget(self._shield)
        
        txt_col = QVBoxLayout()
        txt_col.setSpacing(0)
        stark_lbl = QLabel("STARK")
        stark_lbl.setFont(QFont(_FONT_HDR, 14, QFont.Weight.Bold))
        stark_lbl.setStyleSheet(
            f"color: {C.WHITE}; background: transparent; letter-spacing: 5px;"
        )
        txt_col.addWidget(stark_lbl)
        mark_lbl = QLabel("HUD_TACTICAL_V5.1")
        mark_lbl.setFont(QFont(_FONT_DATA, 7))
        mark_lbl.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent;"
        )
        txt_col.addWidget(mark_lbl)
        left_col.addLayout(txt_col)
        lay.addLayout(left_col)

        lay.addStretch()

        # centre — J.A.R.V.I.S.
        mid = QVBoxLayout()
        mid.setSpacing(1)
        title = QLabel("J . A . R . V . I . S")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(_FONT_HDR, 18, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 8px;"
        )
        mid.addWidget(title)
        sub = QLabel("Just A Rather Very Intelligent System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont(_FONT_DATA, 7))
        sub.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent;"
        )
        mid.addWidget(sub)
        lay.addLayout(mid)

        lay.addStretch()

        # right — badges + clock
        right_col = QVBoxLayout()
        right_col.setSpacing(2)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        for txt, col in [("CORE: STABILISED", C.GREEN),
                         ("AI FREQ: 14.2 GHZ", C.ACC2)]:
            b = QLabel(txt)
            b.setFont(QFont(_FONT_DATA, 7, QFont.Weight.Bold))
            b.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 3px;"
                f"padding: 2px 6px;"
            )
            badge_row.addWidget(b)
        right_col.addLayout(badge_row)

        clock_row = QHBoxLayout()
        clock_row.setSpacing(6)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont(_FONT_HDR, 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(
            f"color: {C.WHITE}; background: transparent;"
        )
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_row.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont(_FONT_DATA, 7))
        self._date_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent;"
        )
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_row.addWidget(self._date_lbl)
        right_col.addLayout(clock_row)

        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    # ── left panel — SYS MONITOR ──

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(
            f"background: {C.DARK}; border-right: 1px solid {C.BORDER};"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(5)

        # header row
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("◈ SYS MONITOR")
        hdr_lbl.setFont(QFont(_FONT_HDR, 8, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()
        rt_badge = QLabel("REALTIME")
        rt_badge.setFont(QFont(_FONT_DATA, 6, QFont.Weight.Bold))
        rt_badge.setStyleSheet(
            f"color: {C.GREEN}; background: {C.PANEL2};"
            f"border: 1px solid {C.GREEN_D}; border-radius: 2px;"
            f"padding: 1px 4px;"
        )
        hdr_row.addWidget(rt_badge)
        lay.addLayout(hdr_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(2)

        # metric bars
        self._bar_cpu = MetricBar("CPU UTILIZATION",  "⚡", C.PRI)
        self._bar_mem = MetricBar("RAM ALLOCATION",   "⟐",  C.ACC2)
        self._bar_net = MetricBar("NET THROUGHPUT",    "↗",  C.GREEN)
        self._bar_gpu = MetricBar("SYNTHS: GPU",      "♦",  C.ACC)
        self._bar_tmp = MetricBar("THERMALS: CORE",   "△",  "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        # core load drift header
        drift_row = QHBoxLayout()
        drift_lbl = QLabel("CORE LOAD DRIFT")
        drift_lbl.setFont(QFont(_FONT_DATA, 7, QFont.Weight.Bold))
        drift_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent;"
        )
        drift_row.addWidget(drift_lbl)
        drift_row.addStretch()
        track_lbl = QLabel("+ TRACKING")
        track_lbl.setFont(QFont(_FONT_DATA, 6))
        track_lbl.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent;"
        )
        drift_row.addWidget(track_lbl)
        lay.addLayout(drift_row)

        # core load bars
        self._core_widget = _CoreLoadWidget()
        lay.addWidget(self._core_widget)

        lay.addSpacing(4)

        # system info
        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER};"
            f"border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(8, 6, 8, 6)
        ip_lay.setSpacing(4)

        self._uptime_lbl = self._info_row(ip_lay, "UPTIME", "--:--", C.GREEN)
        self._proc_lbl   = self._info_row(ip_lay, "ACTIVE_PROC", "--", C.TEXT_MED)
        self._sysmod_lbl = self._info_row(ip_lay, "SYSTEM_MODEL", "J.A.V.I.7", C.ACC2)
        self._kernel_lbl = self._info_row(ip_lay, "KERNEL", "STARK_OS_V.2", C.PRI_DIM)

        lay.addWidget(info_panel)

        lay.addStretch()

        # status indicators
        for txt, col in [("AI CORE\nACTIVE",   C.GREEN),
                         ("SEC\nCLEARED",       C.PRI),
                         ("PROTOCOL\nSTARK",    C.TEXT_DIM)]:
            lbl = QLabel(txt)
            lbl.setFont(QFont(_FONT_DATA, 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 3px;"
                f"padding: 4px;"
            )
            lay.addWidget(lbl)

        return w

    def _info_row(self, parent_lay, label: str, value: str,
                  color: str) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(4)
        l = QLabel(label)
        l.setFont(QFont(_FONT_DATA, 7))
        l.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        row.addWidget(l)
        row.addStretch()
        v = QLabel(value)
        v.setFont(QFont(_FONT_DATA, 8, QFont.Weight.Bold))
        v.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        row.addWidget(v)
        parent_lay.addLayout(row)
        return v

    # ── right panel ──

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(
            f"background: {C.DARK}; border-left: 1px solid {C.BORDER};"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        # ACTIVITY LOG header
        log_hdr = QHBoxLayout()
        log_lbl = QLabel("◈ ACTIVITY LOG")
        log_lbl.setFont(QFont(_FONT_HDR, 8, QFont.Weight.Bold))
        log_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        log_hdr.addWidget(log_lbl)
        log_hdr.addStretch()
        audit_badge = QLabel("AUDIT_STREAM")
        audit_badge.setFont(QFont(_FONT_DATA, 6, QFont.Weight.Bold))
        audit_badge.setStyleSheet(
            f"color: {C.ACC2}; background: {C.PANEL2};"
            f"border: 1px solid {C.BORDER_A}; border-radius: 2px;"
            f"padding: 1px 4px;"
        )
        log_hdr.addWidget(audit_badge)
        lay.addLayout(log_hdr)

        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(sep)

        # stream info row
        stream_row = QHBoxLayout()
        stream_lbl = QLabel("STARK_OS: A_FREQ")
        stream_lbl.setFont(QFont(_FONT_DATA, 6))
        stream_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent;"
        )
        stream_row.addWidget(stream_lbl)
        stream_row.addStretch()
        core_link = QLabel("● CORE_LINK_ONLINE")
        core_link.setFont(QFont(_FONT_DATA, 6, QFont.Weight.Bold))
        core_link.setStyleSheet(
            f"color: {C.GREEN}; background: transparent;"
        )
        stream_row.addWidget(core_link)
        lay.addLayout(stream_row)

        lay.addSpacing(4)

        # FILE FEED UPLOAD
        file_hdr = QHBoxLayout()
        file_lbl = QLabel("◈ FILE FEED UPLOAD")
        file_lbl.setFont(QFont(_FONT_HDR, 8, QFont.Weight.Bold))
        file_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        file_hdr.addWidget(file_lbl)
        lay.addLayout(file_hdr)

        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        lay.addSpacing(4)

        # COMMAND INPUT
        cmd_lbl = QLabel("◈ COMMAND INPUT")
        cmd_lbl.setFont(QFont(_FONT_HDR, 8, QFont.Weight.Bold))
        cmd_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(cmd_lbl)
        lay.addLayout(self._build_input_row())

        # Mute button
        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont(_FONT_DATA, 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        # Fullscreen
        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont(_FONT_DATA, 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type tactical directive…")
        self._input.setFont(QFont(_FONT_DATA, 9))
        self._input.setFixedHeight(32)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 3px 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: #001018;
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(32, 32)
        send.setFont(QFont(_FONT_HDR, 12, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    # ── footer ──

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(24)
        w.setStyleSheet(
            f"background: {C.DARK}; border-top: 1px solid {C.BORDER};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _fl(txt, color=C.TEXT_DIM):
            l = QLabel(txt)
            l.setFont(QFont(_FONT_DATA, 7))
            l.setStyleSheet(
                f"color: {color}; background: transparent;"
            )
            return l

        lay.addWidget(_fl("REPORT PROTOCOL ENGAGED // LVL:STARK S7"))
        lay.addStretch()
        lay.addWidget(_fl("OPERATOR: SHARDA VATSAL BHAT", C.TEXT_MED))
        lay.addStretch()
        lay.addWidget(_fl("STARK_OS_V.2  ·  SVB", C.PRI_DIM))
        return w

    # ── metric updates ──

    def _update_metrics(self):
        snap = _metrics.snapshot()

        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        net = snap["net"]
        net_str = (f"{net * 1024:.0f} KB/s" if net < 1.0
                   else f"{net:.1f} MB/s")
        self._bar_net.set_value(min(100, net * 10), net_str)

        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        tmp = snap["tmp"]
        if tmp >= 0:
            self._bar_tmp.set_value(min(100, tmp), f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        # core load drift
        cores = snap.get("cores", [])
        if cores:
            self._core_widget.set_cores(cores)

        # system info
        try:
            elapsed = time.time() - psutil.boot_time()
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._uptime_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
        except Exception:
            self._uptime_lbl.setText("--:--")

        try:
            self._proc_lbl.setText(str(len(psutil.pids())))
        except Exception:
            self._proc_lbl.setText("--")

    # ── event handlers ──

    def _toggle_fullscreen(self):
        play_sfx("click")
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 480, 400
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _on_file_selected(self, path: str):
        self._current_file = path
        pth  = Path(path)
        cat  = _file_category(pth)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        try:
            size = _fmt_size(pth.stat().st_size)
        except Exception:
            size = "?"
        self._log.append_log(
            f"FILE: {icon} {pth.name} ({size}) loaded"
        )
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={pth.name} | "
                f"type={pth.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{pth.name}' "
                f"({size}) has been uploaded and ask what they'd like to "
                f"do with it."
            )
            threading.Thread(target=self.on_text_command,
                             args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        play_sfx("click")
        self._muted = not self._muted
        self._style_mute_btn()
        # Keep tray menu text in sync
        if hasattr(self, '_tray_mute_action'):
            self._tray_mute_action.setText(
                "🔇  Unmute" if self._muted else "🎙  Mute"
            )
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140008; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 4px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001408; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 4px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    # ── System tray ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Minimize to tray instead of closing the application."""
        event.ignore()
        self.hide()
        self._tray_icon.showMessage(
            "J.A.R.V.I.S",
            "Still running in the background, sir.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _init_tray(self):
        """Create the system tray icon with a glowing orb icon and context menu."""
        # Generate a glowing STARK orb icon programmatically (64x64)
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QRadialGradient(32, 32, 28)
        grad.setColorAt(0.0, QColor(0, 242, 255, 220))
        grad.setColorAt(0.6, QColor(0, 180, 220, 160))
        grad.setColorAt(1.0, QColor(0, 80, 130, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(0, 242, 255, 200), 2))
        painter.drawEllipse(QPointF(32, 32), 26, 26)
        painter.setPen(QPen(QColor(0, 242, 255, 120), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(32, 32), 18, 18)
        painter.setFont(QFont(_FONT_HDR, 18, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(0, 242, 255, 240), 1))
        painter.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "J")
        painter.end()

        self._tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self._tray_icon.setToolTip("J.A.R.V.I.S — STARK INDUSTRIES")

        # Build context menu
        tray_menu = QMenu()

        self._tray_show_action = QAction("Show Window")
        self._tray_show_action.triggered.connect(self._show_from_tray)
        tray_menu.addAction(self._tray_show_action)

        tray_menu.addSeparator()

        self._tray_mute_action = QAction("🎙  Mute")
        self._tray_mute_action.triggered.connect(self._toggle_mute)
        tray_menu.addAction(self._tray_mute_action)

        tray_menu.addSeparator()

        quit_action = QAction("⏻  Quit JARVIS")
        quit_action.triggered.connect(self._quit_from_tray)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _show_from_tray(self):
        """Restore and focus the main window."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        """Restore window on double-click."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _quit_from_tray(self):
        """Actually quit — hide tray icon and exit event loop."""
        self._tray_icon.hide()
        QApplication.quit()

    def _on_hotkey_mute(self):
        """Called by F4 global hotkey. Toggles mute and shows tray notification."""
        self._toggle_mute()
        if hasattr(self, '_tray_icon'):
            if self._muted:
                msg = "Microphone muted. Press F4 to unmute."
            else:
                msg = "Microphone active. Press F4 to mute."
            self._tray_icon.showMessage(
                "J.A.R.V.I.S — STARK INDUSTRIES",
                msg,
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _on_ai_mute(self, muted: bool):
        """Called by AI voice command. Sets mute state directly (thread-safe via signal)."""
        if muted == self._muted:
            return  # already in requested state
        self._muted = muted
        self._style_mute_btn()
        # Keep tray menu text in sync
        if hasattr(self, '_tray_mute_action'):
            self._tray_mute_action.setText(
                "🔇  Unmute" if muted else "🎙  Mute"
            )
        state = "MUTED" if muted else "LISTENING"
        self._apply_state(state)
        self._log.append_log(f"SYS: Microphone {'muted' if muted else 'active'} (AI command).")
        # Show tray notification so user knows the command worked
        if hasattr(self, '_tray_icon'):
            msg = "Microphone muted by your command, sir." if muted else "Microphone active again, sir."
            self._tray_icon.showMessage(
                "J.A.R.V.I.S",
                msg,
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command,
                             args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.core.set_state(state)

    def _check_config(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 480, 400
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name},
                       indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(
            f"SYS: Initialised. OS={os_name.upper()}. JARVIS online."
        )


# ── JarvisUI — Public API (compatible with main.py) ──────────────────────────

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(self, *_):
        pass


class JarvisUI:
    """
    Public API consumed by main.py.

    Methods / properties preserved:
        __init__(face_path, size)
        set_state(state)
        write_log(text)
        wait_for_api_key()
        muted          (property r/w)
        current_file   (property r)
        on_text_command (property r/w)
        root.mainloop()
        start_speaking()
        stop_speaking()
    """

    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        _init_fonts()
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    # ── properties ──

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    # ── methods ──

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)
        play_sfx("startup")

    def set_mute(self, muted: bool):
        """Thread-safe mute/unmute from AI tool calls. Emits signal to main thread."""
        self._win._mute_ai_sig.emit(muted)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def confirm_action(self, tool_name: str, args: dict) -> bool:
        """
        Thread-safe confirmation dialog for high-risk actions.
        Returns True if confirmed, False otherwise.
        """
        # ponytail: simple blocking confirmation for security
        from PyQt6.QtWidgets import QMessageBox
        
        # We must use a thread-safe way to show the dialog
        # For simplicity, we use a signal-slot pattern or just run on main thread
        result = [False]
        event = threading.Event()

        def _show():
            msg = f"SECURITY ALERT: JARVIS is requesting to perform a high-risk action:\n\n"
            msg += f"Tool: {tool_name}\n"
            msg += f"Arguments: {json.dumps(args, indent=2)}\n\n"
            msg += "Do you allow this action, sir?"
            
            box = QMessageBox(self._win)
            box.setWindowTitle("🛡️ STARK SECURITY PROTOCOL")
            box.setText(msg)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            box.setIcon(QMessageBox.Icon.Warning)
            
            # Apply some Stark styling to the message box
            box.setStyleSheet(f"background-color: #0A0F1E; color: white; font-family: '{_FONT_DATA}';")
            
            ret = box.exec()
            result[0] = (ret == QMessageBox.StandardButton.Yes)
            event.set()

        # Execute on main thread
        QTimer.singleShot(0, _show)
        event.wait()
        return result[0]
