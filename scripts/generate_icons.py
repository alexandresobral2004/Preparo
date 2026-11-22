"""Gera os ícones PNG do PWA (192x192, 512x512 e maskable 512x512) sem dependências externas."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"

BG_DARK = (31, 92, 66)  # #1f5c42 verde mata
BG_RING = (45, 118, 86)
CREAM = (244, 247, 241)
GOLD = (245, 184, 46)


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _write_png(path: Path, size: int, pixels: list[tuple[int, int, int, int]]) -> None:
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        row_start = y * size
        for x in range(size):
            r, g, b, a = pixels[row_start + x]
            raw.extend((r, g, b, a))

    compressed = zlib.compress(bytes(raw), level=9)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _dist_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_round_rect(x: float, y: float, left: float, top: float, right: float, bottom: float, r: float) -> bool:
    if x < left or x > right or y < top or y > bottom:
        return False
    cx = min(max(x, left + r), right - r)
    cy = min(max(y, top + r), bottom - r)
    return math.hypot(x - cx, y - cy) <= r


def _sample_icon(nx: float, ny: float, *, maskable: bool) -> tuple[int, int, int, int]:
    """Avalia a cor RGBA em coordenadas normalizadas [0, 1] x [0, 1]."""
    if not maskable:
        # Canto arredondado suave para ícone padrão
        if not _in_round_rect(nx, ny, 0.02, 0.02, 0.98, 0.98, 0.21):
            return (0, 0, 0, 0)

    # Fundo com vinheta suave verde mata
    radial = math.hypot(nx - 0.5, ny - 0.45)
    shade = max(0.0, 1.0 - radial * 0.9)
    bg_r = int(BG_DARK[0] + (BG_RING[0] - BG_DARK[0]) * shade)
    bg_g = int(BG_DARK[1] + (BG_RING[1] - BG_DARK[1]) * shade)
    bg_b = int(BG_DARK[2] + (BG_RING[2] - BG_DARK[2]) * shade)

    # Escala menor no maskable para respeitar safe zone central (80%)
    scale = 0.78 if maskable else 0.92
    sx = 0.5 + (nx - 0.5) / scale
    sy = 0.5 + (ny - 0.5) / scale

    # Alças laterais da panela
    left_handle = _dist_segment(sx, sy, 0.20, 0.51, 0.25, 0.51) <= 0.028
    right_handle = _dist_segment(sx, sy, 0.75, 0.51, 0.80, 0.51) <= 0.028

    # Corpo da panela (retângulo inferior arredondado)
    in_pot = _in_round_rect(sx, sy, 0.24, 0.48, 0.76, 0.80, 0.09)
    # Borda superior da panela
    in_rim = _in_round_rect(sx, sy, 0.21, 0.44, 0.79, 0.50, 0.025)

    # Líquido interno sutil na panela (faixa dourada de vegetal)
    in_gold_band = _in_round_rect(sx, sy, 0.28, 0.54, 0.72, 0.585, 0.018)

    # Três ondas de vapor acima da panela
    steam_hit = False
    for wave_x, top_y, bot_y in ((0.37, 0.21, 0.38), (0.50, 0.16, 0.37), (0.63, 0.21, 0.38)):
        # Curva senoidal suave por 4 segmentos
        pts = []
        steps = 8
        for i in range(steps + 1):
            t = i / steps
            yy = top_y + t * (bot_y - top_y)
            xx = wave_x + 0.024 * math.sin(t * math.pi * 2.0)
            pts.append((xx, yy))
        for i in range(steps):
            if _dist_segment(sx, sy, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) <= 0.021:
                steam_hit = True
                break
        if steam_hit:
            break

    if in_gold_band:
        return (*GOLD, 255)
    if in_pot or in_rim or left_handle or right_handle or steam_hit:
        return (*CREAM, 255)
    return (bg_r, bg_g, bg_b, 255)


def render_icon(size: int, *, maskable: bool, supersample: int = 3) -> list[tuple[int, int, int, int]]:
    pixels: list[tuple[int, int, int, int]] = []
    inv_ss = 1.0 / (supersample * supersample)
    for y in range(size):
        for x in range(size):
            ar = ag = ab = aa = 0.0
            for sy in range(supersample):
                for sx in range(supersample):
                    nx = (x + (sx + 0.5) / supersample) / size
                    ny = (y + (sy + 0.5) / supersample) / size
                    r, g, b, a = _sample_icon(nx, ny, maskable=maskable)
                    ar += r
                    ag += g
                    ab += b
                    aa += a
            pixels.append((round(ar * inv_ss), round(ag * inv_ss), round(ab * inv_ss), round(aa * inv_ss)))
    return pixels


def main() -> None:
    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
    ]
    for filename, size, maskable in targets:
        print(f"Gerando {filename} ({size}x{size}, maskable={maskable})...")
        px = render_icon(size, maskable=maskable, supersample=3)
        _write_png(OUT_DIR / filename, size, px)
    print(f"Ícones salvos em {OUT_DIR}")


if __name__ == "__main__":
    main()
