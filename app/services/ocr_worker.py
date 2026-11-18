"""Render and recognize one page in an isolated, time-limited process."""
import math
import sys
from contextlib import closing

import pypdfium2 as pdfium
from tesserocr import PyTessBaseAPI


def recognize(pdf_path, index, data_dir):
    with pdfium.PdfDocument(pdf_path) as pdf:
        with closing(pdf[index]) as page:
            width, height = page.get_size()
            if not all(math.isfinite(size) and size > 0 for size in (width, height)):
                raise ValueError("Invalid page dimensions")
            scale = min(300 / 72, 4000 / max(width, height), math.sqrt(8_000_000 / width / height))
            with closing(page.render(scale=scale, grayscale=True, limit_image_cache=True)) as bitmap:
                with PyTessBaseAPI(path=data_dir, lang="kaz+rus+eng") as engine:
                    engine.SetImage(bitmap.to_pil())
                    return engine.GetUTF8Text()[:100_000]


if __name__ == "__main__":
    path, index, tessdata = sys.argv[1:]
    sys.stdout.buffer.write(recognize(path, int(index), tessdata).encode("utf-8"))

