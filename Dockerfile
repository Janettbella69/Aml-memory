FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7"
COPY app ./app
COPY scripts ./scripts
ENV DATABASE_PATH=/data/memory.db
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
