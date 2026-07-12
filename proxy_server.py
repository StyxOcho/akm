from flask import Flask, request, jsonify, render_template_string
import subprocess
import signal
import sys
import threading
import time
import os
from collections import deque
from datetime import datetime

app = Flask(__name__)

POOL_MAX = int(os.environ.get("POOL_MAX", "5000"))
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "7200"))

token_pool = deque()
pool_lock = threading.Lock()

stats = {
    "total_requests": 0,
    "single_tokens": 0,
    "tokens_pushed": 0,
    "tokens_served": 0,
    "tokens_expired": 0,
    "duplicates_rejected": 0,
    "tokens_flushed": 0,
    "errors": 0,
    "pool_size": 0,
    "peak_queue": 0,
    "last_received": None,
    "last_served": None,
    "start_time": datetime.now().isoformat()
}
stats_lock = threading.Lock()


def purge_expired():
    now = datetime.now()
    removed = 0
    with pool_lock:
        while token_pool:
            oldest = token_pool[0]
            gen = datetime.fromisoformat(oldest["generated_at"])
            if (now - gen).total_seconds() > TOKEN_TTL:
                token_pool.popleft()
                removed += 1
            else:
                break
    if removed > 0:
        with stats_lock:
            stats["tokens_expired"] += removed
            stats["pool_size"] = len(token_pool)
    return removed


def ttl_cleaner():
    while True:
        time.sleep(5)
        purge_expired()


cleaner_thread = threading.Thread(target=ttl_cleaner, daemon=True)
cleaner_thread.start()


def take_token():
    purge_expired()
    with pool_lock:
        if token_pool:
            token = token_pool.pop()
            with stats_lock:
                stats["tokens_served"] += 1
                stats["pool_size"] = len(token_pool)
                stats["last_served"] = datetime.now().isoformat()
            return token
    return None


def build_frontend(s):
    uptime_sec = (datetime.now() - datetime.fromisoformat(s["start_time"])).total_seconds()
    uptime_min = round(uptime_sec / 60, 1)
    rate = round(s["tokens_pushed"] / max(uptime_min, 0.1), 1)
    q = s["pool_size"]
    pk = s["peak_queue"]
    q_pct = int(min(q / max(pk, 1) * 100, 100)) if pk > 0 else 0
    served_pct = int(min(s["tokens_served"] / max(s["tokens_pushed"], 1) * 100, 100))
    ring_offset = int(251 - (251 * min(uptime_min / max(uptime_min + 60, 1), 1)))
    last_recv = s.get("last_received") or "---"
    last_serv = s.get("last_served") or "---"
    port = int(os.environ.get("PORT", 3030))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ABCK Token Server v2</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

  :root {{
    --bg: #16101a;
    --bg2: #1e1524;
    --surface: rgba(36, 26, 44, 0.75);
    --surface-solid: #241a2c;
    --surface2: rgba(46, 34, 56, 0.8);
    --surface-hover: rgba(56, 40, 66, 0.9);
    --border: rgba(237, 130, 160, 0.08);
    --border-bright: rgba(237, 130, 160, 0.2);
    --border-glow: rgba(248, 140, 170, 0.35);
    --rose: #f8789c;
    --rose-bright: #fcadc4;
    --rose-dim: rgba(248, 120, 156, 0.5);
    --amber: #f5a623;
    --amber-bright: #fcc96e;
    --amber-dim: rgba(245, 166, 35, 0.5);
    --coral: #fb7a5c;
    --coral-dim: rgba(251, 122, 92, 0.5);
    --red: #f87171;
    --red-dim: rgba(248, 113, 113, 0.5);
    --violet: #c77dff;
    --violet-dim: rgba(199, 125, 255, 0.5);
    --gold: #fbbf24;
    --text: #f5f1f2;
    --text-secondary: #c4b5bb;
    --text-muted: #8a7580;
    --text-dim: #4a3848;
    --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', monospace;
    --glass: blur(20px) saturate(1.5);
    --radius: 16px;
    --radius-sm: 10px;
    --radius-xs: 6px;
  }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    min-height: 100vh;
    overflow-x: hidden;
    position: relative;
  }}

  .orb {{
    position: fixed;
    border-radius: 50%;
    filter: blur(100px);
    opacity: 0.15;
    pointer-events: none;
    z-index: 0;
  }}
  .orb-1 {{
    width: 600px; height: 600px;
    background: radial-gradient(circle, #f8789c, transparent 70%);
    top: -200px; left: -100px;
    animation: orbFloat1 20s ease-in-out infinite;
  }}
  .orb-2 {{
    width: 500px; height: 500px;
    background: radial-gradient(circle, #c77dff, transparent 70%);
    bottom: -150px; right: -100px;
    animation: orbFloat2 25s ease-in-out infinite;
  }}
  .orb-3 {{
    width: 400px; height: 400px;
    background: radial-gradient(circle, #f5a623, transparent 70%);
    top: 40%; left: 50%;
    animation: orbFloat3 18s ease-in-out infinite;
  }}

  @keyframes orbFloat1 {{
    0%, 100% {{ transform: translate(0, 0) scale(1); }}
    33% {{ transform: translate(80px, 50px) scale(1.1); }}
    66% {{ transform: translate(-40px, 80px) scale(0.9); }}
  }}
  @keyframes orbFloat2 {{
    0%, 100% {{ transform: translate(0, 0) scale(1); }}
    33% {{ transform: translate(-60px, -40px) scale(1.15); }}
    66% {{ transform: translate(50px, -70px) scale(0.85); }}
  }}
  @keyframes orbFloat3 {{
    0%, 100% {{ transform: translate(-50%, 0) scale(1); opacity: 0.1; }}
    50% {{ transform: translate(-50%, -60px) scale(1.2); opacity: 0.18; }}
  }}

  body::after {{
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(248,120,156,0.02) 1px, transparent 1px),
      linear-gradient(90deg, rgba(248,120,156,0.02) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
    z-index: 0;
    mask-image: radial-gradient(ellipse at 50% 50%, black 30%, transparent 80%);
    -webkit-mask-image: radial-gradient(ellipse at 50% 50%, black 30%, transparent 80%);
  }}

  body::before {{
    content: '';
    position: fixed;
    inset: 0;
    opacity: 0.03;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 1;
  }}

  .wrap {{
    position: relative;
    z-index: 2;
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 36px 60px;
  }}

  .header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 44px;
    flex-wrap: wrap;
    gap: 20px;
  }}

  .header-left {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}

  .logo-box {{
    width: 48px; height: 48px;
    border-radius: 14px;
    background: linear-gradient(135deg, rgba(248,120,156,0.15), rgba(199,125,255,0.1));
    border: 1px solid rgba(248,120,156,0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    flex-shrink: 0;
  }}

  .logo-box::before {{
    content: '';
    position: absolute;
    inset: -1px;
    border-radius: 14px;
    padding: 1px;
    background: linear-gradient(135deg, var(--rose), var(--violet));
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    opacity: 0.4;
  }}

  .logo-box svg {{ position: relative; z-index: 1; filter: drop-shadow(0 0 6px rgba(248,120,156,0.4)); }}

  .header-title h1 {{
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #f5f1f2 30%, var(--rose-bright));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
  }}

  .header-title .sub {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-muted);
    letter-spacing: 0.5px;
    margin-top: 2px;
  }}

  .header-title .sub span {{ color: var(--rose-dim); }}

  .header-right {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .mode-badge {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(251, 122, 92, 0.06);
    border: 1px solid rgba(251, 122, 92, 0.15);
    border-radius: 100px;
    padding: 8px 16px;
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    color: var(--coral);
    letter-spacing: 1px;
    text-transform: uppercase;
  }}

  .status-badge {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(245, 166, 35, 0.06);
    border: 1px solid rgba(245, 166, 35, 0.15);
    border-radius: 100px;
    padding: 8px 20px 8px 14px;
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    color: var(--amber);
    letter-spacing: 1px;
    text-transform: uppercase;
  }}

  .live-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--amber);
    position: relative;
    flex-shrink: 0;
  }}
  .live-dot::after {{
    content: '';
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    background: var(--amber);
    opacity: 0.3;
    animation: livePulse 2s ease-in-out infinite;
  }}
  @keyframes livePulse {{
    0%, 100% {{ transform: scale(1); opacity: 0.3; }}
    50% {{ transform: scale(1.8); opacity: 0; }}
  }}

  .time-badge {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 8px 16px;
    backdrop-filter: var(--glass);
  }}

  .grid-4 {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 16px;
  }}

  .card {{
    background: var(--surface);
    backdrop-filter: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    position: relative;
    overflow: hidden;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }}
  .card:hover {{
    border-color: var(--border-bright);
    background: var(--surface-hover);
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px var(--border-bright);
  }}

  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 20%; right: 20%;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent, var(--rose)), transparent);
    opacity: 0;
    transition: opacity 0.4s;
  }}
  .card:hover::before {{ opacity: 0.6; }}

  .card::after {{
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 120px; height: 120px;
    border-radius: 50%;
    background: var(--accent, var(--rose));
    opacity: 0;
    filter: blur(40px);
    transition: opacity 0.4s;
    pointer-events: none;
  }}
  .card:hover::after {{ opacity: 0.07; }}

  .card.amber {{ --accent: var(--amber); }}
  .card.rose {{ --accent: var(--rose); }}
  .card.coral {{ --accent: var(--coral); }}
  .card.red {{ --accent: var(--red); }}
  .card.violet {{ --accent: var(--violet); }}
  .card.gold {{ --accent: var(--gold); }}

  .card-icon {{
    width: 36px; height: 36px;
    border-radius: var(--radius-sm);
    background: linear-gradient(135deg, color-mix(in srgb, var(--accent, var(--rose)) 12%, transparent), transparent);
    border: 1px solid color-mix(in srgb, var(--accent, var(--rose)) 15%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 16px;
  }}

  .card-label {{
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-muted);
    margin-bottom: 10px;
  }}

  .card-value {{
    font-size: 40px;
    font-weight: 900;
    color: var(--text);
    line-height: 1;
    letter-spacing: -2px;
    font-variant-numeric: tabular-nums;
    position: relative;
  }}

  .card-value .highlight {{
    background: linear-gradient(135deg, var(--accent, var(--rose)), color-mix(in srgb, var(--accent, var(--rose)) 60%, white));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    transition: opacity 0.3s ease;
  }}

  .card-sub {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .card-sub .dot {{
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--accent, var(--rose));
    opacity: 0.5;
  }}

  .section {{
    background: var(--surface);
    backdrop-filter: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
  }}

  .section-hdr {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 24px;
  }}

  .section-hdr .icon {{
    width: 28px; height: 28px;
    border-radius: 8px;
    background: rgba(248,120,156,0.08);
    border: 1px solid rgba(248,120,156,0.1);
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .section-hdr h2 {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: var(--text);
  }}

  .section-hdr .line {{
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--border-bright), transparent);
  }}

  .bar-group {{ margin-bottom: 18px; }}
  .bar-group:last-child {{ margin-bottom: 0; }}

  .bar-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }}

  .bar-title {{
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 500;
    color: var(--text-secondary);
  }}

  .bar-value {{
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    color: var(--text);
  }}

  .bar-track {{
    background: rgba(70, 45, 60, 0.5);
    border-radius: 100px;
    height: 8px;
    overflow: hidden;
    position: relative;
  }}

  .bar-fill {{
    height: 100%;
    border-radius: 100px;
    position: relative;
    transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
  }}

  .bar-fill.gradient-rose {{
    background: linear-gradient(90deg, #e0527a, #f8789c, #fcadc4);
  }}
  .bar-fill.gradient-amber {{
    background: linear-gradient(90deg, #d48a10, #f5a623, #fcc96e);
  }}
  .bar-fill.gradient-violet {{
    background: linear-gradient(90deg, #9b4de0, #c77dff, #e9d5ff);
  }}

  .bar-fill::after {{
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent 60%, rgba(255,255,255,0.2));
    border-radius: 100px;
  }}

  .bar-fill::before {{
    content: '';
    position: absolute;
    top: 0; left: -100%; bottom: 0;
    width: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    animation: shimmer 3s ease-in-out infinite;
  }}

  @keyframes shimmer {{
    0% {{ left: -100%; }}
    100% {{ left: 200%; }}
  }}

  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }}

  .runtime-wrap {{
    display: flex;
    gap: 28px;
    align-items: center;
  }}

  .ring-container {{
    position: relative;
    width: 100px; height: 100px;
    flex-shrink: 0;
  }}

  .ring-container svg {{ transform: rotate(-90deg); }}

  .ring-center {{
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }}

  .ring-number {{
    font-size: 22px;
    font-weight: 800;
    background: linear-gradient(135deg, var(--rose), var(--amber));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
    letter-spacing: -0.5px;
  }}

  .ring-unit {{
    font-family: var(--mono);
    font-size: 9px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-top: 3px;
  }}

  .stat-pills {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
  }}

  .stat-pill {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(55, 35, 48, 0.6);
    border: 1px solid var(--border);
    border-radius: var(--radius-xs);
    padding: 10px 14px;
    transition: border-color 0.3s, background 0.3s;
  }}
  .stat-pill:hover {{
    border-color: var(--border-bright);
    background: rgba(55, 35, 48, 0.9);
  }}

  .stat-pill-label {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .stat-pill-label .indicator {{
    width: 6px; height: 6px;
    border-radius: 2px;
  }}

  .stat-pill-value {{
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
  }}

  .c-rose {{ color: var(--rose); }}
  .c-amber {{ color: var(--amber); }}
  .c-coral {{ color: var(--coral); }}
  .c-violet {{ color: var(--violet); }}
  .c-gold {{ color: var(--gold); }}

  .endpoint-table {{
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}

  .ep-row {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 14px;
    border-radius: var(--radius-xs);
    background: rgba(55, 35, 48, 0.3);
    border: 1px solid transparent;
    transition: all 0.3s;
  }}
  .ep-row:hover {{
    background: rgba(55, 35, 48, 0.7);
    border-color: var(--border);
    transform: translateX(4px);
  }}

  .ep-method {{
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 4px;
    letter-spacing: 0.5px;
    min-width: 50px;
    text-align: center;
    flex-shrink: 0;
  }}

  .ep-method.get {{
    background: rgba(245,166,35,0.08);
    color: var(--amber);
    border: 1px solid rgba(245,166,35,0.2);
  }}
  .ep-method.post {{
    background: rgba(248,120,156,0.08);
    color: var(--rose);
    border: 1px solid rgba(248,120,156,0.2);
  }}
  .ep-method.del {{
    background: rgba(248,113,113,0.08);
    color: var(--red);
    border: 1px solid rgba(248,113,113,0.2);
  }}

  .ep-path {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text);
    font-weight: 500;
    flex: 1;
  }}

  .ep-desc {{
    font-size: 11px;
    color: var(--text-muted);
    text-align: right;
  }}

  .ts-strip {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }}

  .ts-card {{
    display: flex;
    align-items: center;
    gap: 14px;
    background: var(--surface);
    backdrop-filter: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 16px 20px;
    transition: border-color 0.3s;
  }}
  .ts-card:hover {{ border-color: var(--border-bright); }}

  .ts-icon-wrap {{
    width: 40px; height: 40px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    position: relative;
  }}

  .ts-icon-wrap.recv {{
    background: linear-gradient(135deg, rgba(248,120,156,0.1), rgba(248,120,156,0.02));
    border: 1px solid rgba(248,120,156,0.12);
  }}
  .ts-icon-wrap.serv {{
    background: linear-gradient(135deg, rgba(245,166,35,0.1), rgba(245,166,35,0.02));
    border: 1px solid rgba(245,166,35,0.12);
  }}

  .ts-info .ts-label {{
    font-family: var(--mono);
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-muted);
    margin-bottom: 4px;
  }}

  .ts-info .ts-val {{
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
  }}

  .footer {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 36px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
    gap: 12px;
  }}

  .footer-l, .footer-r {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.5px;
  }}

  .footer-r span {{ color: var(--rose-dim); }}

  .particles {{
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
  }}

  .particle {{
    position: absolute;
    width: 2px;
    height: 2px;
    background: var(--rose);
    border-radius: 50%;
    opacity: 0;
    animation: particleFloat linear infinite;
  }}

  @keyframes particleFloat {{
    0% {{ opacity: 0; transform: translateY(100vh) scale(0); }}
    10% {{ opacity: 0.6; }}
    90% {{ opacity: 0.6; }}
    100% {{ opacity: 0; transform: translateY(-10vh) scale(1); }}
  }}

  @media (max-width: 900px) {{
    .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
    .grid-2, .ts-strip {{ grid-template-columns: 1fr; }}
    .wrap {{ padding: 24px 18px 40px; }}
    .card-value {{ font-size: 32px; }}
  }}

  @media (max-width: 500px) {{
    .grid-4 {{ grid-template-columns: 1fr; }}
    .header {{ flex-direction: column; align-items: flex-start; }}
    .header-right {{ width: 100%; justify-content: flex-start; }}
  }}

  .fade-up {{
    animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
  }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(20px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  .fade-up:nth-child(1) {{ animation-delay: 0.0s; }}
  .fade-up:nth-child(2) {{ animation-delay: 0.05s; }}
  .fade-up:nth-child(3) {{ animation-delay: 0.1s; }}
  .fade-up:nth-child(4) {{ animation-delay: 0.15s; }}
  .fade-up:nth-child(5) {{ animation-delay: 0.2s; }}
  .fade-up:nth-child(6) {{ animation-delay: 0.25s; }}
  .fade-up:nth-child(7) {{ animation-delay: 0.3s; }}
  .fade-up:nth-child(8) {{ animation-delay: 0.35s; }}
</style>
</head>
<body>

<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
<div class="orb orb-3"></div>

<div class="particles" id="particles"></div>

<div class="wrap">

  <div class="header fade-up">
    <div class="header-left">
      <div class="logo-box">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L4 6.5V12C4 16.5 7.5 20.7 12 22C16.5 20.7 20 16.5 20 12V6.5L12 2Z" stroke="#f8789c" stroke-width="1.5" stroke-linejoin="round" fill="none"/>
          <path d="M9 12L11 14L15 10" stroke="#fcadc4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="header-title">
        <h1>ABCK Token Server</h1>
        <div class="sub">v2.0 &middot; No Storage &middot; TTL <span>{TOKEN_TTL}s</span> &middot; Auto-refresh 3s</div>
      </div>
    </div>
    <div class="header-right">
      <div class="mode-badge">No Storage</div>
      <div class="status-badge">
        <div class="live-dot"></div>
        Online
      </div>
      <div class="time-badge" id="clock"></div>
    </div>
  </div>

  <div class="grid-4">
    <div class="card amber fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="2" y="8" width="3" height="8" rx="1" fill="#f5a623" opacity="0.5"/><rect x="7.5" y="4" width="3" height="12" rx="1" fill="#f5a623" opacity="0.7"/><rect x="13" y="1" width="3" height="15" rx="1" fill="#f5a623"/></svg>
      </div>
      <div class="card-label">Queue Size</div>
      <div class="card-value"><span class="highlight" id="v-queue">{q}</span></div>
      <div class="card-sub"><span class="dot"></span> tokens ready</div>
    </div>
    <div class="card rose fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 2v10M5 8l4 4 4-4" stroke="#f8789c" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 14h12" stroke="#f8789c" stroke-width="1.8" stroke-linecap="round"/></svg>
      </div>
      <div class="card-label">Received</div>
      <div class="card-value"><span class="highlight" id="v-received">{s["tokens_pushed"]}</span></div>
      <div class="card-sub"><span class="dot"></span> all time</div>
    </div>
    <div class="card coral fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 16V6M5 10l4-4 4 4" stroke="#fb7a5c" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 4h12" stroke="#fb7a5c" stroke-width="1.8" stroke-linecap="round"/></svg>
      </div>
      <div class="card-label">Served</div>
      <div class="card-value"><span class="highlight" id="v-served">{s["tokens_served"]}</span></div>
      <div class="card-sub"><span class="dot"></span> dispatched</div>
    </div>
    <div class="card red fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="6" stroke="#f87171" stroke-width="1.5"/><path d="M9 6v4M9 12.5v.5" stroke="#f87171" stroke-width="1.8" stroke-linecap="round"/></svg>
      </div>
      <div class="card-label">Expired</div>
      <div class="card-value"><span class="highlight" id="v-expired">{s["tokens_expired"]}</span></div>
      <div class="card-sub"><span class="dot"></span> auto-cleaned</div>
    </div>
  </div>

  <div class="grid-4">
    <div class="card violet fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M4 4l10 10M14 4L4 14" stroke="#c77dff" stroke-width="1.8" stroke-linecap="round"/></svg>
      </div>
      <div class="card-label">Duplicates</div>
      <div class="card-value"><span class="highlight" id="v-dupes">{s["duplicates_rejected"]}</span></div>
      <div class="card-sub"><span class="dot"></span> rejected</div>
    </div>
    <div class="card rose fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M2 13l3-4 3 2 4-6 4 3" stroke="#f8789c" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="card-label">Rate</div>
      <div class="card-value"><span class="highlight" id="v-rate">{rate}</span></div>
      <div class="card-sub"><span class="dot"></span> tok / min</div>
    </div>
    <div class="card gold fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 2l2.2 4.5 5 .7-3.6 3.5.8 5L9 13.5 4.6 15.7l.8-5L1.8 7.2l5-.7L9 2z" stroke="#fbbf24" stroke-width="1.3" stroke-linejoin="round" fill="rgba(251,191,36,0.15)"/></svg>
      </div>
      <div class="card-label">Peak Queue</div>
      <div class="card-value"><span class="highlight" id="v-peak">{pk}</span></div>
      <div class="card-sub"><span class="dot"></span> historical max</div>
    </div>
    <div class="card coral fade-up">
      <div class="card-icon">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 9h12M9 3v12" stroke="#fb7a5c" stroke-width="1.8" stroke-linecap="round" opacity="0.4"/><path d="M5 5l8 8M13 5l-8 8" stroke="#fb7a5c" stroke-width="1.8" stroke-linecap="round"/></svg>
      </div>
      <div class="card-label">Flushed</div>
      <div class="card-value"><span class="highlight" id="v-flushed">{s["tokens_flushed"]}</span></div>
      <div class="card-sub"><span class="dot"></span> manually cleared</div>
    </div>
  </div>

  <div class="section fade-up">
    <div class="section-hdr">
      <div class="icon">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="3" width="12" height="8" rx="2" stroke="#f8789c" stroke-width="1.2"/><path d="M4 7h6" stroke="#f8789c" stroke-width="1.2" stroke-linecap="round"/></svg>
      </div>
      <h2>Queue Capacity</h2>
      <div class="line"></div>
    </div>

    <div class="bar-group">
      <div class="bar-header">
        <span class="bar-title">Current Queue</span>
        <span class="bar-value" id="bv-queue">{q} / {pk} peak</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill gradient-rose" id="bar-queue" style="width: {q_pct}%"></div>
      </div>
    </div>

    <div class="bar-group">
      <div class="bar-header">
        <span class="bar-title">Served vs Received</span>
        <span class="bar-value" id="bv-served">{s["tokens_served"]} / {s["tokens_pushed"]}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill gradient-amber" id="bar-served" style="width: {served_pct}%"></div>
      </div>
    </div>

    <div class="bar-group">
      <div class="bar-header">
        <span class="bar-title">Token TTL Lifecycle</span>
        <span class="bar-value">{TOKEN_TTL}s window</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill gradient-violet" style="width: 100%"></div>
      </div>
    </div>
  </div>

  <div class="grid-2">

    <div class="section fade-up">
      <div class="section-hdr">
        <div class="icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="#f8789c" stroke-width="1.2"/><path d="M7 4v3.5l2.5 1.5" stroke="#f8789c" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <h2>Runtime</h2>
        <div class="line"></div>
      </div>

      <div class="runtime-wrap">
        <div class="ring-container">
          <svg width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(248,120,156,0.06)" stroke-width="6"/>
            <circle id="ring-arc" cx="50" cy="50" r="40" fill="none" stroke="url(#rg)" stroke-width="6"
              stroke-dasharray="251" stroke-dashoffset="{ring_offset}" stroke-linecap="round"/>
            <defs>
              <linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#f8789c"/>
                <stop offset="50%" stop-color="#f5a623"/>
                <stop offset="100%" stop-color="#c77dff"/>
              </linearGradient>
            </defs>
          </svg>
          <div class="ring-center">
            <div class="ring-number" id="v-ring-uptime">{uptime_min}</div>
            <div class="ring-unit">minutes</div>
          </div>
        </div>

        <div class="stat-pills">
          <div class="stat-pill">
            <span class="stat-pill-label"><span class="indicator" style="background:var(--rose)"></span>Uptime</span>
            <span class="stat-pill-value c-rose" id="v-uptime-pill">{uptime_min} min</span>
          </div>
          <div class="stat-pill">
            <span class="stat-pill-label"><span class="indicator" style="background:var(--amber)"></span>Tok/min</span>
            <span class="stat-pill-value c-amber" id="v-rate-pill">{rate}</span>
          </div>
          <div class="stat-pill">
            <span class="stat-pill-label"><span class="indicator" style="background:var(--coral)"></span>TTL</span>
            <span class="stat-pill-value c-coral">{TOKEN_TTL}s</span>
          </div>
          <div class="stat-pill">
            <span class="stat-pill-label"><span class="indicator" style="background:var(--violet)"></span>Peak</span>
            <span class="stat-pill-value c-violet" id="v-peak-pill">{pk}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="section fade-up">
      <div class="section-hdr">
        <div class="icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 4h10M2 7h10M2 10h7" stroke="#f8789c" stroke-width="1.2" stroke-linecap="round"/></svg>
        </div>
        <h2>API Endpoints</h2>
        <div class="line"></div>
      </div>

      <div class="endpoint-table">
        <div class="ep-row">
          <span class="ep-method post">POST</span>
          <span class="ep-path">/api/save-token</span>
          <span class="ep-desc">push new token</span>
        </div>
        <div class="ep-row">
          <span class="ep-method get">GET</span>
          <span class="ep-path">/api/get-token</span>
          <span class="ep-desc">grab 1 token</span>
        </div>
        <div class="ep-row">
          <span class="ep-method get">GET</span>
          <span class="ep-path">/api/status</span>
          <span class="ep-desc">statistics</span>
        </div>
        <div class="ep-row">
          <span class="ep-method del">DEL</span>
          <span class="ep-path">/api/tokens</span>
          <span class="ep-desc">flush queue</span>
        </div>
      </div>
    </div>
  </div>

  <div class="ts-strip fade-up">
    <div class="ts-card">
      <div class="ts-icon-wrap recv">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 2v8M5 7l3 3 3-3" stroke="#f8789c" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M3 13h10" stroke="#f8789c" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="ts-info">
        <div class="ts-label">Last Received</div>
        <div class="ts-val" id="v-last-recv">{last_recv}</div>
      </div>
    </div>
    <div class="ts-card">
      <div class="ts-icon-wrap serv">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 14V6M5 9l3-3 3 3" stroke="#f5a623" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M3 3h10" stroke="#f5a623" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="ts-info">
        <div class="ts-label">Last Served</div>
        <div class="ts-val" id="v-last-serv">{last_serv}</div>
      </div>
    </div>
  </div>

  <div class="footer fade-up">
    <div class="footer-l">ABCK TOKEN SERVER v2 &middot; NO STORAGE &middot; AUTO-REFRESH 3S</div>
    <div class="footer-r">BIND <span>0.0.0.0:{port}</span> &middot; TTL <span>{TOKEN_TTL}s</span></div>
  </div>
</div>

<script>
  function updateClock() {{
    const now = new Date();
    const h = String(now.getHours()).padStart(2,'0');
    const m = String(now.getMinutes()).padStart(2,'0');
    const s = String(now.getSeconds()).padStart(2,'0');
    const el = document.getElementById('clock');
    if (el) el.textContent = h + ':' + m + ':' + s;
  }}
  updateClock();
  setInterval(updateClock, 1000);

  function setTxt(id, val) {{
    const el = document.getElementById(id);
    if (el && el.textContent !== String(val)) el.textContent = val;
  }}

  async function refreshStats() {{
    try {{
      const r = await fetch('/api/status');
      const d = await r.json();
      const q = d.pool_size || 0;
      const pk = d.peak_queue || 0;
      const rate = d.rate_per_min || 0;
      const um = d.uptime_minutes || 0;

      setTxt('v-queue', q);
      setTxt('v-received', d.tokens_pushed || 0);
      setTxt('v-served', d.tokens_served || 0);
      setTxt('v-expired', d.tokens_expired || 0);
      setTxt('v-dupes', d.duplicates_rejected || 0);
      setTxt('v-rate', rate);
      setTxt('v-peak', pk);
      setTxt('v-flushed', d.tokens_flushed || 0);

      const qPct = pk > 0 ? Math.min(Math.round(q / pk * 100), 100) : 0;
      const sPct = d.tokens_pushed > 0 ? Math.min(Math.round((d.tokens_served || 0) / d.tokens_pushed * 100), 100) : 0;
      const bq = document.getElementById('bar-queue');
      const bs = document.getElementById('bar-served');
      if (bq) bq.style.width = qPct + '%';
      if (bs) bs.style.width = sPct + '%';
      setTxt('bv-queue', q + ' / ' + pk + ' peak');
      setTxt('bv-served', (d.tokens_served || 0) + ' / ' + (d.tokens_pushed || 0));

      setTxt('v-ring-uptime', um);
      setTxt('v-uptime-pill', um + ' min');
      setTxt('v-rate-pill', rate);
      setTxt('v-peak-pill', pk);

      const ringOff = Math.round(251 - (251 * Math.min(um / Math.max(um + 60, 1), 1)));
      const arc = document.getElementById('ring-arc');
      if (arc) arc.setAttribute('stroke-dashoffset', ringOff);

      setTxt('v-last-recv', d.last_received || '---');
      setTxt('v-last-serv', d.last_served || '---');
    }} catch(e) {{}}
  }}

  refreshStats();
  setInterval(refreshStats, 3000);

  (function() {{
    const container = document.getElementById('particles');
    if (!container) return;
    const colors = ['#f8789c','#f5a623','#c77dff','#fb7a5c'];
    for (let i = 0; i < 30; i++) {{
      const p = document.createElement('div');
      p.className = 'particle';
      p.style.left = Math.random() * 100 + '%';
      p.style.width = p.style.height = (1 + Math.random() * 2) + 'px';
      p.style.background = colors[Math.floor(Math.random() * colors.length)];
      p.style.animationDuration = (8 + Math.random() * 15) + 's';
      p.style.animationDelay = (Math.random() * 10) + 's';
      container.appendChild(p);
    }}
  }})();
</script>

</body>
</html>"""


@app.route("/")
def index():
    purge_expired()
    with stats_lock:
        s = dict(stats)
    with pool_lock:
        s["pool_size"] = len(token_pool)
    return build_frontend(s)


@app.route("/api/get-token", methods=["GET"])
def get_token():
    with stats_lock:
        stats["total_requests"] += 1
        stats["single_tokens"] += 1

    token_data = take_token()
    if token_data:
        token_data["served_at"] = datetime.now().isoformat()
        return jsonify(token_data)

    wait = int(request.args.get("wait", "0"))
    if wait > 0:
        wait = min(wait, 120)
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(1)
            token_data = take_token()
            if token_data:
                token_data["served_at"] = datetime.now().isoformat()
                return jsonify(token_data)

    with stats_lock:
        stats["errors"] += 1
    return jsonify({
        "error": "No tokens available. Push tokens first.",
        "pool_size": stats["pool_size"],
        "hint": "Add ?wait=30 to wait up to 30 seconds for a token"
    }), 503



@app.route("/api/status", methods=["GET"])
def get_status():
    purge_expired()
    with pool_lock:
        stats["pool_size"] = len(token_pool)
    with stats_lock:
        s = dict(stats)
    uptime_sec = (datetime.now() - datetime.fromisoformat(s["start_time"])).total_seconds()
    s["uptime_seconds"] = int(uptime_sec)
    s["uptime_minutes"] = round(uptime_sec / 60, 1)
    s["rate_per_min"] = round(s["tokens_pushed"] / max(uptime_sec / 60, 0.1), 1)
    s["ttl"] = TOKEN_TTL
    return jsonify(s)


@app.route("/api/tokens", methods=["DELETE"])
def flush_tokens():
    with pool_lock:
        count = len(token_pool)
        token_pool.clear()
    with stats_lock:
        stats["tokens_flushed"] += count
        stats["pool_size"] = 0
    return jsonify({"status": "flushed", "removed": count}), 200


@app.route("/api/save-token", methods=["POST"])
def api_save_token():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    if not token or not isinstance(token, str):
        return jsonify({"error": "Missing or invalid 'token' field"}), 400

    source = data.get("source", "akamai server")

    with pool_lock:
        existing = [t["token"] for t in token_pool]
        if token in existing:
            with stats_lock:
                stats["duplicates_rejected"] += 1
            return jsonify({"error": "Duplicate token", "pool_size": len(token_pool)}), 409

        entry = {
            "token": token,
            "source": source,
            "generated_at": datetime.now().isoformat(),
        }
        token_pool.append(entry)

        if len(token_pool) > POOL_MAX:
            token_pool.popleft()

        current_size = len(token_pool)

    with stats_lock:
        stats["tokens_pushed"] += 1
        stats["pool_size"] = current_size
        stats["last_received"] = datetime.now().isoformat()
        if current_size > stats["peak_queue"]:
            stats["peak_queue"] = current_size

    print(f"  [Push] Token from {source} (pool: {current_size})")
    return jsonify({"status": "saved", "pool_size": current_size}), 201


@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def catch_all(path):
    return jsonify({"error": "Not found"}), 404


NUM_AB_INSTANCES = int(os.environ.get("NUM_AB_INSTANCES", "3"))
ab_processes = []

def launch_ab():
    global ab_processes
    ab_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ab.py")
    if not os.path.exists(ab_script):
        print(f"  [!] ab.py not found at {ab_script} — skipping auto-launch")
        return

    port = int(os.environ.get("PORT", 3030))
    env = os.environ.copy()
    env["TOKEN_SERVER_HOST"] = "127.0.0.1"
    env["TOKEN_SERVER_PORT"] = str(port)

    print(f"  [ab.py] Launching {NUM_AB_INSTANCES} generators (pushing to 127.0.0.1:{port})...")
    for i in range(1, NUM_AB_INSTANCES + 1):
        proc = subprocess.Popen(
            [sys.executable, ab_script],
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        ab_processes.append(proc)
        print(f"  [ab.py #{i}] Started (PID: {proc.pid})")
        if i < NUM_AB_INSTANCES:
            time.sleep(2)

def shutdown_handler(signum, frame):
    global ab_processes
    for i, proc in enumerate(ab_processes, 1):
        if proc and proc.poll() is None:
            print(f"\n  [ab.py #{i}] Stopping (PID: {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"  [ab.py #{i}] Stopped")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    port = int(os.environ.get("PORT", 3030))
    skip_ab = os.environ.get("SKIP_AB", "").lower() in ("1", "true", "yes")

    print(f"\n  ABCK Token Server v2")
    print(f"  Port: {port}")
    print(f"  Pool max: {POOL_MAX}")
    print(f"  TTL: {TOKEN_TTL}s")
    print(f"  Generators: {NUM_AB_INSTANCES}")
    print(f"")
    print(f"  -- ENDPOINTS --")
    print(f"  Dashboard:       http://0.0.0.0:{port}/")
    print(f"  Single token:    http://0.0.0.0:{port}/api/get-token")
    print(f"  Stats:           http://0.0.0.0:{port}/api/status")
    print(f"  Flush:           DELETE http://0.0.0.0:{port}/api/tokens")
    print(f"")
    print(f"  -- PUSH --")
    print(f"  Push token: POST http://0.0.0.0:{port}/api/save-token")
    print()

    if not skip_ab:
        time.sleep(1)
        launch_ab()
    else:
        print(f"  [ab.py] Skipped (SKIP_AB=true)")

    print()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
