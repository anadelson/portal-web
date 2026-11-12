FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends tzdata postgresql-client ghostscript && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY deploy/certs ./deploy/certs
# fontes de implantação (para o console gerar o pacote de código de um nó novo: Nós e licenças → Preparar instalação)
COPY Dockerfile docker-compose.yml requirements.txt ./fonte/
COPY deploy ./fonte/deploy
RUN python -m app.imagens otimizar
RUN useradd -r -u 1001 portal && mkdir -p /srv/dados && chown -R portal /srv/dados
USER portal
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
