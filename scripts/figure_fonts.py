#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared Matplotlib font setup for thesis figures.

The thesis figures contain Chinese labels. Matplotlib often falls back to
DejaVu Sans, which has no CJK glyphs, so this helper explicitly registers
common CJK fonts before any figure is saved.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path


def configure_matplotlib_chinese(plt, font_manager) -> str | None:
    """Configure Matplotlib to render Chinese text and minus signs correctly.

    Returns the selected font family name when one is found. The optional
    THESIS_CJK_FONT environment variable may point to a .ttf/.ttc/.otf file.
    """

    candidates: list[Path] = []
    env_font = os.environ.get("THESIS_CJK_FONT")
    if env_font:
        candidates.append(Path(env_font))

    system = platform.system()
    if system == "Windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        fonts_dir = windir / "Fonts"
        candidates.extend(
            fonts_dir / name
            for name in (
                "msyh.ttc",
                "msyhbd.ttc",
                "simhei.ttf",
                "simsun.ttc",
                "Deng.ttf",
            )
        )
    elif system == "Darwin":
        candidates.extend(
            Path(p)
            for p in (
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
            )
        )
    else:
        candidates.extend(
            Path(p)
            for p in (
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc",
            )
        )

    selected: str | None = None
    for path in candidates:
        if not path.is_file():
            continue
        try:
            font_manager.fontManager.addfont(str(path))
            selected = font_manager.FontProperties(fname=str(path)).get_name()
            break
        except (OSError, ValueError, RuntimeError):
            continue

    fallback_names = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "DengXian",
        "PingFang SC",
        "Heiti SC",
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    font_names = ([selected] if selected else []) + fallback_names
    deduped = list(dict.fromkeys(font_names))

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = deduped
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["svg.fonttype"] = "none"
    return selected
