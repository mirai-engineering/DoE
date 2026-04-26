# Mirai DoE Engine — Docker Deployment Guide

This guide explains how to run the Mirai DoE Engine using Docker and why we use an nginx reverse proxy.

## The Problem: CORS Issues

When running frontend and backend on **different ports**, browsers enforce **CORS (Cross-Origin Resource Sharing)** policies:

```
Frontend: http://192.168.100.28:3000  ← Different origin
Backend:  http://192.168.100.28:8000 ← Different origin
```

Browser blocks requests between different origins unless the server explicitly allows them. This leads to:

```
Backend connection issue
Unable to connect to the DoE API. Check that the backend is running.
```

## The Solution: Nginx Reverse Proxy

Route all traffic through a single nginx server. Now both frontend and backend share the **same origin**:

```
                  http://localhost:3000
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    / (SPA)         /api/*         /health
      │              │               │
      ▼              ▼               ▼
  Frontend:80   Backend:8000   Backend:8000
  (static)      (API)          (health check)
```

- **Same origin** = no CORS issues
- **Single entry point** = easier to manage, secure, and deploy

## Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd Analytics/DoE
```

### 2. Build and start the containers

```bash
docker compose up -d --build
```

### 3. Verify it's running

```bash
# Frontend should be accessible
curl http://localhost:3000/

# Backend health check
curl http://localhost:3000/health

# Backend API (example: predict)
curl -X POST http://localhost:3000/api/projects/pem_fuel_cell_demo/predict \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "pt_c_ratio": 0.5,
      "i_c_ratio": 0.8,
      "ionomer_ew": 790,
      "operating_rh": 70,
      "operating_voltage": 0.6,
      "ast_rh": 100,
      "ast_upl": 1.15
    }
  }'
```

### 4. Open in browser

Navigate to: **http://localhost:3000**

---

## Alternative: Run Without Docker

If you prefer running services directly on your machine:

### Backend (FastAPI)

```bash
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend (Vite dev server)

```bash
cd frontend
npm install
npm run dev
```

> **Note:** Running locally means frontend and backend on different ports, so you'll need to configure CORS or access both via `localhost` only.

---

## Architecture Overview

### Files Involved

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Defines all services (backend, frontend, nginx-proxy) |
| `nginx/proxy.conf` | Nginx configuration for routing requests |
| `backend/Dockerfile` | Backend container image |
| `frontend/Dockerfile` | Frontend container image |

### Services

| Service | Port (internal) | Description |
|--------|---------------|-------------|
| `backend` | 8000 | FastAPI with ONNX model inference |
| `frontend` | 80 | React app built to static files |
| `nginx-proxy` | 3000 (exposed) | Reverse proxy routing |

### Request Flow

```
Browser → http://localhost:3000 → nginx → frontend:80 (static files)
         → /api/* → nginx rewrites /api/→/, proxies to backend:8000
         → /health → proxies to backend:8000/health
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs -f
```

### Port already in use

Edit `docker-compose.yml` to change the port:

```yaml
nginx-proxy:
  ports:
    - "8080:3000"  # Now accessible at http://localhost:8080
```

### Rebuild after changes

```bash
docker compose down
docker compose up -d --build
```

### Stop everything

```bash
docker compose down
```

---

## Why This Setup?

| Approach | Pros | Cons |
|----------|------|------|
| **Nginx reverse proxy** | Single origin, no CORS, production-ready | Extra container |
| **CORS configuration** | Simple | Must manage allowed origins, less professional |
| **Same port** | No CORS | Requires root access to bind ports < 1024 |

The nginx reverse proxy is the standard production pattern — it handles SSL termination, load balancing, caching, and security headers in one place.

---

## API Endpoints Reference

Once running, the full API is accessible at `http://localhost:3000/api/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/projects` | GET | List available projects |
| `/projects/{id}/schema` | GET | Get project schema |
| `/projects/{id}/predict` | POST | Predict KPIs for given inputs |
| `/projects/{id}/batch-predict` | POST | Batch predict multiple experiments |
| `/projects/{id}/recommend` | POST | Recommend next experiments |

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) — Python web framework
- [ONNX Runtime](https://onnxruntime.ai/) — Neural network inference
- [React](https://react.dev/) — Frontend framework
- [Vite](https://vitejs.dev/) — Build tool
- [Nginx](https://nginx.org/) — Reverse proxy
- [Docker](https://www.docker.com/) — Containerization