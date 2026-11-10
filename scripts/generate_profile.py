#!/usr/bin/env python3
"""Generate custom, automatically refreshed GitHub profile SVG cards.

Uses only Python's standard library and GitHub's official REST/GraphQL APIs.
All motion is declarative (SMIL `<animate>` / CSS `@keyframes` inside the SVG
itself) so it plays back on GitHub with no JavaScript and no GIF assets.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
USERNAME = os.getenv("GH_USERNAME", "av6r01")
DISPLAY_NAME = os.getenv("PROFILE_NAME", "Avay Charan Das")
ROLE = os.getenv("PROFILE_ROLE", "CYBERSECURITY  /  NETWORKING  /  SOFTWARE DEVELOPMENT")
BIO_LINE = os.getenv("PROFILE_TAGLINE", "Learning by building. Focused on practical, secure software.")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"

BG = "#0b1020"
PANEL = "#111a2e"
PANEL_2 = "#14213a"
BORDER = "#263653"
TEXT = "#edf3ff"
MUTED = "#9aabc6"
ACCENT = "#8b9cff"
ACCENT_2 = "#50d6c8"
PALETTE = ["#18243a", "#243d58", "#286b78", "#2ea69d", "#74e0c8"]
LANG_COLORS = ["#8b9cff", "#50d6c8", "#f4b860", "#bd91f7", "#f080a5", "#8cc8ff", "#d2e27a"]

# Inline icon set (feather-style, 24x24) used instead of emoji or text glyphs.
# Each entry is (mode, [path/shape elements]); "fill" icons paint solid,
# "stroke" icons are outline-based line icons.
ICONS: dict[str, tuple[str, list[str]]] = {
    "star": ("fill", ['<path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14 2 9.27l6.91-1.01L12 2z"/>']),
    "fork": ("stroke", ['<line x1="6" y1="3" x2="6" y2="15"/>', '<circle cx="18" cy="6" r="2.4"/>',
                         '<circle cx="6" cy="18" r="2.4"/>', '<path d="M18 8.4A8.4 8.4 0 0 1 9.6 16.8"/>']),
    "link": ("stroke", ['<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
                         '<polyline points="15 3 21 3 21 9"/>', '<line x1="10" y1="14" x2="21" y2="3"/>']),
    "code": ("stroke", ['<polyline points="16 18 22 12 16 6"/>', '<polyline points="8 6 2 12 8 18"/>']),
    "shield": ("stroke", ['<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>']),
    "activity": ("stroke", ['<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>']),
    "repo": ("stroke", ['<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>',
                         '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>']),
    "users": ("stroke", ['<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>', '<circle cx="9" cy="7" r="4"/>',
                          '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>', '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>']),
}

STYLE_BLOCK = """
.fade-up{opacity:0;animation:fadeUp .7s cubic-bezier(.22,.7,.3,1) forwards}
.fade-in{opacity:0;animation:fadeIn .6s ease forwards}
.pulse{animation:pulse 2.6s ease-in-out infinite}
.drift{animation:drift 10s ease-in-out infinite}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes pulse{0%,100%{opacity:.55}50%{opacity:1}}
@keyframes drift{0%,100%{transform:translate(0,0)}50%{transform:translate(14px,-10px)}}
""".strip()


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def shorten(value: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def est_text_width(value: str, size: float, letter: float = 0.0) -> float:
    """Rough glyph-width estimate, good enough for a clip-reveal animation."""
    return len(value) * (size * 0.6 + letter)


def icon_defs_block() -> str:
    symbols = []
    for icon_id, (_, shapes) in ICONS.items():
        symbols.append(f'<symbol id="i-{icon_id}" viewBox="0 0 24 24">{"".join(shapes)}</symbol>')
    return "".join(symbols)


def icon(icon_id: str, x: float, y: float, size: float, color: str, stroke_width: float = 2.0) -> str:
    mode, _ = ICONS[icon_id]
    if mode == "fill":
        return f'<use href="#i-{icon_id}" x="{x}" y="{y}" width="{size}" height="{size}" fill="{color}"/>'
    return (f'<use href="#i-{icon_id}" x="{x}" y="{y}" width="{size}" height="{size}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>')


def initials_of(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def get_avatar_data_uri(user: dict) -> str | None:
    """Embed the profile photo as a base64 data URI so the hero never depends
    on an external image URL (no possibility of a broken avatar reference).
    Prefers a locally committed assets/avatar.png, falls back to the live
    GitHub avatar, and returns None if neither is available."""
    local = ASSETS / "avatar.png"
    try:
        if local.exists() and local.stat().st_size > 0:
            return f"data:image/png;base64,{base64.b64encode(local.read_bytes()).decode()}"
    except Exception as exc:
        print(f"Warning: could not read local avatar: {exc}", file=sys.stderr)

    avatar_url = user.get("avatar_url")
    if not avatar_url:
        return None
    sep = "&" if "?" in avatar_url else "?"
    try:
        request = urllib.request.Request(f"{avatar_url}{sep}s=240",
                                          headers={"User-Agent": "av6r01-dynamic-profile/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        media_type = response.headers.get_content_type() or "image/png"
        return f"data:{media_type};base64,{base64.b64encode(raw).decode()}"
    except Exception as exc:
        print(f"Warning: could not download avatar: {exc}", file=sys.stderr)
        return None


def api_request(url: str, method: str = "GET", payload: dict | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "av6r01-dynamic-profile/1.0",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = RuntimeError(f"GitHub API returned HTTP {exc.code}: {body}")
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def get_user() -> dict:
    return api_request(f"{API}/users/{urllib.parse.quote(USERNAME)}")


def get_repos() -> list[dict]:
    repos: list[dict] = []
    for page in range(1, 4):
        batch = api_request(
            f"{API}/users/{urllib.parse.quote(USERNAME)}/repos?per_page=100&page={page}&type=owner&sort=updated"
        )
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
    return [r for r in repos if not r.get("fork") and not r.get("archived")]


def get_language_totals(repos: list[dict]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    # Limit to the 30 most recently updated non-fork repositories to keep API use modest.
    selected = sorted(repos, key=lambda r: r.get("updated_at") or "", reverse=True)[:30]
    for repo in selected:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        try:
            langs = api_request(f"{API}/repos/{full_name}/languages")
            if isinstance(langs, dict):
                totals.update({k: int(v) for k, v in langs.items() if isinstance(v, (int, float))})
        except Exception as exc:  # Language card is non-critical.
            print(f"Warning: could not load languages for {full_name}: {exc}", file=sys.stderr)
    return dict(totals.most_common(8))


def get_contributions() -> tuple[list[dict], int] | None:
    if not TOKEN:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(now.year, 1, 1, tzinfo=dt.timezone.utc)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { contributionCount date weekday } }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "login": USERNAME,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
        },
    }
    try:
        result = api_request(GRAPHQL, method="POST", payload=payload)
        if result.get("errors"):
            raise RuntimeError(json.dumps(result["errors"])[:400])
        calendar = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
        return days, int(calendar.get("totalContributions", 0))
    except Exception as exc:
        print(f"Warning: GraphQL contribution query unavailable; using public-event fallback: {exc}", file=sys.stderr)
        return None


def get_public_events() -> list[dict]:
    try:
        data = api_request(f"{API}/users/{urllib.parse.quote(USERNAME)}/events/public?per_page=100")
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"Warning: could not load public events: {exc}", file=sys.stderr)
        return []


def svg_start(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<title>{esc(title)}</title>',
        '<defs>',
        '<linearGradient id="glow" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#8b9cff"/><stop offset="100%" stop-color="#50d6c8"/></linearGradient>',
        '<linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#8b9cff"/><stop offset="100%" stop-color="#50d6c8"/></linearGradient>',
        icon_defs_block(),
        '</defs>',
        f'<style>{STYLE_BLOCK}</style>',
        f'<rect width="{width}" height="{height}" rx="22" fill="{BG}"/>',
        '<circle cx="940" cy="-20" r="150" fill="#6579e8" opacity="0.08" class="drift"/>',
        '<circle cx="35" cy="210" r="110" fill="#50d6c8" opacity="0.045" class="drift"/>',
    ]


def text(x: float, y: float, value: str, size: int = 16, fill: str = TEXT,
         weight: int = 400, anchor: str = "start", letter: float = 0) -> str:
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-family="Inter,Segoe UI,Arial,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
            f'letter-spacing="{letter}">{esc(value)}</text>')


def save_svg(name: str, parts: list[str]) -> None:
    parts.append("</svg>")
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / name).write_text("\n".join(parts), encoding="utf-8")


def make_hero(user: dict, repo_count: int, stars: int) -> None:
    p = svg_start(1100, 260, f"{DISPLAY_NAME} GitHub profile banner")
    p += [
        '<rect x="28" y="28" width="1044" height="204" rx="18" fill="#0f1930" stroke="%s" stroke-width="1.2"/>' % BORDER,
        '<rect x="28" y="28" width="6" height="204" rx="3" fill="url(#glow)"/>',
    ]

    # Avatar: locally committed photo > live GitHub avatar > typographic initials.
    # Embedded as a base64 data URI so the card never depends on an external URL.
    ax, ay, ar = 112, 130, 54
    avatar_data = get_avatar_data_uri(user)
    p.append(f'<clipPath id="avatarClip"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>')
    p.append(
        f'<circle cx="{ax}" cy="{ay}" r="{ar + 9}" fill="none" stroke="url(#glow)" stroke-width="2.4" '
        f'stroke-dasharray="4 7" stroke-linecap="round" opacity="0.85">'
        f'<animateTransform attributeName="transform" type="rotate" from="0 {ax} {ay}" '
        f'to="360 {ax} {ay}" dur="18s" repeatCount="indefinite"/></circle>'
    )
    p.append(f'<circle cx="{ax}" cy="{ay}" r="{ar + 2}" fill="{PANEL_2}" class="pulse"/>')
    if avatar_data:
        p.append(
            f'<image href="{avatar_data}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" '
            f'clip-path="url(#avatarClip)" preserveAspectRatio="xMidYMid slice"/>'
        )
    else:
        p += [
            f'<circle cx="{ax}" cy="{ay}" r="{ar}" fill="url(#glow)" clip-path="url(#avatarClip)"/>',
            text(ax, ay + 13, initials_of(DISPLAY_NAME), 36, "#0b1020", 800, "middle"),
        ]

    text_x = ax + ar + 44
    p += [
        icon("shield", text_x, 56, 16, ACCENT_2),
        text(text_x + 22, 70, "GITHUB PROFILE  /  01", 12, ACCENT_2, 700, letter=2.0),
        f'<g class="fade-up" style="animation-delay:.05s">{text(text_x, 128, DISPLAY_NAME, 36, TEXT, 750)}</g>',
    ]

    # Role line: typewriter-style reveal via an animated clip rect, plus a blinking caret.
    role_w = est_text_width(ROLE, 13, 1.25) + 10
    p.append(
        f'<clipPath id="roleReveal"><rect x="{text_x - 2}" y="146" width="0" height="26">'
        f'<animate attributeName="width" from="0" to="{role_w:.0f}" dur="1.5s" begin="0.3s" '
        f'fill="freeze" calcMode="spline" keySplines="0.25 0.7 0.3 1"/></rect></clipPath>'
    )
    p.append(f'<g clip-path="url(#roleReveal)">{text(text_x, 164, ROLE, 13, MUTED, 650, letter=1.25)}</g>')
    p.append(
        f'<rect x="{text_x - 2}" y="150" width="2" height="15" fill="{ACCENT_2}" class="pulse">'
        f'<animate attributeName="x" from="{text_x - 2}" to="{text_x - 2 + role_w:.0f}" dur="1.5s" '
        f'begin="0.3s" fill="freeze"/></rect>'
    )

    p.append(f'<g class="fade-up" style="animation-delay:.5s">{text(text_x, 198, BIO_LINE, 15, "#c6d2e7", 400)}</g>')
    p += [
        '<rect x="820" y="68" width="215" height="124" rx="14" fill="#14213a" stroke="#2b3a59"/>',
        text(842, 102, "PUBLIC REPOSITORIES", 10, MUTED, 700, letter=1.1),
        f'<g class="fade-up" style="animation-delay:.2s">{text(842, 139, str(repo_count), 27, TEXT, 750)}</g>',
        icon("star", 842, 156, 13, ACCENT_2),
        text(861, 171, f"{stars} total stars  ·  @{USERNAME}", 12, ACCENT_2, 600),
        text(1037, 218, "BUILD  /  LEARN  /  SECURE", 9, MUTED, 600, "end", 1.2),
    ]
    save_svg("hero.svg", p)


def make_stats(user: dict, repos: list[dict], contribution_total: int | None) -> None:
    stars = sum(int(r.get("stargazers_count", 0)) for r in repos)
    forks = sum(int(r.get("forks_count", 0)) for r in repos)
    metrics = [
        ("PUBLIC REPOSITORIES", str(user.get("public_repos", len(repos))), "Owned public projects", "repo"),
        ("TOTAL STARS", str(stars), "Across public repositories", "star"),
        ("FOLLOWERS", str(user.get("followers", 0)), "GitHub community", "users"),
        ("TOTAL FORKS", str(forks), "Community copies", "fork"),
    ]
    if contribution_total is not None:
        metrics.append((f"CONTRIBUTIONS · {dt.datetime.now().year}", str(contribution_total),
                         "GitHub contribution calendar", "activity"))
    p = svg_start(1100, 225, "GitHub statistics")
    p.append(icon("activity", 38, 30, 14, ACCENT_2))
    p.append(text(60, 42, "GITHUB SIGNALS", 12, ACCENT_2, 700, letter=1.8))
    p.append(text(1060, 42, "LIVE DATA FROM GITHUB API", 10, MUTED, 600, "end", 1.1))
    count = len(metrics)
    gap = 14
    left = 34
    card_w = (1032 - (count - 1) * gap) / count
    for i, (label, value, sub, icon_id) in enumerate(metrics):
        x = left + i * (card_w + gap)
        p.append(f'<g class="fade-up" style="animation-delay:{i * 0.08:.2f}s">')
        p += [
            f'<rect x="{x:.1f}" y="62" width="{card_w:.1f}" height="126" rx="14" fill="{PANEL}" stroke="{BORDER}"/>',
            icon(icon_id, x + card_w - 34, 76, 15, ACCENT, 2.2),
            text(x + 17, 91, label, 10, MUTED, 700, letter=0.7),
            text(x + 17, 139, value, 34, TEXT, 750),
            text(x + 17, 166, sub, 11, ACCENT_2, 500),
        ]
        p.append('</g>')
    p.append(text(38, 211, "Counts reflect public GitHub data; contribution totals depend on API access.", 10, MUTED))
    save_svg("stats.svg", p)


def make_languages(totals: dict[str, int]) -> None:
    p = svg_start(1100, 210, "Most used programming languages")
    p += [icon("code", 38, 29, 14, ACCENT_2),
          text(60, 43, "LANGUAGE FOOTPRINT", 12, ACCENT_2, 700, letter=1.8),
          text(1060, 43, "BASED ON REPOSITORY LANGUAGE BYTES", 10, MUTED, 600, "end", 1.0)]
    if not totals:
        p += [text(42, 112, "No language data available yet.", 17, TEXT, 600),
              text(42, 145, "The card will populate after the workflow can read your public repositories.", 12, MUTED)]
        save_svg("languages.svg", p)
        return
    total = sum(totals.values()) or 1
    x0, y0, bar_w = 40, 75, 1020
    x = x0
    for i, (lang, amount) in enumerate(totals.items()):
        w = bar_w * amount / total
        p.append(
            f'<rect x="{x:.2f}" y="{y0}" width="0" height="13" fill="{LANG_COLORS[i % len(LANG_COLORS)]}">'
            f'<animate attributeName="width" from="0" to="{max(1, w):.2f}" dur="1s" begin="{i * 0.08:.2f}s" '
            f'fill="freeze" calcMode="spline" keySplines="0.22 0.7 0.3 1"/></rect>'
        )
        x += w
    cols = 4
    cell_w = 255
    items = list(totals.items())
    for i, (lang, amount) in enumerate(items):
        row, col = divmod(i, cols)
        x = 42 + col * cell_w
        y = 119 + row * 35
        pct = amount * 100 / total
        p.append(f'<g class="fade-in" style="animation-delay:{0.3 + i * 0.05:.2f}s">')
        p += [
            f'<circle cx="{x}" cy="{y-5}" r="5" fill="{LANG_COLORS[i % len(LANG_COLORS)]}"/>',
            text(x + 14, y, lang, 13, TEXT, 650),
            text(x + 206, y, f"{pct:.1f}%", 12, MUTED, 600, "end"),
        ]
        p.append('</g>')
    save_svg("languages.svg", p)


def make_projects(repos: list[dict]) -> None:
    # Prefer starred repositories; if there are no stars, use recently updated work.
    selected = sorted(repos, key=lambda r: (int(r.get("stargazers_count", 0)), r.get("updated_at") or ""), reverse=True)[:6]
    p = svg_start(1100, 520, "Selected GitHub projects")
    p += [icon("repo", 38, 29, 14, ACCENT_2),
          text(60, 43, "SELECTED PROJECTS", 12, ACCENT_2, 700, letter=1.8),
          text(1060, 43, f"{len(repos)} PUBLIC REPOSITORIES SCANNED", 10, MUTED, 600, "end", 1.0)]
    if not selected:
        p += [text(42, 145, "No public repositories found yet.", 18, TEXT, 600)]
    for i, repo in enumerate(selected):
        col, row = i % 2, i // 2
        x, y = 36 + col * 520, 67 + row * 145
        desc = shorten(repo.get("description") or "No description added yet.", 76)
        lang = repo.get("language") or "Mixed / not specified"
        updated = (repo.get("updated_at") or "")[:10]
        p.append(f'<g class="fade-up" style="animation-delay:{i * 0.07:.2f}s">')
        p += [
            f'<rect x="{x}" y="{y}" width="500" height="128" rx="14" fill="{PANEL}" stroke="{BORDER}"/>',
            f'<rect x="{x}" y="{y}" width="4" height="128" rx="2" fill="url(#glow)"/>',
            text(x + 20, y + 31, shorten(repo.get("name", "repository"), 38), 18, TEXT, 700),
            icon("star", x + 395, y + 19, 12, ACCENT_2, 2.2),
            text(x + 413, y + 30, str(repo.get("stargazers_count", 0)), 11, ACCENT_2, 600),
            icon("fork", x + 445, y + 19, 12, ACCENT_2, 2.2),
            text(x + 463, y + 30, str(repo.get("forks_count", 0)), 11, ACCENT_2, 600),
            text(x + 20, y + 58, desc, 12, MUTED, 400),
            text(x + 20, y + 99, f"{lang}  ·  Updated {updated or 'unknown'}", 11, "#c7d4eb", 550),
            icon("link", x + 455, y + 90, 12, ACCENT, 2.2),
            text(x + 448, y + 99, "VIEW REPO", 10, ACCENT, 700, "end", 0.5),
        ]
        p.append('</g>')
    p += [text(40, 500, f"github.com/{USERNAME}  ·  Cards are selected automatically from public repositories.", 10, MUTED)]
    save_svg("projects.svg", p)


def make_activity(contributions: tuple[list[dict], int] | None, events: list[dict]) -> None:
    p = svg_start(1100, 245, "GitHub contribution activity")
    p += [icon("activity", 38, 28, 14, ACCENT_2), text(60, 42, "CONTRIBUTION ACTIVITY", 12, ACCENT_2, 700, letter=1.8)]
    if contributions:
        days, total = contributions
        by_date = {d.get("date"): int(d.get("contributionCount", 0)) for d in days}
        source_label = f"{total} CONTRIBUTIONS THIS YEAR"
        # Github calendar has up to 53 weeks; use date columns so the grid remains stable.
        parsed = []
        for date_s, count in by_date.items():
            try:
                parsed.append((dt.date.fromisoformat(date_s), count))
            except Exception:
                pass
        parsed.sort()
        cells = parsed[-371:]
        start_x, start_y, cell, gap = 42, 77, 11, 4
        for index, (day, count) in enumerate(cells):
            col = index // 7
            row = day.weekday()
            level = 0 if count == 0 else 1 if count <= 2 else 2 if count <= 5 else 3 if count <= 9 else 4
            x, y = start_x + col * (cell + gap), start_y + row * (cell + gap)
            delay = min(col * 0.012, 0.6)
            p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{PALETTE[level]}" '
                      f'class="fade-in" style="animation-delay:{delay:.2f}s"/>')
        p += [text(42, 205, "LESS", 10, MUTED, 500)]
        for i, color in enumerate(PALETTE):
            p.append(f'<rect x="78" y="193" width="11" height="11" rx="3" fill="{color}"/>')
            if i < len(PALETTE) - 1:
                pass
        p += [text(150, 205, "MORE", 10, MUTED, 500), text(1060, 205, source_label, 10, ACCENT, 700, "end", 0.8)]
    else:
        # Events endpoint only returns a limited recent public-event window. Label it honestly.
        counts: Counter[str] = Counter()
        for event in events:
            created = event.get("created_at")
            if not created:
                continue
            try:
                day = dt.datetime.fromisoformat(created.replace("Z", "+00:00")).date().isoformat()
                counts[day] += 1
            except Exception:
                continue
        end = dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=363)
        source_label = "RECENT PUBLIC EVENTS · LIMITED API WINDOW"
        start_x, start_y, cell, gap = 42, 77, 11, 4
        for i in range(364):
            day = start + dt.timedelta(days=i)
            count = counts.get(day.isoformat(), 0)
            level = 0 if count == 0 else 1 if count == 1 else 2 if count <= 2 else 3 if count <= 4 else 4
            x, y = start_x + (i // 7) * (cell + gap), start_y + (i % 7) * (cell + gap)
            delay = min((i // 7) * 0.012, 0.6)
            p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{PALETTE[level]}" '
                      f'class="fade-in" style="animation-delay:{delay:.2f}s"/>')
        p += [text(42, 205, "LESS", 10, MUTED), text(150, 205, "MORE", 10, MUTED),
              text(1060, 205, source_label, 9, ACCENT, 700, "end", 0.5),
              text(42, 229, "Fallback view is based on public events, not the full GitHub contribution calendar.", 9, MUTED)]
        for i, color in enumerate(PALETTE):
            p.append(f'<rect x="{78 + i*16}" y="193" width="11" height="11" rx="3" fill="{color}"/>')
    save_svg("activity.svg", p)


def write_readme() -> None:
    readme = f'''<div align="center">

<img src="./assets/hero.svg" alt="{DISPLAY_NAME} profile banner" width="100%" />

**Cybersecurity · Network Security · Python · Web Development**

[![GitHub](https://img.shields.io/badge/GitHub-@{USERNAME}-111827?style=flat-square&logo=github)](https://github.com/{USERNAME})

<p>
<a href="#about">About</a> ·
<a href="#github-statistics">Statistics</a> ·
<a href="#languages">Languages</a> ·
<a href="#selected-projects">Projects</a> ·
<a href="#contribution-activity">Activity</a>
</p>

</div>

---

## About

I'm **{DISPLAY_NAME}**, a student focused on cybersecurity, networking, and software development. I enjoy learning how systems work, exploring security concepts, and building practical tools.

- **Security:** learning cybersecurity concepts and defensive practices.
- **Networking:** exploring protocols, infrastructure, and system communication.
- **Python:** automation, scripting, and practical utilities.
- **Web development:** building functional applications and interfaces.
- **Go:** currently learning Go for efficient software development.

> Learn by building. Improve through experimentation. Keep the work practical.

## GitHub Statistics

<img src="./assets/stats.svg" alt="Live GitHub statistics" width="100%" />

## Languages

<img src="./assets/languages.svg" alt="Programming language breakdown" width="100%" />

## Selected Projects

<img src="./assets/projects.svg" alt="Selected public repositories" width="100%" />

## Contribution Activity

<img src="./assets/activity.svg" alt="GitHub contribution activity" width="100%" />

---

<div align="center">

**Build · Learn · Secure · Repeat**

<sub>Profile visuals are generated from GitHub data by a custom Python script and refreshed automatically with GitHub Actions.</sub>

</div>
'''
    (ROOT / "README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    print(f"Generating dynamic GitHub profile for @{USERNAME}...")
    user = get_user()
    repos = get_repos()
    contributions = get_contributions()
    events = get_public_events() if contributions is None else []
    languages = get_language_totals(repos)
    contribution_total = contributions[1] if contributions else None
    stars = sum(int(r.get("stargazers_count", 0)) for r in repos)

    make_hero(user, int(user.get("public_repos", len(repos))), stars)
    make_stats(user, repos, contribution_total)
    make_languages(languages)
    make_projects(repos)
    make_activity(contributions, events)
    write_readme()
    print("Generated: assets/hero.svg, stats.svg, languages.svg, projects.svg, activity.svg and README.md")
    if not TOKEN:
        print("Note: no GH_TOKEN found. REST cards can still be generated, but contribution calendar uses the public-events fallback.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
