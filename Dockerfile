# FocusGuard AI - online deployment image (see DEPLOY.md).
# Stage 1 builds the website; stage 2 runs the backend, which serves it.

FROM node:22-slim AS web
WORKDIR /app/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FOCUSGUARD_MODE=cloud \
    FOCUSGUARD_AUTOSTART_TRACKER=0
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY frontend/ frontend/
COPY app_categories.json ./
COPY --from=web /app/frontend-react/dist frontend-react/dist

# Hosts like Render pass the port to listen on in $PORT.
CMD uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
