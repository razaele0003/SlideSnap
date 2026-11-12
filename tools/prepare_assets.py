"""Download official Poppins files; generate the app's geometric program icon."""
from pathlib import Path
from urllib.request import urlopen
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "slidesnap" / "assets"
root.mkdir(parents=True, exist_ok=True)
for name in ["Poppins-Regular.ttf", "Poppins-Medium.ttf", "Poppins-SemiBold.ttf", "OFL.txt"]:
    target = root / name
    if not target.exists():
        target.write_bytes(urlopen(f"https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/{name}", timeout=30).read())
im = Image.new("RGBA", (256, 256), (12, 18, 32, 255))
d = ImageDraw.Draw(im)
d.rounded_rectangle((32, 49, 206, 201), radius=25, fill="#213d45")
d.rounded_rectangle((49, 31, 224, 184), radius=25, fill="#72e4c5")
d.polygon([(112, 75), (112, 142), (166, 108)], fill="#113832")
d.line([(75, 163), (196, 163)], fill="#113832", width=7)
im.save(root / "slidesnap.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Assets ready:", root)
