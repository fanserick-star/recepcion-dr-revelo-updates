from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated"
OUT.mkdir(parents=True, exist_ok=True)

SIZES = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]

def font(size, bold=True):
    candidates = [
        r"C:\\Windows\\Fonts\\segoeuib.ttf" if bold else r"C:\\Windows\\Fonts\\segoeui.ttf",
        r"C:\\Windows\\Fonts\\arialbd.ttf" if bold else r"C:\\Windows\\Fonts\\arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

def rounded_mask(size=1024, radius=180):
    m = Image.new("L", (size,size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((24,24,size-24,size-24), radius=radius, fill=255)
    return m

def base_icon(top, bottom, letter, letter_color, badge, badge_color):
    n=1024
    im=Image.new("RGBA",(n,n),(0,0,0,0))
    shape=Image.new("RGBA",(n,n),(0,0,0,0))
    d=ImageDraw.Draw(shape)
    d.rectangle((24,24,n-24,n//2), fill=top)
    d.rectangle((24,n//2,n-24,n-24), fill=bottom)
    shape.putalpha(rounded_mask(n,180))
    im.alpha_composite(shape)

    d=ImageDraw.Draw(im)
    d.rounded_rectangle((176,218,848,850), radius=145, fill=(248,250,252,255))
    f=font(330, True)
    box=d.textbbox((0,0),letter,font=f)
    tw,th=box[2]-box[0],box[3]-box[1]
    d.text(((n-tw)//2, 465-th//2-12), letter, font=f, fill=letter_color)

    cx,cy,r=748,748,146
    d.ellipse((cx-r,cy-r,cx+r,cy+r), fill=badge_color)
    if badge=="check":
        pts=[(670,748),(722,800),(830,665)]
        d.line(pts, fill="white", width=46, joint="curve")
    else:
        d.rounded_rectangle((cx-82,cy-25,cx+82,cy+25), radius=20, fill="white")
        d.rounded_rectangle((cx-25,cy-82,cx+25,cy+82), radius=20, fill="white")
    return im

icons = {
    "recepcion": base_icon(
        (48,176,188,255), (27,126,145,255), "R", (27,126,145,255),
        "check", (48,188,199,255)
    ),
    "historia": base_icon(
        (38,145,112,255), (32,73,113,255), "H", (32,73,113,255),
        "plus", (40,157,117,255)
    ),
}

for name, im in icons.items():
    png = OUT / f"{name}_icon.png"
    ico = OUT / f"{name}_icon.ico"
    im.resize((256,256), Image.Resampling.LANCZOS).save(png)
    im.save(ico, format="ICO", sizes=SIZES)

# Icono del instalador maestro: mitad Recepción / mitad Historia.
master=Image.new("RGBA",(1024,1024),(0,0,0,0))
m=rounded_mask(1024,180)
fill=Image.new("RGBA",(1024,1024),(0,0,0,0))
df=ImageDraw.Draw(fill)
df.rectangle((24,24,512,1000), fill=(48,176,188,255))
df.rectangle((512,24,1000,1000), fill=(32,73,113,255))
fill.putalpha(m)
master.alpha_composite(fill)
d=ImageDraw.Draw(master)
d.rounded_rectangle((190,220,834,840), radius=140, fill=(248,250,252,255))
f=font(250, True)
text="DR"
box=d.textbbox((0,0),text,font=f)
tw,th=box[2]-box[0],box[3]-box[1]
d.text(((1024-tw)//2,500-th//2-20),text,font=f,fill=(30,92,119,255))
master.resize((256,256),Image.Resampling.LANCZOS).save(OUT/"consultorio_icon.png")
master.save(OUT/"consultorio_icon.ico",format="ICO",sizes=SIZES)
