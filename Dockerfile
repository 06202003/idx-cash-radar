# ==============================================================================
# Dockerfile — IDX Cash & Accrual Radar (v2.0 Production Daemon)
# ==============================================================================
FROM python:3.11-slim

# Prevent python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies for lxml and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create working directory and dedicated non-root user
WORKDIR /app
RUN useradd -m -u 1000 appuser

# Copy dependency definition and install packages
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# Copy application source code and configurations
COPY config/ ./config/
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Initialize SQLite database file with appropriate permissions
RUN touch idx_cash_radar.db && chown -R appuser:appuser /app

# Switch to non-root user for production execution
USER appuser

# Expose FastAPI Web Dashboard port
EXPOSE 8000

# Default command launches both FastAPI Web Dashboard (CRUD + AI) and Telegram Bot daemon
CMD ["python", "scripts/start_all.py"]

