# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files first (Docker layer caching)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

# Copy source
COPY src/ src/

# Copy built frontend
COPY --from=frontend-build /frontend/dist frontend/dist/

# Non-root user
RUN useradd --create-home appuser
USER appuser

# Default: Foundry adapter mode (port 8088)
ENV RUN_MODE=foundry
ENV PORT=8088

EXPOSE 8088

CMD ["python", "-m", "profile_agent"]
