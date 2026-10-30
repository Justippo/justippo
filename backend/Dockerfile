FROM python:3.12-slim AS production

WORKDIR /app

# System dependencies for OCR and document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-fra \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[core,ocr,translation,database,reducto]" \
    "baml-py==0.222.0" \
    "hindsight-client>=0.7.0"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Local Compose target: extend the production image with the focused test tools
# needed by `make test-backend` so the suite can execute inside Linux without
# pulling heavyweight optional model runtimes. Cloudflare does not use this stage.
FROM production AS development

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/
RUN uv pip install --system \
    "pytest>=8.2.0" \
    "pytest-asyncio>=0.23.0" \
    "pytest-cov>=5.0.0" \
    "fpdf2>=2.8.0" \
    "langchain-text-splitters>=0.2.0" \
    "tqdm>=4.66.0"

# Preserve the production stage as Docker's default target for callers that do
# not explicitly select a build stage.
FROM production AS final
