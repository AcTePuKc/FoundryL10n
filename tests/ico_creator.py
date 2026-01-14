from PIL import Image
import base64
from io import BytesIO

def png_to_svg_embed(src="icon_256.png", dst="icon.svg"):
    img = Image.open(src).convert("RGBA")
    width, height = img.size

    # Записваме PNG в памет
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64_data = base64.b64encode(buf.getvalue()).decode("ascii")

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <image href="data:image/png;base64,{b64_data}"
         width="{width}" height="{height}" />
</svg>
"""

    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg_content)

if __name__ == "__main__":
    png_to_svg_embed()
