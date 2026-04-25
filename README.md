# Kidney Segmentation - ONNX Deployment

Deep learning kidney segmentation system deployed with ONNX Runtime for production.

---

## 1. 🎯 Features

- ✅ U-Net model for kidney segmentation
- ✅ FastAPI backend API
- ✅ Vite + React web frontend
- ✅ **Optimized with ONNX Runtime** (20-40% faster, Docker image 10x smaller)
- ✅ Dockerized and production-ready
- ✅ Support for TIFF, PNG, JPEG

---

## 2. 📖 What is this?

Web system for **automated kidney segmentation** in medical images using deep learning.

**Use cases:**
- Medical analysis and research
- Computer-assisted diagnosis
- Medical image processing (CT, MRI, etc.)

**How it works:**
1. Upload a medical image (TIFF, PNG, JPEG)
2. The U-Net model processes the image automatically
3. You get a segmentation mask overlaid on the original image
4. You can adjust the overlay opacity to better visualize the results

**Input:** Medical images in TIFF, PNG, or JPEG format (up to 100MB)  
**Output:** Binary segmentation mask showing detected kidney regions

---

## 3. 📋 System Requirements

**Minimum:**
- **RAM**: 4GB (8GB recommended for better performance)
- **Disk**: 2GB free (for models and dependencies)
- **Python**: 3.11 or higher
- **Node.js**: 18 or higher
- **Docker**: Optional but recommended for deployment

**For model conversion (first time):**
- PyTorch (installed automatically with `uv pip install '.[dev]'`)
- GPU optional (speeds up conversion, but not required)

---

## 4. 🚀 Quick Start

### 1. Convert Model to ONNX (First time)

**IMPORTANT**: Before running the system, you need to convert the PyTorch model to ONNX. The system **only works with ONNX** - there is no fallback to PyTorch.

```bash
cd backend

# Install development dependencies (includes PyTorch only for conversion)

# esto contradice el proposito de uv. la flag --system te hace usar el python global en el Mac. la idea es trabajar con los .venv. idealmente con uv add xxx.

# alternativa seria
# source .venv/bin/activate
# uv pip install -e '.[dev]'
uv pip install --system '.[dev]'

# Convert model (use uv run to use the correct environment)
uv run python convert_to_onnx.py
```

## error (sigue aqui la proxima vez)
❯ uv run python convert_to_onnx.py
Loading PyTorch model from /Users/brunocopa/Public/Git/Mirai/AI_Development/CV/ISSA/backend/models/best_unet_dice.pth...
Using device: cpu
Traceback (most recent call last):
  File "/Users/brunocopa/Public/Git/Mirai/AI_Development/CV/ISSA/backend/convert_to_onnx.py", line 143, in <module>
    convert_pytorch_to_onnx(
  File "/Users/brunocopa/Public/Git/Mirai/AI_Development/CV/ISSA/backend/convert_to_onnx.py", line 41, in convert_pytorch_to_onnx
    checkpoint = torch.load(pytorch_model_path, map_location=device)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/brunocopa/Public/Git/Mirai/AI_Development/CV/ISSA/backend/.venv/lib/python3.12/site-packages/torch/serialization.py", line 1553, in load
    raise pickle.UnpicklingError(_get_wo_message(str(e))) from None
_pickle.UnpicklingError: Weights only load failed. In PyTorch 2.6, we changed the default value of the `weights_only` argument in `torch.load` from `False` to `True`. Re-running `torch.load` with `weights_only` set to `False` will likely succeed, but it can result in arbitrary code execution. Do it only if you got the file from a trusted source.
Please file an issue with the following so that we can make `weights_only=True` compatible with your use case: WeightsUnpickler error: 

Unsupported operand 118

Check the documentation of torch.load to learn more about types accepted by default with weights_only https://pytorch.org/docs/stable/generated/torch.load.html.
---------------------------------

This will create `backend/models/kidney_segmentation.onnx` from `backend/models/best_unet_dice.pth`.

**Note**: Once converted, PyTorch is not needed in production. Only ONNX Runtime is required.

### 2. Download Model with Git LFS (Requirement)

**IMPORTANT**: The ONNX model is stored in Git LFS (Large File Storage). If you just cloned the repository, you will only have the file pointer (a few bytes), not the complete model.

**Before building Docker or running the system, you must download the complete model:**

```bash
# 1. Install Git LFS (first time only)
# macOS:
brew install git-lfs
git lfs install

# Linux (Ubuntu/Debian):
sudo apt-get install git-lfs
git lfs install

# Windows:
# Download from https://git-lfs.github.com/

# 2. Do normal pull (downloads pointers)
git pull

# 3. Download real LFS files
# Note: Requires GitHub authentication (for private repos)
git lfs pull --include="backend/models/*.onnx"

# 4. Verify the file is real (should weigh > 1MB, not just a few bytes)
ls -lh backend/models/kidney_segmentation.onnx
# ✅ Should show a size > 1MB (e.g., 50MB, 100MB, etc.)
```

**If the file weighs only ~130 bytes, it means you only have the pointer. Run `git lfs pull` again.**

### 3. Run with Docker Compose

```bash
# Build and run all services
docker-compose up --build

# Application will be available at:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### 4. Local Development

**Backend:**
```bash
cd backend
uv pip install --system .
uvicorn app.main:app --reload --port 8000
# Or with uv run:
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# Application will be available at http://localhost:3000
```

**Note**: The frontend connects directly to the backend at `http://localhost:8000`. Make sure the backend is running before starting the frontend. The backend already has CORS configured to allow requests from `localhost:3000`.

**Verify the model works:**

```bash
cd backend
uv run python convert_to_onnx.py
```

The script automatically verifies:
- ✅ The ONNX model loads correctly
- ✅ Outputs match PyTorch (difference < 1e-5)

---

## 5. 🎬 Usage Flow

Once the system is running:

1. **Open the frontend** in your browser (http://localhost:3000)

2. **Upload an image:**
   - Drag and drop a TIFF, PNG, or JPEG image
   - Or click to select a file
   - Supported formats: TIFF, PNG, JPEG (up to 100MB)
   - **Batch mode:** You can switch to "Batch" mode to process multiple images simultaneously

3. **Process the image:**
   - Click the "Process Image" button
   - The system will process the image (typically 40-60ms)

4. **Visualize the result:**
   - You'll see the original image with the segmentation mask overlaid
   - Use the slider to adjust the overlay opacity (0-100%)
   - The mask shows detected kidney regions in color

5. **Download or analyze:**
   - The result includes the original image and the segmentation mask
   - You can use these results for further medical analysis

**Batch Mode (Batch Processing):**
- Switch to "Batch" mode using the selector at the top
- Select multiple images at once (drag and drop or click to select)
- Images are processed automatically in parallel (maximum 3 simultaneous)
- You can see the progress of each image, retry failures, and download individual results
- Useful for processing complete studies or multiple patients
- Real-time statistics: processed images, in progress, failed, and total time

---

## 6. ⚠️ Model Limitations

**Important:**
- The model is trained for 256×256 pixel images (automatically resized)
- Average latency: 40-60ms per image (CPU)
- May have limitations with low contrast images, artifacts, or different image modalities

**Recommended use:**
- ✅ Research, development, and educational purposes
- ✅ Preliminary segmentation with human supervision
- ❌ **Not** for independent clinical diagnosis or automated treatment decisions

For more details on accuracy, edge cases, and technical limitations, see [MODEL_CARD.md](./MODEL_CARD.md).

---

## 7. 📁 Project Structure

```
kidney_seg_vite/
├── backend/              # FastAPI API with ONNX Runtime
│   ├── app/
│   │   ├── main.py       # FastAPI application
│   │   ├── inference.py  # ONNX inference logic
│   │   └── model.py      # Model architecture (only for conversion)
│   ├── models/
│   │   ├── best_unet_dice.pth          # Original PyTorch model
│   │   └── kidney_segmentation.onnx    # ONNX model (generated)
│   ├── convert_to_onnx.py # Conversion script
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/             # Vite + React frontend
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

---

## 8. 🔧 Technologies

**Backend:**
- **FastAPI**: Modern and fast web framework with async support
- **ONNX Runtime**: Optimized runtime for inference (replaces PyTorch in production)
- **Pillow**: Image processing (supports TIFF, PNG, JPEG, 16-bit images)
- **uv**: Fast Python package manager
- **Python 3.11+**: Programming language

**Frontend:**
- **Vite**: Fast and modern build tool with HMR
- **React 18**: UI library
- **TypeScript**: Static typing
- **Tailwind CSS**: Utility-first styling framework
- **Axios**: HTTP client for API communication
- **Nginx**: Web server for production (in Docker)

---

## 9. 📊 ONNX Benefits

| Aspect | PyTorch | ONNX Runtime |
|--------|---------|--------------|
| Docker Size | ~5GB | ~500MB |
| Speed | Baseline | 20-40% faster |
| Dependencies | Full PyTorch | ONNX Runtime only |
| Hardware | CPU/GPU specific | CPU, GPU, TensorRT, etc. |

---

## 10. 📝 API

### Available Endpoints

- `GET /health` - Server and model status
- `GET /model-info` - Model information and specifications
- `POST /api/predict` - Image segmentation (single or batch)
  - Body: `multipart/form-data` with `file` field
  - Response: `{ "mask": "base64_png", "original": "base64_png", "format": "png" }`
  - **Note:** For batch processing, the frontend makes multiple calls to this endpoint in parallel (maximum 3 simultaneous)

See complete documentation at: http://localhost:8000/docs

### Test the API

```bash
# Health check
curl http://localhost:8000/health

# Model information
curl http://localhost:8000/model-info

# Test prediction (requires a TIFF/PNG/JPEG image)
curl -X POST http://localhost:8000/api/predict \
  -F "file=@your_image.tiff"
```

---

## 11. 🐳 Docker

### Run with Docker Compose (Recommended)

```bash
# Build and run all services
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Build Individual Images

```bash
# Backend
docker build -t kidney-backend ./backend

# Frontend
docker build -t kidney-frontend ./frontend
```

### Docker Compose Configuration

The `docker-compose.yml` configures:
- **Backend**: Automatic healthcheck, volume for models, custom network, exposes port 8000
- **Frontend**: Nginx to serve static files, direct connection to backend, custom network
- **Network**: Custom Docker network `kidney-network` for service communication

**Default ports:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

---

## 12. ⚙️ Configuration

### Environment Variables (Optional)

**Note:** The system works without additional configuration. You only need to create `.env` if you want to change default values.

**Local Development:**
- No `.env` required (uses default values automatically)

**Docker:**
- No `.env` required (docker-compose.yml has default values)
- Only create `.env` if you need to customize configuration

**To create `.env` (optional):**

```bash
cp env.example .env
# Edit .env if you need to change values
```

**Available variables:**

- **`CORS_ORIGINS`**: Allowed origins for CORS (comma-separated)
  - Development default: `http://localhost:3000`
  - Docker default: `http://localhost:3000,http://frontend:3000`

- **`VITE_API_URL`**: Backend URL (optional, has default value)
  - Development: Defaults to `http://localhost:8000` (no configuration required)
  - Docker: Defaults to `http://localhost:8000` (configured in docker-compose.yml)
  - Production: Must be configured with the complete backend URL (e.g., `https://your-backend.run.app`)

---

## 13. ☁️ Cloud Deployment

### Prerequisites

```bash
# Install tools (once)
# - Docker
# - Google Cloud CLI: gcloud auth login && gcloud config set project YOUR_PROJECT_ID
# - Vercel CLI: npm install -g vercel && vercel login

# Edit deploy-backend.sh: change PROJECT_ID="your-gcp-project"
```

### Automated Deployment (Recommended)

**Backend (Google Cloud Run):**
```bash
export CORS_ORIGINS="https://your-frontend.vercel.app"
./deploy-backend.sh
```

**Frontend (Vercel):**
```bash
export BACKEND_URL="https://your-backend.run.app"  # URL from previous step
./deploy-frontend.sh
```

### Manual Deployment

**Backend:** Deploy to Cloud Run/AWS/Azure and configure `CORS_ORIGINS` with the frontend URL.

**Frontend:** Deploy to Vercel/Netlify and configure `VITE_API_URL` with the backend URL before building.

---

## 14. 🔧 Technical Details: Port Configuration

**Quick port reference:**

| Environment | File | Port | Note |
|-------------|------|------|------|
| Development Frontend | `frontend/vite.config.ts` | 3000 | Line 12 |
| Development Backend | uvicorn command | 8000 | See line 56 |
| Docker Frontend | `docker-compose.yml` | 3000:80 | External:internal mapping |
| Docker Backend | `docker-compose.yml` | 8000:8000 | Reads `PORT` env if exists |
| Cloud Frontend (Vercel/Netlify) | N/A | N/A | No port (static files) |
| Cloud Backend (Cloud Run/AWS/Azure) | `PORT` variable | Dynamic | Automatically injected by platform |

**Note:** In development and Docker, ports are predefined. In cloud, the frontend doesn't use ports (static files) and the backend reads `PORT` automatically.

---

## 15. 📚 Additional Documentation

- [Deployment Roadmap](./Deployment-Roadmap.md) - Complete deployment plan
- [Architecture Diagram](./ARCHITECTURE.md) - System architecture and diagrams
- [Model Card](./MODEL_CARD.md) - Model specifications, limitations, and usage

---

## 16. 🐛 Troubleshooting

### Error: "ONNX model not found"

Run the conversion script:
```bash
cd backend
uv pip install --system '.[dev]'
uv run python convert_to_onnx.py
```

### Error: "Model not loaded"

Verify that `backend/models/kidney_segmentation.onnx` exists and has read permissions.

### Error: "Model invalid" or Docker build fails with Git LFS

This error occurs when Docker tries to build the image but only finds the Git LFS pointer (file of ~130 bytes) instead of the complete model.

**Solution:**
1. Make sure you have Git LFS installed: `brew install git-lfs && git lfs install` (or equivalent on your OS)
2. Download the complete model BEFORE building Docker:
   ```bash
   git lfs pull --include="backend/models/*.onnx"
   ```
3. Verify the file is real (should weigh > 1MB):
   ```bash
   ls -lh backend/models/kidney_segmentation.onnx
   ```
4. If you're in a private repository, make sure you're authenticated with GitHub
5. Then build Docker normally: `docker compose up --build`

**Note:** The Dockerfile tries to do `git lfs pull` inside the container, but this fails in private repos because the container doesn't have GitHub credentials. That's why it's necessary to download the model before building.

### CORS error in development

The frontend connects directly to the backend. Make sure:
- The backend is running (default at http://localhost:8000)
- The frontend is running (default at http://localhost:3000)
- The backend has CORS configured to allow `http://localhost:3000` (already configured by default)
- If you change the backend port, adjust `VITE_API_URL` or use the default value

### Error: "File too large"

The current limit is 100MB. If you need to process larger files, modify `MAX_FILE_SIZE_MB` in `backend/app/main.py`.

### Frontend doesn't connect to backend

1. Verify both services are running
2. Verify the backend is accessible at `http://localhost:8000` (or the configured URL)
3. In development, the frontend uses `http://localhost:8000` by default
4. In Docker Compose, both services are connected - check logs: `docker-compose logs`
5. In production, configure `VITE_API_URL` with the complete backend URL before building

---

## 17. 🔄 Next Steps

According to the [Deployment Roadmap](./Deployment-Roadmap.md):

- [x] ✅ ONNX conversion (Phase 1.1)
- [x] ✅ Backend API (Phase 1.2)
- [x] ✅ Basic frontend (Phase 2.1)
- [x] ✅ Docker (Phase 3.2)
- [x] ✅ Logging and metrics (Phase 4.3)
- [x] ✅ Technical documentation (Phase 6.1)
- [x] ✅ Batch processing
- [ ] ⏳ UX improvements (zoom/pan)
- [ ] ⏳ Testing suite (optional)
- [ ] ⏳ Cloud deployment

---

## 18. 📄 License

[Specify license]
