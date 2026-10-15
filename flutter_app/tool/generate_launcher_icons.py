from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import math

ROOT = Path("android/app/src/main/res")
SIZES = {"mipmap-mdpi":48,"mipmap-hdpi":72,"mipmap-xhdpi":96,"mipmap-xxhdpi":144,"mipmap-xxxhdpi":192}

def make_icon(size):
    # Render large first for smooth edges, then downsample.
    s = 1024
    im = Image.new("RGB", (s,s), (2,19,15))
    px = im.load()
    for y in range(s):
        for x in range(s):
            t = max(0.0, 1 - math.sqrt(((x/s-.22)/.95)**2 + ((y/s-.05)/.95)**2))
            px[x,y] = (int(2+2*t), int(18+93*t), int(14+34*t))
    # Rounded-square alpha mask for launcher-friendly silhouette.
    mask = Image.new("L",(s,s),0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((12,12,s-12,s-12), radius=190, fill=255)
    im.putalpha(mask)
    # Professional green-on-black Fresh mark: bold F plus an upward market chart.
    mark = Image.new("RGBA",(s,s),(0,0,0,0))
    d = ImageDraw.Draw(mark)
    # Bold, clean F silhouette.
    d.rounded_rectangle((205,210,780,315), radius=34, fill=(94,239,75,255))
    d.rounded_rectangle((205,210,315,790), radius=34, fill=(94,239,75,255))
    d.rounded_rectangle((205,425,665,520), radius=28, fill=(32,205,100,255))
    # Rising bars and arrow in the right lower quadrant.
    d.rounded_rectangle((390,625,475,755), radius=18, fill=(30,195,100,255))
    d.rounded_rectangle((505,555,590,755), radius=18, fill=(52,220,105,255))
    d.rounded_rectangle((620,485,705,755), radius=18, fill=(155,246,65,255))
    d.line([(385,600),(500,510),(585,535),(720,390)], fill=(190,255,95,255), width=34, joint="curve")
    d.polygon([(690,385),(770,360),(750,445)], fill=(190,255,95,255))
    # Soft edge polish.
    mark = mark.resize((s,s), Image.Resampling.LANCZOS)
    im = Image.alpha_composite(im.convert("RGBA"), mark)
    return im.resize((size,size), Image.Resampling.LANCZOS)

for folder, size in SIZES.items():
    out = ROOT / folder
    out.mkdir(parents=True, exist_ok=True)
    make_icon(size).save(out / "ic_launcher.png", optimize=True)
print("Generated Fresh professional launcher icons for all Android densities.")
