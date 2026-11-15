FROM node:22-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY whylab ./whylab
COPY backend ./backend
COPY teammate_integration.py ./
RUN pip install --no-cache-dir -c constraints.txt . && useradd --create-home app && mkdir -p /app/.data/previews && chown -R app:app /app/.data
COPY --from=frontend /ui/dist ./frontend/dist
COPY frontend_viewspace ./frontend_viewspace
COPY PythonProject/final_dataset ./PythonProject/final_dataset
COPY scripts/serve.py ./scripts/serve.py
# Rebuild a portable registry from the checksum-verified, bundled observations.
# Local .data is deliberately excluded from the image build context.
RUN python -m whylab.dataset PythonProject/final_dataset --root /app/.data && chown -R app:app /app/.data
ENV WHYLAB_ADAPTER_FACTORY=whylab.integration:build_adapters \
    WHYLAB_FRONTEND_DIR=/app/frontend/dist \
    WHYLAB_OUTPUT_DIR=/app/.data/previews \
    MPLCONFIGDIR=/app/.data/matplotlib \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
USER app
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
