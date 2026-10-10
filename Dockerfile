FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HAVOC_HOME=/app EMBEDDINGS_BACKEND=hf

# CPU-only PyTorch keeps the image far smaller than the default CUDA build
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt requirements-hf.txt ./
RUN pip install -r requirements.txt -r requirements-hf.txt

# Bake the embedding model into the image so containers start offline-ready
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "havoc.api:app", "--host", "0.0.0.0", "--port", "8000"]
