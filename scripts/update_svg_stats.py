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
  {{ AVATAR_DATA_URI }} -> base64 data URI of the GitHub profile avatar

Design note:
  Template files (*.svg.template) are committed to the repo and always
  retain their placeholder tokens.  The production SVG is generated
  fresh every run, so stats never go stale.
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

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

OUTPUT_FILES = [f.replace(".template", "") for f in TEMPLATE_FILES]

# Fallback defaults in case the API call fails
DEFAULT_REPOS = "-"
DEFAULT_FOLLOWERS = "-"

# Avatar
DEFAULT_AVATAR_DATA_URI = ""
AVATAR_SIZE = 192  # Size of avatar image in the SVG (matches template: 192x192)


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
    avatar_url = user_data.get("avatar_url", None)

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


def fetch_avatar_data_uri(avatar_url: str | None, size: int = AVATAR_SIZE) -> str:
    """Download the avatar image and return a base64 data URI."""
    if not avatar_url:
        print("  [!] No avatar URL available, skipping avatar download")
        return DEFAULT_AVATAR_DATA_URI

    # Append size parameter
    if "?" in avatar_url:
        avatar_url = f"{avatar_url}&s={size}"
    else:
        avatar_url = f"{avatar_url}?s={size}"

    try:
        req = urllib.request.Request(avatar_url, headers={"User-Agent": f"{GITHUB_USER}-svg-updater/1.0"})
        print(f"  Downloading avatar ({size}x{size}) ...")
        with urllib.request.urlopen(req, timeout=20) as resp:
            img_data = resp.read()

        # Detect MIME type from Content-Type header
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        if content_type.startswith("image/"):
            mime = content_type
        else:
            mime = "image/jpeg"  # fallback

        b64 = base64.b64encode(img_data).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"
        size_kb = len(data_uri) / 1024
        print(f"  [+] Avatar encoded: {size_kb:.1f} KB")
        return data_uri
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  [!] Failed to download avatar: {e}", file=sys.stderr)
        return DEFAULT_AVATAR_DATA_URI


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
  |        awand795 SVG Stats Updater v1.1               |
  |        Template-based auto-updater                   |
  |        Now with avatar embedding!                    |
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

    # 2. Fetch & encode avatar
    avatar_data_uri = fetch_avatar_data_uri(avatar_url)

    # Format last sync timestamp
    last_sync = format_timestamp()

    print(f"\n  Repos:           {repos}")
    print(f"  Followers:       {followers}")
    print(f"  Status:          {active_status}")
    ok = "[OK]" if avatar_data_uri else "[FAIL]"
    print(f"  Avatar embedded: {ok}")
    print(f"  Last Sync:       {last_sync}\n")

    # 3. Define token replacements
    tokens = {
        "{{ REPOS }}": str(repos),
        "{{ FOLLOWERS }}": str(followers),
        "{{ ACTIVE_STATUS }}": active_status,
        "{{ LAST_SYNC }}": last_sync,
        "{{ AVATAR_DATA_URI }}": avatar_data_uri,
    }

    # 4. Generate SVGs from templates
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
        if k == "{{ AVATAR_DATA_URI }}":
            preview = v[:60] + "..." if len(v) > 60 else v
            print(f"    {k:25s} -> {preview}")
        else:
            print(f"    {k:25s} -> {v}")
    print()


if __name__ == "__main__":
    main()
