# Multi-stage Dockerfile for SmartTub-MQTT
# Build optimized container image with minimal attack surface

# ============================================================================
# Stage 1: Builder - Install dependencies and build wheels
# ============================================================================
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        git \
        make \
        libffi-dev \
        libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the exact production dependency set before source code for cache reuse.
WORKDIR /build
COPY requirements.lock ./
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

# Install locked dependencies and the application as an immutable wheel.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.lock && \
    pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir /wheels . && \
    pip install --no-cache-dir --no-deps /wheels/smarttub_mqtt-*.whl && \
    test -z "$(find /opt/venv/lib/python3.13/site-packages -name '__editable__*' -print -quit)"

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.13-slim AS runtime

# Metadata
LABEL maintainer="SmartTub MQTT Maintainers"
LABEL org.opencontainers.image.source="https://github.com/Habnix/smarttub-mqtt"
LABEL org.opencontainers.image.description="SmartTub MQTT Bridge with Web UI"
# The CI workflows pass this from src/core/version.py (or the release tag).
ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

# Security: Run as non-root user
RUN groupadd -r smarttub && \
    useradd -r -g smarttub -u 1000 -d /app -s /sbin/nologin smarttub

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Create required directories with correct permissions
RUN mkdir -p /config /logs && \
    chown -R smarttub:smarttub /config /logs

# Volume mounts for persistent data
VOLUME ["/config", "/logs"]

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_DIR=/logs

# Expose Web UI port (default: 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/live').read()" || exit 1

# Switch to non-root user
USER smarttub

# Entrypoint for initialization and graceful shutdown
ENTRYPOINT ["python", "-m", "src.docker.entrypoint"]

# Default command (can be overridden)
CMD []
