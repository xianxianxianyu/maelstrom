import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.pdf_parser import PDFParser
from app.services.translator import TranslationService
from app.services.markdown_builder import MarkdownBuilder
from app.services.providers.base import ProviderConfig
from app.core.key_store import get_api_key
from app.models.schemas import TranslationResponse
import aiofiles
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


@router.post("/upload", response_model=TranslationResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    provider: str = Form("zhipuai"),
    model: str = Form("glm-4"),
    api_key: str | None = Form(None)
):
    logger.info(f"Received upload request: file={file.filename}, provider={provider}, model={model}")
    logger.info(f"Request api_key provided: {bool(api_key)}, length: {len(api_key) if api_key else 0}")

    # Validate file
    if not file.filename or not file.filename.endswith(".pdf"):
        logger.error(f"Invalid file: {file.filename}")
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    # Get API key
    actual_key = get_api_key(provider, api_key)
    logger.info(f"Using API key for {provider}, key length: {len(actual_key) if actual_key else 0}")

    if not actual_key:
        logger.error(f"No API key found for provider: {provider}")
        raise HTTPException(status_code=400, detail=f"API key required for provider: {provider}")

    logger.info(f"API key found for {provider}")

    # Save temp file
    Path("temp").mkdir(exist_ok=True)
    temp_path = Path(f"temp/{file.filename}")
    logger.info(f"Saving file to: {temp_path}")

    async with aiofiles.open(temp_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    logger.info(f"File saved, size: {len(content)} bytes")

    try:
        # Pipeline: Parse -> Translate -> Build
        logger.info("Starting PDF parsing...")
        parser = PDFParser()
        provider_config = ProviderConfig(
            api_key=actual_key,
            model=model
        )
        translator = TranslationService(provider_config, provider_override=provider)
        builder = MarkdownBuilder()

        parsed = await parser.process(temp_path)
        logger.info(f"PDF parsed: {len(parsed.pages)} pages")

        # For each page, translate text
        for idx, page in enumerate(parsed.pages):
            if page.text.strip():
                logger.info(f"Translating page {idx + 1}/{len(parsed.pages)}...")
                page.text = await translator.translate(page.text)
                logger.info(f"Page {idx + 1} translated")

        logger.info("Building markdown...")
        markdown = await builder.process(parsed)
        logger.info(f"Markdown generated, length: {len(markdown)}")

        return TranslationResponse(
            markdown=markdown,
            provider_used=provider,
            model_used=model
        )
    except Exception as e:
        logger.exception(f"Error processing PDF: {e}")
        raise
    finally:
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()
            logger.info(f"Cleaned up temp file: {temp_path}")
