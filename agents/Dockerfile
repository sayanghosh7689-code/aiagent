FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROMA_PATH=/data/chroma

WORKDIR /app

# build-essential only matters if a wheel is unavailable for your CPU architecture
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user; /data/chroma is the persistent vector store
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/chroma && chown -R appuser:appuser /data /app
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000 8501

# Default command (overridden in docker-compose for the Streamlit service)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
