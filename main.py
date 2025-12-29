import json
import random
import threading
import time
import ctypes
import subprocess
import tempfile
import os
import asyncio
from pathlib import Path

import edge_tts
import ollama

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget


# ---------- Windows helpers: click-through ----------
def set_click_through(hwnd: int, enabled: bool):
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020

    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED
    if enabled:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


# ---------- Signals bridge ----------
class Bridge(QObject):
    set_talking = Signal(bool)
    say_text = Signal(str)
    toggle_click_through = Signal()
    quit_app = Signal()


# ---------- Overlay widget ----------
class AvatarOverlay(QWidget):
    def __init__(self, config: dict):
        super().__init__()

        self.config = config
        self.scale = float(config.get("scale", 1.0))
        self.fps_ms = int(config.get("fps_ms", 120))

        frames_cfg = config.get("frames", {})

        blink_generic = frames_cfg.get("blink", [])
        blink_idle_cfg = frames_cfg.get("blink_idle", blink_generic)
        blink_talk_cfg = frames_cfg.get("blink_talk", blink_generic)

        self.frames = {
            "idle": self._load_frames(frames_cfg.get("idle", [])),
            "talk": self._load_frames(frames_cfg.get("talk", [])),
            "blink_idle": self._load_frames(blink_idle_cfg),
            "blink_talk": self._load_frames(blink_talk_cfg),
        }

        if not self.frames["idle"]:
            raise FileNotFoundError("Config precisa ter pelo menos 1 frame em frames.idle")
        if not self.frames["talk"]:
            self.frames["talk"] = self.frames["idle"]

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground)

        flags = Qt.FramelessWindowHint | Qt.Tool
        if config.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._talking = False
        self._blinking = False
        self._frame_index = 0

        self._set_pixmap(self.frames["idle"][0])

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(self.fps_ms)

        self._schedule_next_blink()
        self._place_on_screen()

        self.click_through = bool(config.get("click_through", False))

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        set_click_through(hwnd, self.click_through)

    def mousePressEvent(self, event):
        if not self.click_through and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.click_through and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def toggle_click_through(self):
        self.click_through = not self.click_through
        hwnd = int(self.winId())
        set_click_through(hwnd, self.click_through)
        print(f"[overlay] click-through = {self.click_through}")

    def set_talking(self, value: bool):
        self._talking = bool(value)
        self._frame_index = 0

    def _tick(self):
        if self._blinking:
            return

        frames = self.frames["talk"] if self._talking else self.frames["idle"]
        if not frames:
            return

        self._frame_index = (self._frame_index + 1) % len(frames)
        self._set_pixmap(frames[self._frame_index])

    def _do_blink(self):
        blink_cfg = self.config.get("blink", {})
        if not blink_cfg.get("enabled", True):
            self._schedule_next_blink()
            return

        blink_frames = self.frames["blink_talk"] if self._talking else self.frames["blink_idle"]
        if not blink_frames:
            self._schedule_next_blink()
            return

        self._blinking = True
        self._set_pixmap(blink_frames[0])

        duration = int(blink_cfg.get("duration_ms", 120))

        def end_blink():
            self._blinking = False
            frames = self.frames["talk"] if self._talking else self.frames["idle"]
            self._set_pixmap(frames[self._frame_index % len(frames)])
            self._schedule_next_blink()

        QTimer.singleShot(duration, end_blink)

    def _schedule_next_blink(self):
        blink_cfg = self.config.get("blink", {})
        if not blink_cfg.get("enabled", True):
            return

        if not self.frames["blink_idle"] and not self.frames["blink_talk"]:
            return

        min_ms = int(blink_cfg.get("min_ms", 2500))
        max_ms = int(blink_cfg.get("max_ms", 6000))
        wait = random.randint(min_ms, max_ms)
        QTimer.singleShot(wait, self._do_blink)

    def _load_frames(self, paths):
        loaded = []
        for p in paths:
            pix = QPixmap(str(Path(p)))
            if pix.isNull():
                print(f"[warn] não consegui carregar: {p}")
                continue
            loaded.append(pix)
        return loaded

    def _set_pixmap(self, pixmap: QPixmap):
        if self.scale != 1.0:
            w = int(pixmap.width() * self.scale)
            h = int(pixmap.height() * self.scale)
            pixmap = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.label.setPixmap(pixmap)
        self.resize(pixmap.width(), pixmap.height())
        self.label.resize(pixmap.width(), pixmap.height())

    def _place_on_screen(self):
        pos = self.config.get("position", "bottom_right")
        margin = self.config.get("margin", [20, 20])
        mx, my = int(margin[0]), int(margin[1])

        screen = QApplication.primaryScreen().availableGeometry()
        x, y = 20, 20

        if pos == "bottom_right":
            x = screen.right() - self.width() - mx
            y = screen.bottom() - self.height() - my
        elif pos == "bottom_left":
            x = screen.left() + mx
            y = screen.bottom() - self.height() - my
        elif pos == "top_right":
            x = screen.right() - self.width() - mx
            y = screen.top() + my
        elif pos == "top_left":
            x = screen.left() + mx
            y = screen.top() + my

        self.move(x, y)


# ---------- Neural TTS (edge-tts + mpv) ----------
class NeuralTTS:
    def __init__(self):
        self.voice = "ja-JP-NanamiNeural"
        self.rate = "+10%"
        self.pitch = "+25Hz"
        self.volume = "+0%"

        self.mpv_cmd = self._resolve_mpv()

    def _resolve_mpv(self):
        try:
            r = subprocess.run(["where", "mpv"], capture_output=True, text=True)
            if r.returncode == 0:
                return "mpv"
        except Exception:
            pass
        return "mpv"

    async def _synth_to_file(self, text: str, out_path: str):
        comm = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume,
        )
        await comm.save(out_path)

    def speak_blocking(self, text: str) -> tuple[bool, str]:
        text = (text or "").strip()
        if not text:
            return True, ""

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_path = tmp.name
        tmp.close()

        try:
            try:
                asyncio.run(self._synth_to_file(text, tmp_path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._synth_to_file(text, tmp_path))
                loop.close()

            p = subprocess.Popen([self.mpv_cmd, "--no-video", "--really-quiet", tmp_path])
            p.wait()
            return True, ""

        except FileNotFoundError:
            return False, "mpv não encontrado. Instale com: winget install mpv"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---------- Local LLM (Ollama) ----------
class LocalLLM:
    def __init__(self):
        self.model = "qwen2.5:3b"  # troque aqui se quiser (ex: llama3.1:8b)

        self.system_prompt = """
Você é a Nya, uma assistente virtual estilo anime.
Personalidade: fofa, direta, prestativa, com humor leve.
Regras:
- Responda em PT-BR.
- Respostas curtas (máx. 6 linhas), a menos que eu peça detalhes.
- Se eu pedir para executar algo no computador, peça confirmação antes.
""".strip()

    def reply(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return "Diga algo pra eu responder, nya~"

        try:
            resp = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_text},
                ],
            )
            return resp["message"]["content"].strip()
        except Exception as e:
            return (
                "Não consegui falar com o Ollama.\n"
                "1) Verifique se o app do Ollama está instalado e aberto.\n"
                f"2) Verifique se você baixou um modelo: ollama pull {self.model}\n"
                f"Erro: {type(e).__name__} - {e}"
            )


def load_config():
    cfg_path = Path("config.json")
    if not cfg_path.exists():
        default = {
            "scale": 0.55,
            "click_through": False,
            "always_on_top": True,
            "position": "bottom_right",
            "margin": [20, 20],
            "fps_ms": 110,
            "frames": {
                "idle": ["assets/Open Eyes Closed Mouth.png"],
                "talk": [
                    "assets/Open Eyes Open Mouth.png",
                    "assets/Open Eyes Closed Mouth.png"
                ],
                "blink_idle": ["assets/Closed Eyes Closed Mouth.png"],
                "blink_talk": ["assets/Closed Eyes Open Mouth.png"]
            },
            "blink": {"enabled": True, "min_ms": 2500, "max_ms": 6000, "duration_ms": 120}
        }
        cfg_path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def start_console_commands(bridge: Bridge, tts: NeuralTTS, llm: LocalLLM):
    print("\nComandos:")
    print("  say <texto>     | fala (voz neural Nanami)")
    print("  ask <texto>     | pergunta pra IA local (Ollama)")
    print("  model <nome>    | troca o modelo do Ollama (ex: qwen2.5:3b)")
    print("  talk on/off     | liga/desliga animação (manual)")
    print("  ct              | alterna click-through")
    print("  voice <nome>    | troca voz (ex: ja-JP-NanamiNeural)")
    print("  pitch <+25Hz>   | ajusta pitch")
    print("  rate <+10%>     | ajusta rate")
    print("  quit            | sair")
    print("  help            | ajuda\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            bridge.quit_app.emit()
            return

        if not line:
            continue

        cmd, *rest = line.split(" ", 1)
        arg = rest[0] if rest else ""
        cmd = cmd.lower()

        if cmd == "help":
            print("  say <texto>")
            print("  ask <texto>")
            print("  model <nome>")
            print("  talk on/off")
            print("  ct")
            print("  voice <nome>")
            print("  pitch <+25Hz>")
            print("  rate <+10%>")
            print("  quit")

        elif cmd == "quit":
            bridge.quit_app.emit()
            return

        elif cmd == "ct":
            bridge.toggle_click_through.emit()

        elif cmd == "talk":
            val = arg.strip().lower()
            if val in ("on", "true", "1"):
                bridge.set_talking.emit(True)
            elif val in ("off", "false", "0"):
                bridge.set_talking.emit(False)
            else:
                print("Use: talk on  |  talk off")

        elif cmd == "voice":
            if not arg:
                print("Use: voice <nome>  (ex: ja-JP-NanamiNeural)")
            else:
                tts.voice = arg.strip()
                print(f"[tts] voice = {tts.voice}")

        elif cmd == "pitch":
            if not arg:
                print("Use: pitch <+25Hz>  (ex: +35Hz)")
            else:
                tts.pitch = arg.strip()
                print(f"[tts] pitch = {tts.pitch}")

        elif cmd == "rate":
            if not arg:
                print("Use: rate <+10%>  (ex: -10%)")
            else:
                tts.rate = arg.strip()
                print(f"[tts] rate = {tts.rate}")

        elif cmd == "model":
            if not arg:
                print("Use: model <nome>  (ex: qwen2.5:3b)")
            else:
                llm.model = arg.strip()
                print(f"[llm] model = {llm.model}")
                print(f"Agora baixe com: ollama pull {llm.model}")

        elif cmd == "say":
            if not arg:
                print("Use: say <texto>")
            else:
                bridge.say_text.emit(arg)

        elif cmd == "ask":
            if not arg:
                print("Use: ask <pergunta>")
            else:
                # Rodar o LLM em thread pra não travar tudo
                def run_ask():
                    reply = llm.reply(arg)
                    print(f"nya> {reply}")
                    bridge.say_text.emit(reply)

                threading.Thread(target=run_ask, daemon=True).start()

        else:
            print("Comando desconhecido. Digite: help")


def main():
    config = load_config()

    app = QApplication([])
    bridge = Bridge()

    overlay = AvatarOverlay(config)
    overlay.show()

    tts = NeuralTTS()
    llm = LocalLLM()

    bridge.set_talking.connect(overlay.set_talking)
    bridge.toggle_click_through.connect(overlay.toggle_click_through)

    def do_say(text: str):
        def run():
            bridge.set_talking.emit(True)
            try:
                ok, err = tts.speak_blocking(text)
                if not ok and err:
                    print(f"[tts] erro: {err}")
            finally:
                bridge.set_talking.emit(False)

        threading.Thread(target=run, daemon=True).start()

    bridge.say_text.connect(do_say)
    bridge.quit_app.connect(app.quit)

    threading.Thread(target=start_console_commands, args=(bridge, tts, llm), daemon=True).start()
    app.exec()


if __name__ == "__main__":
    main()
