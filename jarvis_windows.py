#!/usr/bin/env python3
"""
⚡ J.A.R.V.I.S. for Windows 10/11
Provides:
  - Global Hotkey (Alt + A) -> Sleek floating Siri-style input bar
  - Top-Center Futuristic J.A.R.V.I.S. Streaming HUD Card (Tkinter borderless overlay)
  - Neural British Jarvis Voice (edge-tts + pygame) with Replay / Voice Toggle / Pin / Copy
  - Live Web Search (ddgs), Instant Weather (wttr.in), Screen Vision (Pillow), Gmail, & System Controls
"""
import asyncio
import base64
import ctypes
import email
import imaplib
import io
import json
import os
import re
import smtplib
import tempfile
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv, set_key
from openai import OpenAI
import edge_tts
from ddgs import DDGS

try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:
    HAS_KEYBOARD = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except Exception:
    HAS_PYPERCLIP = False

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except Exception:
    HAS_PIL = False

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

API_KEY = os.getenv("TNSA_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "").replace(" ", "").strip()
MODEL_NAME = os.getenv("TNSA_MODEL", "NGen-4.5-Vayu").strip()
JARVIS_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural").strip()
JARVIS_VOICE_RATE = os.getenv("JARVIS_VOICE_RATE", "+6%").strip()
JARVIS_VOICE_PITCH = os.getenv("JARVIS_VOICE_PITCH", "-2Hz").strip()
JARVIS_VOICE_ENABLED = os.getenv("JARVIS_VOICE_ENABLED", "1").strip() == "1"

SPEECH_MP3 = Path(tempfile.gettempdir()) / "jarvis_win_speech.mp3"

VOICE_PRESETS = {
    "ryan": ("en-GB-RyanNeural", "OG Iron Man Jarvis - Crisp British (Male)"),
    "thomas": ("en-GB-ThomasNeural", "Classic British Butler Jarvis (Male)"),
    "friday": ("en-GB-SoniaNeural", "British F.R.I.D.A.Y. (Female)"),
    "brian": ("en-US-BrianMultilingualNeural", "Smooth American AI (Male)"),
    "christopher": ("en-US-ChristopherNeural", "Deep Cinematic American (Male)"),
    "ava": ("en-US-AvaMultilingualNeural", "Expressive American AI (Female)"),
    "prabhat": ("en-IN-PrabhatNeural", "Clear Indian English (Male)"),
    "neerja": ("en-IN-NeerjaNeural", "Clear Indian English (Female)"),
}

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., Tony Stark's iconic British AI assistant, "
    "running on the user's Windows PC. Address the user politely as 'sir'. "
    "CRITICAL RULES:\n"
    "1. Reply in 1 to 2 crisp, natural spoken sentences ONLY.\n"
    "2. NEVER include internal reasoning, chain-of-thought notes, bullet headers like '**Greeting**:', or markdown formatting (*, **, #, `).\n"
    "3. Output ONLY the final words Jarvis speaks out loud."
)

EXTRA_FAST_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

tnsa_client = OpenAI(
    base_url="https://api.tnsaai.com/v1",
    api_key=API_KEY or "none",
    default_headers={"x-api-key": API_KEY or "none"},
    timeout=5.5,
    max_retries=0,
)

gemini_client = (
    OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=GEMINI_API_KEY,
        timeout=6.0,
        max_retries=0,
    )
    if GEMINI_API_KEY
    else None
)

groq_client = (
    OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
        timeout=6.0,
        max_retries=0,
    )
    if GROQ_API_KEY
    else None
)

backup_client = OpenAI(
    base_url="https://text.pollinations.ai/openai",
    api_key="free",
    timeout=6.5,
    max_retries=0,
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live internet when the user asks to search the web or asks about live current events, weather, or news.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "open_in_browser": {"type": "boolean", "description": "True if user asks to open in browser"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_action",
            "description": "Run local Windows actions, control media, fix clipboard text, or check unread Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "battery",
                            "fix_clipboard",
                            "unread_gmail",
                            "media_play_pause",
                            "media_next",
                            "media_prev",
                            "toggle_voice_mode",
                        ],
                    }
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_voice",
            "description": "Switch Jarvis's neural TTS voice preset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voice_preset": {"type": "string", "enum": list(VOICE_PRESETS.keys())}
                },
                "required": ["voice_preset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via the user's Gmail account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_address": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to_address", "subject", "body"],
            },
        },
    },
]


def _get_provider_candidates(tools_list=None):
    candidates = []
    if groq_client:
        kw = {"model": "llama-3.3-70b-versatile"}
        if tools_list:
            kw["tools"] = tools_list
        candidates.append((groq_client, kw))
    if gemini_client:
        kw = {"model": "gemini-2.5-flash"}
        if tools_list:
            kw["tools"] = tools_list
        candidates.append((gemini_client, kw))
    if API_KEY and API_KEY != "put_your_tnsa_api_key_here":
        kw = {"model": MODEL_NAME}
        if "4.3" in MODEL_NAME:
            kw["extra_body"] = EXTRA_FAST_BODY
        if tools_list:
            kw["tools"] = tools_list
        candidates.append((tnsa_client, kw))
    candidates.append((backup_client, {"model": "openai-fast"}))
    return candidates


def clean_jarvis_text(raw: str | None, allow_empty: bool = False) -> str:
    if not raw:
        return "" if allow_empty else "At your service, sir."
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL).strip()

    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^[-*]?\s*\*\*[^*]+\*\*\s*:", s):
            continue
        if re.match(r"^(Thinking|Reasoning|Analysis|Plan|Step \d+)\s*:", s, flags=re.IGNORECASE):
            continue
        filtered_lines.append(s)

    if filtered_lines:
        text = " ".join(filtered_lines)
    elif allow_empty:
        return ""
    else:
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
        text = paragraphs[-1] if paragraphs else raw

    text = re.sub(r"[*_`#~]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if allow_empty else (text or "At your service, sir.")


def decode_mime_str(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for content, charset in parts:
        if isinstance(content, bytes):
            decoded.append(content.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(content))
    return "".join(decoded)


class JarvisWindowsApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.last_text = "All systems online, sir. Press Alt + A anytime to summon me."
        self.pinned = False
        self.hide_job = None

        self._build_hud_window()
        self._build_input_window()

        if HAS_KEYBOARD:
            try:
                keyboard.add_hotkey("alt+a", lambda: self.root.after(0, self.toggle_input_bar))
            except Exception:
                pass

        # Show initial welcome card
        self.root.after(200, lambda: self.show_hud(self.last_text, status="READY (ALT + A)"))

    def _build_hud_window(self):
        self.hud = tk.Toplevel(self.root)
        self.hud.overrideredirect(True)
        self.hud.attributes("-topmost", True)
        self.hud.configure(bg="#0b0e14")

        self.hud_frame = tk.Frame(
            self.hud, bg="#0b0e14", highlightbackground="#00d2ff", highlightthickness=1, padx=14, pady=10
        )
        self.hud_frame.pack(fill="both", expand=True)

        header = tk.Frame(self.hud_frame, bg="#0b0e14")
        header.pack(fill="x")

        tk.Label(
            header, text="⚡ J.A.R.V.I.S.", fg="#00d2ff", bg="#0b0e14", font=("Consolas", 10, "bold")
        ).pack(side="left")

        self.status_lbl = tk.Label(
            header, text="VOICE + HUD", fg="#8b949e", bg="#161b22", font=("Consolas", 8), padx=6, pady=1
        )
        self.status_lbl.pack(side="left", padx=8)

        btn_style = {"bg": "#161b22", "fg": "#e6edf3", "bd": 0, "font": ("Segoe UI", 8, "bold"), "padx": 6, "pady": 2, "cursor": "hand2"}

        tk.Button(header, text="✕", command=self.hide_hud, **btn_style).pack(side="right", padx=2)
        self.pin_btn = tk.Button(header, text="📌 Pin", command=self.toggle_pin, **btn_style)
        self.pin_btn.pack(side="right", padx=2)
        tk.Button(header, text="📋 Copy", command=self.copy_text, **btn_style).pack(side="right", padx=2)
        self.mode_btn = tk.Button(
            header,
            text="🎙️ Voice ON" if JARVIS_VOICE_ENABLED else "💬 Text Only",
            command=self.toggle_voice,
            **btn_style,
        )
        self.mode_btn.pack(side="right", padx=2)
        tk.Button(header, text="🔊 Replay", command=self.replay_audio, **btn_style).pack(side="right", padx=2)

        tk.Frame(self.hud_frame, bg="#21262d", height=1).pack(fill="x", pady=6)

        self.sub_lbl = tk.Label(
            self.hud_frame,
            text="",
            fg="#ffffff",
            bg="#0b0e14",
            font=("Segoe UI", 11),
            wraplength=620,
            justify="left",
            anchor="w",
        )
        self.sub_lbl.pack(fill="x")
        self.hud.withdraw()

    def _build_input_window(self):
        self.inp_win = tk.Toplevel(self.root)
        self.inp_win.overrideredirect(True)
        self.inp_win.attributes("-topmost", True)
        self.inp_win.configure(bg="#0b0e14")

        frame = tk.Frame(
            self.inp_win, bg="#0b0e14", highlightbackground="#00d2ff", highlightthickness=1, padx=14, pady=12
        )
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame, text="⚡ Jarvis", fg="#00d2ff", bg="#0b0e14", font=("Consolas", 11, "bold")
        ).pack(side="left", padx=(0, 10))

        self.entry = tk.Entry(
            frame,
            bg="#161b22",
            fg="#ffffff",
            insertbackground="#00d2ff",
            relief="flat",
            font=("Segoe UI", 12),
            width=44,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", self.on_submit)
        self.entry.bind("<Escape>", lambda e: self.inp_win.withdraw())
        self.inp_win.withdraw()

    def toggle_input_bar(self):
        if self.inp_win.state() == "normal":
            self.inp_win.withdraw()
        else:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w, h = 540, 56
            x = (sw - w) // 2
            y = int(sh * 0.28)
            self.inp_win.geometry(f"{w}x{h}+{x}+{y}")
            self.inp_win.deiconify()
            self.inp_win.lift()
            self.entry.delete(0, "end")
            self.entry.focus_force()

    def on_submit(self, _event=None):
        query = self.entry.get().strip()
        self.inp_win.withdraw()
        if query:
            threading.Thread(target=self.process_query, args=(query,), daemon=True).start()

    def show_hud(self, text: str, status: str | None = None, duration_ms: int = 12000):
        self.sub_lbl.configure(text=text)
        default_status = "VOICE + HUD" if JARVIS_VOICE_ENABLED else "TEXT ONLY"
        self.status_lbl.configure(text=status or default_status)
        self.hud.update_idletasks()
        sw = self.root.winfo_screenwidth()
        w = max(480, min(680, self.hud.winfo_reqwidth()))
        h = self.hud.winfo_reqheight()
        x = (sw - w) // 2
        self.hud.geometry(f"{w}x{h}+{x}+14")
        self.hud.deiconify()
        self.hud.lift()

        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        if not self.pinned:
            self.hide_job = self.root.after(duration_ms, self.hide_hud)

    def hide_hud(self):
        self.pinned = False
        self.pin_btn.configure(text="📌 Pin")
        self.hud.withdraw()
        if HAS_PYGAME and pygame.mixer.get_init():
            pygame.mixer.music.stop()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.pin_btn.configure(text="📌 Pinned" if self.pinned else "📌 Pin")
        if self.pinned and self.hide_job:
            self.root.after_cancel(self.hide_job)

    def copy_text(self):
        if HAS_PYPERCLIP:
            pyperclip.copy(self.last_text)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_text)

    def toggle_voice(self):
        global JARVIS_VOICE_ENABLED
        JARVIS_VOICE_ENABLED = not JARVIS_VOICE_ENABLED
        set_key(str(ENV_FILE), "JARVIS_VOICE_ENABLED", "1" if JARVIS_VOICE_ENABLED else "0")
        self.mode_btn.configure(text="🎙️ Voice ON" if JARVIS_VOICE_ENABLED else "💬 Text Only")
        if not JARVIS_VOICE_ENABLED and HAS_PYGAME and pygame.mixer.get_init():
            pygame.mixer.music.stop()

    def replay_audio(self):
        threading.Thread(target=self._speak_worker, args=(self.last_text, True), daemon=True).start()

    def _speak_worker(self, text: str, force: bool = False):
        if not (JARVIS_VOICE_ENABLED or force):
            return
        try:
            if HAS_PYGAME and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            asyncio.run(
                edge_tts.Communicate(
                    text, JARVIS_VOICE, rate=JARVIS_VOICE_RATE, pitch=JARVIS_VOICE_PITCH
                ).save(str(SPEECH_MP3))
            )
            if HAS_PYGAME and pygame.mixer.get_init():
                pygame.mixer.music.load(str(SPEECH_MP3))
                pygame.mixer.music.play()
        except Exception:
            pass

    def finish_reply(self, text: str, force_speak: bool = False):
        cleaned = clean_jarvis_text(text)
        self.last_text = cleaned
        est_ms = max(10000, min(22000, len(cleaned) * 120))
        self.root.after(0, lambda: self.show_hud(cleaned, duration_ms=est_ms))
        self._speak_worker(cleaned, force=force_speak)

    def stream_llm(self, messages: list[dict], tools_list=None) -> tuple[str, list[dict]]:
        last_err = None
        for client_obj, kw in _get_provider_candidates(tools_list):
            try:
                stream = client_obj.chat.completions.create(messages=messages, stream=True, **kw)
                acc = ""
                tc_map: dict[int, dict] = {}
                last_ui = 0.0
                for chunk in stream:
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    if getattr(delta, "tool_calls", None):
                        for tc in delta.tool_calls:
                            idx = getattr(tc, "index", 0) or 0
                            entry = tc_map.setdefault(idx, {"name": "", "arguments": ""})
                            if getattr(tc, "function", None):
                                if tc.function.name:
                                    entry["name"] += tc.function.name
                                if tc.function.arguments:
                                    entry["arguments"] += tc.function.arguments
                    piece = getattr(delta, "content", None)
                    if piece:
                        acc += piece
                        now = time.time()
                        if now - last_ui >= 0.08:
                            partial = clean_jarvis_text(acc, allow_empty=True)
                            if partial:
                                self.root.after(
                                    0,
                                    lambda p=partial: self.show_hud(p + " ▍", status="STREAMING...", duration_ms=18000),
                                )
                                last_ui = now
                tcs = [tc_map[i] for i in sorted(tc_map.keys()) if tc_map[i]["name"]]
                if acc.strip() or tcs:
                    return clean_jarvis_text(acc), tcs
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(last_err or "All AI providers timed out")

    def run_windows_action(self, action: str) -> str:
        if action == "battery":
            if HAS_PSUTIL and psutil.sensors_battery():
                b = psutil.sensors_battery()
                state = "charging" if b.power_plugged else "discharging"
                return f"Battery is at {int(b.percent)} percent and {state}, sir."
            return "Running on desktop AC power, sir."
        elif action == "media_play_pause":
            ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
            return "Toggled media playback, sir."
        elif action == "media_next":
            ctypes.windll.user32.keybd_event(0xB0, 0, 0, 0)
            return "Skipped to the next track, sir."
        elif action == "media_prev":
            ctypes.windll.user32.keybd_event(0xB1, 0, 0, 0)
            return "Returned to the previous track, sir."
        elif action == "fix_clipboard":
            clip = pyperclip.paste() if HAS_PYPERCLIP else ""
            if not clip.strip():
                return "Your clipboard is currently empty, sir."
            text, _ = self.stream_llm(
                [
                    {
                        "role": "system",
                        "content": "Fix any code, config, or grammar in the user's text. Output ONLY the corrected text.",
                    },
                    {"role": "user", "content": clip},
                ]
            )
            if HAS_PYPERCLIP:
                pyperclip.copy(text)
            return "I have repaired your clipboard contents, sir. Press Ctrl+V to paste."
        elif action == "unread_gmail":
            if not GMAIL_USER or not GMAIL_APP_PASS or "xxxx" in GMAIL_APP_PASS:
                return "Gmail App Password is not configured in .env yet, sir."
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(GMAIL_USER, GMAIL_APP_PASS)
                mail.select("inbox")
                _, messages = mail.search(None, '(UNSEEN X-GM-RAW "category:primary")')
                ids = messages[0].split()[-3:]
                if not ids:
                    mail.logout()
                    return "You have no unread emails in your primary inbox, sir."
                subjects = []
                for e_id in reversed(ids):
                    _, data = mail.fetch(e_id, "(RFC822)")
                    msg = email.message_from_bytes(data[0][1])
                    sender = decode_mime_str(msg.get("From") or "Unknown").split("<")[0].strip().strip('"')
                    subj = decode_mime_str(msg.get("Subject") or "(No Subject)")
                    subjects.append(f"{subj} from {sender}")
                mail.logout()
                return "Sir, your latest unread emails are: " + "; ".join(subjects)
            except Exception as e:
                return f"Gmail check failed, sir: {e}"
        elif action == "toggle_voice_mode":
            self.root.after(0, self.toggle_voice)
            return "Toggled voice mode, sir."
        return "Action completed, sir."

    def process_query(self, prompt: str):
        self.root.after(0, lambda: self.show_hud(f'"{prompt}"', status="THINKING...", duration_ms=16000))
        q = prompt.lower().strip().rstrip("?.!")

        # Weather fast path
        m = re.search(r"\b(?:weather|wether|temperature|forecast)\s+(?:in|at|for)\s+([a-zA-Z\s,]+)$", q)
        if m:
            loc = m.group(1).strip()
            try:
                req = urllib.request.Request(
                    f"https://wttr.in/{urllib.parse.quote(loc)}?format=j1",
                    headers={"User-Agent": "curl/8.0"},
                )
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                cur = data["current_condition"][0]
                temp_c = cur.get("temp_C", "")
                desc = cur.get("weatherDesc", [{}])[0].get("value", "clear")
                self.finish_reply(f"Sir, it is currently {temp_c} degrees Celsius and {desc.lower()} in {loc.title()}.")
                return
            except Exception:
                pass

        # Screen reading
        if any(k in q for k in ("screen", "screenshot", "on my display", "what am i looking at")) and HAS_PIL:
            try:
                self.root.after(0, self.hud.withdraw)
                time.sleep(0.2)
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
                self.root.after(0, lambda: self.show_hud("Inspecting your screen, sir...", status="VISION SCAN..."))
                ans, _ = self.stream_llm(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                            ],
                        },
                    ]
                )
                self.finish_reply(ans)
                return
            except Exception as e:
                self.finish_reply(f"Could not capture screen, sir: {e}")
                return

        try:
            needs_tools = any(
                k in q
                for k in (
                    "battery", "clipboard", "email", "gmail", "send ", "voice",
                    "play", "pause", "next", "previous", "track", "search", "web",
                    "google", "news", "price", "latest", "open ", "browser",
                )
            )
            ans, tool_calls = self.stream_llm(
                [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                tools_list=tools if needs_tools else None,
            )
            if tool_calls:
                for call in tool_calls:
                    fn = call["name"]
                    args = json.loads(call["arguments"] or "{}")
                    if fn == "web_search":
                        sq = args.get("query", prompt)
                        if args.get("open_in_browser"):
                            webbrowser.open(f"https://duckduckgo.com/?q={urllib.parse.quote_plus(sq)}")
                        results = list(DDGS().text(sq, max_results=3))
                        ctx = "\n".join(f"- {r.get('title','')}: {r.get('body','')}" for r in results)
                        summary, _ = self.stream_llm(
                            [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": f"Question: {sq}\nResults:\n{ctx}\nSummarize in 1-2 spoken sentences."},
                            ]
                        )
                        self.finish_reply(summary)
                    elif fn == "system_action":
                        self.finish_reply(self.run_windows_action(args["action"]))
                    elif fn == "change_voice":
                        global JARVIS_VOICE
                        pk = args["voice_preset"].lower()
                        if pk in VOICE_PRESETS:
                            JARVIS_VOICE, label = VOICE_PRESETS[pk]
                            set_key(str(ENV_FILE), "JARVIS_VOICE", JARVIS_VOICE)
                            self.finish_reply(f"Voice calibration complete, sir. Now using {label}.", force_speak=True)
                    elif fn == "send_email":
                        msg = EmailMessage()
                        msg["From"] = GMAIL_USER
                        msg["To"] = args["to_address"]
                        msg["Subject"] = args["subject"]
                        msg.set_content(args["body"])
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
                            smtp.send_message(msg)
                        self.finish_reply(f"Email sent to {args['to_address']}, sir.")
            else:
                self.finish_reply(ans)
        except Exception as e:
            self.finish_reply(f"Sir, the AI server timed out: {e}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    JarvisWindowsApp().run()
