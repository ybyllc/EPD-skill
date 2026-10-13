"""Render title/subtitle/rows/footer JSON into a 400x300 three-color card."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RED = (200, 0, 0)


def render(data, output, font_path):
    rows = data.get("rows", [])
    if not isinstance(rows, list) or len(rows) > 5 or not all(isinstance(row, str) for row in rows):
        raise ValueError("rows 必须是最多 5 行文字的数组。")
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size, color="black", width=350):
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise ValueError("文字字段必须为单行字符串。")
        font = ImageFont.truetype(str(font_path), size)
        bounds = font.getbbox(value)
        if font.getlength(value) > width or bounds[2] - bounds[0] > width:
            raise ValueError(f"文字过长，请缩短或使用自定义版面：{value}")
        mask = Image.new("1", image.size)
        ImageDraw.Draw(mask).text((x, y), value, font=font, fill=1)
        image.paste(color, (0, 0), mask)

    draw.rectangle((0, 0, 7, 299), fill=RED)
    text(24, 17, data.get("title", "每日计划"), 26, RED)
    text(24, 55, data.get("subtitle", ""), 15)
    draw.line((24, 84, 375, 84), fill="black", width=2)
    for index, row in enumerate(rows):
        y = 101 + 30 * index
        draw.rectangle((25, y + 3, 36, y + 14), outline="black")
        text(48, y, row, 18, width=327)
    draw.line((24, 255, 375, 255), fill=RED, width=2)
    text(24, 270, data.get("footer", ""), 14)
    image.save(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("/System/Library/Fonts/STHeiti Light.ttc"))
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error("找不到字体，请用 --font 指定支持中文的 TTF/OTF/TTC 文件。")
    try:
        render(json.loads(args.input.read_text(encoding="utf-8")), args.output, args.font)
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        parser.error(str(exc))
    print(f"已生成 {args.output}（400×300，黑白红）")
