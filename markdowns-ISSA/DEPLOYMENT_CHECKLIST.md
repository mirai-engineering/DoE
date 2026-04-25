# ✅ Production Deployment Checklist

## 📋 Prerequisites (Before starting)

### 1. Required accounts and tools

- [ ] **Google Cloud Platform (GCP) account**
  - Create account at: https://cloud.google.com/
  - Enable billing (has $300 free credits)
  - Install Google Cloud SDK: `gcloud` CLI

- [ ] **Vercel account**
  - Create account at: https://vercel.com/
  - Install Vercel CLI: `npm install -g vercel`

- [ ] **Docker installed**
  - Verify: `docker --version`
  - If not installed: https://docs.docker.com/get-docker/

### 2. Google Cloud configuration

- [ ] **Create a project in GCP**
  ```bash
  gcloud projects create your-project-id --name="Kidney Segmentation"
  gcloud config set project your-project-id
  ```

- [ ] **Enable required APIs**
  ```bash
  gcloud services enable run.googleapis.com
  gcloud services enable containerregistry.googleapis.com
  ```

- [ ] **Configure Docker authentication for GCR**
  ```bash
  gcloud auth configure-docker
  ```

- [ ] **Update `deploy-backend.sh` with your PROJECT_ID**
  - Edit line 5: `PROJECT_ID="your-real-project-id"`

### 3. Verify everything is ready

- [ ] **Download model with Git LFS** (if you just cloned the repo)
  - ⚠️ **IMPORTANT**: The model is in Git LFS. See complete instructions in [README.md](./README.md) section "Download Model with Git LFS"
  - Quick summary: `git lfs pull --include="backend/models/*.onnx"` (after `git pull`)

- [ ] **ONNX model exists and is valid**
  ```bash
  ls -lh backend/models/kidney_segmentation.onnx
  # ✅ File must exist AND weigh > 1MB
  ```

- [ ] **Dockerfiles are correct**
  - ✅ `backend/Dockerfile` - Ready
  - ✅ `frontend/Dockerfile` - Ready

- [ ] **Deploy scripts exist**
  - ✅ `deploy-backend.sh` - Ready
  - ✅ `deploy-frontend.sh` - Ready

---

## 🚀 Deployment Process

### Step 1: Deploy Backend to Google Cloud Run

1. **Configure CORS_ORIGINS**
   ```bash
   # First you need to know the Vercel URL, but since you don't have it yet,
   # you can use a placeholder and update it later
   export CORS_ORIGINS='https://your-app.vercel.app'
   ```

2. **Run backend deployment**
   ```bash
   ./deploy-backend.sh
   ```

3. **Save the backend URL**
   - The script will show: `Backend URL: https://kidney-segmentation-backend-xxxx.run.app`
   - **SAVE THIS URL!** You'll need it for the frontend

### Step 2: Deploy Frontend to Vercel

1. **Configure BACKEND_URL**
   ```bash
   export BACKEND_URL='https://kidney-segmentation-backend-xxxx.run.app'
   # (Use the real URL you got from the previous step)
   ```

2. **Run frontend deployment**
   ```bash
   ./deploy-frontend.sh
   ```

3. **Get Vercel URL**
   - Vercel will give you a URL like: `https://your-app.vercel.app`

### Step 3: Update CORS with real Vercel URL

1. **Update CORS in Cloud Run**
   ```bash
   export CORS_ORIGINS='https://your-app.vercel.app'
   gcloud run services update kidney-segmentation-backend \
     --region europe-west1 \
     --update-env-vars "CORS_ORIGINS=$CORS_ORIGINS"
   ```

---

## 🔧 Additional Recommended Configuration

### Custom domain (Optional)

- [ ] **Configure domain in Vercel**
  - In Vercel dashboard, add your domain
  - Update CORS with the new domain

- [ ] **Configure domain in Cloud Run**
  - Map custom domain to Cloud Run service

### Additional environment variables

The backend already has these variables configured in `deploy-backend.sh`:
- ✅ `CORS_ORIGINS` - Configured
- ✅ `ENVIRONMENT=production` - Configured
- ✅ `MODEL_PATH=/app/models/kidney_segmentation.onnx` - Configured

### Monitoring (Optional but recommended)

- [ ] **Configure Google Cloud Logging**
  - Logs are already available in Cloud Console

- [ ] **Configure alerts**
  - Create alerts for 5xx errors
  - Monitor inference latency

---

## 🧪 Post-Deployment Verification

### Verify Backend

- [ ] **Health check**
  ```bash
  curl https://your-backend.run.app/health
  # Should respond: {"status":"healthy","model_loaded":true}
  ```

- [ ] **Model info**
  ```bash
  curl https://your-backend.run.app/model-info
  # Should show model information
  ```

- [ ] **API docs**
  - Open: `https://your-backend.run.app/docs`
  - Should show FastAPI documentation

### Verify Frontend

- [ ] **Open Vercel URL**
  - Application should load
  - No errors in browser console

- [ ] **Test uploading an image**
  - Upload a test image
  - Verify it processes correctly
  - Verify result is displayed

### Verify CORS

- [ ] **Open browser DevTools**
  - Network tab → Verify requests to `/api/predict` work
  - No CORS errors

---

## ⚠️ Common Problems and Solutions

### Error: "CORS_ORIGINS must be set"
- **Solution**: Run `export CORS_ORIGINS='https://your-app.vercel.app'` before `./deploy-backend.sh`

### Error: "BACKEND_URL must be set"
- **Solution**: Run `export BACKEND_URL='https://your-backend.run.app'` before `./deploy-frontend.sh`

### Error: "Permission denied" on Docker push
- **Solution**: Run `gcloud auth configure-docker`

### Error: "Model not found" or "Model invalid" on Docker build
- **Solution**: See [README.md](./README.md) troubleshooting section "Error: Model invalid" for complete Git LFS instructions

### Error: CORS blocking requests
- **Solution**: Verify that `CORS_ORIGINS` includes the exact Vercel URL (with https://)

### Frontend doesn't connect to backend
- **Solution**: Verify that `VITE_API_URL` is configured correctly in Vercel
  - In Vercel dashboard → Settings → Environment Variables
  - Add: `VITE_API_URL` = `https://your-backend.run.app`

---

## 📊 Estimated Costs

### Google Cloud Run
- **Free**: First 2 million requests/month
- **After**: ~$0.40 per million requests
- **Memory/CPU**: ~$0.00002400 per GB-second
- **Estimated for MVP**: $0-20/month

### Vercel
- **Free**: 100GB bandwidth/month, unlimited deployments
- **Pro**: $20/month (if you need more)
- **Estimated for MVP**: $0/month (free plan sufficient)

### Total estimated: $0-20/month for MVP

---

## ✅ Command Summary

```bash
# 1. Configure GCP
gcloud projects create your-project-id
gcloud config set project your-project-id
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud auth configure-docker

# 2. Edit deploy-backend.sh with your PROJECT_ID
# (Edit line 5 manually)

# 3. Deploy backend
export CORS_ORIGINS='https://your-app.vercel.app'  # Or use placeholder
./deploy-backend.sh

# 4. Save BACKEND_URL shown by the script

# 5. Deploy frontend
export BACKEND_URL='https://kidney-segmentation-backend-xxxx.run.app'
./deploy-frontend.sh

# 6. Update CORS with real Vercel URL
export CORS_ORIGINS='https://your-real-app.vercel.app'
gcloud run services update kidney-segmentation-backend \
  --region europe-west1 \
  --update-env-vars "CORS_ORIGINS=$CORS_ORIGINS"
```

---

## 🎉 Done!

Once all steps are completed, your application will be in production and publicly accessible.

**Important URLs:**
- Frontend: `https://your-app.vercel.app`
- Backend: `https://kidney-segmentation-backend-xxxx.run.app`
- API Docs: `https://kidney-segmentation-backend-xxxx.run.app/docs`
