#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🥕 앱 아이콘 생성기 / PWA app-icon builder.

소스 이미지 1장(정사각 권장, 당근 마스코트 등)에서 PWA/iOS 아이콘 5종을 만든다.
  - icon-192.png, icon-512.png            (purpose: any, 풀블리드)
  - icon-maskable-192.png, -512.png        (안전영역 위해 ~80% 패딩 + 단색 배경)
  - apple-touch-icon.png (180, RGB)        (iOS 가 모서리 자동 라운딩)
배경색은 소스 모서리 픽셀에서 샘플링.

사용 / usage:  python3 scripts/make_app_icons.py <source-image> [--out docs]
"""
import sys, os, argparse
from PIL import Image

def square(im):
    w, h = im.size
    if w == h: return im
    s = min(w, h)
    return im.crop(((w-s)//2, (h-s)//2, (w-s)//2+s, (h-s)//2+s))

def bg_color(im):
    rgb = im.convert("RGB")
    px = rgb.load(); w, h = rgb.size
    corners = [px[1,1], px[w-2,1], px[1,h-2], px[w-2,h-2]]
    return tuple(sum(c[i] for c in corners)//4 for i in range(3))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "docs"))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    src = square(Image.open(a.source).convert("RGBA"))
    bg = bg_color(src)

    def save_any(size, name):
        src.resize((size, size), Image.LANCZOS).save(os.path.join(out, name))

    def save_maskable(size, name):
        canvas = Image.new("RGBA", (size, size), bg + (255,))
        inner = int(size * 0.80)
        carrot = src.resize((inner, inner), Image.LANCZOS)
        off = (size - inner) // 2
        canvas.alpha_composite(carrot, (off, off))
        canvas.save(os.path.join(out, name))

    save_any(512, "icon-512.png")
    save_any(192, "icon-192.png")
    save_maskable(512, "icon-maskable-512.png")
    save_maskable(192, "icon-maskable-192.png")
    src.resize((180, 180), Image.LANCZOS).convert("RGB").save(os.path.join(out, "apple-touch-icon.png"))
    print(f"✅ 아이콘 5종 생성 → {out}  (bg={bg})")

if __name__ == "__main__":
    main()
