# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Final image
FROM python:3.12-slim

WORKDIR /app

# Install dependencies directly (no build step needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv pip install --system --no-cache . && rm -f /usr/local/bin/uv

# Copy built frontend
COPY --from=frontend-build /build/dist frontend/dist/

# Non-root user
RUN useradd --create-home appuser
USER appuser

ENV RUN_MODE=web
ENV PORT=8000
EXPOSE 8000

CMD ["python", "-m", "profile_agent"]
