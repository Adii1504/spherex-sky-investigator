import io
import textwrap
import numpy as np
from PIL import Image, ImageDraw


def render(frame, quality, size=512):
    """Native orientation: x right, y up. FITS row 0 becomes PNG bottom row."""
    image = frame.image
    display_status = "image_unavailable"
    low = high = None
    if image is None:
        canvas = Image.new("RGB", (size, size), "black")
    else:
        finite = np.isfinite(image)
        pixels = np.zeros(image.shape, dtype=np.uint8)
        if finite.any():
            low, high = [float(v) for v in np.percentile(image[finite], [1, 99])]
            display_status = "constant" if high == low else "stretched"
            if high == low:
                pixels[finite] = 127
            else:
                # Normalize first to avoid overflow when finite values span float limits.
                scale = max(abs(low), abs(high), 1.)
                norm = np.clip((image[finite]/scale-low/scale)/(high/scale-low/scale), 0, 1)
                pixels[finite] = (255*np.arcsinh(10*norm)/np.arcsinh(10)).astype(np.uint8)
        else:
            display_status = "all_invalid"
        height, width = image.shape
        canvas = Image.fromarray(np.flipud(pixels)).convert("RGB")
        factor = size / max(width, height)
        canvas = canvas.resize((max(1, round(width*factor)), max(1, round(height*factor))))
        g = quality["geometry"]
        if g["inside_image"]:
            px = (g["x"]+.5)*canvas.width/width-.5
            py = (height-.5-g["y"])*canvas.height/height-.5
            draw = ImageDraw.Draw(canvas)
            draw.ellipse((px-6, py-6, px+6, py+6), outline="red", width=2)
    # A footer preserves the image geometry and keeps provisional labels visible.
    status = quality["position"]["astrometry_status"]
    footer_width = max(canvas.width, 360)
    lines = textwrap.wrap(f"Astrometry: {status}", width=max(20, footer_width//7))
    lines += ["Predicted position only; not a detection", display_status]
    footer = Image.new("RGB", (footer_width, canvas.height+18*len(lines)+8), "black")
    footer.paste(canvas, (0, 0))
    draw = ImageDraw.Draw(footer)
    for i, line in enumerate(lines):
        draw.text((4, canvas.height+4+i*18), line, fill="white")
    stream = io.BytesIO()
    footer.save(stream, format="PNG")
    return stream.getvalue(), {"status": display_status, "percentiles": [1, 99],
        "low": low, "high": high, "stretch": "asinh(10)", "size": size,
        "orientation": "native WCS, x right / y up; not reprojected north-up",
        "image_panel_width": canvas.width, "image_panel_height": canvas.height}
