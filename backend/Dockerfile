# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

# Install uv and build tools needed for Python packages that may not provide
# wheels for every platform (for example phik via ydata-profiling).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

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
COPY backend/ml_lifecycle ./ml_lifecycle

# Install the local app package without reinstalling runtime dependencies.
RUN uv pip install --system --no-deps .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy backend runtime files only. This legacy backend-only image is for local/dev
# use; production Railway deploys via root Dockerfile.railway and Railway S3/Postgres/MLflow.
COPY backend/app ./app
COPY backend/ml_lifecycle ./ml_lifecycle
COPY backend/seeds ./seeds
COPY data/reference/pem_fuel_cell_cathode_degradation/model_table.csv ./data/reference/pem_fuel_cell_cathode_degradation/model_table.csv
COPY data/reference/pem_fuel_cell_cathode_degradation/cell_metadata.csv ./data/reference/pem_fuel_cell_cathode_degradation/cell_metadata.csv
COPY data/reference/pem_fuel_cell_cathode_degradation/ast_trace_manifest.csv ./data/reference/pem_fuel_cell_cathode_degradation/ast_trace_manifest.csv
COPY data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest ./data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest
COPY backend/healthcheck.py ./healthcheck.py

ENV OBJECT_STORAGE_BACKEND=local
ENV LOCAL_OBJECT_STORAGE_ROOT=/app/.object-storage-local
ENV DOE_REFERENCE_DATA_ROOT=/app/data/reference

RUN test -s ./seeds/object_storage/workspaces/fraunhofer/workspace.json || \
    (echo "ERROR: Fraunhofer workspace seed metadata missing" && exit 1)
RUN test -s ./data/reference/pem_fuel_cell_cathode_degradation/model_table.csv && \
    test -s ./data/reference/pem_fuel_cell_cathode_degradation/cell_metadata.csv && \
    test -s ./data/reference/pem_fuel_cell_cathode_degradation/ast_trace_manifest.csv || \
    (echo "ERROR: business-impact real data artifacts missing" && exit 1)
RUN test -s ./data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest/preprocessing_report.json && \
    test -s ./data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest/preprocessing.json && \
    test -s ./data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest/split_report.json || \
    (echo "ERROR: model-quality preprocessing/split artifacts missing" && exit 1)

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Command to start (PORT env var for Cloud Run compatibility, defaults to 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
