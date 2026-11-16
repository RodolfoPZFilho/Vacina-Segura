"""Cadastro inicial de dispositivos (seed do PostgreSQL e config padrao do simulador).

Cada UBS tem sensores de sala e uma luz; cada geladeira tem sensores, um compressor
(equipamento monitorado para manutencao preditiva) e dois atuadores.
"""

UBS = {"ubs01": "UBS Centro", "ubs02": "UBS Vila Nova"}
GELADEIRAS = {"ubs01": ["g01", "g02"], "ubs02": ["g01", "g02"]}

# grandeza: (categoria, unidade, faixa_min, faixa_max, controle)
#   categoria: sensor | equipamento | atuador
#   controle (atuadores): auto = regra de negocio, manual = aplicacao Web
GRANDEZAS = {
    "temperatura": ("sensor", "°C", 2.0, 8.0, None),
    "umidade": ("sensor", "%", 30.0, 75.0, None),
    "porta": ("sensor", "aberta", 0.0, 0.0, None),
    "temp_ambiente": ("sensor", "°C", 15.0, 30.0, None),
    "luminosidade": ("sensor", "lux", 0.0, 1200.0, None),
    "compressor": ("equipamento", "", None, None, None),
    "alarme": ("atuador", "", None, None, "auto"),
    "resfriamento": ("atuador", "", None, None, "manual"),
    "luz": ("atuador", "", None, None, "manual"),
}

# Faixas normais das variaveis do compressor (para colorir o 3D e o painel)
FAIXAS_COMPRESSOR = {
    "vibracao": (0.0, 3.5, "mm/s"),
    "corrente": (0.0, 2.6, "A"),
    "temp_compressor": (0.0, 60.0, "°C"),
}

SUFIXO = {"temperatura": "temp", "umidade": "umid", "porta": "porta", "compressor": "comp",
          "alarme": "alarme", "resfriamento": "resfr", "temp_ambiente": "tamb",
          "luminosidade": "lux", "luz": "luz"}

NOMES = {"temperatura": "Temperatura interna", "umidade": "Umidade interna", "porta": "Sensor de porta",
         "compressor": "Compressor", "alarme": "Alarme sonoro", "resfriamento": "Resfriamento de emergência",
         "temp_ambiente": "Temperatura da sala", "luminosidade": "Luminosidade da sala", "luz": "Luz da sala"}


def dispositivo(ubs: str, geladeira: str | None, grandeza: str) -> dict:
    cat, unidade, fmin, fmax, controle = GRANDEZAS[grandeza]
    base = f"{ubs}-{geladeira}" if geladeira else ubs
    nome = NOMES[grandeza] + (f" {geladeira.upper()}" if geladeira else "")
    return {
        "id": f"{base}-{SUFIXO[grandeza]}",
        "nome": f"{nome} - {UBS.get(ubs, ubs)}",
        "categoria": cat,
        "grandeza": grandeza,
        "ubs": ubs,
        "geladeira": f"{ubs}-{geladeira}" if geladeira else None,
        "unidade": unidade,
        "faixa_min": fmin,
        "faixa_max": fmax,
        "controle": controle,
        "ativo": True,
    }


def cadastro_inicial() -> list[dict]:
    itens = []
    for ubs, gels in GELADEIRAS.items():
        for g in ("temp_ambiente", "luminosidade", "luz"):
            itens.append(dispositivo(ubs, None, g))
        for gel in gels:
            for g in ("temperatura", "umidade", "porta", "compressor", "alarme", "resfriamento"):
                itens.append(dispositivo(ubs, gel, g))
    return itens
