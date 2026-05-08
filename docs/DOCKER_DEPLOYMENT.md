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

## Deep Dive: How Docker Networking Works

### The Problem: Multiple Services on Same Port?

You might wonder: if both frontend and backend want to use port 3000, isn't there a conflict?

The answer: **No** — because each container has its own isolated network namespace.

### How Docker Networking Actually Works

When you run Docker containers, each container gets its own **virtual network interface** with its own IP address. They're like mini-computers:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Your Mac (host machine)                                  │
│                                                     │
│  Physical network: 192.168.100.28                       │
│                                                     │
│  :3000 (exposed to host) ──────────────────────┐       │
│                                             │       │
└──────────────────────────────────────────────│───────┘
                                              │
                                 ┌────────────┴────────────┐
                                 │ Docker internal network │
                                 │ (172.18.0.0/16)         │
                                 │                         │
                                 │  ┌──────────────┐     │
                                 │  │ nginx-proxy  │      │
                                 │  │ 172.18.0.2   │        │ :3000
                                 │  └──────┬───────┘  │
                                 │         │            │
              ┌────────────────────┼────────┼────────┼────────┐
              │                    │        │        │        │
              │                    ▼        ▼        ▼        │
              │         ┌──────────┐ ┌──────────┐     │
              │         │ frontend │  │ backend │     │
              │         │ :80     │  │ :8000  │     │
              │         └──────────┘ └────────┘     │
              └────────────────────────────────────┘
```

### Key Insight: Internal Ports vs. Exposed Ports

- **Internal port** — What the service listens on *inside* its container (frontend:80, backend:8000)
- **Exposed port** — What the host machine exposes to the outside world (nginx:3000 → host:3000)

Each container independently uses whatever port it wants internally. There's no conflict because they're completely isolated.

### How Requests Flow

1. You open `http://localhost:3000` in your browser
2. Your Mac receives the request on port 3000
3. Docker forwards it to the nginx-proxy container (which bound to port 3000 inside Docker)
4. Nginx decides where to send it:
   - `/` → forwards to `frontend:80`
   - `/api/*` → forwards to `backend:8000`

### Docker Compose Creates an Internal Network

In `docker-compose.yml`, we defined:

```yaml
networks:
  mirai-doe-network:
    driver: bridge
```

This creates an internal network where containers can reach each other by name. Inside the network:
- `http://backend:8000` resolves to the backend container
- `http://frontend:80` resolves to the frontend container

Without Docker, you'd get "host not found" errors trying to connect to `backend:8000` — it's only available inside Docker's network.

### This is the Docker Advantage

Docker makes it feel like you have three separate computers, each with their own ports:

| What you see | What's actually happening |
|-------------|----------------------|
| Port 3000 on your Mac | nginx-proxy listening on :3000 inside container |
| Backend at port 8000 | backend listening on :8000 inside its container |
| Frontend at port 80 | nginx serving static files from frontend container |

They don't conflict because they're in isolated network namespaces, connected only through Docker's internal network.

---

## Concrete Example: Our Mirai DoE Setup

Let's trace exactly what happens when you open the app:

### Step 1: You open http://localhost:3000

```
Browser (on your Mac)
    │
    └─► GET / HTTP/1.1
        Host: localhost:3000
```

### Step 2: Docker receives the request

```
Host machine port 3000
    │
    └─► Forwards to nginx-proxy container (internal port 3000)
```

### Step 3: Nginx processes the request

nginx.conf has:
```
location / {
    proxy_pass http://frontend:80;  # Internal Docker network!
}
```

### Step 4: Nginx forwards to frontend container

```
nginx (172.18.0.2:3000)
    │
    └─► http://frontend:80
        │
        └─► 172.18.0.3:80
```

### Step 5: Frontend returns HTML

```
172.18.0.3:80
    │
    └─► <!doctype html>...
        │
        ◄────────────────┘ Proxy back through nginx
```

### Step 6: Browser receives the response

Same TCP connection from `localhost:3000`, but the content came from the frontend container internally.

### The API Call Flow (Same Pattern)

When the frontend JavaScript calls the API:

```
Frontend JavaScript (in user's browser)
    │
    └─► POST http://localhost:3000/api/projects/.../predict
        │
        ▼
nginx receives request
    │
    │ location /api/ {
    │     rewrite /api/(.*) /$1 break;
    │     proxy_pass http://backend:8000;
    │ }
    │
    ▼ (rewrites /api/... → /... and proxies)
http://backend:8000 (internal Docker network)
    │
    └─► ONNX inference
        │
        ▼
Response proxies back through nginx to browser
```

### Why This Works Without CORS

1. **Browser requests from `http://localhost:3000`** — the frontend JavaScript loaded from `localhost:3000`
2. **JavaScript calls `http://localhost:3000/api/...`** — same origin!
3. **nginx forwards to backend** — internal Docker network, no CORS involved
4. **Response comes back through nginx** — still from `localhost:3000`

The browser sees only one origin (`localhost:3000`), so no CORS headers needed. The magic is nginx hiding the internal container ports from the outside world.

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

## What Each Component Actually Does

It's easy to confuse nginx with the backend API. Here's what each container is actually doing:

| Component | What it is | What it runs | Holds model? |
|-----------|-----------|-------------|--------------|
| **nginx-proxy** | Reverse proxy (traffic cop) | Pure C program, routes HTTP requests | ❌ No |
| **backend** | FastAPI (Python web server) | API endpoints, runs ONNX model inference | ✅ YES |
| **frontend** | Static HTML/JS files | Built React app (just files) | ❌ No |

### The Actual Request Flow

```
Browser ──► http://localhost:3000
                │
                ▼ nginx container listens on :3000
                │ (sees /api/* path, routes to backend)
                │
                │ /api/*
                ▼
backend:8000 (FastAPI/Python process)
                │
                │ Loads .onnx model file from disk
                │ Runs neural network inference
                │ Returns JSON result
                │
                ▼
Response back through nginx → Browser
```

### Common Confusion: "Is nginx running FastAPI?"

**No.** The ONNX model lives in the **backend container** as a `.onnx` file (`backend/artifacts/pem_fuel_cell_demo/model.onnx`). nginx doesn't know about it — it just passes traffic back and forth.

Think of it this way:
- **nginx** = the receptionist (routes you to the right person)
- **backend** = the engineer (actually runs the AI model)
- **frontend** = the brochure (static information)

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