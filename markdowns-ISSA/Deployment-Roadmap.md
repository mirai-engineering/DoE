# Kidney Segmentation Model Deployment Roadmap

## **Introduction**

This document outlines the deployment roadmap for our deep learning kidney segmentation model. Before diving into the technical phases, let's address the key architectural decisions that guide this entire project. Quickly go over the phases of the project, and then come back to this introduction. Many of the questions that will probably arise during the read are answered here. Then you can go and read carefully each phase again.

### Why ONNX Model Conversion?

Our CNN model was developed in PyTorch, which is excellent for research and training but introduces deployment challenges. ONNX (Open Neural Network Exchange) solves this by providing a **framework-agnostic runtime format**.

**Key benefits:**

- **Portability**: Once converted, the model runs anywhere ONNX Runtime is installed—no need for the full PyTorch/TensorFlow stack on production servers. This reduces our Docker image from ~5GB (with PyTorch) to ~500MB (ONNX Runtime only).
- **Lower inference latency**: ONNX Runtime applies graph-level optimizations (operator fusion, constant folding, memory planning) that typically yield 20-40% faster inference compared to native framework execution.
- **Hardware flexibility**: The same ONNX model runs on CPU, GPU (CUDA), or even specialized hardware (TensorRT, DirectML) without code changes—crucial for on-premise hospital deployments where we don't control the hardware.
- **Decoupled dependencies**: Hospital IT doesn't need to manage CUDA toolkit versions or Python deep learning frameworks. ONNX Runtime is a single, well-maintained dependency.

### Why Backend API Development?

Without a backend API, running the model would require either:
1. Your personal computer running 24/7 for anyone to use the model
2. Each user installing Python, PyTorch, and dependencies locally

A backend API transforms the model into a **service** that can be accessed over HTTP. Think of it as a receptionist at a clinic—users knock on the door (send a request), the receptionist processes them (validation, preprocessing), consults the specialist (model inference), and returns results (segmented mask).

**This architecture enables:**
- Multiple simultaneous users without local installation
- Centralized model updates (fix the model once, everyone benefits)
- Usage logging and monitoring
- Scalability (add more servers as demand grows)

### Why not hosting the MVP on HuggingFace?

This is great for bootstrapping a quick and effective demo service:

**Pros:**

- **Lightning Fast Setup**
  - Working demo in days, not weeks. Zero infrastructure costs, and no Docker/AWS knowledge needed.

- **Easy to Share**
  - Just send clients a URL, no installation required + works on any device/browser.

- **Free (within limits)**
  - Free tier: 2 CPU cores, 16GB RAM. Upgrade to GPU if needed (~$0.60/hour).

- **Built-in Analytics**
  - See how many people use it, tracks engagement, validates interest before building

- **API Access**
  ```python
  # Client can call your model via API
  from gradio_client import Client

  client = Client("mirai/kidney-segmentation")
  result = client.predict(image_path)
  ```

**Perfect for:**

- Conference demos
- Investor pitches
- Initial client interest validation
- Research collaborations
- Getting feedback

---

**Why This WON'T Work for Hospital pitchs**

**Critical Problems:**

**1. Hospital Compliance/Data Privacy**

*Data Sovereignty Requirements.* European hospitals especially require:
- Data stays in EU
- Data never leaves hospital network
- Full audit trail of data access
- HF Spaces can't guarantee this

*GDPR/HIPAA Showstopper (specific to hospitals):*
- Patient CT scans uploaded to Hugging Face servers (US-based)
- Data leaves hospital premises
- Goes through public internet
- Violates GDPR and HIPAA regulations

**2. No White Labeling**
- URL is huggingface.co/spaces/mirai/...
- Not kidney-segmentation.mirai.com. This looks less professional to enterprise clients, and we wan't integrate with hospital branding

**3. Limited Compute Control**
- Free tier might be slow for large 3D CT volumes
- Paid tier costs add up at scale
- Can't guarantee latency SLAs
- What if HF has downtime?

**4. No Integration with Hospital Systems**
- Can't integrate with PACS (Picture Archiving System)
- Can't integrate with hospital EHR
- Can't support DICOM format natively
- Manual upload/download workflow

**5. Perception Problem**
- Client: "Wait, you're just hosting this on Hugging Face? That's not an enterprise solution."

### Why Cloud-Hosted Web App Instead of Vercel/GoDaddy Static Hosting?

Vercel, Netlify, or GoDaddy are designed for **static websites and frontend-only applications**. Our application requires **backend compute**—a server that actually runs the neural network inference.

Static hosting platforms can only serve HTML, CSS, JavaScript, and assets. They cannot:
- Run Python code or ONNX Runtime
- Process medical images server-side
- Store and serve large model files (our model is ~100MB+)
- Perform GPU-accelerated inference

**Cloud providers (GCP, AWS, Digital Ocean) offer:**
- Compute instances that can run our Docker containers
- GPU instances for faster inference (when needed)
- Auto-scaling to handle variable load
- Healthcare compliance certifications (HIPAA, SOC2) required for clinical data

**Why Docker for the Web App?**

Docker containers solve the "it works on my machine" problem. A container packages the entire runtime environment (OS dependencies, Python version, libraries, model files) into a portable unit that runs identically everywhere.

For hospital on-premise deployments, this is critical: instead of writing 20 pages of installation instructions ("install Python 3.11, then pip install these 47 packages, configure CUDA 11.8..."), we deliver a single Docker image that IT runs with one command.

---

## **Phase 1: Foundation & Model Preparation** 

### 1.1 Model Export to ONNX

- Convert your current CNN model from PyTorch/TensorFlow to ONNX format  
- Test inference equivalence (output difference should be < 1e-5)
- ONNX is a framework-agnostic platform with lower inference latency. Measure and document the latency improvement.

**Code Example - PyTorch to ONNX Export:**

```python
import torch
import onnxruntime as ort
import numpy as np

# Load your trained PyTorch model
model = YourSegmentationModel()
model.load_state_dict(torch.load("kidney_segmentation.pth"))
model.eval()

# Create dummy input matching your expected image dimensions
# Assuming input is [batch, channels, height, width]
dummy_input = torch.randn(1, 1, 512, 512)

# Export to ONNX
torch.onnx.export(
    model,
    dummy_input,
    "kidney_segmentation.onnx",
    export_params=True,
    opset_version=17,
    do_constant_folding=True,
    input_names=["input"],
    output_names=["segmentation_mask"],
    dynamic_axes={
        "input": {0: "batch_size", 2: "height", 3: "width"},
        "segmentation_mask": {0: "batch_size", 2: "height", 3: "width"}
    }
)

# Verify equivalence
ort_session = ort.InferenceSession("kidney_segmentation.onnx")
pytorch_output = model(dummy_input).detach().numpy()
onnx_output = ort_session.run(None, {"input": dummy_input.numpy()})[0]

# Check outputs match
max_diff = np.abs(pytorch_output - onnx_output).max()
print(f"Max difference between PyTorch and ONNX: {max_diff}")
assert max_diff < 1e-5, "ONNX conversion introduced unacceptable error!"
```

**Optional Optimizations (can revisit later):**
- Quantization if CPU-only deployment
- Graph optimization for specific hardware
- Document input/output shapes, preprocessing requirements, expected latency

---

### 1.2 Backend API Development

Create a Python backend using FastAPI (recommended over Flask for async support).

**Code Example - FastAPI Backend (`main.py`):**

```python
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import onnxruntime as ort
import numpy as np
from PIL import Image
import io

app = FastAPI(title="Kidney Segmentation API", version="1.0.0")

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model once at startup
MODEL_PATH = "kidney_segmentation.onnx"
session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])

def preprocess(image: Image.Image) -> np.ndarray:
    """Resize, normalize, and convert to tensor."""
    img = image.convert("L").resize((512, 512))
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr.reshape(1, 1, 512, 512)  # [batch, channel, H, W]

def postprocess(mask: np.ndarray, original_size: tuple) -> Image.Image:
    """Convert model output to displayable mask."""
    mask = (mask[0, 0] > 0.5).astype(np.uint8) * 255
    return Image.fromarray(mask).resize(original_size)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": session is not None}

@app.get("/model-info")
async def model_info():
    return {
        "model_version": "1.0.0",
        "input_shape": "1x1x512x512",
        "input_format": "grayscale, normalized 0-1",
        "output": "binary segmentation mask"
    }

@app.post("/predict")
async def predict(file: UploadFile):
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(400, "Only JPEG/PNG images supported")
    
    # Read and validate size
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "File too large (max 10MB)")
    
    # Process image
    try:
        image = Image.open(io.BytesIO(contents))
        original_size = image.size
        
        input_tensor = preprocess(image)
        outputs = session.run(None, {"input": input_tensor})
        mask = postprocess(outputs[0], original_size)
        
        # Return mask as PNG
        buffer = io.BytesIO()
        mask.save(buffer, format="PNG")
        buffer.seek(0)
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(buffer, media_type="image/png")
    
    except Exception as e:
        raise HTTPException(500, f"Inference failed: {str(e)}")
```

**Run locally with:**
```bash
pip install fastapi uvicorn onnxruntime pillow python-multipart
uvicorn main:app --reload --port 8000
```

---

### 1.3 Technology Stack Selection

| Layer | Technology | Why |
|-------|------------|-----|
| Backend | FastAPI + ONNX Runtime + Pillow | Async, fast, automatic OpenAPI docs |
| Frontend | React + Vite | Fast dev experience, simple deployment |
| File Upload | react-dropzone | Mature, accessible drag-and-drop |
| Image Display | Canvas API | Direct pixel manipulation for overlays |

---

## **Phase 2: Frontend Development** 

Keep the UI simple but professional.

### 2.1 Core UI Components

- Image upload interface (drag-and-drop, file browser)  
- Loading state during inference  
- Side-by-side view: original image vs segmented overlay  
- Opacity slider for overlay  
- Download button for segmented mask  
- Error messages for invalid uploads

**Code Example - React Upload Component:**

```jsx
// src/components/ImageUploader.jsx
import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function ImageUploader() {
  const [original, setOriginal] = useState(null);
  const [mask, setMask] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [opacity, setOpacity] = useState(0.5);

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setError(null);
    setOriginal(URL.createObjectURL(file));
    setMask(null);
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/predict`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const blob = await response.blob();
      setMask(URL.createObjectURL(blob));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpeg', '.jpg', '.png'] },
    maxSize: 10 * 1024 * 1024,
    multiple: false,
  });

  return (
    <div className="uploader">
      <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
        <input {...getInputProps()} />
        {isDragActive ? (
          <p>Drop the image here...</p>
        ) : (
          <p>Drag & drop a CT/MRI image, or click to select</p>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="loading">Processing...</p>}

      {original && mask && (
        <div className="results">
          <div className="image-container">
            <img src={original} alt="Original" />
            <img 
              src={mask} 
              alt="Segmentation" 
              style={{ opacity }}
              className="overlay"
            />
          </div>
          
          <label>
            Overlay opacity: {Math.round(opacity * 100)}%
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={opacity}
              onChange={(e) => setOpacity(parseFloat(e.target.value))}
            />
          </label>

          <a href={mask} download="segmentation_mask.png">
            Download Mask
          </a>
        </div>
      )}
    </div>
  );
}
```

---

### 2.2 User Experience Enhancements

- Progress indicators  
- Image zoom/pan for detailed inspection  
- Multiple file batch processing (queue system)  
- Session history (last N processed images)  
- Responsive design for tablets (doctors on rounds)

### 2.3 Medical-Specific Features (for future)

- Confidence score display
- Manual annotation tools
- Export formats: PNG, DICOM overlay, annotation JSON  
- Case ID/patient metadata input (anonymized)

---

## **Phase 3: Integration & Testing** 

### 3.1 End-to-End Integration

- Connect frontend to backend API  
- Handle file upload with progress tracking  
- Display results with proper error handling  
- Test with various image formats (JPEG, PNG, DICOM if supported)  
- Performance testing (inference time, concurrent users)

---

### 3.2 Docker Containerization 

#### What is Docker?

Docker containers are like lightweight virtual machines that package an application with all its dependencies. Think of it as shipping a complete "box" that contains everything needed to run your software: operating system libraries, Python, packages, model files, and code.

**Why we need containers:**
- **Consistency**: "Works on my machine" → "Works everywhere"
- **Isolation**: Backend and frontend have separate, clean environments
- **Portability**: Same container runs on your laptop, cloud servers, or hospital infrastructure
- **Simplicity**: Hospital IT runs one command instead of following 50 installation steps

We create **two containers**—one for the backend (Python + ONNX Runtime) and one for the frontend (Node + Nginx to serve the React build).

**Backend Dockerfile (`backend/Dockerfile`):**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and model
COPY main.py .
COPY kidney_segmentation.onnx .

# Expose port and run
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Backend requirements.txt:**
```
fastapi==0.109.0
uvicorn==0.27.0
onnxruntime==1.17.0
pillow==10.2.0
python-multipart==0.0.6
```

**Frontend Dockerfile (`frontend/Dockerfile`):**

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Docker Compose (`docker-compose.yml`):**

This file orchestrates your multi-container application (backend + frontend), defining how services connect, what ports they expose, and environment variables they need. It ensures consistent deployment across dev/staging/production environments.

**Why you need it:**
- Multi-service coordination: Frontend and backend run together with automatic networking
- Configuration management: All container settings centralized in one file
- Reproducibility: Same setup everywhere eliminates "works on my machine" issues

**How to deploy:**
- **Locally:** `docker-compose up --build`
- **Production:** Use Docker Swarm (`docker stack deploy`), AWS ECS/Fargate, Google Cloud Run, or any VM with Docker installed

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - MODEL_PATH=/app/kidney_segmentation.onnx
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    environment:
      - VITE_API_URL=http://backend:8000
```

**Run locally:**
```bash
docker-compose up --build
# App available at http://localhost:80
# API available at http://localhost:8000/docs
```

---

### 3.3 Testing Suite (Best practice, but optional for MVP)

- Unit tests for preprocessing/postprocessing  
- API endpoint tests (pytest + httpx)  
- Frontend component tests (React Testing Library)  
- Integration tests (upload → inference → display)  
- Performance benchmarks

---

## **Phase 4: Cloud Deployment — Option 1 (MVP)**

This is where the software will live. Similar to "hosting" a website, but we rent CPUs/GPUs that perform inference at runtime. Bruno will guide provider selection at this stage.

### 4.1 Cloud Provider Options

| Provider | Service | Best For |
|----------|---------|----------|
| Google Cloud | Cloud Run | Serverless, easiest, auto-scaling |
| Digital Ocean | App Platform | Simplest, cheapest for MVP |
| AWS | ECS/Fargate | Enterprise scale |

**MVP Recommendation**: Google Cloud Run or Digital Ocean App Platform (~$20-50/month initially)

---

### 4.2 Deployment Steps (Google Cloud Run Example)

**Code Example - Deploy Script (`deploy.sh`):**

```bash
#!/bin/bash
set -e

PROJECT_ID="your-gcp-project"
REGION="europe-west1"
SERVICE_NAME="kidney-segmentation"

# Build and push backend image
docker build -t gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest ./backend
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME-backend \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest \
  --platform managed \
  --region $REGION \
  --memory 2Gi \
  --cpu 2 \
  --timeout 60s \
  --allow-unauthenticated \
  --set-env-vars MODEL_PATH=/app/kidney_segmentation.onnx

echo "Backend deployed at: $(gcloud run services describe $SERVICE_NAME-backend --region $REGION --format 'value(status.url)')"
```

**Steps:**
1. Push Docker images to Google Container Registry  
2. Create Cloud Run service from backend image  
3. Deploy frontend to Cloud Storage + CDN (or Vercel/Netlify)  
4. Configure CORS for API access  
5. Set up custom domain + SSL certificate  
6. Configure environment variables

---

### 4.3 Monitoring & Maintenance

- Set up logging (Google Cloud Logging)  
- Monitor inference latency, error rates  
- Cost monitoring and alerts  
- Automated health checks  
- Backup/rollback strategy

---

## **Phase 5: On-Premise Deployment — Option 2 (Future)**

This phase applies once we sell to clients who require data sovereignty (data never leaves hospital network). Out of scope for MVP but documented for completeness.

### 5.1 Hospital IT Requirements

**Hardware:**
- CPU: 4+ cores, 16GB RAM minimum  
- GPU: Optional (RTX 3060+ recommended)  
- Storage: 50GB minimum  
- Network: Internal only, no internet required

**Software:**
- Docker + Docker Compose  
- Ubuntu 22.04 or Windows Server

---

### 5.2 Simplified Installation Package

**Installation Script (`install.sh`):**

```bash
#!/bin/bash
set -e

echo "=== Kidney Segmentation System Installer ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not installed. Please install Docker first."
    exit 1
fi

# Pull images (or load from provided .tar files for air-gapped systems)
docker-compose pull

# Start services
docker-compose up -d

# Wait for health check
echo "Waiting for services to start..."
sleep 10

if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo ""
    echo "✓ Installation complete!"
    echo "Application running at: http://localhost:80"
    echo "API documentation at: http://localhost:8000/docs"
else
    echo "Error: Health check failed. Check logs with: docker-compose logs"
    exit 1
fi
```

---

## **Phase 6: Documentation & Handoff**

### 6.1 Technical Documentation
- Architecture diagram  
- API documentation (FastAPI auto-generates Swagger at `/docs`)  
- Model card (input/output specs, limitations, accuracy)  
- Deployment guides (cloud + on-premise)

### 6.2 User Documentation
- Quick start guide for radiologists  
- Video tutorial (2-3 minutes)  
- FAQ section  
- Known limitations and edge cases

### 6.3 Training Materials
- Demo dataset (anonymized)  
- Step-by-step workflow guide  
- Best practices for image quality

---

# Development Timeline Summary

| Week | Phase | Deliverables |
|------|-------|--------------|
| 1-2 | Model prep + Backend | ONNX model, working API |
| 2-3 | Frontend | React app with upload/display |
| 3-4 | Integration | Docker setup, end-to-end testing |
| 4-5 | Cloud deployment | Live MVP on Cloud Run |
| 5-6 | On-premise package | Installation scripts (if needed) |
| 6-7 | Documentation | User guides, handoff materials |
