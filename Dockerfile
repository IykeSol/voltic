# Prepaid Meter Usage Pattern Analyzer
# Optimised for Hugging Face Spaces (Docker SDK) - serves on port 7860.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Generate the dataset and train the models at build time so the image is
# fully self-contained and ready to serve on first request.
RUN python scripts/generate_dataset.py && python scripts/train_model.py

# Make the runtime-writable folders accessible to the Spaces user (uid 1000).
RUN mkdir -p app/database && chmod -R 777 app/database dataset trained_models

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
