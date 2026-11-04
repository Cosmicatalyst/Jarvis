#!/home/cosmic/jarvis/venv/bin/python
import asyncio
import base64
import email
import imaplib
import json
import os
import re
import smtplib
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv, set_key
from openai import OpenAI
import edge_tts
from ddgs import DDGS

# Load the .env file from the exact directory where this script lives
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
JARVIS_HUD_FILTER = os.getenv("JARVIS_HUD_FILTER", "1").strip() == "1"
JARVIS_VOICE_ENABLED = os.getenv("JARVIS_VOICE_ENABLED", "1").strip() == "1"

SUBTITLE_FILE = Path.home() / ".cache" / "43pr" / "jarvis-subtitle.json"
SPEECH_MP3 = Path(tempfile.gettempdir()) / "jarvis_speech.mp3"
LAST_TEXT_FILE = Path(tempfile.gettempdir()) / "jarvis_last_text.txt"

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
    "running on the user's Arch Linux Hyprland system. Address the user politely as 'sir'. "
    "CRITICAL RULES:\n"
    "1. Reply in 1 to 2 crisp, natural spoken sentences ONLY.\n"
    "2. NEVER include internal reasoning, chain-of-thought notes, bullet headers like '**Greeting**:', or markdown formatting (*, **, #, `).\n"
    "3. Output ONLY the final words Jarvis speaks out loud."
)

EXTRA_FAST_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

# Strict 5.5s connection/read timeout + 0 retries on TNSA so Cloudflare 524 outages never freeze Jarvis
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


def _get_provider_candidates(tools_list: list[dict] | None = None):
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


def call_llm(messages: list[dict], tools_list: list[dict] | None = None):
    """Non-streaming fallback helper when needed."""
    last_err = None
    for client_obj, kw in _get_provider_candidates(tools_list):
        try:
            return client_obj.chat.completions.create(messages=messages, **kw)
        except Exception as e:
            last_err = e
    raise RuntimeError(last_err or "All AI providers failed")


def stream_llm_to_hud(
    messages: list[dict], tools_list: list[dict] | None = None
) -> tuple[str, list[dict]]:
    """
    Streams tokens live from the LLM into the top-center Quickshell HUD card and terminal.
    Returns (final_cleaned_text, tool_calls_list).
    """
    last_err = None
    for client_obj, kw in _get_provider_candidates(tools_list):
        try:
            stream = client_obj.chat.completions.create(
                messages=messages, stream=True, **kw
            )
            accumulated_text = ""
            tool_calls_by_idx: dict[int, dict] = {}
            last_hud_update = 0.0
            printed_prefix = False

            for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta

                # 1. Collect streamed tool calls if any
                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0) or 0
                        entry = tool_calls_by_idx.setdefault(
                            idx, {"name": "", "arguments": ""}
                        )
                        if getattr(tc, "function", None):
                            if tc.function.name:
                                entry["name"] += tc.function.name
                            if tc.function.arguments:
                                entry["arguments"] += tc.function.arguments

                # 2. Collect streamed text tokens and update HUD live
                piece = getattr(delta, "content", None)
                if piece:
                    if not printed_prefix:
                        sys.stdout.write("⚡ Jarvis: ")
                        printed_prefix = True
                    sys.stdout.write(piece)
                    sys.stdout.flush()
                    accumulated_text += piece

                    now = time.time()
                    if now - last_hud_update >= 0.08:
                        partial_clean = clean_jarvis_text(accumulated_text, allow_empty=True)
                        if partial_clean:
                            set_hud_card(
                                partial_clean + " ▍",
                                active=True,
                                thinking=True,
                                status="STREAMING...",
                                duration_ms=18000,
                            )
                            last_hud_update = now

            if printed_prefix:
                sys.stdout.write("\n")
                sys.stdout.flush()

            tool_calls = [
                tool_calls_by_idx[i]
                for i in sorted(tool_calls_by_idx.keys())
                if tool_calls_by_idx[i]["name"]
            ]
            if accumulated_text.strip() or tool_calls:
                return clean_jarvis_text(accumulated_text), tool_calls
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(last_err or "All streaming AI providers timed out")


tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live internet ONLY when the user explicitly asks to search the web or asks about live current events, weather, or news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up on the live web",
                    },
                    "open_in_browser": {
                        "type": "boolean",
                        "description": "Set to true ONLY if the user explicitly asks to open the search or website in their browser",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_action",
            "description": (
                "Run local Arch Linux / Hyprland / Quickshell actions, control media, "
                "toggle desktop theme/panels, toggle voice/text mode, fix clipboard text, check unread Gmail, or open the voice selector menu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "battery",
                            "updates",
                            "fix_clipboard",
                            "unread_gmail",
                            "media_play_pause",
                            "media_next",
                            "media_prev",
                            "toggle_theme",
                            "toggle_bar",
                            "toggle_todo",
                            "voice_menu",
                            "toggle_voice_mode",
                        ],
                        "description": "The system action to run",
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
            "description": "Switch Jarvis's neural TTS voice to one of the presets (ryan, thomas, friday, brian, christopher, ava, prabhat, neerja).",
            "parameters": {
                "type": "object",
                "properties": {
                    "voice_preset": {
                        "type": "string",
                        "enum": list(VOICE_PRESETS.keys()),
                        "description": "The voice preset key to switch to",
                    }
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
                    "to_address": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain text email body",
                    },
                },
                "required": ["to_address", "subject", "body"],
            },
        },
    },
]


def clean_jarvis_text(raw: str | None, allow_empty: bool = False) -> str:
    """Strips leaked chain-of-thought reasoning blocks and markdown symbols so TTS speaks cleanly."""
    if not raw:
        return "" if allow_empty else "At your service, sir."
    text = raw.strip()
    # Strip complete <think>...</think> blocks, or an unclosed <think>... during streaming
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
        if any(
            meta in s.lower()
            for meta in [
                "user is saying",
                "user is asking",
                "i'll respond with",
                "staying in character",
                "one or two spoken sentences",
                "no markdown",
            ]
        ):
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
    if allow_empty:
        return text
    return text or "At your service, sir."


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


def set_hud_card(
    text: str,
    active: bool = True,
    thinking: bool = False,
    status: str | None = None,
    duration_ms: int = 12000,
) -> None:
    try:
        SUBTITLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_status = (
            "ANALYZING..."
            if thinking
            else ("VOICE + HUD" if JARVIS_VOICE_ENABLED else "TEXT ONLY")
        )
        payload = {
            "text": text,
            "active": active,
            "thinking": thinking,
            "voiceEnabled": JARVIS_VOICE_ENABLED,
            "status": status or default_status,
            "durationMs": duration_ms,
            "ts": int(time.time() * 1000),
        }
        SUBTITLE_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def play_speech_async(text: str, voice: str | None = None) -> None:
    """Synthesizes and plays speech in a detached background process so the text box appears immediately."""
    chosen_voice = voice or JARVIS_VOICE
    af_arg = (
        "--af='lavfi=[aecho=0.8:0.88:10:0.12,highpass=f=100,treble=g=2]'"
        if JARVIS_HUD_FILTER
        else ""
    )
    subprocess.run(
        ["pkill", "-f", "mpv.*jarvis_speech"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    helper_code = (
        "import asyncio, subprocess, edge_tts, sys\n"
        "text, voice, rate, pitch, mp3 = sys.argv[1:6]\n"
        "try:\n"
        "    asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(mp3))\n"
        f"    subprocess.run(f'mpv --no-video --really-quiet {af_arg} \"{{mp3}}\"', shell=True)\n"
        "except Exception:\n"
        "    subprocess.run(['espeak-ng', '-s', '175', text])\n"
    )
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            helper_code,
            text,
            chosen_voice,
            JARVIS_VOICE_RATE,
            JARVIS_VOICE_PITCH,
            str(SPEECH_MP3),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def notify_and_speak(raw_text: str, force_speak: bool = False, already_printed: bool = False) -> None:
    text = clean_jarvis_text(raw_text)
    if not already_printed:
        print(f"⚡ Jarvis: {text}")
    try:
        LAST_TEXT_FILE.write_text(text, encoding="utf-8")
    except Exception:
        pass

    est_ms = max(10000, min(22000, len(text) * 120))
    set_hud_card(text, active=True, thinking=False, duration_ms=est_ms)

    if JARVIS_VOICE_ENABLED or force_speak:
        play_speech_async(text)


def replay_last_speech() -> None:
    if not LAST_TEXT_FILE.exists():
        notify_and_speak("No previous message to replay, sir.", force_speak=True)
        return
    last_text = LAST_TEXT_FILE.read_text(encoding="utf-8").strip()
    if not last_text:
        return
    set_hud_card(last_text, active=True, thinking=False, status="REPLAYING AUDIO", duration_ms=14000)
    play_speech_async(last_text)


def toggle_voice_mode() -> str:
    global JARVIS_VOICE_ENABLED
    JARVIS_VOICE_ENABLED = not JARVIS_VOICE_ENABLED
    set_key(str(ENV_FILE), "JARVIS_VOICE_ENABLED", "1" if JARVIS_VOICE_ENABLED else "0")
    if not JARVIS_VOICE_ENABLED:
        subprocess.run(
            ["pkill", "-f", "mpv.*jarvis_speech"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "Switched to silent text-box mode, sir. Click Replay anytime to hear a message."
    return "Voice mode restored, sir. Audio systems online."


def fetch_fast_weather(location: str) -> str | None:
    """0.4s instant weather lookup via wttr.in JSON API."""
    try:
        loc_enc = urllib.parse.quote(location.strip())
        req = urllib.request.Request(
            f"https://wttr.in/{loc_enc}?format=j1",
            headers={"User-Agent": "curl/8.0"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cur = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        city = area.get("areaName", [{}])[0].get("value", location.title())
        country = area.get("country", [{}])[0].get("value", "")
        temp_c = cur.get("temp_C", "")
        feels_c = cur.get("FeelsLikeC", "")
        desc = cur.get("weatherDesc", [{}])[0].get("value", "clear")
        place = f"{city}, {country}" if country and country.lower() not in city.lower() else city
        return f"Sir, it is currently {temp_c} degrees Celsius and {desc.lower()} in {place}, feeling like {feels_c} degrees."
    except Exception:
        return None


def analyze_screen(question: str, select_region: bool = False) -> None:
    shot_path = Path(tempfile.gettempdir()) / "jarvis_screen.png"
    try:
        set_hud_card("", active=False)
        time.sleep(0.15)
        if select_region:
            geom = subprocess.getoutput("slurp 2>/dev/null").strip()
            if not geom:
                notify_and_speak("Screen region selection was cancelled, sir.")
                return
            subprocess.run(["grim", "-g", geom, str(shot_path)], check=True)
        else:
            subprocess.run(["grim", str(shot_path)], check=True)

        set_hud_card("Inspecting your screen now, sir...", active=True, thinking=True, status="VISION SCANNING...")
        b64_img = base64.b64encode(shot_path.read_bytes()).decode("utf-8")

        final_text, _ = stream_llm_to_hud(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{question}\nReply in 1 to 3 clear, concise sentences with no markdown or asterisks.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_img}"},
                        },
                    ],
                },
            ]
        )
        notify_and_speak(final_text, already_printed=True)
    except Exception as e:
        notify_and_speak(f"I could not capture or read your screen, sir: {e}")


def perform_web_search(query: str, open_in_browser: bool = False) -> None:
    set_hud_card(f"Searching the web for '{query}', sir...", active=True, thinking=True, status="WEB SEARCH...")
    if open_in_browser:
        url = f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}"
        subprocess.Popen(
            ["brave", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        results = list(DDGS().text(query, max_results=3))
        if not results:
            notify_and_speak(f"No web results found for '{query}', sir.")
            return
        snippets = [f"- {r.get('title', '')}: {r.get('body', '')}" for r in results]
        context = "\n".join(snippets)

        try:
            final_text, _ = stream_llm_to_hud(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"User asked: {query}\n\n"
                            f"Live web search results:\n{context}\n\n"
                            "Answer the user's question directly in 1 to 2 spoken sentences as Jarvis (no markdown, no asterisks)."
                        ),
                    },
                ]
            )
            notify_and_speak(final_text, already_printed=True)
        except Exception:
            top = results[0]
            notify_and_speak(f"According to web results, sir: {top.get('body', top.get('title', ''))}")
    except Exception as e:
        notify_and_speak(f"I encountered an issue searching the web, sir: {e}")


def switch_voice_preset(preset_key: str) -> str:
    global JARVIS_VOICE
    preset_key = preset_key.lower().strip()
    if preset_key not in VOICE_PRESETS:
        return f"Unknown voice preset '{preset_key}', sir."
    voice_id, label = VOICE_PRESETS[preset_key]
    JARVIS_VOICE = voice_id
    set_key(str(ENV_FILE), "JARVIS_VOICE", voice_id)
    return f"Voice calibration complete, sir. Now using {label}."


def open_voice_menu() -> None:
    mode_label = (
        "🔇 Switch to Text-Only Mode (Mute Voice)"
        if JARVIS_VOICE_ENABLED
        else "🎙️ Switch to Voice + HUD Mode (Enable Voice)"
    )
    options = [f"mode  ·  {mode_label}"]
    for key, (voice_id, label) in VOICE_PRESETS.items():
        marker = "★ " if voice_id == JARVIS_VOICE else "  "
        options.append(f"{marker}{key}  ·  {label}")
    menu_input = "\n".join(options)
    res = subprocess.run(
        [
            "rofi",
            "-dmenu",
            "-i",
            "-p",
            "🎙️ Jarvis Audio",
            "-theme-str",
            "window {width: 580px; height: 360px;}",
        ],
        input=menu_input,
        text=True,
        capture_output=True,
    )
    choice = res.stdout.strip()
    if not choice:
        return
    key = choice.replace("★", "").strip().split()[0].strip()
    if key == "mode":
        msg = toggle_voice_mode()
        notify_and_speak(msg)
    else:
        msg = switch_voice_preset(key)
        notify_and_speak(msg, force_speak=True)


def check_gmail() -> str:
    if not GMAIL_USER or not GMAIL_APP_PASS or "xxxx" in GMAIL_APP_PASS or "your_email" in GMAIL_USER:
        return "Gmail App Password is not configured in ~/jarvis/.env yet, sir."
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


def send_quick_email(to_address: str, subject: str, body: str) -> str:
    if not GMAIL_USER or not GMAIL_APP_PASS:
        return "Gmail credentials are not configured in ~/jarvis/.env, sir."
    try:
        msg = EmailMessage()
        msg["From"] = GMAIL_USER
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.send_message(msg)
        return f"Email sent to {to_address} with subject {subject}, sir."
    except Exception as e:
        return f"Failed to send email, sir: {e}"


def run_tool(action: str) -> str | None:
    home = str(Path.home())
    if action == "battery":
        cap = subprocess.getoutput(
            "cat /sys/class/power_supply/BAT*/capacity 2>/dev/null || echo 'Desktop'"
        ).strip()
        status = subprocess.getoutput(
            "cat /sys/class/power_supply/BAT*/status 2>/dev/null || echo ''"
        ).strip()
        if cap == "Desktop":
            return "Running on desktop power, sir."
        return f"Battery is at {cap} percent and {status.lower()}, sir."
    elif action == "updates":
        count = subprocess.getoutput(
            "(checkupdates 2>/dev/null || pacman -Qu 2>/dev/null) | wc -l"
        ).strip()
        return f"You have {count} pending Arch package updates, sir."
    elif action == "fix_clipboard":
        set_hud_card("Repairing your clipboard contents, sir...", active=True, thinking=True, status="CLIPBOARD AI")
        clip = subprocess.getoutput("wl-paste")
        if not clip.strip():
            return "Your clipboard is currently empty, sir."
        res = call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Fix any code, config, or grammar in the user's text. "
                        "Output ONLY the corrected text with no markdown fences or explanation."
                    ),
                },
                {"role": "user", "content": clip},
            ]
        )
        fixed = (res.choices[0].message.content or "").strip()
        subprocess.run(["wl-copy"], input=fixed.encode("utf-8"))
        return "I have repaired your clipboard contents, sir. Ready to paste."
    elif action == "unread_gmail":
        set_hud_card("Checking your primary Gmail inbox, sir...", active=True, thinking=True, status="GMAIL SYNC")
        return check_gmail()
    elif action == "media_play_pause":
        subprocess.run(["playerctl", "play-pause"])
        return "Toggled media playback, sir."
    elif action == "media_next":
        subprocess.run(["playerctl", "next"])
        return "Skipped to the next track, sir."
    elif action == "media_prev":
        subprocess.run(["playerctl", "previous"])
        return "Returned to the previous track, sir."
    elif action == "toggle_theme":
        subprocess.Popen(["python3", f"{home}/.config/43pr/bin/theme.py", "toggle"])
        return "Toggled your desktop theme, sir."
    elif action == "toggle_bar":
        subprocess.Popen(["qs", "ipc", "call", "bar", "toggle"])
        return "Toggled the Quickshell bar, sir."
    elif action == "toggle_todo":
        subprocess.Popen(["qs", "ipc", "call", "todo", "toggle"])
        return "Toggled your Todo panel, sir."
    elif action == "voice_menu":
        open_voice_menu()
        return None
    elif action == "toggle_voice_mode":
        return toggle_voice_mode()
    return "Done, sir."


def try_instant_local_shortcut(prompt: str) -> str | None:
    """0.01s zero-latency local matcher for common system commands & weather."""
    q = prompt.lower().strip().rstrip("?.!")
    if q in {"battery", "battery level", "check battery", "what is my battery", "whats my battery", "what's my battery", "what is my battery level"}:
        return run_tool("battery")
    if q in {"updates", "check updates", "system updates", "arch updates"}:
        return run_tool("updates")
    if q in {"toggle theme", "switch theme", "dark mode", "light mode"}:
        return run_tool("toggle_theme")
    if q in {"play", "pause", "play pause", "toggle media"}:
        return run_tool("media_play_pause")
    if q in {"next", "next track", "skip", "skip track"}:
        return run_tool("media_next")
    if q in {"previous", "prev", "previous track"}:
        return run_tool("media_prev")
    if q in {"unread emails", "check email", "check emails", "check my emails", "check my unread emails", "unread gmail"}:
        return run_tool("unread_gmail")
    if q in {"fix clipboard", "fix my clipboard"}:
        return run_tool("fix_clipboard")
    if q in {"text mode", "silent mode", "mute voice", "voice mode", "toggle voice"}:
        return toggle_voice_mode()

    m = re.search(r"\b(?:weather|wether|temperature|forecast)\s+(?:in|at|for)\s+([a-zA-Z\s,]+)$", q)
    if m:
        loc = m.group(1).strip()
        set_hud_card(f"Checking live weather in {loc.title()}, sir...", active=True, thinking=True, status="WEATHER SCAN")
        w = fetch_fast_weather(loc)
        if w:
            return w
    return None


def needs_action_tools(prompt: str) -> bool:
    """Only attach function-calling tools when the prompt mentions an action, search, or email."""
    q = prompt.lower()
    keywords = (
        "battery", "update", "clipboard", "email", "gmail", "inbox", "mail", "send ",
        "theme", "dark mode", "light mode", "bar", "todo", "voice", "play", "pause",
        "next", "previous", "track", "music", "song", "search", "web", "google",
        "weather", "wether", "news", "price", "latest", "open ", "browser",
    )
    return any(k in q for k in keywords)


def is_screen_query(prompt: str) -> tuple[bool, bool]:
    """Returns (is_screen_request, select_region) strictly when the user asks about their screen."""
    q = prompt.lower()
    if any(k in q for k in ("screen", "screenshot", "on my display", "what am i looking at")):
        select_region = any(r in q for r in ("region", "area", "select", "crop"))
        return True, select_region
    return False, False


def ask_jarvis(prompt: str) -> None:
    low = prompt.lower().strip()
    if low in {"--voice-menu", "voice menu", "voices"}:
        open_voice_menu()
        return
    if low == "--replay":
        replay_last_speech()
        return
    if low == "--toggle-voice":
        msg = toggle_voice_mode()
        set_hud_card(msg, active=True, thinking=False, duration_ms=9000)
        return
    if low == "--read-screen-region":
        analyze_screen("Explain or solve what is shown in this selected screen region.", select_region=True)
        return

    # 1. Check 0.01s instant local shortcuts & weather first
    instant = try_instant_local_shortcut(prompt)
    if instant is not None:
        notify_and_speak(instant)
        return

    # 2. Check if the user is explicitly asking Jarvis to read their screen
    screen_req, select_reg = is_screen_query(prompt)
    if screen_req:
        analyze_screen(prompt, select_region=select_reg)
        return

    # 3. Show immediate "Thinking..." card in top-center HUD
    set_hud_card(
        f'"{prompt}"',
        active=True,
        thinking=True,
        status="THINKING...",
        duration_ms=18000,
    )

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        tools_to_use = tools if needs_action_tools(prompt) else None
        final_text, tool_calls = stream_llm_to_hud(messages, tools_list=tools_to_use)

        if tool_calls:
            for call in tool_calls:
                fn_name = call["name"]
                args = json.loads(call["arguments"] or "{}")
                if fn_name == "web_search":
                    perform_web_search(
                        args.get("query", prompt), bool(args.get("open_in_browser", False))
                    )
                elif fn_name == "system_action":
                    result = run_tool(args["action"])
                    if result:
                        notify_and_speak(result)
                elif fn_name == "change_voice":
                    result = switch_voice_preset(args["voice_preset"])
                    notify_and_speak(result, force_speak=True)
                elif fn_name == "send_email":
                    result = send_quick_email(
                        args["to_address"], args["subject"], args["body"]
                    )
                    notify_and_speak(result)
                else:
                    notify_and_speak("Action completed, sir.")
        else:
            notify_and_speak(final_text or "At your service, sir.", already_printed=True)
    except Exception as e:
        notify_and_speak(f"Sir, the AI server timed out: {e}")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip()
    if query:
        ask_jarvis(query)
    else:
        print("⚡ Jarvis Interactive HUD (type 'voices' to change voice, 'exit' to close)")
        while True:
            try:
                user_in = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_in:
                continue
            if user_in.lower() in {"exit", "quit", "q"}:
                break
            ask_jarvis(user_in)
