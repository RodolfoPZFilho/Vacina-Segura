# Imagem unica dos servicos Python (simulador, gateway, gravador, inferencia, lab, api, rabbit-init).
# Cada servico do docker-compose.yml escolhe o modulo pelo "command".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# usuario sem privilegios; as pastas dos volumes ja nascem com o dono certo
RUN useradd --uid 10001 --create-home app \
 && mkdir -p /modelos /dados \
 && chown app:app /modelos /dados

COPY vacinasegura ./vacinasegura
USER app

CMD ["python", "-m", "vacinasegura.api.main"]
