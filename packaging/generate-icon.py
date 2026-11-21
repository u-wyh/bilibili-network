"""Regenerate the desktop icon with Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def main():
    scale = 4
    size = 256 * scale
    ramp = Image.linear_gradient("L").resize((size, size))
    icon = ImageOps.colorize(ramp, "#183940", "#117c70").convert("RGBA")
    mask = Image.new("L", icon.size)

    def box(*coordinates):
        return tuple(coordinate * scale for coordinate in coordinates)

    ImageDraw.Draw(mask).rounded_rectangle(box(8, 8, 248, 248), radius=56 * scale, fill=255)
    icon.putalpha(mask)
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle(box(44, 62, 193, 165), radius=24 * scale,
                           outline="#f1fffb", width=12 * scale)
    draw.polygon([box(99, 89), box(99, 140), box(143, 114)], fill="#f1fffb")
    draw.ellipse(box(146, 135, 228, 217), fill="#baf2db", outline="#165b57", width=5 * scale)
    draw.rounded_rectangle(box(182, 151, 192, 184), radius=5 * scale, fill="#114743")
    draw.line([box(172, 174), box(187, 190), box(202, 174)],
              fill="#114743", width=9 * scale, joint="curve")
    draw.rounded_rectangle(box(171, 195, 203, 202), radius=3 * scale, fill="#114743")

    icon = icon.resize((256, 256), Image.Resampling.LANCZOS)
    app = Path(__file__).resolve().parents[1] / "app"
    icon.save(app / "icon.png")
    icon.save(app / "icon.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == "__main__":
    main()
