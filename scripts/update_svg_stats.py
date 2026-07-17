#!/usr/bin/env python3
"""
update_svg_stats.py

Fetches live GitHub stats for awand795 and replaces placeholder tokens
in the SVG console card template files (*.svg.template) with real data,
outputting production-ready SVG files (*.svg).

Tokens:
  {{ REPOS }}          -> total public repositories
  {{ FOLLOWERS }}      -> total followers
  {{ ACTIVE_STATUS }}  -> "ACTIVE • Xh ago" or "ACTIVE" based on last activity
  {{ LAST_SYNC }}      -> human-readable timestamp of this update
  {{ ASCII_PORTRAIT }} -> ASCII art generated from GitHub avatar

Design note:
  Template files (*.svg.template) are committed to the repo and always
  retain their placeholder tokens.  The production SVG is generated
  fresh every run, so stats never go stale.
"""

import io
import json
import os
import random
import sys
import urllib.request
import urllib.error
import warnings
from datetime import datetime, timezone

# Suppress Pillow getdata() deprecation warning — still needed for Pillow <14
warnings.filterwarnings("ignore", message=".*getdata.*deprecated.*")


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Config ──────────────────────────────────────────────────────────────
GITHUB_USER = "awand795"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_DIR = os.path.join(REPO_ROOT, "assets", "hero")

TEMPLATE_FILES = [
    "agent-console-dark.svg.template",
    "agent-console-light.svg.template",
    "agent-console-mobile-dark.svg.template",
    "agent-console-mobile-light.svg.template",
]

OUTPUT_FILES = [f.replace(".template", "").replace(".svg", "-v2.svg") for f in TEMPLATE_FILES]

# Fallback defaults in case the API call fails
DEFAULT_REPOS = "-"
DEFAULT_FOLLOWERS = "-"


# ── Helpers ─────────────────────────────────────────────────────────────

def fetch_json(url: str):
    """Fetch JSON from a URL with a short timeout."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"{GITHUB_USER}-svg-updater/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
        print(f"  [!] Failed to fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_github_stats(username: str) -> dict:
    """Fetch public profile stats from the GitHub API."""
    print(f"  Fetching GitHub stats for @{username} ...")
    user_data = fetch_json(f"https://api.github.com/users/{username}")

    if not user_data:
        return {"repos": DEFAULT_REPOS, "followers": DEFAULT_FOLLOWERS, "is_active": True, "avatar_url": None}

    repos = user_data.get("public_repos", DEFAULT_REPOS)
    followers = user_data.get("followers", DEFAULT_FOLLOWERS)
    updated_at_str = user_data.get("updated_at", "")
    avatar_url = user_data.get("avatar_url")

    # Determine if user has been active recently (within 7 days)
    is_active = True
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_since = (now - updated_at).days
            is_active = days_since < 7
        except (ValueError, TypeError):
            pass

    return {"repos": repos, "followers": followers, "is_active": is_active, "avatar_url": avatar_url}


def fetch_last_push(username: str):
    """Fetch the last push event date to determine recent activity."""
    events = fetch_json(f"https://api.github.com/users/{username}/events/public?per_page=1")
    if events and isinstance(events, list) and len(events) > 0:
        created_at = events[0].get("created_at", "")
        if created_at:
            return created_at
    return None


# ── Matrix Rain ───────────────────────────────────────────────────────────
MATRIX_CHARS = (
    # Half-width katakana (matrix aesthetic)
    "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿ"
    "ﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓ"
    "ﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
    # Latin & digits — guaranteed to render in any monospace font
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    # Symbols for extra cyberpunk flavor
    "#$%&+-*/=>?@[]^_"
)


def generate_matrix_rain(rng=None) -> str:
    """Generate SVG matrix rain effect: falling columns of katakana & symbols.

    Creates 16 columns spread across the portrait panel, each containing
    a random string of characters that scrolls vertically with staggered
    timing, cycling indefinitely. Provides the classic 'digital rain' vibe.
    """
    if rng is None:
        rng = random.Random()

    panel_x0 = 24
    panel_x1 = 494
    panel_w = panel_x1 - panel_x0  # 470
    panel_y0 = 82
    panel_y1 = 520
    panel_h = panel_y1 - panel_y0  # 438

    n_cols = 16
    chars_per_col = 22
    col_spacing = panel_w // (n_cols + 1)

    drops = []

    for i in range(n_cols):
        x = panel_x0 + col_spacing * (i + 1) + rng.randint(-4, 4)
        # Vary speed and timing for organic feel
        duration = rng.uniform(3.5, 7.5)
        delay = rng.uniform(0.0, 5.0)
        # Head brighter than tail via max_opacity
        max_op = rng.uniform(0.30, 0.55)

        # Build random character string
        chars = "".join(rng.choice(MATRIX_CHARS) for _ in range(chars_per_col))

        # The column scrolls from above panel to below
        # y-offset starts at -panel_h and ends at +panel_h
        y_start = -panel_h  # -438 -> starts above view
        y_end = panel_h     # +438 -> ends below view

        drop = (
            f'  <g opacity="0">'
            f'<animate attributeName="opacity" '
            f'values="0;{max_op:.2f};{max_op:.2f};0" '
            f'keyTimes="0;0.06;0.94;1" '
            f'dur="{duration:.1f}s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
            f'<text class="matrix" x="{x}" y="{panel_y0}">{chars}'
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="0 {y_start}" to="0 {y_end}" '
            f'dur="{duration:.1f}s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
            f'</text></g>'
        )
        drops.append(drop)

        # Add a shorter "spark" drop for half the columns for visual density
        # (reduced from 16 to 8 to save ~16 indefinite animations per frame)
        if i % 2 == 0:
            spark_chars = "".join(rng.choice(MATRIX_CHARS) for _ in range(rng.randint(4, 8)))
            spark_dur = duration * rng.uniform(0.6, 0.85)
            spark_delay = delay + rng.uniform(0.3, 1.5)
            spark_max_op = max_op * rng.uniform(0.35, 0.55)

            spark = (
                f'  <g opacity="0">'
                f'<animate attributeName="opacity" '
                f'values="0;{spark_max_op:.2f};{spark_max_op:.2f};0" '
                f'keyTimes="0;0.06;0.94;1" '
                f'dur="{spark_dur:.1f}s" begin="{spark_delay:.1f}s" repeatCount="indefinite"/>'
                f'<text class="matrix" x="{x + rng.choice([-2, 0, 2])}" '
                f'y="{panel_y0 + rng.randint(-20, 20)}">{spark_chars}'
                f'<animateTransform attributeName="transform" type="translate" '
                f'from="0 {y_start}" to="0 {y_end}" '
                f'dur="{spark_dur:.1f}s" begin="{spark_delay:.1f}s" repeatCount="indefinite"/>'
                f'</text></g>'
            )
            drops.append(spark)

    spark_count = len(drops) - n_cols
    svg_markup = "\n".join(drops)
    print(f"  [+] Matrix rain: {n_cols} columns + {spark_count} sparks = {len(drops)} drops")
    return svg_markup


# ── Boot Particles ─────────────────────────────────────────────────────────
def generate_boot_particles(rng=None) -> str:
    """Generate SVG spark/particle effect during boot sequence.

    Creates ~35 small circular particles scattered across the portrait
    panel that drift in random directions with fade in/out during the
    boot sequence period (0.3s to 3.2s). Provides a cinematic 'system
    wake-up' visual.
    """
    if rng is None:
        rng = random.Random()

    panel_x0 = 24
    panel_x1 = 494
    panel_y0 = 82
    panel_y1 = 520

    n_particles = 35
    particles = []

    # Boot sequence animation period
    # First message at 0.40s, last message gone by ~3.01s
    # Particles should appear during this window
    boot_start = 0.30
    boot_end = 3.00

    for _ in range(n_particles):
        # Random position within panel
        cx = rng.uniform(panel_x0 + 10, panel_x1 - 10)
        cy = rng.uniform(panel_y0 + 10, panel_y1 - 10)

        # Random size (small dots for sparkle effect)
        r = rng.uniform(0.8, 2.5)

        # Random movement (small drift in random direction)
        dx = rng.uniform(-25, 25)
        dy = rng.uniform(-25, 25)

        # Random animation timing
        dur = rng.uniform(0.8, 2.0)
        delay = rng.uniform(boot_start, boot_end - dur)
        max_op = rng.uniform(0.25, 0.65)

        # Random initial size animation (pulsing)
        r_variation = r * rng.uniform(0.3, 0.7)

        particle = (
            f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'class="particle" opacity="0">'
            # Fade in/out during boot period
            f'<animate attributeName="opacity" '
            f'values="0;{max_op:.2f};{max_op:.2f};0" '
            f'keyTimes="0;0.10;0.85;1" '
            f'dur="{dur:.1f}s" begin="{delay:.2f}s" fill="freeze"/>'
            # Subtle size pulse for sparkle (freezes when particle fades out)
            f'<animate attributeName="r" '
            f'values="{r:.1f};{r + r_variation:.1f};{r:.1f}" '
            f'dur="{dur * 0.6:.1f}s" begin="{delay:.2f}s" '
            f'fill="freeze"/>'
            # Movement drift
            f'<animateTransform attributeName="transform" '
            f'type="translate" '
            f'from="0 0" to="{dx:.1f} {dy:.1f}" '
            f'dur="{dur:.1f}s" begin="{delay:.2f}s" fill="freeze"/>'
            f'</circle>'
        )
        particles.append(particle)

    svg_markup = "\n".join(particles)
    print(f"  [+] Boot particles: {n_particles} sparks generated")
    return svg_markup


# ── Boot Sequence ──────────────────────────────────────────────────────────
BOOT_MESSAGES = [
    ("OK",   "INITIALIZING CONSOLE: @{username}..."),
    ("OK",   "LOADING PROFILE: {username}..."),
    ("OK",   "SYNCING DATA: {repos} REPOS, {followers} FOLLOWERS"),
    ("WARN", "ESTABLISHING CONNECTION..."),
    ("PROG", "SYSTEM INITIALIZATION"),
    ("OK",   "AUTHENTICATING: @{username}..."),
    ("OK",   "DECRYPTING PAYLOAD..."),
    ("RUN",  "AGENT PROFILE: {username} [ACTIVE]"),
]


def generate_boot_sequence(username: str = "unknown", repos: int | str = "?", followers: int | str = "?") -> tuple[str, float]:
    """Generate SVG boot sequence elements with personalized GitHub stats.

    Args:
        username:  GitHub username (e.g. "awand795")
        repos:     Total public repositories (e.g. 51)
        followers: Total followers (e.g. 4)

    Returns (svg_markup, boot_delay):
      - svg_markup: SVG elements for the animated boot messages
      - boot_delay:  time (seconds) after which typing animation should start

    Each boot message fades in, stays visible briefly, then fades out
    with staggered timing, creating a terminal boot-up effect.
    Messages are formatted with the user's actual GitHub data.
    """
    panel_center_x = 259  # 24 + 470/2
    panel_center_y = 301  # 82 + 438/2

    line_height = 22
    # Format messages with personal data
    formatted_messages = []
    for status, msg_template in BOOT_MESSAGES:
        msg = msg_template.format(username=username, repos=repos, followers=followers)
        formatted_messages.append((status, msg))

    total_lines = len(formatted_messages)
    total_height = total_lines * line_height
    start_y = panel_center_y - total_height / 2

    dur_per_line = 1.3    # total animation duration per message
    stagger = 0.25        # stagger between message starts
    first_delay = 0.40    # first message start delay

    lines = []
    for i, (status, msg) in enumerate(formatted_messages):
        y = start_y + i * line_height
        begin = first_delay + i * stagger

        if status == "OK":
            status_color = "#10B981"
        elif status == "WARN":
            status_color = "#F59E0B"
        else:  # "RUN" / ">>"
            status_color = "#22D3EE"

        status_text = f"[{status:>4}]"

        # Build this line's content — standard message or progress bar
        if status == "WARN":
            # [WARN] blinks red before settling to amber — terminal tension moment
            badge = (
                f'<tspan fill="#EF4444">'
                f'<animate attributeName="fill" '
                f'values="#EF4444;#EF4444;#B91C1C;#EF4444;#B91C1C;#EF4444;#B91C1C;#F59E0B" '
                f'keyTimes="0;0.06;0.10;0.14;0.18;0.22;0.26;0.32" '
                f'dur="{dur_per_line:.1f}s" begin="{begin:.2f}s" fill="freeze"/>'
                f'{status_text}</tspan>'
            )
            line_content = (
                f'{badge}'
                f'<tspan fill="#94A3B8">  {msg}</tspan>'
            )
        else:
            badge = f'<tspan fill="{status_color}">{status_text}</tspan>'
            line_content = (
                f'{badge}'
                f'<tspan fill="#94A3B8">  {msg}</tspan>'
            )

        # Build the line wrapper
        if status == "PROG":
            # Progress bar uses custom layout with rects
            bar_width = 130
            bar_height = 12
            bar_rx = 2
            bar_x = 188
            bar_y = y - bar_height // 2 - 1
            bar_dur = 1.0

            pct_states = []
            pct_values = [("0%", 0.0), ("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)]
            for j, (pct_text, pct_time) in enumerate(pct_values):
                show_at = begin + pct_time * bar_dur
                if j < len(pct_values) - 1:
                    hide_at = begin + pct_values[j + 1][1] * bar_dur
                    pct_states.append(
                        f'<tspan visibility="hidden" class="pbar-pct">'
                        f'<set attributeName="visibility" to="visible" begin="{show_at:.2f}s" fill="freeze"/>'
                        f'<set attributeName="visibility" to="hidden" begin="{hide_at:.2f}s" fill="freeze"/>'
                        f'{pct_text}</tspan>'
                    )
                else:
                    # Last value (100%) stays visible
                    pct_states.append(
                        f'<tspan visibility="hidden" class="pbar-pct">'
                        f'<set attributeName="visibility" to="visible" begin="{show_at:.2f}s" fill="freeze"/>'
                        f'{pct_text}</tspan>'
                    )

            line_svg = (
                f'  <g opacity="0">'
                f'<animate attributeName="opacity" values="0;1;1;0;0" '
                f'keyTimes="0;0.06;0.70;0.85;1" dur="{dur_per_line:.1f}s" '
                f'begin="{begin:.2f}s" fill="freeze"/>'
                # Label
                f'<text x="{panel_center_x - 70}" y="{y:.0f}" '
                f'class="boot-msg" text-anchor="start">'
                f'<tspan class="pbar-label">[LOAD]</tspan>'
                f'</text>'
                # Bar background
                f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" '
                f'rx="{bar_rx}" fill="none" stroke="#64748B" stroke-width="1" opacity="0.4"/>'
                # Bar fill
                f'<rect x="{bar_x + 1}" y="{bar_y + 1}" width="0" height="{bar_height - 2}" '
                f'rx="{bar_rx - 0.5}" class="pbar-fill" opacity="0.55">'
                f'<animate attributeName="width" from="0" to="{bar_width - 2}" '
                f'dur="{bar_dur:.1f}s" begin="{begin:.2f}s" fill="freeze"/>'
                f'</rect>'
                # Percentage
                f'<text x="{bar_x + bar_width + 8}" y="{y:.0f}" '
                f'class="boot-msg" text-anchor="start">'
                + "".join(pct_states) + ""
                f'</text>'
                f'</g>'
            )
        else:
            line_svg = (
                f'  <g opacity="0">'
                f'<animate attributeName="opacity" values="0;1;1;0;0" '
                f'keyTimes="0;0.06;0.70;0.85;1" dur="{dur_per_line:.1f}s" '
                f'begin="{begin:.2f}s" fill="freeze"/>'
                f'<text x="{panel_center_x}" y="{y:.0f}" text-anchor="middle" '
                f'class="boot-msg">'
                f'{line_content}'
                f'</text></g>'
            )

        lines.append(line_svg)

    svg_markup = "\n".join(lines)
    boot_delay = first_delay + (total_lines - 1) * stagger + dur_per_line + 0.20
    # = 0.40 + 1.50 + 1.30 + 0.20 = 3.40s

    print(f"  [+] Boot sequence: {total_lines} messages, ~{boot_delay - 0.20:.1f}s total, typing at {boot_delay:.2f}s")
    return svg_markup, boot_delay


def _remove_background(img: Image.Image, margin: float = 0.10) -> Image.Image:
    """
    Auto-detect and crop away the background of a GitHub avatar.

    Strategy:
      1. Downscale to a 40×40 thumbnail for fast pixel analysis.
      2. Sample edge pixels (corners + mid-edges) to estimate background color.
      3. Mark any pixel whose RGB Euclidean distance from the background
         estimate exceeds a threshold as "foreground".
      4. Find the bounding box of foreground pixels.
      5. Crop the original image with a small margin around the subject.

    Falls back to the full image if the result would be empty or tiny,
    or if the avatar is already tightly cropped with no clear background.
    """
    # Downscale to a thumbnail for fast analysis
    thumb = img.copy()
    thumb.thumbnail((40, 40), Image.LANCZOS)
    tw, th = thumb.size
    if tw < 8 or th < 8:
        print("  [-] Thumbnail too small — skipping background removal")
        return img

    # Sample background from 8 edge positions (corners + edge midpoints)
    edge_samples = [
        thumb.getpixel((0, 0)),
        thumb.getpixel((tw - 1, 0)),
        thumb.getpixel((0, th - 1)),
        thumb.getpixel((tw - 1, th - 1)),
        thumb.getpixel((tw // 2, 0)),
        thumb.getpixel((tw // 2, th - 1)),
        thumb.getpixel((0, th // 2)),
        thumb.getpixel((tw - 1, th // 2)),
    ]

    # Compute median per channel (robust to outliers)
    r_vals = sorted(p[0] for p in edge_samples)
    g_vals = sorted(p[1] for p in edge_samples)
    b_vals = sorted(p[2] for p in edge_samples)
    mid = len(r_vals) // 2
    bg_color = (r_vals[mid], g_vals[mid], b_vals[mid])

    # Threshold: squared Euclidean distance
    bg_r, bg_g, bg_b = bg_color
    threshold_sq = 2000  # ~45 per-channel difference

    # Build a binary mask from the thumbnail
    pixels = list(thumb.getdata())  # Pillow <14 compat; must be get_flattened_data().tolist() for Pillow 14+
    fg_mask = [
        (r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2 > threshold_sq
        for (r, g, b) in pixels
    ]

    # Find bounding box
    fg_y = [
        y for y in range(th)
        if any(fg_mask[y * tw + x] for x in range(tw))
    ]
    fg_x = [
        x for x in range(tw)
        if any(fg_mask[y * tw + x] for y in range(th))
    ]

    if not fg_y or not fg_x:
        print("  [-] No distinct background detected — using full image")
        return img

    y0, y1 = min(fg_y), max(fg_y)
    x0, x1 = min(fg_x), max(fg_x)

    # If the foreground fills most of the image, skip cropping
    fg_area_ratio = (y1 - y0 + 1) * (x1 - x0 + 1) / (tw * th)
    if fg_area_ratio > 0.85:
        print(f"  [-] Subject fills {fg_area_ratio:.0%} of frame — no background to crop")
        return img

    # Add margin
    margin_x = max(int((x1 - x0) * margin), 2)
    margin_y = max(int((y1 - y0) * margin), 2)
    y0 = max(0, y0 - margin_y)
    y1 = min(th - 1, y1 + margin_y)
    x0 = max(0, x0 - margin_x)
    x1 = min(tw - 1, x1 + margin_x)

    # Scale bounding box to original image coordinates
    scale_x = img.size[0] / tw
    scale_y = img.size[1] / th
    crop_box = (
        int(x0 * scale_x),
        int(y0 * scale_y),
        int((x1 + 1) * scale_x),
        int((y1 + 1) * scale_y),
    )

    # Guard against degenerate crops
    crop_w = crop_box[2] - crop_box[0]
    crop_h = crop_box[3] - crop_box[1]
    if crop_w < 10 or crop_h < 10:
        print("  [-] Foreground crop too small — using full image")
        return img

    cropped = img.crop(crop_box)
    print(f"  [+] Auto-cropped to subject: {cropped.size}")
    return cropped


def fetch_ascii_portrait(avatar_url: str | None, width: int = 82, max_rows: int = 60,
                         typing_delay_start: float = 0.30) -> tuple[str, str]:
    """Download the GitHub avatar and convert it to an ASCII art SVG text block.

    Returns (tspan_lines, typing_clip_paths):
      - tspan_lines:  SVG <tspan> elements wrapped in per-line <g clip-path="..."> groups
                      for the typing animation effect.
      - typing_clip_paths: SVG <clipPath> definitions that reveal each line
                           left-to-right with staggered timing.

    Auto-crops the background, applies contrast stretch, and inverts for
    dark-background SVG rendering. Each line's clip path animates width
    from 0 → full text width over 0.25s, staggered 0.07s per line,
    starting 0.3s after the SVG loads.
    """
    if not HAS_PIL or not avatar_url:
        print("  [!] Pillow not available or no avatar URL — using fallback portrait")
        return "", ""

    try:
        # Download avatar (2x ASCII width for good source resolution)
        req = urllib.request.Request(
            f"{avatar_url}&s={width * 2}",
            headers={"User-Agent": f"{GITHUB_USER}-svg-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            img = Image.open(io.BytesIO(resp.read()))

        # Auto-crop background — focus on the person
        img = _remove_background(img)

        # Rich ASCII ramp: dense chars first (for dark bg, dense = more visible)
        ascii_chars = "@%#*+=-:. "

        # Resize to ASCII grid
        aspect = img.size[1] / img.size[0]
        chars_tall = min(int(width * aspect * 0.55), max_rows)
        img_small = img.resize((width, chars_tall), Image.LANCZOS)
        img_gray = img_small.convert("L")
        px_list = list(img_gray.getdata())  # Pillow <14 compat; must be get_flattened_data().tolist() for Pillow 14+

        # Percentile-based contrast stretch (more robust than hard clip)
        sorted_px = sorted(px_list)
        n = len(sorted_px)
        lo = sorted_px[int(n * 0.02)]   # 2nd percentile
        hi = sorted_px[int(n * 0.98)]   # 98th percentile
        span = hi - lo
        if span > 20:  # only stretch if there's meaningful contrast to gain
            px_list = [
                max(0, min(255, int((v - lo) / span * 255))) for v in px_list
            ]

        # Calculate centering position within the 470×438 portrait panel
        # Panel bounds: x=24..494, y=82..520
        # Each ASCII char is ~3.75px wide at font-size 6.5px + letter-spacing -0.15px
        char_width = 3.9   # approximate width of Courier New at 6.5px
        line_height = 7.15

        text_width = width * char_width
        text_height = chars_tall * line_height

        panel_x = 24       # portrait panel left edge
        panel_y = 82       # portrait panel top edge
        panel_w = 470      # portrait panel width
        panel_h = 438      # portrait panel height

        # Center horizontally
        start_x = panel_x + (panel_w - text_width) / 2
        # Center vertically
        start_y = panel_y + (panel_h - text_height) / 2

        # Build SVG tspan elements
        n_chars = len(ascii_chars)
        lines = []
        clip_paths = []

        # Typing animation timing
        # Each line reveals left-to-right over 0.25s, staggered 0.08s apart
        # Animation starts after boot sequence completes (typing_delay_start)
        typing_duration = 0.25
        typing_stagger = 0.08
        reveal_width = text_width + 15  # slightly wider than text to avoid clipping last char

        for y in range(chars_tall):
            row_chars = []
            for x in range(width):
                pixel = px_list[y * width + x]
                inv = 255 - pixel  # invert for dark background
                idx = int(inv * (n_chars - 1) / 255)
                idx = min(idx, n_chars - 1)
                row_chars.append(ascii_chars[idx])
            row = "".join(row_chars)
            y_pos = start_y + y * line_height
            delay = typing_delay_start + y * typing_stagger

            # Per-line clip path for typing effect
            clip_paths.append(
                f'  <clipPath id="typing-{y}">'
                f'<rect x="{start_x:.1f}" y="{y_pos:.2f}" width="0" height="{line_height}">'
                f'<animate attributeName="width" from="0" to="{reveal_width:.0f}" '
                f'dur="{typing_duration}s" begin="{delay:.2f}s" fill="freeze" '
                f'calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
                f'</rect></clipPath>'
            )

            # Use separate <text> element per line with clip-path attribute
            # This is SVG 1.1 compliant (unlike <g> inside <text> which librsvg drops)
            # Inline font-family/font-size as defensive fallback in case CSS stripped by sanitizer
            lines.append(
                f'<text class="ascii" '
                f'font-family="\'Courier New\',Consolas,monospace" font-size="6.5px" '
                f'x="{start_x:.1f}" y="{y_pos:.2f}" '
                f'clip-path="url(#typing-{y})" xml:space="preserve">{row}</text>'
            )

        tspan_output = "\n".join(lines)
        clip_output = "\n".join(clip_paths)

        # Cache cursor position & timing for compute_cursor_position()
        global _CURSOR_X, _CURSOR_Y, _CURSOR_CHARS_TALL, _CURSOR_DELAY_START, _CURSOR_STAGGER, _CURSOR_DURATION
        last_line_y = start_y + (chars_tall - 1) * line_height
        _CURSOR_X = start_x + text_width + 2  # 2px after last char
        _CURSOR_Y = last_line_y - line_height + 0.5  # top of character cell
        _CURSOR_CHARS_TALL = chars_tall
        _CURSOR_DELAY_START = typing_delay_start
        _CURSOR_STAGGER = typing_stagger
        _CURSOR_DURATION = typing_duration

        total_anim = typing_delay_start + (chars_tall - 1) * typing_stagger + typing_duration
        print(f"  [+] Generated ASCII portrait: {width}x{chars_tall} chars (centered at x={start_x:.0f}, y={start_y:.0f})")
        print(f"  [+] Typing animation: {chars_tall} lines, {typing_duration}s each, "
              f"stagger {typing_stagger}s, total ~{total_anim:.1f}s")
        print(f"  [+] Cursor at x={_CURSOR_X:.0f}, y={_CURSOR_Y:.0f}, "
              f"delay={total_anim + 0.30:.2f}s")
        return tspan_output, clip_output

    except Exception as e:
        print(f"  [!] Failed to generate ASCII portrait: {e}", file=sys.stderr)
        return "", ""    # Module-level cache for cursor position set by fetch_ascii_portrait
_CURSOR_X = 0.0
_CURSOR_Y = 0.0
_CURSOR_CHARS_TALL = 0
_CURSOR_DELAY_START = 0.30
_CURSOR_STAGGER = 0.08
_CURSOR_DURATION = 0.25


def compute_cursor_position() -> dict:
    """Return the blinking cursor position and animation delay.

    Uses cached values from the last fetch_ascii_portrait call.
    Falls back to defaults if no ASCII was generated.
    """
    if _CURSOR_CHARS_TALL == 0:
        return {"x": "0", "y": "0", "delay": "0"}

    # Cursor appears at end of last line after typing animation completes
    # with a small pause (0.3s) for readability
    typing_end = _CURSOR_DELAY_START + (_CURSOR_CHARS_TALL - 1) * _CURSOR_STAGGER + _CURSOR_DURATION
    delay = typing_end + 0.30

    return {
        "x": f"{_CURSOR_X:.1f}",
        "y": f"{_CURSOR_Y:.1f}",
        "delay": f"{delay:.2f}",
    }


def format_timestamp() -> str:
    """Return a human-readable timestamp like 'Jul 16, 2026 14:30 UTC'."""
    now = datetime.now(timezone.utc)
    return now.strftime("%b %d, %Y %H:%M UTC")


def humanize_time_ago(iso_str: str) -> str:
    """Convert ISO timestamp to 'X hours/days ago'."""
    if not iso_str:
        return "recently"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            mins = seconds // 60
            return f"{mins}m ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        days = seconds // 86400
        return f"{days}d ago"
    except (ValueError, TypeError):
        return "recently"


def generate_svg_from_template(template_path: str, output_path: str, tokens: dict) -> bool:
    """
    Read the template file, replace all tokens, and write the output SVG.
    Returns True if the file was written successfully.
    """
    if not os.path.isfile(template_path):
        print(f"  [!] Template not found: {template_path}", file=sys.stderr)
        return False

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    for key, value in tokens.items():
        content = content.replace(key, str(value))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  [+] Generated {os.path.basename(output_path)}")
    return True


# ── Main ────────────────────────────────────────────────────────────────

def main():
    banner = """
  +------------------------------------------------------+
  |        awand795 SVG Stats Updater v1.0               |
  |        Template-based auto-updater                   |
  +------------------------------------------------------+
"""
    print(banner)

    # 1. Fetch live data
    stats = fetch_github_stats(GITHUB_USER)
    last_push = fetch_last_push(GITHUB_USER)
    repos = stats["repos"]
    followers = stats["followers"]
    avatar_url = stats.get("avatar_url")

    # Determine active status
    if last_push:
        time_ago = humanize_time_ago(last_push)
        active_status = f"ACTIVE | {time_ago}"
    elif stats["is_active"]:
        active_status = "ACTIVE"
    else:
        active_status = "IDLE"

    # Format last sync timestamp
    last_sync = format_timestamp()

    # Generate boot sequence (terminal boot-up animation before typing)
    boot_svg, boot_delay = generate_boot_sequence(username=GITHUB_USER, repos=repos, followers=followers)

    # Generate ASCII portrait from avatar (typing starts after boot sequence)
    ascii_portrait, typing_clip_paths = fetch_ascii_portrait(avatar_url, typing_delay_start=boot_delay)

    print(f"\n  Repos:      {repos}")
    print(f"  Followers:  {followers}")
    print(f"  Status:     {active_status}")
    print(f"  Last Sync:  {last_sync}")
    print(f"  ASCII art:  {'Yes' if ascii_portrait else 'Fallback'}")
    print(f"  Boot delay: {boot_delay:.2f}s\n")

    # Compute blinking cursor position (end of last ASCII line)
    # and delay (after typing animation finishes)
    cursor_data = compute_cursor_position()

    # 2. Define token replacements
    tokens = {
        "{{ REPOS }}": str(repos),
        "{{ FOLLOWERS }}": str(followers),
        "{{ ACTIVE_STATUS }}": active_status,
        "{{ LAST_SYNC }}": last_sync,
        "{{ ASCII_PORTRAIT }}": ascii_portrait,
        "{{ TYPING_CLIP_PATHS }}": typing_clip_paths,
        "{{ MATRIX_RAIN }}": generate_matrix_rain(),
        "{{ BOOT_PARTICLES }}": generate_boot_particles(),
        "{{ BOOT_SEQUENCE }}": boot_svg,
        "{{ CURSOR_X }}": str(cursor_data["x"]),
        "{{ CURSOR_Y }}": str(cursor_data["y"]),
        "{{ CURSOR_DELAY }}": str(cursor_data["delay"]),
    }

    # 3. Generate SVGs from templates
    svg_dir = SVG_DIR
    if not os.path.isdir(svg_dir):
        print(f"  [!] SVG directory not found: {svg_dir}", file=sys.stderr)
        sys.exit(1)

    generated = 0
    for template_name, output_name in zip(TEMPLATE_FILES, OUTPUT_FILES):
        template_path = os.path.join(svg_dir, template_name)
        output_path = os.path.join(svg_dir, output_name)
        if generate_svg_from_template(template_path, output_path, tokens):
            generated += 1

    print(f"\n  [+] {generated}/{len(TEMPLATE_FILES)} SVG file(s) generated successfully.\n")

    # Print token summary for debugging
    print("  Token map:")
    for k, v in tokens.items():
        print(f"    {k:25s} -> {v}")
    print()


if __name__ == "__main__":
    main()
