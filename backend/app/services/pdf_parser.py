import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass
from typing import List
from .base import BaseService


@dataclass
class PDFPage:
    page_number: int
    text: str
    images: List[bytes]


@dataclass
class ParsedPDF:
    pages: List[PDFPage]
    metadata: dict


class PDFParser(BaseService[Path]):
    async def process(self, pdf_path: Path) -> ParsedPDF:
        """Extract text and images from PDF maintaining order"""
        doc = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            images = self._extract_images(page)
            pages.append(PDFPage(page_num + 1, text, images))

        return ParsedPDF(pages, doc.metadata)

    def _extract_images(self, page) -> List[bytes]:
        """Extract images as bytes in document order"""
        images = []
        for img_index, img in enumerate(page.get_images()):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            images.append(base_image["image"])
        return images
