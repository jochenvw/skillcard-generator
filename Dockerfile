# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build
ARG GIT_SHA=dev
ARG GIT_TAG=
ENV GIT_SHA=$GIT_SHA
ENV GIT_TAG=$GIT_TAG
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Final image
FROM python:3.12-slim
ARG GIT_SHA=dev
ARG GIT_TAG=
ENV APP_VERSION=$GIT_SHA
ENV APP_GIT_TAG=$GIT_TAG

WORKDIR /app

# Install project + deps in one layer, then clean up
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv pip install --system --no-cache . \
    && rm -f /usr/local/bin/uv \
    && rm -rf /root/.cache /tmp/* \
    && find /usr/local/lib/python3.12/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

# Copy built frontend
COPY --from=frontend-build /build/dist frontend/dist/

# Non-root user
RUN useradd --no-log-init --create-home appuser
USER appuser

ENV RUN_MODE=web
ENV PORT=8000
EXPOSE 8000

CMD ["python", "-m", "profile_agent"]
