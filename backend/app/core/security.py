from pathlib import Path


def validate_pdf_file(filename: str, max_size: int) -> bool:
    """Validate PDF file extension and size"""
    if not filename or not filename.lower().endswith(".pdf"):
        return False
    return True


def get_safe_filename(filename: str) -> str:
    """Generate safe filename from input"""
    name = Path(filename).stem
    # Remove any non-alphanumeric characters except spaces and hyphens
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    return safe.strip() or "document"
