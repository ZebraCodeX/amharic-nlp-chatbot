#!/usr/bin/env python3
"""Generate the ሕሳር PWA icons (pure stdlib PNG writer).

Usage: python3 tools/gen_icons.py
Writes static/icon-180.png, static/icon-192.png, static/icon-512.png to match
static/icon.svg (gradient background, white ring + inner dot, accent dot).
"""
import os
import struct
import zlib


def make_png(size, path):
    def lerp(a, b, t):
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    top = (0x4e, 0xcd, 0xc4)
    bottom = (0x0f, 0x34, 0x60)
    accent = (0xe9, 0x45, 0x60)
    white = (0xff, 0xff, 0xff)
    dark = (0x0f, 0x34, 0x60)

    def px(x, y):
        t = y / size
        base = lerp(top, bottom, t)
        cx, cy = size * 0.5, size * 0.453
        r_ring = size * 0.16
        r_dot = size * 0.062
        cxd, cyd = size * 0.90, size * 0.82
        r_acc = size * 0.09
        dx, dy = x - cx, y - cy
        d = (dx * dx + dy * dy) ** 0.5
        dd = ((x - cxd) * (x - cxd) + (y - cyd) * (y - cyd)) ** 0.5
        if dd <= r_acc * 1.08:
            # accent dot with soft edge
            col = lerp(accent, base, max(0.0, (dd - r_acc) / (r_acc * 0.08)))
        elif r_dot <= d <= r_ring:
            soft = max(0.0, min(1.0, min(d - r_ring + 3, r_dot - d + 3)))
            col = lerp(white, base, soft * 0.25)
        elif d < r_dot * 0.9:
            col = dark
        else:
            col = base
        return (col[0], col[1], col[2], 255)

    raw = b''.join(
        b'\x00' + b''.join(struct.pack('4B', *px(x, y)) for x in range(size))
        for y in range(size))
    data = zlib.compress(raw, 9)

    def chunk(tag, payload):
        c = struct.pack('>I', len(payload)) + tag + payload
        return c + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', data) + chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)
    print('wrote', path, size, 'x', size)


if __name__ == '__main__':
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static = os.path.join(here, 'static')
    for s in (512, 192, 180):
        make_png(s, os.path.join(static, 'icon-%d.png' % s))