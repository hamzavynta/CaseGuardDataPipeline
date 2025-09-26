FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install Poetry and dependencies
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

# Production stage
FROM base as production

# Copy V2 application code
COPY v2/ ./v2/
COPY caseguard/ ./caseguard/
COPY agents/ ./agents/
COPY config/ ./config/

# Set environment variables
ENV PYTHONPATH=/app
ENV PREFECT_API_URL=http://prefect-server:4200/api

# Expose port for health checks
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command - run the worker
CMD ["python", "-m", "v2.etl.worker"]

# Development stage
FROM base as development

# Install development dependencies
RUN poetry install --no-root

# Copy all code for development
COPY . .

# Command for development
CMD ["python", "-m", "v2.etl.worker", "--dev"]