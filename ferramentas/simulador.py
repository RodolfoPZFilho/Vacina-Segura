"""Simulador de geladeira (ferramenta de teste, alternativa ao Wokwi).

Publica leituras no mesmo broker e tópico que o ESP32 do Wokwi usa,
então o fluxo percorrido é idêntico: broker público -> ponte -> Mosquitto -> Python.

Uso (com o ambiente virtual do backend ativo):
    python ferramentas/simulador.py                 # 1 geladeira normal
    python ferramentas/simulador.py --falha         # simula porta aberta (temperatura sobe)
    python ferramentas/simulador.py --local         # publica direto no Mosquitto local (porta 1884)
"""
import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt

ID_PROJETO = "35kr1sud"

parser = argparse.ArgumentParser()
parser.add_argument("--ubs", default="ubs01")
parser.add_argument("--geladeira", default="g01")
parser.add_argument("--intervalo", type=float, default=5, help="segundos entre leituras")
parser.add_argument("--falha", action="store_true", help="simula porta aberta")
parser.add_argument("--local", action="store_true", help="publica no Mosquitto local")
parser.add_argument("--vezes", type=int, default=0, help="quantidade de leituras (0 = infinito)")
args = parser.parse_args()

if args.local:
    host, porta = "localhost", 1884
    topico = f"vacinasegura/ubs/{args.ubs}/geladeira/{args.geladeira}"
else:
    host, porta = "broker.hivemq.com", 1883
    topico = f"vacinasegura/{ID_PROJETO}/ubs/{args.ubs}/geladeira/{args.geladeira}"

cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cliente.connect(host, porta, keepalive=30)
cliente.loop_start()
print(f"Publicando em {host}:{porta} -> {topico}  (Ctrl+C para parar)")

inicio = time.time()
n = 0
try:
    while args.vezes == 0 or n < args.vezes:
        t = time.time() - inicio
        temperatura = 5 + 1.2 * math.sin(t / 60) + random.uniform(-0.2, 0.2)
        if args.falha:
            temperatura += min(t / 10, 6)  # sobe até +6 °C
        leitura = {"temperatura": round(temperatura, 2), "umidade": round(random.uniform(55, 65), 1)}
        cliente.publish(topico, json.dumps(leitura)).wait_for_publish()
        print(leitura)
        n += 1
        time.sleep(args.intervalo)
except KeyboardInterrupt:
    pass
finally:
    cliente.loop_stop()
    cliente.disconnect()
