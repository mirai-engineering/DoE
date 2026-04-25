# Stage 1: Dependencies
FROM node:20-alpine AS deps
WORKDIR /app

# Copy dependency files
COPY package.json package-lock.json* ./
RUN npm ci

# Stage 2: Build
FROM node:20-alpine AS builder
WORKDIR /app

# Accept build argument for API URL
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build Vite application
RUN npm run build

# Stage 3: Runtime (Nginx to serve static files)
FROM nginx:alpine AS runner

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
