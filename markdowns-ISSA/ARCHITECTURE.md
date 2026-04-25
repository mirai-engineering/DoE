# System Architecture

## Overview

The Kidney Segmentation System is a web-based application that provides automated kidney segmentation using a deep learning U-Net model. The system is designed for both cloud deployment and on-premise hospital installations.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
│                    (Chrome, Firefox, Safari)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Frontend (Vite + React)                    │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Components:                                              │ │
│  │  - ImageUpload (drag & drop, file selection)             │ │
│  │  - SegmentationResult (overlay display, opacity control)  │ │
│  │  - App (main application component)                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│  Port: 3000 (dev) / 80 (production with Nginx)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP REST API
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Backend API (FastAPI)                        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Endpoints:                                              │ │
│  │  - GET  /               (API info)                      │ │
│  │  - GET  /health         (health check)                  │ │
│  │  - GET  /model-info     (model specifications)          │ │
│  │  - POST /api/predict    (segmentation inference)        │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Services:                                               │ │
│  │  - Image Preprocessing (normalize, resize)              │ │
│  │  - ONNX Runtime Inference                                │ │
│  │  - Post-processing (sigmoid, threshold)                 │ │
│  │  - Logging                                               │ │
│  └──────────────────────────────────────────────────────────┘ │
│  Port: 8000                                                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                  ONNX Runtime Engine                            │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Model: /app/models/kidney_segmentation.onnx             │ │
│  │  - Input:  [1, 1, 256, 256] float32                     │ │
│  │  - Output: [1, 1, 256, 256] float32 (logits)             │ │
│  │  - Provider: CPUExecutionProvider (CUDA optional)        │ │
│  │  - Loaded at startup, cached in memory                   │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### Frontend (Vite + React)

**Technology Stack:**
- Vite (build tool and dev server)
- React 18
- TypeScript
- Tailwind CSS
- Axios (HTTP client)

**Key Components:**
- `ImageUpload`: Handles file selection and upload (single image mode)
- `BatchImageUpload`: Handles multiple file selection for batch processing
- `SegmentationResult`: Displays original image with overlay mask
- `BatchResults`: Displays batch processing results with progress tracking
- `App`: Main application component (manages single and batch modes)

**Responsibilities:**
- User interface and interaction (TypeScript + React)
- File upload with drag-and-drop support (single and batch modes)
- File format validation (TIFF, PNG, JPG)
- Display of segmentation results with overlay
- Opacity control for overlay visualization (0-1 range)
- Batch processing with parallel execution (max 3 concurrent requests)
- Progress tracking and statistics for batch operations
- Error handling and user feedback
- Loading states during processing
- Static file serving with Nginx in production
- API communication via Axios with 60s timeout
- Automatic environment detection (`import.meta.env.DEV`) for dev/prod configuration

### Backend (FastAPI + ONNX Runtime)

**Technology Stack:**
- FastAPI (async web framework)
- ONNX Runtime (inference engine)
- Pillow (image processing)
- Python 3.11+
- `uv` (fast Python package manager)
- `pyproject.toml` (dependency management)

**Key Modules:**
- `app/main.py`: FastAPI application, endpoints, middleware, CORS
- `app/inference.py`: ONNX model loading and inference
- `scripts/model.py`: U-Net architecture (used only for conversion)
- `healthcheck.py`: Docker health check script
- `convert_to_onnx.py`: Model conversion script

**Responsibilities:**
- REST API endpoints
- Image preprocessing (normalization, resizing, 16-bit support)
- Model inference via ONNX Runtime
- Post-processing (sigmoid, thresholding)
- Structured logging with timestamps
- CORS configuration (environment-based via `CORS_ORIGINS` env var)
- Error handling and timeout management (60s)
- Health checks for container orchestration
- Dynamic port configuration (reads `PORT` env var, defaults to 8000 for Cloud Run compatibility)

### Model (U-Net 2D)

**Architecture:**
- Encoder-Decoder structure
- 4 encoder blocks (64, 128, 256, 512 channels)
- 1 bottleneck block (1024 channels)
- 4 decoder blocks with skip connections
- Binary segmentation output

**Deployment Format:**
- Training: PyTorch (`.pth` checkpoint stored in `models/best_unet_dice.pth`)
- Production: ONNX (`.onnx` file stored in `models/kidney_segmentation.onnx`)
- Conversion: `convert_to_onnx.py` script
- Model Location: `/app/models/kidney_segmentation.onnx` (in container)
- **Note:** Model files are stored in Git LFS. See README.md for instructions on downloading the full model before building Docker images.

## Data Flow

### 1. Image Upload Flow

```
User selects image (TIFF, PNG, JPEG)
    ↓
Frontend validates file (size, format)
    ↓
User clicks "Process Image" button
    ↓
Frontend sends POST /api/predict with multipart/form-data (Axios)
    ↓
Backend receives file, validates size (max 100MB)
    ↓
Backend loads image with PIL, validates format (TIFF, TIF, PNG, JPEG, JPG)
    ↓
Backend preprocesses image:
  - Handle 16-bit images (I;16, I, F modes)
  - Convert to grayscale
  - Normalize (min-max scaling)
  - Resize to 256×256 (LANCZOS resampling)
  - Convert to tensor [1, 1, 256, 256] float32
    ↓
Backend runs ONNX inference (with 60s timeout)
    ↓
Backend post-processes:
  - Apply sigmoid to logits
  - Threshold at 0.5
  - Convert to PNG mask (uint8, 0-255)
    ↓
Backend returns JSON:
  - mask (base64 encoded PNG)
  - original (base64 encoded PNG, resized to 256×256)
  - format: "png"
    ↓
Frontend displays overlay with opacity control
```

## Deployment Architecture

### Development (Local)

```
┌─────────────────────────────────────────┐
│         Local Machine                   │
│                                         │
│  ┌──────────────┐  ┌──────────────┐   │
│  │  Frontend    │  │   Backend     │   │
│  │  (Vite+React)│  │  (FastAPI)   │   │
│  │  :3000       │  │  :8000       │   │
│  └──────────────┘  └──────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

### Production (Docker Compose)

```
┌─────────────────────────────────────────────────────┐
│              Docker Host                             │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │         Docker Network (kidney-network)      │  │
│  │                                               │  │
│  │  ┌──────────────┐      ┌──────────────┐     │  │
│  │  │  Frontend    │      │   Backend     │     │  │
│  │  │  Container   │◄────►│  Container   │     │  │
│  │  │  (Nginx)     │      │  (FastAPI)    │     │  │
│  │  │  Port: 3000  │      │  Port: 8000   │     │  │
│  │  │  (external)  │      │  (internal)   │     │  │
│  │  │  Port: 80    │      │  (reads PORT  │     │  │
│  │  │  (internal)  │      │   env if set) │     │  │
│  │  └──────────────┘      └──────────────┘     │  │
│  │                                               │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  Multi-stage builds:                                 │
│  - Backend: builder (uv) → runtime (Python)         │
│  - Frontend: deps → builder (Vite) → runner (Nginx) │
└─────────────────────────────────────────────────────┘
```

### Cloud Deployment (Google Cloud Run)

```
┌─────────────────────────────────────────────────────┐
│           Google Cloud Platform                      │
│                                                      │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  Cloud Run       │    │  Cloud Run       │       │
│  │  (Frontend)      │    │  (Backend)       │       │
│  │                  │    │                  │       │
│  │  - Auto-scaling  │    │  - Auto-scaling  │       │
│  │  - HTTPS         │    │  - HTTPS         │       │
│  │  - CDN           │    │  - Load balancer │       │
│  └──────────────────┘    └──────────────────┘       │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │  Cloud Logging / Monitoring                  │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Technology Decisions

### Why ONNX Runtime?

- **Portability:** Model runs on CPU, GPU, or specialized hardware
- **Performance:** 20-40% faster inference vs. PyTorch
- **Size:** Docker image ~500MB vs. ~5GB with PyTorch
- **Dependencies:** Single runtime, no framework dependencies

### Why FastAPI?

- **Async Support:** Handles concurrent requests efficiently
- **Auto Documentation:** OpenAPI/Swagger docs at `/docs`
- **Type Safety:** Pydantic validation
- **Performance:** One of the fastest Python frameworks

### Why Vite?

- **Fast Development:** Lightning-fast HMR (Hot Module Replacement)
- **Simple Setup:** Minimal configuration required
- **TypeScript:** Full TypeScript support out of the box
- **Production Ready:** Optimized builds with Rollup
- **Lightweight:** Smaller bundle size, faster builds
- **Modern Tooling:** ES modules native support

### Why Docker?

- **Consistency:** Same environment everywhere
- **Isolation:** Backend and frontend separated
- **Portability:** Runs on any Docker host
- **Simplicity:** One command deployment

## Security Considerations

### Current Implementation

- **CORS:** Configurable origins via `CORS_ORIGINS` environment variable (comma-separated)
- **File Size Limits:** 100MB maximum upload (suitable for medical TIFF images)
- **Input Validation:** Format (TIFF, PNG, JPEG) and size checks
- **Error Handling:** Structured error responses with HTTP status codes
- **Timeout Protection:** 60-second processing timeout to prevent hanging requests
- **16-bit Image Support:** Automatic conversion of 16-bit medical images to 8-bit
- **Non-root User:** Backend runs as non-root user (appuser) for security

### Production Recommendations

- **Authentication:** Add API keys or OAuth for production
- **Rate Limiting:** Prevent abuse
- **HTTPS:** Enforce encrypted connections
- **Input Sanitization:** Additional validation layers
- **Logging:** Structured logs for audit trails

## Monitoring and Observability

### Logging

- Structured logging with timestamps
- Log levels: INFO, WARNING, ERROR, DEBUG
- Request/response logging
- Error stack traces

### Health Checks

- `/health` endpoint for service status
- Model loaded status verification
- Docker healthcheck via `healthcheck.py` script
- Health check interval: 30s, timeout: 10s, retries: 3

## Scalability

### Horizontal Scaling

- **Stateless Backend:** Can run multiple instances
- **Load Balancing:** Cloud Run handles distribution
- **Auto-scaling:** Based on request volume

### Performance Optimization

- **Model Caching:** Model loaded once at startup
- **Async Processing:** Non-blocking I/O
- **ONNX Optimizations:** Graph-level optimizations
- **Image Caching:** (Future: CDN for static assets)

## Future Enhancements

### Planned Features

- ✅ Batch processing (multiple images) - **Implemented**
- Session history (last N processed images)
- Zoom/pan for detailed inspection
- Confidence score visualization
- DICOM format support
- Integration with PACS systems

### Architecture Evolution

- **Microservices:** Split preprocessing and inference
- **Message Queue:** For async batch processing
- **Database:** Store processing history
- **GPU Support:** CUDA provider for faster inference

---

## Dependency Management

### Backend
- Uses `uv` (fast Python package manager) for dependency installation
- Dependencies defined in `pyproject.toml`
- Multi-stage Docker build: builder stage installs dependencies, runtime stage copies them
- Key dependencies: FastAPI, ONNX Runtime, Pillow, NumPy, tifffile

### Frontend
- Uses `npm` with `package-lock.json` for dependency locking
- Multi-stage Docker build: deps → builder → runner
- Key dependencies: React 18, TypeScript, Vite, Axios, Tailwind CSS

---

**Last Updated:** 2024  
**Architecture Version:** 1.1.0

