FROM python:3.11-slim

WORKDIR /app

# system deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml requirements.txt requirements-dev.txt* /app/
COPY src /app/src

RUN pip install --no-cache-dir -r requirements.txt || true

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.cli.run"]
# Multi-stage Dockerfile for SmartTub-MQTT
# Build optimized container image with minimal attack surface

# ============================================================================
# Stage 1: Builder - Install dependencies and build wheels
# ============================================================================
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        make \
        libffi-dev \
        libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency specifications
WORKDIR /build
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies (cached layer)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e .

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim AS runtime

# Metadata
LABEL maintainer="SmartTub MQTT Maintainers"
LABEL org.opencontainers.image.source="https://github.com/smarttub-mqtt"
LABEL org.opencontainers.image.description="SmartTub MQTT Bridge with Web UI"
LABEL org.opencontainers.image.version="0.3.0"

# Security: Run as non-root user
RUN groupadd -r smarttub && \
    useradd -r -g smarttub -u 1000 -d /app -s /sbin/nologin smarttub

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=smarttub:smarttub src/ /app/src/
COPY --chown=smarttub:smarttub tools/ /app/tools/

# Create required directories with correct permissions
RUN mkdir -p /config /log && \
    chown -R smarttub:smarttub /config /log

# Volume mounts for persistent data
VOLUME ["/config", "/log"]

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONFIG_PATH=/config/smarttub.yaml \
    LOG_DIR=/log

# Expose Web UI port (default: 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()" || exit 1

# Switch to non-root user
USER smarttub

# Entrypoint for initialization and graceful shutdown
ENTRYPOINT ["python", "-m", "src.docker.entrypoint"]

# Default command (can be overridden)
CMD []
