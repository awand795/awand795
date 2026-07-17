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


def fetch_ascii_portrait(avatar_url: str | None, width: int = 82, max_rows: int = 60) -> tuple[str, str]:
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
        # Each line reveals left-to-right over 0.25s, staggered 0.07s apart
        # Animation starts 0.3s after SVG loads
        typing_duration = 0.25
        typing_stagger = 0.08
        typing_delay_start = 0.30
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

        # Cache cursor position for compute_cursor_position()
        global _CURSOR_X, _CURSOR_Y, _CURSOR_CHARS_TALL
        last_line_y = start_y + (chars_tall - 1) * line_height
        _CURSOR_X = start_x + text_width + 2  # 2px after last char
        _CURSOR_Y = last_line_y - line_height + 0.5  # top of character cell
        _CURSOR_CHARS_TALL = chars_tall

        total_anim = typing_delay_start + (chars_tall - 1) * typing_stagger + typing_duration
        print(f"  [+] Generated ASCII portrait: {width}x{chars_tall} chars (centered at x={start_x:.0f}, y={start_y:.0f})")
        print(f"  [+] Typing animation: {chars_tall} lines, {typing_duration}s each, "
              f"stagger {typing_stagger}s, total ~{total_anim:.1f}s")
        print(f"  [+] Cursor at x={_CURSOR_X:.0f}, y={_CURSOR_Y:.0f}, "
              f"delay={total_anim + 0.30:.2f}s")
        return tspan_output, clip_output

    except Exception as e:
        print(f"  [!] Failed to generate ASCII portrait: {e}", file=sys.stderr)
        return "", ""


# Module-level cache for cursor position set by fetch_ascii_portrait
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

    # Generate ASCII portrait from avatar
    ascii_portrait, typing_clip_paths = fetch_ascii_portrait(avatar_url)

    print(f"\n  Repos:      {repos}")
    print(f"  Followers:  {followers}")
    print(f"  Status:     {active_status}")
    print(f"  Last Sync:  {last_sync}")
    print(f"  ASCII art:  {'Yes' if ascii_portrait else 'Fallback'}\n")

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
