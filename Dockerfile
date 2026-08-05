FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (separate layer for build caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create logs directory and a non-root user to own the app
RUN mkdir -p logs && \
    useradd --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]