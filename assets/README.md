# Visual asset lifecycle

This directory intentionally contains no invented final anchors in phase one.
The benchmark must be scored before the following assets may be frozen:

- `dialogue-sketch-v1/style-anchor.png` — style-only reference;
- `dialogue-sketch-v1/cast/achi.png` — identity-only reference;
- `dialogue-sketch-v1/cast/zhoushu.png` — identity-only reference;
- `dialogue-sketch-v1/cast/qinyi.png` — identity-only reference;
- `dialogue-sketch-v1/cast/pair-achi-zhoushu.png` — primary two-person identity sheet;
- `dialogue-sketch-v1/cast/pair-achi-qinyi.png` — second two-person identity sheet.

`scripts/finalize_style.py` verifies and hashes these files, then writes the
machine-readable lock. A style image can never fill a cast slot, and a cast
image can never fill the style slot.

