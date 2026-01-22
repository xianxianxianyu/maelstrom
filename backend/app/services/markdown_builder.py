from .pdf_parser import ParsedPDF, PDFPage
from .base import BaseService
import base64


class MarkdownBuilder(BaseService[ParsedPDF]):
    async def process(self, parsed_pdf: ParsedPDF) -> str:
        """Build markdown with embedded images in order"""
        md_lines = ["# Translated Document\n\n"]

        for page in parsed_pdf.pages:
            md_lines.append(f"## Page {page.page_number}\n\n")
            md_lines.append(page.text)
            md_lines.append("\n\n")

            for idx, img_bytes in enumerate(page.images):
                img_b64 = base64.b64encode(img_bytes).decode()
                md_lines.append(f"![Figure {idx + 1}](data:image/png;base64,{img_b64})\n\n")

        return "".join(md_lines)
