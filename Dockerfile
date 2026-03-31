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
COPY pyproject.toml uv.lock ./

# Install dependencies only (not the project itself)
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy source
COPY src/ src/

# Install the project itself
RUN uv pip install --system --no-cache --no-deps .

# Copy built frontend
COPY --from=frontend-build /frontend/dist frontend/dist/

# Non-root user
RUN useradd --create-home appuser
USER appuser

# Default: Web mode (port 8000), override with RUN_MODE=foundry for Foundry adapter
ENV RUN_MODE=web
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "profile_agent"]
