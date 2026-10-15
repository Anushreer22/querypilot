# ==============================================================================
# Optional multi-stage Dockerfile for QueryPilot Frontend (Self-Hosted Nginx)
# ==============================================================================

# Stage 1: Build static assets
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Argument for backend API base URL at build time (e.g. https://api.querypilot.dev)
ARG VITE_API_BASE_URL=""
ARG VITE_DEMO_MODE="true"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_DEMO_MODE=$VITE_DEMO_MODE

RUN npm run build

# Stage 2: Serve with Nginx Alpine
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

