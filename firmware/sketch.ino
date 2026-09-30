/*
 * VacinaSegura - firmware do ESP32 (Wokwi ou placa física)
 *
 * Lê a temperatura/umidade da geladeira de vacinas (DHT22) e publica via MQTT.
 * LED verde = temperatura dentro da faixa segura (2 a 8 °C)
 * LED vermelho = fora da faixa
 *
 * No Wokwi: durante a simulação, clique no DHT22 para alterar a temperatura.
 * A cada 20 s é publicada uma leitura, com uma pequena variação aleatória somada ao sensor.
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include "DHTesp.h"

// ---------- Rede ----------
// Wokwi: rede "Wokwi-GUEST" sem senha. Placa física: troque pela sua rede.
const char* WIFI_SSID  = "Wokwi-GUEST";
const char* WIFI_SENHA = "";

// ---------- MQTT ----------
// O ESP32 do Wokwi publica no broker público; o Mosquitto do projeto
// busca essas mensagens por meio da ponte (ver infra/mosquitto.conf).
// Placa física na mesma rede do PC: use o IP do PC e a porta 1884 e
// troque TOPICO para "vacinasegura/ubs/ubs01/geladeira/g01".
const char* MQTT_HOST  = "broker.hivemq.com";
const int   MQTT_PORTA = 1883;
const char* TOPICO     = "vacinasegura/35kr1sud/ubs/ubs01/geladeira/g01";

// ---------- Hardware ----------
const int PINO_DHT    = 15;
const int PINO_LED_OK = 2;
const int PINO_LED_ALERTA = 4;

const float TEMP_MIN = 2.0;
const float TEMP_MAX = 8.0;
const unsigned long INTERVALO_MS = 20000;  // uma leitura a cada 20 s

// Variacao aleatoria somada a leitura do sensor, para a simulacao nao ficar
// com valor fixo. Passeio aleatorio limitado: muda um pouco a cada leitura.
const float VARIACAO_MAX_TEMP = 1.5;   // +/- graus Celsius
const float VARIACAO_MAX_UMID = 6.0;   // +/- pontos percentuais
float desvioTemp = 0;
float desvioUmid = 0;

float passoAleatorio(float atual, float passo, float limite) {
  float novo = atual + (random(-100, 101) / 100.0) * passo;
  return constrain(novo, -limite, limite);
}

DHTesp dht;
WiFiClient wifi;
PubSubClient mqtt(wifi);
unsigned long ultimaLeitura = 0;

void conectarWifi() {
  Serial.print("Conectando ao Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_SENHA, 6);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(" conectado!");
}

void conectarMqtt() {
  while (!mqtt.connected()) {
    String clientId = "vacinasegura-esp32-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.print("Conectando ao broker MQTT... ");
    if (mqtt.connect(clientId.c_str())) {
      Serial.println("ok");
    } else {
      Serial.printf("falhou (estado %d), nova tentativa em 2 s\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_LED_OK, OUTPUT);
  pinMode(PINO_LED_ALERTA, OUTPUT);
  dht.setup(PINO_DHT, DHTesp::DHT22);

  conectarWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  conectarMqtt();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWifi();
  if (!mqtt.connected()) conectarMqtt();
  mqtt.loop();

  if (millis() - ultimaLeitura < INTERVALO_MS) return;
  ultimaLeitura = millis();

  TempAndHumidity leitura = dht.getTempAndHumidity();
  if (dht.getStatus() != DHTesp::ERROR_NONE) {
    Serial.printf("Erro no sensor: %s\n", dht.getStatusString());
    return;
  }

  desvioTemp = passoAleatorio(desvioTemp, 0.4, VARIACAO_MAX_TEMP);
  desvioUmid = passoAleatorio(desvioUmid, 1.5, VARIACAO_MAX_UMID);
  float temperatura = leitura.temperature + desvioTemp;
  float umidade = constrain(leitura.humidity + desvioUmid, 0.0f, 100.0f);

  bool dentroDaFaixa = temperatura >= TEMP_MIN && temperatura <= TEMP_MAX;
  digitalWrite(PINO_LED_OK, dentroDaFaixa ? HIGH : LOW);
  digitalWrite(PINO_LED_ALERTA, dentroDaFaixa ? LOW : HIGH);

  char payload[80];
  snprintf(payload, sizeof(payload), "{\"temperatura\":%.2f,\"umidade\":%.1f}",
           temperatura, umidade);
  mqtt.publish(TOPICO, payload);
  Serial.printf("Publicado: %s %s\n", payload, dentroDaFaixa ? "" : "<- FORA DA FAIXA");
}
