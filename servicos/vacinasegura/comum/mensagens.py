"""Formato unico das mensagens trocadas no MQTT e no RabbitMQ.

    {
      "id": "uuid",
      "ts": "2026-11-16T12:00:00.000Z",
      "tipo": "telemetria | comando | previsao | alerta | job | config",
      "dispositivo": "ubs01-g01-comp",
      "ubs": "ubs01",
      "conteudo": { ... }
    }
"""
import json
import uuid
from datetime import datetime, timezone

TIPOS = {"telemetria", "comando", "previsao", "alerta", "job", "config"}


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nova(tipo: str, dispositivo: str, conteudo: dict, ubs: str = "sistema", ts: str | None = None) -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    return {
        "id": str(uuid.uuid4()),
        "ts": ts or agora_iso(),
        "tipo": tipo,
        "dispositivo": dispositivo,
        "ubs": ubs,
        "conteudo": conteudo,
    }


def validar(msg: dict) -> dict:
    """Garante os campos obrigatorios; lanca ValueError se a mensagem for invalida."""
    if not isinstance(msg, dict):
        raise ValueError("mensagem nao e um objeto JSON")
    for campo in ("id", "ts", "tipo", "dispositivo", "conteudo"):
        if campo not in msg:
            raise ValueError(f"campo ausente: {campo}")
    if msg["tipo"] not in TIPOS:
        raise ValueError(f"tipo invalido: {msg['tipo']}")
    if not isinstance(msg["conteudo"], dict):
        raise ValueError("conteudo deve ser objeto")
    msg.setdefault("ubs", "sistema")
    return msg


def codificar(msg: dict) -> bytes:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode()


def decodificar(dados: bytes) -> dict:
    return validar(json.loads(dados))


def seguro(texto: str) -> str:
    """Normaliza um trecho de routing key / topico (sem '.', '#', '+', '/')."""
    return "".join(c for c in texto if c.isalnum() or c in "-_") or "x"
