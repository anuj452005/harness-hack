# Harness API Quality & Doc-Drift Validator
#
# Build:  docker build -t apiqual .
#
# No-creds run (downloads spec + runs static checks; dynamic/LLM skip cleanly):
#   docker run --rm apiqual
#
# Full run with credentials + persisted results on the host:
#   docker run --rm --env-file .env -v "$PWD/results:/app/results" apiqual
#
# Serve the dashboard (Streamlit on :8501):
#   docker run --rm -p 8501:8501 -v "$PWD/results:/app/results" apiqual \
#       streamlit run dashboard.py --server.address 0.0.0.0

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so the layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Streamlit dashboard port.
EXPOSE 8501

# Default to the full pipeline; override the command for static-only / serve.
CMD ["python", "run.py"]