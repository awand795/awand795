#!/usr/bin/env python3
"""
strip_svg_animations.py

Creates a static version of the animated SVG console card suitable for
PNG conversion (via rsvg-convert or similar).

Strips all SMIL animations (<animate>, <animateTransform>, <set>) and
removes the typewriter clip-paths and portrait-reveal mask so that the
static SVG renders with all content visible.

Usage:
  python scripts/strip_svg_animations.py <input.svg> [output.svg]
  (If output is omitted, writes to stdout.)
"""

import re
import sys
import os

# Match an <animate>, <animateTransform>, or <set> block (with children)
ANIM_BLOCK_RE = re.compile(
    r'<(?:animate(?:Transform)?|set)\b[^>]*>.*?</(?:animate(?:Transform)?|set)\s*>',
    re.IGNORECASE | re.DOTALL,
)
# Match a self-closing variant
ANIM_SELFCLOSE_RE = re.compile(
    r'<(?:animate(?:Transform)?|set)\b[^>]*/\s*>',
    re.IGNORECASE,
)


def strip_animations(content: str) -> str:
    """Strip all SVG animations & animated clip paths for a static render."""
    # 1. Remove all <animate>, <animateTransform>, <set> blocks
    result = ANIM_BLOCK_RE.sub('', content)
    result = ANIM_SELFCLOSE_RE.sub('', result)

    # 2. Remove clip paths used for typewriter reveal (sys-*)
    result = re.sub(
        r'<clipPath\s+id="sys-\d+">.*?</clipPath>\s*',
        '',
        result,
        flags=re.DOTALL,
    )

    # 3. Remove the portrait reveal mask
    result = re.sub(
        r'<mask\s+id="portrait-reveal">.*?</mask>\s*',
        '',
        result,
        flags=re.DOTALL,
    )

    # 4. Remove clip-path / mask attribute references
    result = re.sub(r'\s*clip-path="url\(#sys-\d+\)"', '', result)
    result = re.sub(r'\s*mask="url\(#portrait-reveal\)"', '', result)

    # 5. Remove the animated scan line effect (decorative)
    result = re.sub(
        r'<!-- Scan line effect -->.*?</rect>\s*',
        '',
        result,
        flags=re.DOTALL,
    )

    # 6. Remove the blinking cursor (animated)
    result = re.sub(
        r'<rect x="530" y="\d+" width="10" height="\d+" fill="#22D3EE" opacity="0">\s*<animate.*?</rect>',
        '',
        result,
        flags=re.DOTALL,
    )

    # 7. Collapse triple+ blank lines into double
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/strip_svg_animations.py <input.svg> [output.svg]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isfile(input_path):
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    static = strip_animations(content)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(static)
        print(f"Static SVG written to {output_path}")
    else:
        sys.stdout.write(static)


if __name__ == '__main__':
    main()
