# NOTE: Data is persisted to /app/data via docker-compose volume mounts.
# Pulled from docker.com, generic dockerfile for python applications. See https://docs.docker.com/language/python/build-images/ for more details.
FROM python:3.13-slim

WORKDIR /app

# Prevent Python from writing .pyc files and force stdout/stderr flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python dependencies
# requirements.txt should include at least:
# fastapi
# uvicorn[standard]

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ./

# Create a non-root user and ensure the app directory is writable
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]