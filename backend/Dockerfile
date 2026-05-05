# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files (context is root, so need backend/ prefix)
COPY backend/pyproject.toml ./
COPY backend/uv.lock ./

# Install locked runtime dependencies before copying app code. BoTorch pulls in
# large wheels, so keep this layer independent from ordinary source edits.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file requirements.txt && \
    uv pip install --system --requirements requirements.txt

COPY backend/app ./app

# Install the local app package without reinstalling runtime dependencies.
RUN uv pip install --system --no-deps .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy backend runtime files only
COPY backend/app ./app
COPY backend/artifacts ./artifacts
COPY backend/data/replay ./data/replay
COPY backend/healthcheck.py ./healthcheck.py

RUN test -s ./artifacts/pem_fuel_cell_demo/model.onnx || \
    (echo "ERROR: DoE ONNX model artifact missing" && exit 1)
RUN test -s ./data/replay/pem_fuel_cell_demo_initial_observed.csv && \
    test -s ./data/replay/pem_fuel_cell_demo_hidden_pool.csv || \
    (echo "ERROR: BO replay datasets missing" && exit 1)

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Command to start (PORT env var for Cloud Run compatibility, defaults to 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
