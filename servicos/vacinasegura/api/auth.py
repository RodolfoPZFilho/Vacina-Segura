"""Autenticacao: bcrypt, JWT, papeis e limite de tentativas de login."""
from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..comum.config import env, env_int

JWT_SEGREDO = env("JWT_SEGREDO")
JWT_HORAS = env_int("JWT_HORAS", 8)
NIVEL = {"visualizador": 1, "operador": 2, "administrador": 3}
MAX_FALHAS_LOGIN = 5
BLOQUEIO_MIN = 5
_falhas_ip: dict[str, deque] = defaultdict(deque)
_bearer = HTTPBearer(auto_error=False)


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=12)).decode()


def conferir_senha(senha: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode(), hash_.encode())
    except ValueError:
        return False


def criar_token(usuario: dict) -> str:
    agora = datetime.now(timezone.utc)
    return jwt.encode({"sub": usuario["login"], "nome": usuario["nome"], "papel": usuario["papel"],
                       "iat": agora, "exp": agora + timedelta(hours=JWT_HORAS)}, JWT_SEGREDO, algorithm="HS256")


def ip_bloqueado(ip: str) -> bool:
    fila = _falhas_ip[ip]
    while fila and fila[0] < time.time() - 600:
        fila.popleft()
    return len(fila) >= 20


def registrar_falha_ip(ip: str):
    _falhas_ip[ip].append(time.time())


async def usuario_atual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login necessario")
    try:
        dados = jwt.decode(cred.credentials, JWT_SEGREDO, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessao invalida ou expirada")
    return {"login": dados["sub"], "nome": dados.get("nome", ""), "papel": dados["papel"]}


def exigir(papel: str):
    async def _dep(u: dict = Depends(usuario_atual)) -> dict:
        if NIVEL.get(u["papel"], 0) < NIVEL[papel]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Acao exige papel '{papel}'")
        return u
    return _dep


def ip_de(req: Request) -> str:
    return req.headers.get("x-real-ip") or (req.client.host if req.client else "?")


# --- tickets de uso unico para o WebSocket (o JWT nunca vai na URL) ---------------
_tickets: dict[str, tuple[dict, float]] = {}


def emitir_ticket(usuario: dict) -> str:
    agora = time.time()
    for t, (_, exp) in list(_tickets.items()):
        if exp < agora:
            _tickets.pop(t, None)
    ticket = secrets.token_urlsafe(24)
    _tickets[ticket] = (usuario, agora + 30)
    return ticket


def consumir_ticket(ticket: str) -> dict | None:
    item = _tickets.pop(ticket, None)
    if not item or item[1] < time.time():
        return None
    return item[0]


BLOQUEIO = timedelta(minutes=BLOQUEIO_MIN)
