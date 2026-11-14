FROM node:22-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY whylab ./whylab
RUN pip install --no-cache-dir -c constraints.txt . && useradd --create-home app && mkdir -p /app/.data/previews && chown -R app:app /app/.data
COPY --from=frontend /ui/dist ./frontend/dist
ENV WHYLAB_ADAPTER_FACTORY=whylab.integration:build_adapters
USER app
EXPOSE 8000
CMD ["uvicorn", "whylab.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
