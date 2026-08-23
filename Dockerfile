FROM node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && python -m pip uninstall --yes setuptools wheel \
    && python -m pip uninstall --yes pip

COPY backend/ .
COPY examples/ ./examples/
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN addgroup --system docintel \
    && adduser --system --ingroup docintel docintel \
    && mkdir -p /data \
    && chown -R docintel:docintel /app /data

USER docintel
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30", "--no-access-log"]
