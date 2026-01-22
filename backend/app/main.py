from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import pdf, models, keys

app = FastAPI(
    title="PDF to Markdown Translator",
    description="Translate PDF documents to Markdown with extracted images",
    version="1.0.0"
)

# Configure CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pdf.router)
app.include_router(models.router)
app.include_router(keys.router)


@app.get("/")
async def root():
    return {
        "message": "PDF to Markdown Translator API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/api/pdf/upload",
            "models": "/api/models/",
            "keys": "/api/keys/"
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
