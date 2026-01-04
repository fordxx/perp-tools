FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    cargo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# /src is provided via a bind mount for Lighter support
COPY app ./app
COPY okx_compat_layer.py ./
COPY README.md ./
COPY router_app.py ./

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/src:$PYTHONPATH
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
