import undetected_chromedriver as uc
import os, sys, time, random, subprocess, threading, shutil, re, gc, platform
from datetime import datetime
import requests

IS_LINUX = platform.system() == 'Linux'
IS_WINDOWS = platform.system() == 'Windows'

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
SCRIPT_DIR             = os.path.dirname(os.path.abspath(__file__))
TARGET_URL             = "https://mtacc.mobilelegends.com"
ABCK_FILE              = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abck.txt")
SERVER_HOST            = os.environ.get("TOKEN_SERVER_HOST", "0.0.0.0")
SERVER_PORT            = os.environ.get("TOKEN_SERVER_PORT", "5050")
SERVER_URL             = f"http://{SERVER_HOST}:{SERVER_PORT}"
SERVER_SAVE_ENDPOINT   = f"{SERVER_URL}/api/save-token"
NUM_BROWSERS           = 5
MAX_TOKENS_PER_BROWSER = 15         # More tokens per browser, reduce relaunches
MAX_CONSECUTIVE_FAILS  = 5          # More patient before relaunch
SOLVE_TIMEOUT          = 45         # VPS needs more time
CHECK_INTERVAL         = 0.12
DELAY_BETWEEN_TOKENS   = (0.3, 0.8) # More human-like
DELAY_BROWSER_RELAUNCH = (1.0, 2.0)
DEFAULT_TOKEN_COUNT    = 50
MAX_TOKENS_IN_MEMORY   = 5000       # Token limit in RAM for dedup
CLEANUP_INTERVAL       = 100        # Cleanup temp Chrome every N tokens
SAVE_TO_FILE           = False      # Default: RAM only, enable with --save-file
WIN_W, WIN_H           = 1280, 720  # Realistic size, Akamai checks window size
WIN_GAP, WIN_TOP       = 10, 30
BROWSER_POSITIONS      = [
    (0,                           0),
]

# ═══════════════════════════════════════════════════════════════════
# ANSI COLOR SYSTEM
# ═══════════════════════════════════════════════════════════════════
RST   = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
ITAL  = "\033[3m"
UNDER = "\033[4m"

def fg(n): return f"\033[38;5;{n}m"
def bg(n): return f"\033[48;5;{n}m"
def rgb(r,g,b): return f"\033[38;2;{r};{g};{b}m"
def bgrgb(r,g,b): return f"\033[48;2;{r};{g};{b}m"

# Color palette — neon cyberpunk
C_CYAN    = rgb(0, 230, 255)
C_AZURE   = rgb(0, 150, 255)
C_GOLD    = rgb(255, 200, 0)
C_AMBER   = rgb(255, 160, 0)
C_LIME    = rgb(57, 255, 138)
C_MINT    = rgb(100, 255, 200)
C_ROSE    = rgb(255, 100, 180)
C_VIOLET  = rgb(180, 130, 255)
C_TEAL    = rgb(0, 210, 200)
C_ORANGE  = rgb(255, 140, 0)
C_RED     = rgb(255, 50, 80)
C_GREEN   = rgb(57, 255, 100)
C_WHITE   = rgb(235, 240, 250)
C_SILVER  = rgb(180, 190, 210)
C_GRAY    = rgb(120, 135, 160)
C_MUTED   = rgb(60, 70, 90)
C_DARK    = rgb(30, 35, 50)

# Gradient presets
GRAD_CYAN  = [rgb(0,180,255), rgb(0,210,240), rgb(0,235,220), rgb(50,255,180), rgb(57,255,138)]
GRAD_GOLD  = [rgb(255,100,50), rgb(255,150,0), rgb(255,200,0), rgb(255,230,50)]
GRAD_NEON  = [rgb(0,150,255), rgb(0,230,255), rgb(57,255,200), rgb(57,255,138)]

# Colors per browser
B_COLORS = [C_CYAN]
B_ICONS  = ["\u25c6"]
B_LABELS = ["CHROME\u00b71"]

_print_lock = threading.Lock()
_file_lock  = threading.Lock()

def strip_ansi(s):
    return re.sub(r'\033\[[^m]*m', '', s)

def tw():
    return shutil.get_terminal_size((110, 30)).columns

def cprint(msg):
    with _print_lock:
        print(msg)

def ts():
    return datetime.now().strftime("%H:%M:%S")

# ═══════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════


def hline(char="\u2500", col=C_MUTED, w=None):
    return f"{col}{char*(w or tw())}{RST}"

def center(text, w=None, pad=" "):
    width = w or tw()
    raw = strip_ansi(text)
    p = max(0, width - len(raw))
    return pad*(p//2) + text + pad*(p - p//2)

def rpad(text, width):
    raw = strip_ansi(text)
    return text + " " * max(0, width - len(raw))

def gradient_text(text, colors):
    if not text:
        return text
    out = []
    n = len(colors)
    for i, ch in enumerate(text):
        ci = int(i * (n - 1) / max(len(text) - 1, 1))
        out.append(f"{colors[ci]}{ch}")
    return "".join(out) + RST

def gradient_bar(width, chars="\u2588", grad=None):
    if grad is None:
        grad = GRAD_NEON
    out = []
    for i in range(width):
        ci = int(i * (len(grad) - 1) / max(width - 1, 1))
        out.append(f"{grad[ci]}{chars}")
    return "".join(out) + RST

def neon_box_top(w, col=C_CYAN):
    return f"{col}\u2554{'\u2550'*(w-2)}\u2557{RST}"

def neon_box_mid(w, col=C_CYAN):
    return f"{col}\u2560{'\u2550'*(w-2)}\u2563{RST}"

def neon_box_bot(w, col=C_CYAN):
    return f"{col}\u255a{'\u2550'*(w-2)}\u255d{RST}"

def neon_box_row(content, w, col=C_CYAN):
    raw = strip_ansi(content)
    pad = max(0, w - 4 - len(raw))
    return f"{col}\u2551{RST} {content}{' '*pad} {col}\u2551{RST}"

def progress_bar(current, total, w=30):
    pct = min(1.0, current / max(total, 1))
    filled = int(w * pct)
    empty  = w - filled
    bar_chars = ""
    for i in range(max(filled, 1)):
        ci = int(i * (len(GRAD_NEON) - 1) / max(filled - 1, 1))
        bar_chars += f"{GRAD_NEON[ci]}\u2588"
    if filled == 0:
        bar_chars = ""
    bar_chars += f"{C_MUTED}{'\u2591' * empty}{RST}"
    pct_str = f"{int(pct * 100):3d}%"
    return bar_chars, pct_str

# -- Logo ASCII art -- neon gradient --
def _make_logo():
    raw_lines = [
        "  \u2591\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2591\u2588\u2588\u2588\u2588\u2588\u2557\u2591 \u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2591 \u2588\u2588\u2557\u2591\u2591\u2588\u2588\u2557",
        "  \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557 \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557 \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557 \u2588\u2588\u2551\u2591\u2588\u2588\u2554\u255d",
        "  \u2588\u2588\u2551\u2591\u2591\u2588\u2588\u2551 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551 \u2588\u2588\u2588\u2588\u2588\u2588\u2566\u255d\u2591 \u2588\u2588\u2588\u2588\u2588\u2550\u255d\u2591",
        "  \u2588\u2588\u2551\u2591\u2591\u2588\u2588\u2551 \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551 \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557 \u2588\u2588\u2554\u2550\u2588\u2588\u2557\u2591",
        "  \u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d \u2588\u2588\u2551\u2591\u2591\u2588\u2588\u2551 \u2588\u2588\u2551\u2591\u2591\u2588\u2588\u2551 \u2588\u2588\u2551\u2591\u255a\u2588\u2588\u2557",
        "  \u255a\u2550\u2550\u2550\u2550\u2550\u255d\u2591 \u255a\u2550\u255d\u2591\u2591\u255a\u2550\u255d \u255a\u2550\u255d\u2591\u2591\u255a\u2550\u255d \u255a\u2550\u255d\u2591\u2591\u255a\u2550\u255d",
    ]
    grad = [
        rgb(0, 180, 255),
        rgb(0, 210, 245),
        rgb(0, 235, 230),
        rgb(30, 250, 200),
        rgb(50, 255, 160),
        rgb(57, 255, 120),
    ]
    return [f"{grad[i]}{BOLD}{line}{RST}" for i, line in enumerate(raw_lines)]

LOGO_LINES = _make_logo()

def print_banner():
    W = tw()
    PW = min(W, 80)
    print()
    print(center(gradient_bar(PW, "\u2550", GRAD_NEON), W))
    print(center(f"{C_MUTED}{'\u2500' * PW}{RST}", W))
    print()
    for line in LOGO_LINES:
        print(center(line, W))
    print()
    pill_bg = bgrgb(10, 15, 35)
    pill_bl = f"{C_CYAN}\u2590{RST}"
    pill_br = f"{C_CYAN}\u258c{RST}"
    pill = (
        f"{pill_bg}{C_RED}{BOLD} DARK {RST}"
        f"{pill_bg}{C_CYAN}{BOLD}ABCK GENERATOR {RST}"
        f"{pill_bg}{C_MUTED} \u00b7 {RST}"
        f"{pill_bg}{C_WHITE}1 CHROME{RST}"
        f"{pill_bg}{C_MUTED} \u00b7 {RST}"
        f"{pill_bg}{C_LIME}AKAMAI BYPASS{RST}"
        f"{pill_bg}{C_MUTED} \u00b7 {RST}"
        f"{pill_bg}{C_RED}{BOLD}TURBO MODE{RST}"
        f"{pill_bg}{C_MUTED} \u00b7 {RST}"
        f"{pill_bg}{C_GOLD}UNLIMITED{RST}"
    )
    print(center(f"{pill_bl}{pill}{pill_br}", W))
    print()
    credit = f"{C_MUTED}Powered by {C_RED}{BOLD}DARK ABCK GENERATOR{RST}"
    print(center(credit, W))
    print()
    print(center(f"{C_MUTED}{'\u2500' * PW}{RST}", W))
    print(center(gradient_bar(PW, "\u2550", GRAD_NEON), W))
    print()

def print_info_table(target_count, hidden, loop_forever, use_server, existing, chrome_ver):
    W  = tw()
    PW = min(W - 4, 76)

    title = f"{bgrgb(10,15,35)}{C_CYAN}{BOLD}  \u25c6  SESSION CONFIG  \u25c6  {RST}"
    print(center(title, W))
    print()

    def row(icon, label, value, val_col=C_WHITE):
        inner_w = PW - 4
        lpart = f" {icon}  {C_GRAY}{label}{RST}"
        vpart = f"{val_col}{BOLD}{value}{RST}"
        lraw  = strip_ansi(lpart)
        vraw  = strip_ansi(vpart)
        gap   = inner_w - len(lraw) - len(vraw)
        dots  = f"{C_MUTED}{'\u00b7' * max(1, gap - 1)}{RST}"
        content = f"{lpart}{dots} {vpart}"
        print(center(neon_box_row(content, PW, C_MUTED), W))

    def divrow(style="thin"):
        if style == "glow":
            inner = PW - 2
            print(center(f"{C_MUTED}\u2560{RST}{gradient_bar(inner, '\u2500', GRAD_NEON)}{C_MUTED}\u2563{RST}", W))
        else:
            print(center(neon_box_mid(PW, C_MUTED), W))

    def section_label(text):
        inner = PW - 4
        raw_t = strip_ansi(text)
        pad = inner - len(raw_t)
        left_pad = pad // 2
        right_pad = pad - left_pad
        content = f"{' ' * left_pad}{C_CYAN}{DIM}{text}{RST}{' ' * right_pad}"
        print(center(neon_box_row(content, PW, C_MUTED), W))

    print(center(neon_box_top(PW, C_MUTED), W))

    section_label("\u2500\u2500 NETWORK \u2500\u2500")
    row("\U0001f310", "Target",         TARGET_URL,                          C_CYAN)
    row("\U0001f4be", "Storage",        "RAM \u2192 Server (zero disk)" if not SAVE_TO_FILE else "RAM + Disk", C_LIME if not SAVE_TO_FILE else C_AMBER)
    row("\U0001f30d", "Server",         f"{'\u2713 ' + SERVER_URL if use_server else '\u2717 Disabled'}",
        C_GREEN if use_server else C_RED)

    divrow("glow")

    section_label("\u2500\u2500 GENERATOR \u2500\u2500")
    row("\U0001f3af", "Target",         "\u221e  UNLIMITED" if loop_forever else f"{target_count} tokens", C_GOLD)
    row("\U0001f511", "Existing",       f"{existing} tokens",                C_VIOLET)
    row("\U0001f9f9", "Disk Impact",    "ZERO \u2014 no writes" if not SAVE_TO_FILE else "Minimal", C_LIME if not SAVE_TO_FILE else C_AMBER)

    divrow("glow")

    section_label("\u2500\u2500 BROWSER \u2500\u2500")
    row("\U0001f5a5 ", "Instance",       "1\u00d7 Chrome (ANTI-RATELIMIT)",   C_AZURE)
    row("\U0001f4d0", "Window",         f"{WIN_W}\u00d7{WIN_H}px",               C_SILVER)
    row("\U0001f441 ", "Display",        "Off-screen" if hidden else "Visible", C_AMBER if hidden else C_GREEN)
    row("\U0001f504", "Auto Rotate",    f"/{MAX_TOKENS_PER_BROWSER} tok \u00b7 /{MAX_CONSECUTIVE_FAILS}\u00d7 fail", C_GRAY)
    row("\u2699 ", "Chrome",         f"v{chrome_ver}" if chrome_ver else "auto",  C_SILVER)

    print(center(neon_box_bot(PW, C_MUTED), W))
    print()

    hint_bg = bgrgb(20, 10, 10)
    hint = f"  {hint_bg}{C_AMBER}{DIM} \u2328  Ctrl+C to stop {RST}"
    print(center(hint, W))
    print()

def print_section_start():
    W = tw()
    PW = min(W, 80)
    print(center(gradient_bar(PW, "\u2550", GRAD_NEON), W))
    pill = f"{bgrgb(10,15,35)}{C_CYAN}{BOLD}  \u25b6  GENERATING  \u25c0  {RST}"
    print(center(pill, W))
    print(center(gradient_bar(PW, "\u2550", GRAD_NEON), W))
    print()

def print_done(generated, total, elapsed):
    W  = tw()
    PW = min(W - 4, 66)
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    rate = f"{generated / max(elapsed/60, 0.01):.1f}" if elapsed > 3 else "\u2014"

    print()
    print(center(gradient_bar(min(W,80), "\u2550", GRAD_GOLD), W))
    done_pill = f"{bgrgb(30,20,5)}{C_GOLD}{BOLD}  \U0001f3c1  COMPLETE  \U0001f3c1  {RST}"
    print(center(done_pill, W))
    print(center(gradient_bar(min(W,80), "\u2550", GRAD_GOLD), W))
    print()

    bar, pct = progress_bar(generated, max(generated, 1), 36)
    print(center(f"  {bar}  {C_GREEN}{BOLD}{pct}{RST}", W))
    print()

    def stat_card(icon, label, value, val_col):
        lbl = f"{C_GRAY}{label}{RST}"
        val = f"{val_col}{BOLD}{value}{RST}"
        return f"  {icon}  {lbl}  {val}"

    cards = [
        stat_card("\u2705", "Generated", str(generated), C_GREEN),
        stat_card("\U0001f4e6", "Total",     str(total),     C_GOLD),
        stat_card("\u23f1 ", "Time",      f"{mins}m {secs}s", C_AZURE),
        stat_card("\u26a1", "Rate",      f"{rate} tok/min",  C_LIME),
        stat_card("\U0001f4be", "Storage",   "RAM only" if not SAVE_TO_FILE else "File", C_TEAL),
    ]

    print(center(neon_box_top(PW, C_GOLD), W))
    for card in cards:
        print(center(neon_box_row(card, PW, C_GOLD), W))
    print(center(neon_box_bot(PW, C_GOLD), W))
    print()
    credit = f"{C_MUTED}Powered by {C_RED}{BOLD}DARK ABCK GENERATOR{RST}"
    print(center(credit, W))
    print()

# ═══════════════════════════════════════════════════════════════════
# LOG FUNCTIONS (per browser, colored)
# ═══════════════════════════════════════════════════════════════════

def _prefix(idx):
    col   = B_COLORS[idx % len(B_COLORS)]
    icon  = B_ICONS[idx % len(B_ICONS)]
    label = B_LABELS[idx % len(B_LABELS)]
    ts_   = f"{C_MUTED}{ts()}{RST}"
    tag_bg = bgrgb(10, 18, 40)
    tag   = f"{tag_bg}{col}{BOLD} {icon} {label} {RST}"
    return f"  {ts_} {tag}"

def log_info(idx, msg):
    cprint(f"{_prefix(idx)}  {C_GRAY}\u203a {msg}{RST}")

def log_status(idx, attempt, gen, fcount, remaining, slot):
    pre = _prefix(idx)
    slot_pct = min(1.0, slot / max(MAX_TOKENS_PER_BROWSER, 1))
    slot_filled = int(8 * slot_pct)
    slot_bar = f"{C_CYAN}{'\u25b0' * slot_filled}{C_MUTED}{'\u25b1' * (8 - slot_filled)}{RST}"
    parts = [
        f"{C_MUTED}#{attempt}{RST}",
        f"{C_GREEN}\u2b06{gen}{RST}",
        f"{C_GOLD}\u25c9{fcount}{RST}",
        f"{C_AZURE}\u25ce{remaining}{RST}",
        f"{slot_bar} {C_VIOLET}{slot}{C_MUTED}/{MAX_TOKENS_PER_BROWSER}{RST}",
    ]
    sep = f" {C_MUTED}\u2502{RST} "
    cprint(f"{pre}  {sep.join(parts)}")

def log_solving(idx, elapsed):
    frames = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]
    spin = frames[elapsed % len(frames)]
    ndots = (elapsed % 4) + 1
    dot_colors = [C_CYAN, C_TEAL, C_MINT, C_LIME]
    dots = "".join(f"{dot_colors[i % len(dot_colors)]}\u25cf" for i in range(ndots))
    trail = f"{C_MUTED}{'\u25cb' * (4 - ndots)}{RST}"
    bar_w = min(20, elapsed)
    wave = "".join(f"{GRAD_NEON[i % len(GRAD_NEON)]}\u2501" for i in range(bar_w))
    cprint(f"{_prefix(idx)}  {C_AMBER}{spin} Bypass Akamai {dots}{trail}  {wave}{RST}  {C_MUTED}{elapsed}s{RST}")

def log_success(idx, num, token, extra=""):
    pre = _prefix(idx)
    num_badge = f"{bgrgb(15,40,20)}{C_GREEN}{BOLD} \u2714 #{num} {RST}"
    tok_preview = f"{C_TEAL}{token[:40]}{C_MUTED}\u2026{RST}"
    cprint(f"{pre} {num_badge}  {tok_preview}{extra}")

def log_fail(idx, fail, maxf):
    pre = _prefix(idx)
    bar = ""
    for i in range(maxf):
        if i < fail:
            bar += f"{C_RED}\u25cf"
        else:
            bar += f"{C_MUTED}\u25cb"
    fail_badge = f"{bgrgb(40,10,15)}{C_RED}{BOLD} \u2717 FAIL {RST}"
    cprint(f"{pre} {fail_badge}  {bar}{RST}  {C_MUTED}[{fail}/{maxf}]{RST}")

def log_warn(idx, msg):
    warn_badge = f"{bgrgb(40,30,5)}{C_AMBER}{BOLD} \u26a0 {RST}"
    cprint(f"{_prefix(idx)} {warn_badge}  {C_AMBER}{msg}{RST}")

def log_relaunch(idx, reason):
    relaunch_badge = f"{bgrgb(30,20,5)}{C_ORANGE}{BOLD} \u21bb RELAUNCH {RST}"
    cprint(f"{_prefix(idx)} {relaunch_badge}  {C_MUTED}{reason}{RST}")

# ═══════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════

def load_existing_tokens():
    """Load tokens from file when save-file mode is active."""
    if not SAVE_TO_FILE or not os.path.exists(ABCK_FILE):
        return set()
    try:
        with open(ABCK_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        recent = lines[-MAX_TOKENS_IN_MEMORY:] if len(lines) > MAX_TOKENS_IN_MEMORY else lines
        return {line.strip() for line in recent if line.strip()}
    except Exception:
        return set()

def save_token(token):
    """Save to file only when --save-file is active."""
    if not SAVE_TO_FILE:
        return
    with _file_lock:
        with open(ABCK_FILE, 'a', encoding='utf-8') as f:
            f.write(token + '\n')

def send_token_to_server(token, use_server=False):
    if not use_server:
        return None
    try:
        r = requests.post(SERVER_SAVE_ENDPOINT, json={"token": token}, timeout=5)
        if r.status_code in [200, 201]:
            return r.json().get('id')
    except Exception:
        pass
    return None

# In-memory counter — no need to read file
_ram_token_count = 0
_ram_token_count_lock = threading.Lock()

def count_tokens():
    """Return token count — from RAM counter, not file read."""
    with _ram_token_count_lock:
        return _ram_token_count

def increment_token_count():
    global _ram_token_count
    with _ram_token_count_lock:
        _ram_token_count += 1
        return _ram_token_count

_chrome_version_cache = None

def get_chrome_version():
    global _chrome_version_cache
    if _chrome_version_cache is not None:
        return _chrome_version_cache

    if IS_LINUX:
        for cmd in ['google-chrome --version', 'google-chrome-stable --version',
                     'chromium-browser --version', 'chromium --version']:
            try:
                result = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    match = re.search(r'(\d+)\.', result.stdout)
                    if match:
                        _chrome_version_cache = int(match.group(1))
                        return _chrome_version_cache
            except Exception:
                pass
    else:
        try:
            result = subprocess.run(
                ['reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'version' in line.lower():
                        _chrome_version_cache = int(line.strip().split()[-1].split('.')[0])
                        return _chrome_version_cache
        except Exception:
            pass
        try:
            for base in [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google', 'Chrome', 'Application'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application'),
            ]:
                if os.path.isdir(base):
                    for name in os.listdir(base):
                        if name[0].isdigit() and '.' in name:
                            _chrome_version_cache = int(name.split('.')[0])
                            return _chrome_version_cache
        except Exception:
            pass
    return None

def cleanup_chrome_garbage():
    """Clean all Chrome garbage from temp dir — aggressive."""
    base = _get_temp_base()
    cleaned = 0
    prefixes = ('scoped_dir', '.com.google', 'chrome_', 'Crashpad',
                'uc_', '.org.chromium', 'tmp', 'gpu-process')
    try:
        for name in os.listdir(base):
            if any(name.startswith(p) for p in prefixes):
                path = os.path.join(base, name)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                    cleaned += 1
                except Exception:
                    pass
    except Exception:
        pass
    gc.collect()
    return cleaned

def kill_chrome():
    if IS_LINUX:
        for proc in ['chrome', 'chromedriver', 'google-chrome', 'chromium']:
            try:
                subprocess.run(['pkill', '-f', proc], capture_output=True, timeout=5)
            except Exception:
                pass
    else:
        for proc in ['chrome.exe', 'chromedriver.exe']:
            try:
                subprocess.run(['taskkill', '/F', '/IM', proc], capture_output=True, timeout=5)
            except Exception:
                pass

# ═══════════════════════════════════════════════════════════════════
# BROWSER
# ═══════════════════════════════════════════════════════════════════

def _get_temp_base():
    return os.environ.get('TEMP', os.environ.get('TMP', '/tmp'))

def _cleanup_old_temp_dirs():
    """Remove all leftover Chrome temp dirs from previous sessions."""
    base = _get_temp_base()
    try:
        for name in os.listdir(base):
            if name.startswith('uc_b'):
                path = os.path.join(base, name)
                shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

def _setup_virtual_display():
    """Set up virtual display for headless Linux VPS (Xvfb)."""
    try:
        from pyvirtualdisplay import Display
        display = Display(visible=0, size=(WIN_W, WIN_H))
        display.start()
        return display
    except ImportError:
        pass
    except Exception:
        pass
    try:
        subprocess.run(
            ['Xvfb', ':99', '-screen', '0', f'{WIN_W}x{WIN_H}x24', '-ac'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        os.environ['DISPLAY'] = ':99'
        time.sleep(0.5)
        return True
    except Exception:
        pass
    return None

_virtual_display = None


def _get_own_chromedriver():
    """Get this instance's own chromedriver path, auto-refresh if missing/corrupt."""
    cd_dir = os.path.join(SCRIPT_DIR, "chromedriver_data")
    cd_path = os.path.join(cd_dir, "chromedriver")
    os.makedirs(cd_dir, exist_ok=True)
    if not os.path.isfile(cd_path) or os.path.getsize(cd_path) < 1000000:
        shared = os.path.expanduser("~/.local/share/undetected_chromedriver/undetected_chromedriver")
        if os.path.isfile(shared):
            shutil.copy2(shared, cd_path)
            os.chmod(cd_path, 0o755)
        else:
            try:
                import undetected_chromedriver as _uc
                _tmp = _uc.Chrome.__init__
                _uc.Patcher(executable_path=cd_path).auto()
            except Exception:
                pass
    return cd_path

def _refresh_chromedriver():
    """Force re-download chromedriver for this instance."""
    cd_dir = os.path.join(SCRIPT_DIR, "chromedriver_data")
    cd_path = os.path.join(cd_dir, "chromedriver")
    try:
        if os.path.exists(cd_path):
            os.remove(cd_path)
        shared = os.path.expanduser("~/.local/share/undetected_chromedriver/undetected_chromedriver")
        if os.path.isfile(shared):
            shutil.copy2(shared, cd_path)
            os.chmod(cd_path, 0o755)
        else:
            import undetected_chromedriver as _uc
            _uc.Patcher(executable_path=cd_path).auto()
    except Exception as e:
        pass
    return cd_path

def create_driver(hidden=False, chrome_ver=None, browser_index=0):
    global _virtual_display
    if IS_LINUX and _virtual_display is None:
        _virtual_display = _setup_virtual_display()

    for attempt in range(3):
        try:
            options = uc.ChromeOptions()
            for arg in [
                "--no-first-run", "--no-service-autorun", "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-popup-blocking", "--disable-infobars", "--disable-gpu",
                "--disable-dev-shm-usage", "--disable-software-rasterizer", "--disable-default-apps",
                "--no-sandbox",
                "--disk-cache-size=1",
                "--disable-logging",
                "--disable-crash-reporter",
                "--disable-breakpad",
                "--disable-component-update",
                "--disable-sync",
                "--disable-translate",
                "--log-level=3",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-hang-monitor",
                "--disable-domain-reliability",
                "--disable-client-side-phishing-detection",
                "--safebrowsing-disable-auto-update",
                f"--window-size={WIN_W},{WIN_H}",
            ]:
                options.add_argument(arg)

            prefs = {}
            options.add_experimental_option("prefs", prefs)

            if IS_LINUX and not os.environ.get('DISPLAY'):
                options.add_argument("--headless=new")

            if hidden:
                options.add_argument("--window-position=-3000,-3000")
            else:
                px, py = BROWSER_POSITIONS[browser_index % len(BROWSER_POSITIONS)]
                options.add_argument(f"--window-position={px},{py}")

            temp_dir = os.path.join(_get_temp_base(), f'uc_b{browser_index}')
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            os.makedirs(temp_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={temp_dir}")
            try:
                bins = os.environ.get('CHROME_BINARIES')
                binary = None
                if bins:
                    parts = [p.strip() for p in bins.split(',') if p.strip()]
                    if parts:
                        binary = parts[browser_index % len(parts)]
                if not binary:
                    binary = os.environ.get('CHROME_BINARY')
                if not binary and IS_LINUX:
                    for path in ['/usr/bin/google-chrome-stable', '/usr/bin/google-chrome',
                                 '/usr/bin/chromium-browser', '/usr/bin/chromium',
                                 '/snap/bin/chromium']:
                        if os.path.isfile(path):
                            binary = path
                            break
                if binary:
                    options.binary_location = binary
            except Exception:
                pass

            own_cd = _get_own_chromedriver()
            try:
                driver = uc.Chrome(options=options, version_main=chrome_ver, driver_executable_path=own_cd)
            except Exception as _cd_err:
                if "Text file busy" in str(_cd_err) or "No such file" in str(_cd_err) or "unable to obtain" in str(_cd_err).lower():
                    own_cd = _refresh_chromedriver()
                    time.sleep(2)
                    driver = uc.Chrome(options=options, version_main=chrome_ver, driver_executable_path=own_cd)
                else:
                    raise
            driver.set_page_load_timeout(30)
            driver.set_script_timeout(10)
            try:
                driver.set_window_size(WIN_W, WIN_H)
            except Exception:
                pass
            return driver
        except Exception as e:
            log_warn(browser_index, f"Launch failed ({attempt+1}/3): {e}")
            time.sleep(0.5)
    return None

def safe_quit(driver, browser_index=None):
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        if browser_index is not None:
            temp_dir = os.path.join(_get_temp_base(), f'uc_b{browser_index}')
            shutil.rmtree(temp_dir, ignore_errors=True)
        cleanup_chrome_garbage()

# ═══════════════════════════════════════════════════════════════════
# CDP MOUSE
# ═══════════════════════════════════════════════════════════════════

def _bezier_points(x1, y1, x2, y2, steps=12):
    """Generate smooth bezier curve points between two coordinates."""
    cx1 = x1 + random.randint(-80, 80)
    cy1 = y1 + random.randint(-60, 60)
    cx2 = x2 + random.randint(-80, 80)
    cy2 = y2 + random.randint(-60, 60)
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        px = int(u**3*x1 + 3*u**2*t*cx1 + 3*u*t**2*cx2 + t**3*x2)
        py = int(u**3*y1 + 3*u**2*t*cy1 + 3*u*t**2*cy2 + t**3*y2)
        px = max(5, min(px, WIN_W - 5))
        py = max(5, min(py, WIN_H - 5))
        points.append((px, py))
    return points

def cdp_mouse_move(driver):
    """Simulate realistic mouse movement with bezier curve."""
    try:
        x1, y1 = random.randint(100, WIN_W-200), random.randint(80, WIN_H-200)
        x2, y2 = random.randint(100, WIN_W-100), random.randint(80, WIN_H-100)
        points = _bezier_points(x1, y1, x2, y2, steps=random.randint(8, 18))
        for px, py in points:
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseMoved', 'x': px, 'y': py
            })
            time.sleep(random.uniform(0.005, 0.025))
        if random.random() < 0.3:
            cx, cy = points[-1]
            for etype in ['mousePressed', 'mouseReleased']:
                driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                    'type': etype, 'x': cx, 'y': cy,
                    'button': 'left', 'clickCount': 1
                })
                time.sleep(random.uniform(0.03, 0.08))
    except Exception:
        pass

def cdp_scroll(driver):
    """Simulate page scrolling."""
    try:
        x, y = random.randint(200, WIN_W-200), random.randint(200, WIN_H-200)
        delta_y = random.choice([-120, -80, 80, 120, 200, -200])
        driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': 'mouseWheel', 'x': x, 'y': y,
            'deltaX': 0, 'deltaY': delta_y
        })
    except Exception:
        pass

def cdp_keyboard(driver):
    """Simulate random keyboard events."""
    try:
        driver.execute_script("""
            document.dispatchEvent(new Event('mouseover'));
            document.dispatchEvent(new Event('focus'));
            var el = document.elementFromPoint(
                Math.random() * window.innerWidth,
                Math.random() * window.innerHeight
            );
            if (el) { el.dispatchEvent(new MouseEvent('mouseover', {bubbles: true})); }
        """)
    except Exception:
        pass

def inject_sensor_triggers(driver):
    """Inject JavaScript to trigger sensor data needed by Akamai."""
    try:
        driver.execute_script("""
            ['pointerdown','pointerup','pointerover','pointermove'].forEach(function(evt){
                document.dispatchEvent(new PointerEvent(evt, {
                    pointerId: 1, bubbles: true, clientX: Math.random()*800+100, clientY: Math.random()*400+100
                }));
            });
            ['mousedown','mouseup','mousemove','mouseover'].forEach(function(evt){
                document.dispatchEvent(new MouseEvent(evt, {
                    bubbles: true, clientX: Math.random()*900+50, clientY: Math.random()*500+50
                }));
            });
            ['keydown','keyup'].forEach(function(evt){
                document.dispatchEvent(new KeyboardEvent(evt, {
                    key: 'a', code: 'KeyA', keyCode: 65, bubbles: true
                }));
            });
            window.dispatchEvent(new Event('scroll'));
            document.dispatchEvent(new Event('visibilitychange'));
            window.dispatchEvent(new Event('focus'));
        """)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════
# SOLVE
# ═══════════════════════════════════════════════════════════════════

def get_solved_abck(cookies):
    for c in cookies:
        if c.get('name') == '_abck' and '~0~' in c.get('value', ''):
            return c['value']
    return None

def wait_for_solve(driver, timeout=SOLVE_TIMEOUT, browser_index=0):
    start    = time.time()
    dots     = 0
    last_log = -10

    time.sleep(random.uniform(1.0, 2.0))
    inject_sensor_triggers(driver)
    time.sleep(random.uniform(0.5, 1.0))
    cdp_mouse_move(driver)

    while time.time() - start < timeout:
        try:
            cookies = driver.get_cookies()
        except Exception:
            return None
        solved = get_solved_abck(cookies)
        if solved:
            return solved

        action = dots % 5
        if action == 0:
            cdp_mouse_move(driver)
        elif action == 1:
            cdp_scroll(driver)
        elif action == 2:
            cdp_keyboard(driver)
        elif action == 3:
            cdp_mouse_move(driver)
            inject_sensor_triggers(driver)

        dots   += 1
        elapsed = int(time.time() - start)
        if elapsed - last_log >= 8:
            log_solving(browser_index, elapsed)
            last_log = elapsed
        time.sleep(CHECK_INTERVAL)
    return None

# ═══════════════════════════════════════════════════════════════════
# SHARED STATE
# ═══════════════════════════════════════════════════════════════════

class SharedState:
    def __init__(self, target_count, loop_forever):
        self.target_count = target_count
        self.loop_forever = loop_forever
        self.generated    = 0
        self.existing     = load_existing_tokens()
        self.lock         = threading.Lock()
        self.stop_event   = threading.Event()

    def should_continue(self):
        if self.stop_event.is_set():
            return False
        if self.loop_forever:
            return True
        with self.lock:
            return self.generated < self.target_count

    def add_token(self, token):
        with self.lock:
            if token in self.existing:
                return False
            self.existing.add(token)
            if len(self.existing) > MAX_TOKENS_IN_MEMORY:
                excess = len(self.existing) - MAX_TOKENS_IN_MEMORY
                for _ in range(excess):
                    self.existing.pop()
            self.generated += 1
            if self.generated % CLEANUP_INTERVAL == 0:
                cleanup_chrome_garbage()
            return True

# ═══════════════════════════════════════════════════════════════════
# WORKER
# ═══════════════════════════════════════════════════════════════════

def browser_worker(idx, shared, hidden, use_server, chrome_ver):
    driver = None
    consec_fails = 0
    tok_this_br  = 0
    attempt      = 0

    try:
        while shared.should_continue():
            attempt += 1
            need_new = (
                driver is None or
                consec_fails >= MAX_CONSECUTIVE_FAILS or
                tok_this_br  >= MAX_TOKENS_PER_BROWSER
            )

            if need_new:
                if driver is not None:
                    reason = (f"{consec_fails}x failed"
                              if consec_fails >= MAX_CONSECUTIVE_FAILS
                              else f"{tok_this_br} tokens")
                    log_relaunch(idx, reason)
                    safe_quit(driver, idx)
                    driver = None
                    time.sleep(random.uniform(*DELAY_BROWSER_RELAUNCH))

                log_info(idx, "Opening browser...")
                driver = create_driver(hidden=hidden, chrome_ver=chrome_ver, browser_index=idx)
                if not driver:
                    log_warn(idx, "Browser failed! Retry 3s...")
                    time.sleep(3)
                    continue

                consec_fails = 0
                tok_this_br  = 0
                try:
                    driver.get(TARGET_URL)
                    time.sleep(random.uniform(2.0, 3.5))
                    cdp_mouse_move(driver)
                    time.sleep(random.uniform(0.3, 0.6))
                    inject_sensor_triggers(driver)
                except Exception as e:
                    log_warn(idx, f"Page load error: {e}")
                    safe_quit(driver, idx)
                    driver = None
                    continue
            else:
                try:
                    driver.delete_cookie('_abck')
                    if random.random() < 0.3:
                        driver.refresh()
                    else:
                        driver.get(TARGET_URL)
                    time.sleep(random.uniform(1.5, 2.5))
                    cdp_mouse_move(driver)
                    inject_sensor_triggers(driver)
                except Exception:
                    safe_quit(driver, idx)
                    driver = None
                    continue

            with shared.lock:
                gen_now = shared.generated
            remaining  = "\u221e" if shared.loop_forever else str(shared.target_count - gen_now)
            file_count = count_tokens()
            log_status(idx, attempt, gen_now, file_count, remaining, tok_this_br)

            token = wait_for_solve(driver, timeout=SOLVE_TIMEOUT, browser_index=idx)

            if token:
                if shared.add_token(token):
                    save_token(token)
                    increment_token_count()
                    server_id  = send_token_to_server(token, use_server)
                    tok_this_br  += 1
                    consec_fails  = 0
                    with shared.lock:
                        g = shared.generated
                    extra = f"  {C_TEAL}[srv:{server_id}]{RST}" if use_server and server_id else ""
                    log_success(idx, g, token, extra)
                    time.sleep(random.uniform(*DELAY_BETWEEN_TOKENS))
                else:
                    log_warn(idx, "Duplicate token, skip")
                    try: driver.delete_all_cookies()
                    except Exception: pass
            else:
                consec_fails += 1
                log_fail(idx, consec_fails, MAX_CONSECUTIVE_FAILS)
                try:
                    driver.delete_all_cookies()
                except Exception:
                    safe_quit(driver, idx)
                    driver = None

            if shared.should_continue():
                time.sleep(random.uniform(*DELAY_BETWEEN_TOKENS))

    except Exception as e:
        log_warn(idx, f"Error: {e}")
    finally:
        safe_quit(driver, idx)
        log_info(idx, "Worker finished.")

# ═══════════════════════════════════════════════════════════════════
# GENERATE
# ═══════════════════════════════════════════════════════════════════

def generate(target_count, hidden=False, loop_forever=False, use_server=False):
    shared  = SharedState(target_count, loop_forever)
    threads = []

    chrome_ver = get_chrome_version()
    for i in range(NUM_BROWSERS):
        t = threading.Thread(
            target=browser_worker,
            args=(i, shared, hidden, use_server, chrome_ver),
            daemon=True, name=f"B{i+1}"
        )
        threads.append(t)
        t.start()
        if i < NUM_BROWSERS - 1:
            time.sleep(1.5)

    try:
        while any(t.is_alive() for t in threads):
            if not loop_forever and not shared.should_continue():
                shared.stop_event.set()
            time.sleep(1)
    except KeyboardInterrupt:
        W = tw()
        cprint(f"\n{hline('\u2500', C_AMBER, W)}")
        cprint(center(f"{C_AMBER}{BOLD}  \u26a0  Stopped by user (Ctrl+C)  {RST}", W))
        cprint(hline('\u2500', C_AMBER, W))
        shared.stop_event.set()

    for t in threads:
        try:
            t.join(timeout=10)
        except KeyboardInterrupt:
            pass

    return shared.generated

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    global SAVE_TO_FILE
    os.system('cls' if os.name == 'nt' else 'clear')

    args         = sys.argv[1:]
    target_count = DEFAULT_TOKEN_COUNT
    hidden       = '--hidden' in args
    loop_forever = True
    use_server   = '--no-server' not in args
    SAVE_TO_FILE = '--save-file' in args

    for arg in args:
        if arg.isdigit():
            target_count = int(arg)

    existing   = count_tokens()
    chrome_ver = get_chrome_version()

    _cleanup_old_temp_dirs()

    print_banner()
    print_info_table(target_count, hidden, loop_forever, use_server, existing, chrome_ver)
    print_section_start()

    start     = time.time()
    generated = generate(target_count, hidden, loop_forever, use_server)
    elapsed   = time.time() - start
    total     = count_tokens()

    print_done(generated, total, elapsed)
    kill_chrome()
    cleanup_chrome_garbage()


if __name__ == "__main__":
    main()
