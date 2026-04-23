# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies needed for OpenSpiel wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install in builder stage
COPY requirements-openspiel.txt requirements-local.txt ./
RUN pip install --no-cache-dir --user -r requirements-openspiel.txt -r requirements-local.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy only the installed packages from builder
COPY --from=builder /root/.local /root/.local

# Set PATH to use installed packages
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import pyspiel; print('OK')" || exit 1

# Run the server
CMD ["python", "run_server.py"]
