# ─── AuraGrade Backend Dockerfile ─────────────────────────────
FROM python:3.12-slim AS base

# Security: run as non-root
RUN groupadd -r auragrade && useradd -r -g auragrade auragrade

WORKDIR /app

# Install system deps for OpenCV and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Remove any accidentally included secret files
RUN rm -f keys .env .env.local .env.production

# Switch to non-root user
USER auragrade

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Start with production settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
