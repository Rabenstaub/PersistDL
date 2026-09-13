# -*- coding: utf-8 -*-
"""
PersistDL – Download-Manager mit lückenloser Fortsetzung
Version 1.8.0

Merkt sich bei jedem Abbruch (Netzfehler, Pause, Programmende) die exakte
Byte-Position und setzt den Download später per HTTP-Range-Request fort –
egal ob nach Sekunden oder Tagen.

Copyright (c) 2026 Christian ("Rabenstaub"). Alle Rechte vorbehalten,
siehe LICENSE.md fuer die Nutzungsbedingungen.
"""

import json
import os
import sys
import time
import re
import traceback
import subprocess
import shutil
import threading
from pathlib import Path
from urllib.parse import (urlparse, unquote, parse_qs, urlencode, urlunparse)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- App-Ordner
# In einer per PyInstaller gebauten .exe zeigt __file__ auf einen fluechtigen
# Temp-Entpackordner (_MEIPASS), nicht auf den Ordner, in dem die .exe
# tatsaechlich liegt - "neben der .exe" abgelegte Dateien (Fehlerlog,
# lang/-Ordner) wuerden sonst nach jedem Programmende verschwinden bzw. gar
# nicht gefunden. sys.frozen ist die von PyInstaller gesetzte Kennung dafuer.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

# ---------------------------------------------------------------- Crash-Log
# pythonw hat keine Konsole – jeder Fehler beim Start wäre unsichtbar.
# Deshalb: Fehler in Logdatei schreiben UND als Windows-Dialog anzeigen.
LOG_PATH = APP_DIR / "persistdl_error.log"

# ---------------------------------------------------------------- Sprache
# Alle sichtbaren Texte liegen in lang/<code>.json - jeder kann sich eine
# eigene Datei anlegen (z.B. lang/fr.json, Kopie von en.json), ohne den
# Python-Code anzufassen. Bewusst KEINE komplizierte i18n-Bibliothek,
# nur einfache Schluessel -> Text (bzw. -> Liste bei den Tabellen-
# ueberschriften), mit "{platzhalter}".format(...) fuer eingesetzte Werte.
# Standardsprache ist bewusst fest Englisch (keine Windows-Spracherkennung -
# die war unzuverlaessig/ueberraschend) - wer Deutsch will, waehlt es im
# "Sprache:"-Dropdown, das merkt sich die Wahl dauerhaft.
LANG_DIR = APP_DIR / "lang"
LANG = {}
DEFAULT_LANGUAGE = "en"


def load_language(code):
    try:
        return json.loads((LANG_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def init_language(code):
    """Laedt die gewaehlte Sprachdatei; fehlt sie oder ist sie kaputt,
    faellt es auf Englisch zurueck, notfalls auf den nackten Schluessel
    (App bleibt so auch ohne lang/-Ordner benutzbar, nur unschoen)."""
    global LANG
    data = load_language(code)
    if not data and code != "en":
        data = load_language("en")
    LANG = data


def T(key, **kwargs):
    text = LANG.get(key, key)
    if isinstance(text, str) and kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def TN(key_one, key_other, n, **kwargs):
    """Waehlt automatisch die Singular- oder Pluralform je nach n (in
    beiden Sprachdateien einfach: n==1 -> _one, sonst -> _other)."""
    return T(key_one if n == 1 else key_other, n=n, **kwargs)


init_language(DEFAULT_LANGUAGE)


def _fatal(msg):
    try:
        LOG_PATH.write_text(msg, encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, msg[:1500], T("err.start_title"), 0x10)
    except Exception:
        print(msg, file=sys.stderr)
    sys.exit(1)


try:
    import requests
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QByteArray, QObject
    from PyQt6.QtGui import QFont, QAction, QColor, QShortcut, QKeySequence
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLineEdit, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
        QProgressBar, QFileDialog, QMessageBox, QHeaderView, QCheckBox,
        QSpinBox, QMenu, QComboBox
    )
except ImportError:
    _fatal(T("err.missing_package", traceback=traceback.format_exc(),
             python=sys.executable))


def _excepthook(etype, value, tb):
    msg = "".join(traceback.format_exception(etype, value, tb))
    try:
        LOG_PATH.write_text(msg, encoding="utf-8")
    except Exception:
        pass
    try:
        QMessageBox.critical(None, T("err.crash_title"),
                             T("err.crash_body", log=LOG_PATH.name,
                               msg=msg[:1200]))
    except Exception:
        pass


sys.excepthook = _excepthook

VERSION = "1.8.0"
CONFIG_PATH = Path.home() / ".persistdl_settings.json"
_OLD_CONFIG_PATH = Path.home() / ".weiterlader_settings.json"  # Umbenennung von WeiterLader

# Lokaler Port, auf dem der Browser-Catcher lauscht. Die Chrome-Erweiterung
# schickt abgefangene Download-Links an http://127.0.0.1:<PORT>/add
DEFAULT_CATCH_PORT = 47800

# ---------------------------------------------------------------- Theme
BG = "#eceae5"
ACCENT = "#5558a0"
TEXT = "#2b2b33"

STYLE = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}
QLineEdit {{
    background: #ffffff; border: 1px solid #c9c6bd; border-radius: 4px;
    padding: 6px 8px; selection-background-color: {ACCENT};
}}
QPushButton {{
    background: {ACCENT}; color: #ffffff; border: none; border-radius: 4px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #6a6db8; }}
QPushButton:disabled {{ background: #b6b4c6; }}
QPushButton#secondary {{
    background: #dedbd2; color: {TEXT};
}}
QPushButton#secondary:hover {{ background: #d2cfc4; }}
QPushButton[stateColor="off"] {{ background: #dedbd2; color: {TEXT}; }}
QPushButton[stateColor="off"]:hover {{ background: #d2cfc4; }}
QPushButton[stateColor="green"] {{ background: #3f8f4a; color: #ffffff; }}
QPushButton[stateColor="green"]:hover {{ background: #4da35a; }}
QPushButton[stateColor="red"] {{ background: #b3261e; color: #ffffff; }}
QPushButton[stateColor="red"]:hover {{ background: #c74038; }}
QTableWidget {{
    background: #f7f6f2; alternate-background-color: #efede7;
    border: 1px solid #c9c6bd; border-radius: 4px; gridline-color: #dedbd2;
}}
QHeaderView::section {{
    background: #dedbd2; color: {TEXT}; border: none; padding: 6px;
    font-weight: 600;
}}
QCheckBox {{ spacing: 6px; }}
QSpinBox {{
    background: #ffffff; border: 1px solid #c9c6bd; border-radius: 4px;
    padding: 3px 6px;
}}
QLabel#hint {{ color: #6f6d66; }}
"""

CHUNK = 256 * 1024  # 256 KB


def human_size(n):
    if n is None or n < 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def human_speed(bps):
    return human_size(bps) + "/s" if bps else "–"


def human_eta(sec):
    if sec is None or sec <= 0 or sec > 30 * 86400:
        return "–"
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def filename_from_response(url, resp):
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
    if not m:
        m = re.search(r'filename="?([^";]+)"?', cd, re.I)
    if m:
        return unquote(m.group(1)).strip()
    name = os.path.basename(urlparse(url).path)
    return unquote(name) if name else "download.bin"


def is_civitai_download(url):
    try:
        pu = urlparse(url)
        host = pu.netloc.lower()
        # civitai.com plus Mirrors (civitai.red / civitai.green)
        return (any(host == d or host.endswith("." + d)
                    for d in ("civitai.com", "civitai.red", "civitai.green"))
                and "/api/download/" in pu.path)
    except Exception:
        return False


def apply_civitai_auth(url, token):
    """Hängt bei Civitai-Download-Links den API-Token an die URL (?token=…)
    und liefert zusätzlich einen passenden Authorization-Header.
    Andere URLs bleiben unverändert. Rückgabe: (url, headers)."""
    headers = {}
    if not token or not is_civitai_download(url):
        return url, headers
    try:
        pu = urlparse(url)
        q = parse_qs(pu.query, keep_blank_values=True)
        if "token" not in q:
            q["token"] = [token]
        flat = {k: (v[0] if isinstance(v, list) else v) for k, v in q.items()}
        url = urlunparse(pu._replace(query=urlencode(flat)))
        headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass
    return url, headers


# ---------------------------------------------------------------- Worker
class DownloadWorker(QThread):
    """Lädt eine Datei mit Range-Fortsetzung. Bei Netzfehlern wird
    automatisch neu verbunden und ab der letzten Byte-Position weitergemacht."""

    # float statt int: pyqtSignal(int) ist 32-bittig -> Dateien > 2 GB
    # kamen als negative Zahl an (Groesse '?', Balken unbestimmt).
    sig_progress = pyqtSignal(float, float, float, float)  # downloaded, total, speed, eta
    sig_status = pyqtSignal(str)                        # Statustext
    sig_done = pyqtSignal(str)                          # fertiger Dateipfad
    sig_failed = pyqtSignal(str)                        # Fehlermeldung
    sig_meta = pyqtSignal(str, float)                   # Dateiname, Gesamtgröße

    def __init__(self, url, folder, auto_retry=True, retry_wait=10,
                 max_retries=0, civitai_token="", parent=None):
        super().__init__(parent)
        self.url = url                    # Original-URL (für Anzeige/Merkzettel)
        self.civitai_token = civitai_token
        # URL fürs eigentliche Laden – bei Civitai mit angehängtem Token.
        self.dl_url, self._auth_headers = apply_civitai_auth(url, civitai_token)
        self.folder = Path(folder)
        self.auto_retry = auto_retry
        self.retry_wait = retry_wait
        self.max_retries = max_retries  # 0 = unbegrenzt
        self._pause = False
        self._cancel = False

    def pause(self):
        self._pause = True

    def cancel(self):
        self._cancel = True
        self._pause = True

    # ---------- Metadaten (merken sich den Stand über Neustarts hinweg)
    def _meta_path(self, target: Path) -> Path:
        return target.with_name(target.name + ".persistdl.json")

    def _old_meta_path(self, target: Path) -> Path:
        # Umbenennung von WeiterLader: alte Merkzettel weiter lesbar machen.
        return target.with_name(target.name + ".weiterlader.json")

    def _load_meta(self, target: Path):
        for p in (self._meta_path(target), self._old_meta_path(target)):
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {}

    def _save_meta(self, target: Path, meta: dict):
        try:
            self._meta_path(target).write_text(
                json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass

    def run(self):
        session = requests.Session()
        session.headers["User-Agent"] = f"PersistDL/{VERSION}"
        if self._auth_headers:
            session.headers.update(self._auth_headers)
        attempt = 0

        # 1) Server abfragen: Größe, Dateiname, Range-Unterstützung, ETag
        try:
            head = session.get(self.dl_url, stream=True, timeout=(10, 30),
                               allow_redirects=True)
            head.raise_for_status()
            # Civitai liefert ohne gültigen Token eine HTML-Login-Seite
            # (Status 200) statt der Datei – das früh und klar melden.
            ctype = head.headers.get("Content-Type", "").lower()
            if is_civitai_download(self.url) and "text/html" in ctype:
                head.close()
                self.sig_failed.emit(T("worker.civitai_html"))
                return
            filename = filename_from_response(self.url, head)
            total = int(head.headers.get("Content-Length", -1))
            accept_ranges = "bytes" in head.headers.get("Accept-Ranges", "").lower()
            etag = head.headers.get("ETag", "")
            last_mod = head.headers.get("Last-Modified", "")
            head.close()
        except Exception as e:
            hint = ""
            if is_civitai_download(self.url) and not self.civitai_token:
                hint = T("worker.civitai_hint")
            self.sig_failed.emit(
                T("worker.server_unreachable", error=e, hint=hint))
            return

        target = self.folder / filename
        part = target.with_name(target.name + ".part")
        self.sig_meta.emit(filename, total)

        # Metadaten prüfen: hat sich die Datei auf dem Server geändert?
        meta = self._load_meta(target)
        if part.exists() and meta:
            if (etag and meta.get("etag") and etag != meta["etag"]) or \
               (last_mod and meta.get("last_modified") and last_mod != meta["last_modified"]):
                self.sig_status.emit(T("worker.file_changed"))
                part.unlink(missing_ok=True)

        self._save_meta(target, {
            "url": self.url, "etag": etag, "last_modified": last_mod,
            "total": total,
        })

        while not self._cancel:
            downloaded = part.stat().st_size if part.exists() else 0

            if total > 0 and downloaded >= total:
                break  # bereits vollständig

            headers = {}
            mode = "wb"
            if downloaded > 0 and accept_ranges:
                headers["Range"] = f"bytes={downloaded}-"
                mode = "ab"
                self.sig_status.emit(
                    T("worker.resuming_at", size=human_size(downloaded)))
            elif downloaded > 0 and not accept_ranges:
                self.sig_status.emit(T("worker.no_range_support"))
                downloaded = 0

            try:
                resp = session.get(self.dl_url, stream=True, headers=headers,
                                   timeout=(10, 30))
                if headers and resp.status_code == 200:
                    # Server ignoriert Range → von vorn
                    downloaded = 0
                    mode = "wb"
                resp.raise_for_status()

                t0 = time.time()
                bytes_window = 0
                last_emit = 0.0

                with open(part, mode) as f:
                    for chunk in resp.iter_content(CHUNK):
                        if self._pause or self._cancel:
                            resp.close()
                            if self._cancel:
                                self.sig_status.emit(T("worker.cancelled"))
                            else:
                                self.sig_status.emit(T(
                                    "worker.paused_at",
                                    size=human_size(part.stat().st_size)))
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            bytes_window += len(chunk)
                            now = time.time()
                            if now - last_emit >= 0.4:
                                dt = max(now - t0, 0.001)
                                speed = bytes_window / dt
                                eta = ((total - downloaded) / speed) if (total > 0 and speed > 0) else -1
                                self.sig_progress.emit(downloaded, total, speed, eta)
                                last_emit = now
                                if dt > 5:  # Geschwindigkeitsfenster zurücksetzen
                                    t0, bytes_window = now, 0
                resp.close()

                if total > 0 and downloaded < total:
                    raise IOError(T("worker.connection_ended_early"))
                break  # fertig

            except Exception as e:
                attempt += 1
                if not self.auto_retry or (self.max_retries and attempt > self.max_retries):
                    self.sig_failed.emit(T(
                        "worker.error_saved_at", error=e,
                        size=human_size(
                            part.stat().st_size if part.exists() else 0)))
                    return
                for s in range(self.retry_wait, 0, -1):
                    if self._pause or self._cancel:
                        return
                    self.sig_status.emit(T(
                        "worker.retry_in", error_type=e.__class__.__name__,
                        seconds=s, attempt=attempt))
                    time.sleep(1)

        if self._cancel:
            return

        # 2) Fertig: .part umbenennen, Metadaten löschen
        try:
            if target.exists():
                stem, suffix = target.stem, target.suffix
                i = 1
                while target.exists():
                    target = self.folder / f"{stem} ({i}){suffix}"
                    i += 1
            part.rename(target)
            self._meta_path(self.folder / filename).unlink(missing_ok=True)
        except Exception as e:
            self.sig_failed.emit(T("worker.finalize_failed", error=e))
            return

        self.sig_done.emit(str(target))


# ---------------------------------------------------------------- Shutdown
class BigTextProgressBar(QProgressBar):
    """Fortschrittsbalken mit großer, fetter Prozentanzeige.
    Die Schrift ist zweifarbig: dunkel auf dem ungefüllten Teil,
    weiß auf dem blauen Balken – wechselt exakt an der Balkenkante."""

    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = 4

        # Hintergrund
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#dedbd2"))
        p.drawRoundedRect(rect, radius, radius)

        # Füllstand berechnen
        if self.maximum() > self.minimum():
            frac = ((self.value() - self.minimum()) /
                    (self.maximum() - self.minimum()))
            indeterminate = False
        else:
            frac, indeterminate = 1.0, True
        chunk_w = int(rect.width() * frac)

        # Balken
        if chunk_w > 0:
            p.setBrush(QColor("#8a8dc4" if indeterminate else ACCENT))
            p.save()
            p.setClipRect(0, 0, chunk_w, rect.height())
            p.drawRoundedRect(rect, radius, radius)
            p.restore()

        # Text bestimmen
        if indeterminate:
            text = T("progress.indeterminate")
        else:
            fmt = self.format()
            if "%p" in fmt:
                text = fmt.replace("%p", f"{frac * 100:.0f}")
            else:
                text = fmt

        # Große, fette Schrift – von der App-Schrift abgeleitet.
        # Wichtig: NICHT p.font() verwenden; Stylesheet-Schriften in
        # Pixeln liefern pointSize() == -1 und ergaben 1-Punkt-Text.
        font = QApplication.instance().font()
        size = font.pointSize()
        if size <= 0:
            size = 10
        font.setPointSize(max(size + 2, 12))
        font.setBold(True)
        p.setFont(font)

        # Dunkler Text auf dem ungefüllten Teil …
        p.save()
        p.setClipRect(chunk_w, 0, rect.width() - chunk_w, rect.height())
        p.setPen(QColor(TEXT))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        p.restore()
        # … weißer Text auf dem Balken
        if chunk_w > 0:
            p.save()
            p.setClipRect(0, 0, chunk_w, rect.height())
            p.setPen(QColor("#ffffff"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            p.restore()
        p.end()


class ShutdownDialog(QMessageBox):
    """60-Sekunden-Countdown vor erzwungenem Herunterfahren.
    Der shutdown-Befehl ist bereits abgesetzt; 'Abbrechen' ruft
    'shutdown /a' auf und stoppt ihn wieder."""

    def __init__(self, seconds=60, parent=None):
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Warning)
        self.setWindowTitle(T("shutdown.title"))
        # Immer ueber allen Fenstern bleiben
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.abort_btn = self.addButton(
            T("shutdown.abort_button"), QMessageBox.ButtonRole.RejectRole)
        self.seconds = seconds
        self._tick()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _alert_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            QApplication.beep()

    def _tick(self):
        self.setText(T("shutdown.countdown_text", seconds=self.seconds))
        # Piepton: erste 10 Sekunden jede Sekunde, danach alle 10 Sekunden
        if self.seconds > 50 or self.seconds % 10 == 0:
            self._alert_sound()
        # Sich immer wieder nach vorn holen, falls etwas darueber liegt
        self.raise_()
        self.activateWindow()
        self.seconds -= 1
        if self.seconds < 0:
            self.timer.stop()
            self.accept()


# ---------------------------------------------------------------- Catcher
class CatcherBridge(QObject):
    """Brücke vom HTTP-Server-Thread in den Qt-GUI-Thread. pyqtSignal wird
    thread-sicher (queued) in den Hauptthread zugestellt."""
    sig_url = pyqtSignal(str)


def make_catch_handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/ping"):
                self._json(200, {"ok": True, "app": "PersistDL",
                                 "version": VERSION})
            else:
                self._json(404, {"ok": False})

        def do_POST(self):
            if not self.path.startswith("/add"):
                self._json(404, {"ok": False})
                return
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length else b""
            url = ""
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
                url = (data.get("url") or "").strip()
            except Exception:
                url = ""
            if url.lower().startswith(("http://", "https://")):
                bridge.sig_url.emit(url)
                self._json(200, {"ok": True})
            else:
                self._json(400, {"ok": False, "error": T("catcher.invalid_url")})

        def log_message(self, *args):
            pass  # keine Konsolenausgabe (pythonw hat keine Konsole)

    return Handler


class CatcherServer:
    """Startet/stoppt den lokalen HTTP-Listener in einem Daemon-Thread."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.httpd = None
        self.thread = None
        self.port = None

    @property
    def running(self):
        return self.httpd is not None

    def start(self, port):
        self.stop()
        # Nur an 127.0.0.1 binden – von außen nicht erreichbar.
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", int(port)), make_catch_handler(self.bridge))
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = int(port)

    def stop(self):
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        self.thread = None
        self.port = None


class MainWindow(QMainWindow):
    (COL_NAME, COL_FOLDER, COL_SIZE, COL_PROGRESS,
     COL_SPEED, COL_ETA, COL_STATUS, COL_OPEN) = range(8)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PersistDL v{VERSION}")
        self.setMinimumSize(480, 320)
        self.resize(1100, 480)  # Fallback, falls _restore_geometry() unten
                                 # aus irgendeinem Grund nichts setzen kann.
                                 # Breiter als frueher (920) - die Options-
                                 # zeile lief bei laengeren (v.a. englischen)
                                 # Texten sonst rechts aus dem Fenster.
        self.workers = {}   # row -> worker
        self.rows = []      # row -> dict(url, folder, filename, done)

        self.cfg = self._load_cfg()
        self.font_size = self.cfg.get("font_size", 10)
        self.lang_code = self.cfg.get("language") or DEFAULT_LANGUAGE
        init_language(self.lang_code)

        # Browser-Catcher (lokaler HTTP-Server) vorbereiten
        self._catch_bridge = CatcherBridge()
        self._catch_bridge.sig_url.connect(self._on_intercepted)
        self._catch_server = CatcherServer(self._catch_bridge)

        self._build_ui()
        self._apply_font()
        self._restore_downloads()
        self._restore_geometry()

        # Catcher automatisch starten, wenn beim letzten Mal aktiv
        if self.cfg.get("catch_enabled", False):
            self.chk_catch.setChecked(True)  # löst _toggle_catch aus

    # ---------- Fenstergroesse/-position (ueber Neustarts hinweg, immer auf
    # den aktuell verfuegbaren Bildschirm eingepasst)
    def _restore_geometry(self):
        geo_b64 = self.cfg.get("window_geometry")
        restored = False
        if geo_b64:
            try:
                ba = QByteArray.fromBase64(geo_b64.encode("ascii"))
                restored = bool(ba) and self.restoreGeometry(ba)
            except Exception:
                restored = False
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if not restored and avail:
            # Erststart (oder kaputter Wert): Startgroesse, aber nie groesser
            # als der tatsaechlich verfuegbare Bildschirmbereich - genau das
            # hat vorher auf kleinen Monitoren ueber den Rand geragt.
            w = max(480, min(1100, avail.width() - 40))
            h = max(320, min(480, avail.height() - 40))
            self.resize(w, h)
        if avail:
            # Egal ob wiederhergestellt oder Default: auf den sichtbaren
            # Bereich zwingen (faengt auch einen zwischenzeitlichen
            # Monitorwechsel/kleineren Bildschirm ab).
            geo = self.frameGeometry()
            w = min(geo.width(), avail.width())
            h = min(geo.height(), avail.height())
            x = min(max(geo.x(), avail.x()), avail.x() + avail.width() - w)
            y = min(max(geo.y(), avail.y()), avail.y() + avail.height() - h)
            self.setGeometry(x, y, w, h)

    def _save_window_geometry(self):
        try:
            self.cfg["window_geometry"] = bytes(
                self.saveGeometry().toBase64()).decode("ascii")
        except Exception:
            pass

    # ---------- Konfiguration
    def _load_cfg(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        # Umbenennung von WeiterLader: alte Einstellungen einmalig übernehmen.
        try:
            return json.loads(_OLD_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cfg(self):
        self.cfg["font_size"] = self.font_size
        self.cfg["folder"] = self.folder_edit.text()
        self.cfg["auto_retry"] = self.chk_retry.isChecked()
        self.cfg["retry_wait"] = self.spin_wait.value()
        self.cfg["queue_mode"] = self.chk_queue.isChecked()
        self.cfg["sound_enabled"] = self.chk_sound.isChecked()
        if hasattr(self, "chk_catch"):
            self.cfg["catch_enabled"] = self.chk_catch.isChecked()
            self.cfg["catch_port"] = self.spin_port.value()
            self.cfg["civitai_token"] = self.token_edit.text().strip()
        self.cfg["downloads"] = [
            {"url": r["url"], "folder": r["folder"],
             "filename": r.get("filename", ""),
             "done": r.get("done", False),
             "final_path": r.get("final_path", "")}
            for r in self.rows
        ]
        try:
            CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Zeile 1: URL
        row1 = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(T("ui.url_placeholder"))
        self.url_edit.returnPressed.connect(self.add_download)
        btn_paste = QPushButton(T("ui.btn_paste"))
        btn_paste.setObjectName("secondary")
        btn_paste.clicked.connect(
            lambda: self.url_edit.setText(
                " ".join(QApplication.clipboard().text().split())))
        btn_add = QPushButton(T("ui.btn_add"))
        btn_add.clicked.connect(self.add_download)
        btn_list = QPushButton(T("ui.btn_import_list"))
        btn_list.setObjectName("secondary")
        btn_list.setToolTip(T("ui.btn_import_list_tooltip"))
        btn_list.clicked.connect(self.import_list)
        row1.addWidget(self.url_edit, 1)
        row1.addWidget(btn_paste)
        row1.addWidget(btn_add)
        row1.addWidget(btn_list)
        root.addLayout(row1)

        # Zeile 2: Zielordner (mit Verlauf) + Optionen
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(T("ui.label_target_folder")))
        self.folder_combo = QComboBox()
        self.folder_combo.setEditable(True)
        self.folder_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        history = self.cfg.get("folder_history") or [
            self.cfg.get("folder", str(Path.home() / "Downloads"))]
        self.folder_combo.addItems(history)
        self.folder_combo.setCurrentText(
            self.cfg.get("folder", history[0]))
        self.folder_edit = self.folder_combo.lineEdit()
        btn_folder = QPushButton("…")
        btn_folder.setObjectName("secondary")
        btn_folder.setFixedWidth(36)
        btn_folder.clicked.connect(self.pick_folder)
        self.chk_retry = QCheckBox(T("ui.chk_auto_retry"))
        self.chk_retry.setChecked(self.cfg.get("auto_retry", True))
        self.spin_wait = QSpinBox()
        self.spin_wait.setRange(3, 300)
        self.spin_wait.setSuffix(T("ui.spin_seconds_suffix"))
        self.spin_wait.setValue(self.cfg.get("retry_wait", 10))
        self.chk_queue = QCheckBox(T("ui.chk_queue_mode"))
        self.chk_queue.setChecked(self.cfg.get("queue_mode", True))
        self.chk_queue.toggled.connect(lambda _: (self._save_cfg(),
                                                  self._advance_queue()))
        # Bewusst NICHT persistiert – muss pro Sitzung neu angehakt werden.
        self.chk_shutdown = QCheckBox(T("ui.chk_shutdown"))
        self.chk_shutdown.setStyleSheet(
            "QCheckBox { color: #a33; font-weight: 600; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }")
        self.chk_shutdown.setToolTip(T("ui.chk_shutdown_tooltip"))
        row2.addWidget(self.folder_combo, 1)
        row2.addWidget(btn_folder)
        row2.addSpacing(16)
        row2.addWidget(self.chk_retry)
        row2.addWidget(self.spin_wait)
        row2.addSpacing(16)
        row2.addWidget(self.chk_queue)
        row2.addSpacing(16)
        self.chk_sound = QCheckBox(T("ui.chk_sound"))
        self.chk_sound.setChecked(self.cfg.get("sound_enabled", True))
        self.chk_sound.toggled.connect(lambda _: self._save_cfg())
        btn_sound = QPushButton("🔔")
        btn_sound.setObjectName("secondary")
        btn_sound.setFixedWidth(36)
        btn_sound.setToolTip(T("ui.btn_sound_tooltip"))
        btn_sound.clicked.connect(self._sound_menu)
        self._btn_sound = btn_sound
        row2.addWidget(self.chk_sound)
        row2.addWidget(btn_sound)
        row2.addSpacing(16)
        row2.addWidget(self.chk_shutdown)
        root.addLayout(row2)

        # Zeile 2b: Browser-Interception + Civitai-Token
        row2b = QHBoxLayout()
        self.chk_catch = QCheckBox(T("ui.chk_catch"))
        self.chk_catch.setToolTip(T("ui.chk_catch_tooltip"))
        self.chk_catch.toggled.connect(self._toggle_catch)
        row2b.addWidget(self.chk_catch)
        row2b.addWidget(QLabel(T("ui.label_port")))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(self.cfg.get("catch_port", DEFAULT_CATCH_PORT))
        self.spin_port.valueChanged.connect(self._on_port_changed)
        row2b.addWidget(self.spin_port)
        self.lbl_catch = QLabel(T("ui.catch_off"))
        self.lbl_catch.setObjectName("hint")
        row2b.addWidget(self.lbl_catch)
        row2b.addSpacing(24)
        row2b.addWidget(QLabel(T("ui.label_civitai_token")))
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText(T("ui.civitai_token_placeholder"))
        self.token_edit.setText(self.cfg.get("civitai_token", ""))
        self.token_edit.setToolTip(T("ui.civitai_token_tooltip"))
        self.token_edit.editingFinished.connect(self._save_token)
        row2b.addWidget(self.token_edit, 1)
        root.addLayout(row2b)

        # Zeile 2c: Sprache (wirkt nach Neustart; jede *.json in lang/
        # taucht hier automatisch auf - eigene Uebersetzungen brauchen
        # keinen Code-Eingriff)
        row2c = QHBoxLayout()
        row2c.addWidget(QLabel(T("ui.label_language")))
        self.lang_combo = QComboBox()
        for code, name in self._scan_languages():
            self.lang_combo.addItem(name, code)
        idx = self.lang_combo.findData(self.lang_code)
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        row2c.addWidget(self.lang_combo)
        lang_hint = QLabel(T("ui.language_restart_hint"))
        lang_hint.setObjectName("hint")
        row2c.addWidget(lang_hint)
        row2c.addStretch(1)
        root.addLayout(row2c)

        # Tabelle
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(T("table.headers"))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setSectionsMovable(True)   # Spalten per Drag umsortierbar
        # Standardbreiten (greifen nur beim allerersten Start)
        for col, width in ((self.COL_NAME, 320), (self.COL_FOLDER, 190),
                           (self.COL_SIZE, 90), (self.COL_PROGRESS, 170),
                           (self.COL_SPEED, 100), (self.COL_ETA, 80),
                           (self.COL_STATUS, 220), (self.COL_OPEN, 40)):
            self.table.setColumnWidth(col, width)
        # Gemerkte Spaltenbreiten und -reihenfolge wiederherstellen
        state = self.cfg.get("header_state")
        if state:
            try:
                hdr.restoreState(QByteArray.fromBase64(state.encode("ascii")))
            except Exception:
                pass
        # Änderungen (Breite/Reihenfolge) verzögert speichern
        self._hdr_timer = QTimer(self)
        self._hdr_timer.setSingleShot(True)
        self._hdr_timer.setInterval(600)
        self._hdr_timer.timeout.connect(self._save_header_state)
        hdr.sectionResized.connect(lambda *_: self._hdr_timer.start())
        hdr.sectionMoved.connect(lambda *_: self._hdr_timer.start())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        # Entf-Taste entfernt die markierten Zeilen (wie im Kontextmenü)
        del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_shortcut.activated.connect(self.remove_selected)
        root.addWidget(self.table, 1)

        # Buttons unten (Farbe zeigt den Zustand: gruen = laeuft,
        # rot = alles pausiert)
        row3 = QHBoxLayout()
        self.btn_resume = QPushButton(T("ui.btn_resume"))
        self.btn_resume.clicked.connect(self.resume_selected)
        self.btn_pause = QPushButton(T("ui.btn_pause"))
        self.btn_pause.clicked.connect(self.pause_selected)
        self.btn_clear_list = QPushButton(T("ui.btn_clear_list"))
        self.btn_clear_list.setObjectName("secondary")
        self.btn_clear_list.setToolTip(T("ui.btn_clear_list_tooltip"))
        self.btn_clear_list.clicked.connect(self.clear_list)
        hint = QLabel(T("ui.hint_bottom"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        row3.addWidget(self.btn_resume)
        row3.addWidget(self.btn_pause)
        row3.addWidget(self.btn_clear_list)
        row3.addWidget(hint, 1)
        root.addLayout(row3)
        self._update_state_buttons()
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._update_state_buttons)
        self._state_timer.start(700)

    # ---------- Sprache
    def _scan_languages(self):
        """Findet alle lang/*.json - eine selbst hinzugefuegte Uebersetzung
        taucht damit automatisch in der Auswahl auf."""
        files = sorted(LANG_DIR.glob("*.json")) if LANG_DIR.is_dir() else []
        result = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("_meta", {}).get("name", f.stem)
            except Exception:
                name = f.stem
            result.append((f.stem, name))
        return result or [("en", "English")]

    def _on_language_changed(self, _idx):
        code = self.lang_combo.currentData()
        if code and code != self.lang_code:
            self.lang_code = code
            self.cfg["language"] = code
            self._save_cfg()

    @staticmethod
    def _paint_btn(btn, state):
        if btn.property("stateColor") == state:
            return
        btn.setProperty("stateColor", state)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _update_state_buttons(self):
        """Gruen = mindestens ein Download laeuft.
        Rot auf Pause = unfertige Downloads vorhanden, aber keiner laeuft.
        Beide neutral = nichts zu tun (Liste leer oder alles fertig)."""
        running = self._any_running()
        unfinished = any(not r.get("done") for r in self.rows)
        if running:
            self._paint_btn(self.btn_resume, "green")
            self._paint_btn(self.btn_pause, "off")
        elif unfinished:
            self._paint_btn(self.btn_resume, "off")
            self._paint_btn(self.btn_pause, "red")
        else:
            self._paint_btn(self.btn_resume, "off")
            self._paint_btn(self.btn_pause, "off")

    def _sound_menu(self):
        menu = QMenu(self)
        cur = self.cfg.get("sound_path", "")
        info = QAction(
            T("sound.current_prefix") + (os.path.basename(cur) if cur
                           else T("sound.default_windows")), self)
        info.setEnabled(False)
        a_test = QAction(T("sound.test"), self)
        a_test.triggered.connect(lambda: self.play_success_sound(force=True))
        a_choose = QAction(T("sound.choose_custom"), self)
        a_choose.triggered.connect(self.choose_sound)
        a_reset = QAction(T("sound.reset_default"), self)
        a_reset.triggered.connect(self.reset_sound)
        menu.addAction(info)
        menu.addSeparator()
        menu.addAction(a_test)
        menu.addAction(a_choose)
        menu.addAction(a_reset)
        menu.exec(self._btn_sound.mapToGlobal(
            self._btn_sound.rect().bottomLeft()))

    def choose_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, T("dialog.choose_sound_title"), "",
            T("dialog.audio_filter"))
        if path:
            self.cfg["sound_path"] = path
            self._save_cfg()
            self.play_success_sound(force=True)  # Test abspielen

    def reset_sound(self):
        self.cfg["sound_path"] = ""
        self._save_cfg()
        self.play_success_sound(force=True)  # Test abspielen

    def play_success_sound(self, force=False):
        """Spielt den Fertig-Sound: eigene MP3/WAV falls gewählt, sonst
        Standard-Windows-Sound. Asynchron, blockiert nichts."""
        if not force and not self.chk_sound.isChecked():
            return
        path = self.cfg.get("sound_path", "")
        if path and Path(path).exists() and self._play_media(path):
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            QApplication.beep()

    def _play_media(self, path):
        """Spielt MP3/WAV ab. Reihenfolge:
        1. Qt Multimedia (im PyQt6-Paket enthalten, kann MP3 + WAV)
        2. Windows-MCI (winmm.dll, kann MP3 + WAV, keine Zusatzpakete)
        3. winsound (nur WAV)
        Gibt True zurück, wenn eine Stufe die Wiedergabe gestartet hat."""
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PyQt6.QtCore import QUrl
            if not hasattr(self, "_audio_out"):
                self._audio_out = QAudioOutput()
                self._player = QMediaPlayer()
                self._player.setAudioOutput(self._audio_out)
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(path)))
            self._audio_out.setVolume(1.0)
            self._player.play()
            return True
        except Exception:
            pass
        try:
            import ctypes
            mci = ctypes.windll.winmm.mciSendStringW
            mci("close persistdl_snd", None, 0, None)
            if mci(f'open "{path}" alias persistdl_snd',
                   None, 0, None) == 0:
                mci("play persistdl_snd", None, 0, None)
                return True
        except Exception:
            pass
        if str(path).lower().endswith(".wav"):
            try:
                import winsound
                winsound.PlaySound(
                    str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception:
                pass
        return False

    def _save_header_state(self):
        hdr = self.table.horizontalHeader()
        self.cfg["header_state"] = bytes(
            hdr.saveState().toBase64()).decode("ascii")
        self._save_cfg()

    def _apply_font(self):
        f = QFont("Segoe UI", self.font_size)
        QApplication.instance().setFont(f)
        self.setStyleSheet(STYLE)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.font_size = max(7, min(20, self.font_size +
                                        (1 if ev.angleDelta().y() > 0 else -1)))
            self._apply_font()
            self._save_cfg()
            ev.accept()
        else:
            super().wheelEvent(ev)

    # ---------- Browser-Catcher
    def _toggle_catch(self, on):
        if on:
            port = self.spin_port.value()
            try:
                self._catch_server.start(port)
            except OSError as e:
                self.chk_catch.blockSignals(True)
                self.chk_catch.setChecked(False)
                self.chk_catch.blockSignals(False)
                self.lbl_catch.setText(T("catch.port_busy"))
                QMessageBox.warning(
                    self, "PersistDL",
                    T("catch.port_busy_body", port=port, error=e))
                self._save_cfg()
                return
            self.lbl_catch.setText(T("ui.catch_listening", port=port))
            self.lbl_catch.setStyleSheet("color:#3f8f4a; font-weight:600;")
        else:
            self._catch_server.stop()
            self.lbl_catch.setText(T("ui.catch_off"))
            self.lbl_catch.setStyleSheet("")
        self._save_cfg()

    def _on_port_changed(self, _val):
        # Bei laufendem Server neu binden
        self._save_cfg()
        if self.chk_catch.isChecked():
            self.chk_catch.setChecked(False)
            self.chk_catch.setChecked(True)

    def _save_token(self):
        self._save_cfg()

    def _on_intercepted(self, url):
        """Wird aufgerufen, wenn die Browser-Erweiterung einen Download
        abgefangen und hierher geschickt hat."""
        folder = self.folder_edit.text().strip() or str(Path.home() / "Downloads")
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._remember_folder(folder)
        row = self._add_row(url, folder)
        self._set(row, self.COL_STATUS, T("row.intercepted"))
        self._start_or_queue(row)
        self._save_cfg()
        # Fenster kurz nach vorn holen, damit man den neuen Eintrag sieht
        self.showNormal()
        self.raise_()

    # ---------- Downloads
    def _restore_downloads(self):
        for d in self.cfg.get("downloads", []):
            row = self._add_row(d["url"], d["folder"], d.get("filename", ""))
            self.rows[row]["done"] = d.get("done", False)
            self.rows[row]["final_path"] = d.get("final_path", "")
            if d.get("done"):
                bar = self.table.cellWidget(row, self.COL_PROGRESS)
                bar.setMaximum(1000)
                bar.setValue(1000)
                bar.setFormat(T("progress.done_100"))
                self._check_file(row)
            else:
                self._set(row, self.COL_STATUS,
                          T("row.interrupted_click_resume"))

    def _row_file_path(self, row):
        """Wahrscheinlichster Ablageort der Datei dieses Eintrags."""
        r = self.rows[row]
        if r.get("final_path"):
            return Path(r["final_path"])
        fn = r.get("filename", "")
        return Path(r["folder"]) / fn if fn else Path(r["folder"])

    def _check_file(self, row):
        """Prueft bei fertigen Downloads, ob die Datei noch am gemerkten
        Ort liegt. Wenn nicht: roter Hinweis."""
        item = self.table.item(row, self.COL_STATUS)
        if item is None:
            return False
        path = self._row_file_path(row)
        if self.rows[row].get("filename") and path.is_file():
            item.setText(T("row.done"))
            item.setForeground(QColor(TEXT))
            return True
        item.setText(T("row.file_missing"))
        item.setForeground(QColor("#b3261e"))
        return False

    def open_row_location(self, row):
        """Springt in den Ordner der Datei; im Explorer wird die Datei
        direkt markiert. Fehlt die Datei -> roter Status."""
        if row is None:
            return
        r = self.rows[row]
        path = self._row_file_path(row)
        if not r.get("done") and not path.is_file():
            # laufender/unfertiger Download: .part markieren
            part = Path(r["folder"]) / (r.get("filename", "") + ".part")
            if part.is_file():
                path = part
        if path.is_file():
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
            if r.get("done"):
                self._check_file(row)
            return
        # Datei weg -> rot markieren, wenigstens den Ordner oeffnen
        if r.get("done"):
            self._check_file(row)
        folder = Path(r["folder"])
        if folder.is_dir():
            if os.name == "nt":
                os.startfile(str(folder))  # noqa
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        else:
            QMessageBox.warning(
                self, "PersistDL",
                T("dialog.neither_file_nor_folder", path=path))

    def _add_row(self, url, folder, filename=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = filename or os.path.basename(urlparse(url).path) or url
        for col, text in ((self.COL_NAME, unquote(name)),
                          (self.COL_FOLDER, folder), (self.COL_SIZE, "?"),
                          (self.COL_SPEED, "–"), (self.COL_ETA, "–"),
                          (self.COL_STATUS, T("row.waiting"))):
            item = QTableWidgetItem(text)
            if col == self.COL_FOLDER:
                item.setToolTip(folder)
            self.table.setItem(row, col, item)
        bar = BigTextProgressBar()
        bar.setValue(0)
        self.table.setCellWidget(row, self.COL_PROGRESS, bar)
        btn_open = QPushButton("📂")
        btn_open.setObjectName("secondary")
        btn_open.setFixedWidth(32)
        btn_open.setToolTip(T("ui.btn_open_folder_tooltip"))
        btn_open.clicked.connect(
            lambda _checked, b=btn_open: self.open_row_location(
                self._row_of_widget(b, self.COL_OPEN)))
        self.table.setCellWidget(row, self.COL_OPEN, btn_open)
        self.rows.append({"url": url, "folder": folder,
                          "filename": filename, "done": False})
        return row

    def _row_of_widget(self, widget, col):
        """Findet die AKTUELLE Zeile eines Cell-Widgets ueber seine Identitaet
        statt ueber eine beim Erstellen eingefrorene Zeilennummer - nach dem
        Entfernen anderer Zeilen (siehe _remove_rows) verschieben sich die
        Indizes, ein fest erfasstes 'row' im Klick-Handler wuerde sonst auf
        die falsche Zeile zeigen (gleiche Ursache wie bei _row_for_worker)."""
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, col) is widget:
                return row
        return None

    def _set(self, row, col, text):
        item = self.table.item(row, col)
        if item:
            item.setText(text)

    def add_download(self):
        text = self.url_edit.text().strip()
        if not text:
            return
        urls = [t for t in re.split(r"\s+", text)
                if t.lower().startswith(("http://", "https://"))]
        if not urls:
            QMessageBox.warning(self, "PersistDL", T("dialog.invalid_url"))
            return
        folder = self.folder_edit.text().strip()
        Path(folder).mkdir(parents=True, exist_ok=True)
        self._remember_folder(folder)
        self.url_edit.clear()
        for url in urls:
            row = self._add_row(url, folder)
            self._start_or_queue(row)
        self._save_cfg()

    def import_list(self):
        """Laedt eine Textdatei mit mehreren Downloads (je Zeile eine URL,
        eigener Zielordner, optional eigener Dateiname) und reiht sie alle
        auf einmal ein - jede Zeile kann an einen anderen Ort gehen, anders
        als beim normalen Mehrfach-Einfuegen oben (das nutzt fuer alle
        eingefuegten Links denselben Zielordner)."""
        path, _ = QFileDialog.getOpenFileName(
            self, T("dialog.import_list_title"), "",
            T("dialog.txt_filter"))
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8-sig")
        except Exception as e:
            QMessageBox.warning(self, "PersistDL",
                                T("dialog.cant_read_file", error=e))
            return

        added, skipped, bad_lines = 0, 0, []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            url = parts[0] if parts else ""
            folder = parts[1] if len(parts) >= 2 else ""
            filename = parts[2] if len(parts) >= 3 else ""
            if not url.lower().startswith(("http://", "https://")) or not folder:
                skipped += 1
                bad_lines.append(T("import.bad_line", lineno=lineno,
                                    line=line[:70]))
                continue
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                skipped += 1
                bad_lines.append(T("import.folder_error", lineno=lineno,
                                    error=e))
                continue
            self._remember_folder(folder)
            row = self._add_row(url, folder, filename)
            self._start_or_queue(row)
            added += 1

        if added:
            self._save_cfg()

        msg = TN("import.summary_added_one", "import.summary_added_other",
                 added)
        if skipped:
            msg += TN("import.summary_skipped_one",
                      "import.summary_skipped_other", skipped,
                      lines="\n".join(bad_lines[:10]))
            if len(bad_lines) > 10:
                msg += T("import.summary_more", count=len(bad_lines) - 10)
        QMessageBox.information(self, T("dialog.import_done_title"), msg)

    def _remember_folder(self, folder):
        """Ordner-Verlauf pflegen: zuletzt benutzt nach oben, max. 15."""
        hist = self.cfg.get("folder_history") or []
        if folder in hist:
            hist.remove(folder)
        hist.insert(0, folder)
        del hist[15:]
        self.cfg["folder_history"] = hist
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItems(hist)
        self.folder_combo.setCurrentText(current)
        self.folder_combo.blockSignals(False)

    def _any_running(self):
        return any(w.isRunning() for w in self.workers.values())

    def _start_or_queue(self, row):
        """Startet sofort – oder reiht ein, wenn Warteschlangen-Modus aktiv
        ist und bereits ein Download läuft."""
        if self.chk_queue.isChecked() and self._any_running():
            self.rows[row]["queued"] = True
            self._set(row, self.COL_STATUS, T("row.queued"))
        else:
            self._start(row)

    def _advance_queue(self):
        """Startet den nächsten wartenden Download, sobald keiner mehr läuft."""
        if not self.chk_queue.isChecked() or self._any_running():
            return
        for row, r in enumerate(self.rows):
            if r.get("queued") and not r.get("done"):
                self._start(row)
                return

    def _start(self, row):
        if row in self.workers and self.workers[row].isRunning():
            return
        self.rows[row]["queued"] = False
        r = self.rows[row]
        w = DownloadWorker(r["url"], r["folder"],
                           auto_retry=self.chk_retry.isChecked(),
                           retry_wait=self.spin_wait.value(),
                           civitai_token=self.token_edit.text().strip())
        w.sig_meta.connect(lambda name, total, w=w: self._on_meta(w, name, total))
        w.sig_progress.connect(lambda d, t, s, e, w=w: self._on_progress(w, d, t, s, e))
        w.sig_status.connect(lambda txt, w=w: self._on_status(w, txt))
        w.sig_done.connect(lambda path, w=w: self._on_done(w, path))
        w.sig_failed.connect(lambda msg, w=w: self._on_failed(w, msg))
        self.workers[row] = w
        self._set(row, self.COL_STATUS, T("row.connecting"))
        w.start()

    def _row_for_worker(self, w):
        """Findet die AKTUELLE Tabellenzeile eines Workers. Wird ein Auftrag
        entfernt, dessen Worker nicht rechtzeitig stoppt (siehe
        _remove_rows), laufen seine Signale im Hintergrund weiter - ohne
        diesen Zwischenschritt wuerden sie mit der alten, inzwischen
        ungueltigen Zeilennummer auf die Tabelle zugreifen und abstuerzen."""
        for row, worker in self.workers.items():
            if worker is w:
                return row
        return None

    def _on_status(self, w, txt):
        row = self._row_for_worker(w)
        if row is None:
            return
        self._set(row, self.COL_STATUS, txt)

    def _on_meta(self, w, name, total):
        row = self._row_for_worker(w)
        if row is None:
            return
        total = int(total)
        self.rows[row]["filename"] = name
        self._set(row, self.COL_NAME, name)
        self._set(row, self.COL_SIZE, human_size(total) if total > 0 else "?")
        self._save_cfg()

    def _on_progress(self, w, downloaded, total, speed, eta):
        row = self._row_for_worker(w)
        if row is None:
            return
        downloaded, total = int(downloaded), int(total)
        bar = self.table.cellWidget(row, self.COL_PROGRESS)
        if bar is None:
            return
        if total > 0:
            bar.setMaximum(1000)
            bar.setValue(int(downloaded / total * 1000))
            bar.setFormat(T("progress.percent", value=downloaded / total * 100))
        else:
            bar.setMaximum(0)  # unbestimmt
        self._set(row, self.COL_SPEED, human_speed(speed))
        self._set(row, self.COL_ETA, human_eta(eta))
        self._set(row, self.COL_STATUS,
                  T("row.downloading", size=human_size(downloaded)))

    def _on_done(self, w, path):
        row = self._row_for_worker(w)
        if row is None:
            return
        bar = self.table.cellWidget(row, self.COL_PROGRESS)
        if bar is None:
            return
        bar.setMaximum(1000)
        bar.setValue(1000)
        bar.setFormat(T("progress.done_100"))
        self._set(row, self.COL_SPEED, "–")
        self._set(row, self.COL_ETA, "–")
        self._set(row, self.COL_STATUS, T("row.done"))
        self.rows[row]["done"] = True
        self.rows[row]["final_path"] = path
        self.play_success_sound()
        self._save_cfg()
        self._advance_queue()
        self._maybe_shutdown()

    def _maybe_shutdown(self):
        """Fährt den PC erzwungen herunter, wenn die Option aktiv ist und
        wirklich ALLE Downloads erfolgreich abgeschlossen sind."""
        if not self.chk_shutdown.isChecked():
            return
        if self._any_running():
            return
        if any(r.get("queued") for r in self.rows):
            return
        if not self.rows or not all(r.get("done") for r in self.rows):
            # Mindestens ein Download ist fehlgeschlagen/unfertig →
            # sicherheitshalber NICHT herunterfahren.
            return
        if os.name != "nt":
            return

        # Befehl sofort absetzen (60 s Frist), Dialog erlaubt Abbruch.
        try:
            subprocess.run(
                ["shutdown", "/s", "/f", "/t", "60",
                 "/c", T("shutdown.notice_cmd")],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as e:
            QMessageBox.critical(self, "PersistDL",
                                 T("shutdown.cmd_failed", error=e))
            return

        # Fenster aus der Minimierung holen und nach vorn bringen,
        # damit der Countdown sichtbar ist
        self.showNormal()
        self.raise_()
        self.activateWindow()
        dlg = ShutdownDialog(60, self)
        dlg.exec()
        if dlg.clickedButton() is dlg.abort_btn:
            try:
                subprocess.run(["shutdown", "/a"],
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.chk_shutdown.setChecked(False)
                QMessageBox.information(
                    self, "PersistDL", T("shutdown.aborted"))
            except Exception as e:
                QMessageBox.critical(self, "PersistDL",
                                     T("shutdown.abort_failed", error=e))

    def _on_failed(self, w, msg):
        row = self._row_for_worker(w)
        if row is None:
            return
        self._set(row, self.COL_STATUS, msg)
        self._set(row, self.COL_SPEED, "–")
        self._advance_queue()

    # ---------- Aktionen
    def _selected_rows(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def resume_selected(self):
        rows = self._selected_rows() or [
            i for i, r in enumerate(self.rows) if not r["done"]]
        for row in rows:
            if not self.rows[row]["done"]:
                self._start_or_queue(row)

    def pause_selected(self):
        rows = self._selected_rows() or list(self.workers.keys())
        for row in rows:
            w = self.workers.get(row)
            if w and w.isRunning():
                w.pause()

    def _remove_rows(self, rows):
        for row in sorted(rows, reverse=True):
            w = self.workers.pop(row, None)
            if w and w.isRunning():
                w.cancel()
                w.wait(2000)
            self.table.removeRow(row)
            self.rows.pop(row)
            # Worker-Indizes anpassen
            self.workers = {(k - 1 if k > row else k): v
                            for k, v in self.workers.items()}
        self._save_cfg()

    def remove_selected(self):
        rows = self._selected_rows()
        if not rows:
            return
        ask = QMessageBox.question(
            self, "PersistDL",
            TN("confirm.remove_selected_one", "confirm.remove_selected_other",
               len(rows)))
        if ask != QMessageBox.StandardButton.Yes:
            return
        self._remove_rows(rows)

    def remove_done(self):
        rows = [i for i, r in enumerate(self.rows) if r.get("done")]
        if not rows:
            QMessageBox.information(
                self, "PersistDL", T("info.no_done_downloads"))
            return
        ask = QMessageBox.question(
            self, "PersistDL",
            T("confirm.remove_done", count=len(rows)))
        if ask != QMessageBox.StandardButton.Yes:
            return
        self._remove_rows(rows)

    def clear_list(self):
        """'Liste leeren' - entfernt ALLE Eintraege aus der Liste, egal ob
        fertig oder nicht. Laufende/pausierte Downloads werden dabei ueber
        _remove_rows sauber abgebrochen. Nur die Anzeige-Liste wird
        geleert - bereits heruntergeladene Dateien bleiben auf der
        Festplatte unangetastet."""
        rows = list(range(len(self.rows)))
        if not rows:
            QMessageBox.information(
                self, "PersistDL", T("info.list_already_empty"))
            return
        ask = QMessageBox.question(
            self, "PersistDL",
            T("confirm.clear_list", count=len(rows)))
        if ask != QMessageBox.StandardButton.Yes:
            return
        self._remove_rows(rows)

    def open_folder(self):
        folder = self.folder_edit.text().strip()
        if os.name == "nt":
            os.startfile(folder)  # noqa
        else:
            subprocess.Popen(["xdg-open", folder])

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, T("dialog.pick_folder_title"), self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)
            self._save_cfg()

    def change_row_folder(self, row):
        """Zielordner eines Downloads nachträglich ändern. Bereits geladene
        Teildaten (.part + Merkzettel) ziehen mit um, damit die Fortsetzung
        lückenlos bleibt."""
        w = self.workers.get(row)
        if w and w.isRunning():
            QMessageBox.information(
                self, "PersistDL", T("info.pause_before_folder_change"))
            return
        old = self.rows[row]["folder"]
        d = QFileDialog.getExistingDirectory(
            self, T("dialog.new_folder_title"), old)
        if not d or d == old:
            return
        fn = self.rows[row].get("filename", "")
        try:
            if fn:
                for suffix in (".part", ".persistdl.json", ".weiterlader.json", ""):
                    src = Path(old) / (fn + suffix)
                    if src.exists():
                        shutil.move(str(src), str(Path(d) / src.name))
        except Exception as e:
            QMessageBox.critical(self, "PersistDL",
                                 T("error.move_failed", error=e))
            return
        self.rows[row]["folder"] = d
        self._set(row, self.COL_FOLDER, d)
        item = self.table.item(row, self.COL_FOLDER)
        if item:
            item.setToolTip(d)
        self._remember_folder(d)
        self._save_cfg()

    def context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        a_resume = QAction(T("ui.btn_resume"), self)
        a_resume.triggered.connect(lambda: self._start(row))
        a_pause = QAction(T("ui.btn_pause"), self)
        a_pause.triggered.connect(
            lambda: self.workers.get(row) and self.workers[row].pause())
        a_copy = QAction(T("menu.copy_url"), self)
        a_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(self.rows[row]["url"]))
        a_folder = QAction(T("menu.change_folder"), self)
        a_folder.triggered.connect(lambda: self.change_row_folder(row))
        a_show = QAction(T("menu.show_in_folder"), self)
        a_show.triggered.connect(lambda: self.open_row_location(row))
        a_forget = QAction(T("menu.remove_row"), self)
        a_forget.triggered.connect(
            lambda: (self.table.selectRow(row), self.remove_selected()))
        a_clear_done = QAction(T("menu.remove_done"), self)
        a_clear_done.triggered.connect(self.remove_done)
        menu.addAction(a_resume)
        menu.addAction(a_pause)
        menu.addSeparator()
        menu.addAction(a_show)
        menu.addAction(a_folder)
        menu.addAction(a_copy)
        menu.addSeparator()
        menu.addAction(a_forget)
        menu.addAction(a_clear_done)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def closeEvent(self, ev):
        # Catcher-Server stoppen
        try:
            self._catch_server.stop()
        except Exception:
            pass
        # Laufende Downloads sauber pausieren – Stand bleibt erhalten
        for w in self.workers.values():
            if w.isRunning():
                w.pause()
        for w in self.workers.values():
            w.wait(3000)
        self._save_window_geometry()
        self._save_cfg()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
