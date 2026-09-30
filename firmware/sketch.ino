/*
 * VacinaSegura - firmware do ESP32 (Wokwi ou placa física)
 *
 * Lê a temperatura/umidade da geladeira de vacinas (DHT22) e publica via MQTT.
 * LED verde = temperatura dentro da faixa segura (2 a 8 °C)
 * LED vermelho = fora da faixa
 *
 * A cada 20 s é publicada uma leitura: o valor do sensor somado a uma variação
 * aleatória. Além da oscilação normal, a cada 2 a 4 minutos acontece uma
 * "excursão" que leva a temperatura para FORA da faixa segura, alternando entre
 * acima de 8 °C e abaixo de 2 °C, e depois volta ao normal.
 * (Os valores assumem o DHT22 em 5 °C, o padrão do diagram.json.)
 *
 * No Wokwi: durante a simulação, clique no DHT22 para alterar a temperatura base.
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

// ---------- Aleatoriedade ----------
// Oscilação normal: cada leitura difere da anterior em até +/-1,2 °C e +/-5 %,
// com tendência de voltar ao valor do sensor.
const float PASSO_TEMP = 1.2;
const float PASSO_UMID = 5.0;
const float RETORNO    = 0.6;   // fração do desvio que se mantém de uma leitura para a outra

// Excursões para fora da faixa (garantidas, alternando acima/abaixo)
const int   LEITURAS_ENTRE_EXCURSOES_MIN = 6;   // 6 x 20 s = 2 min
const int   LEITURAS_ENTRE_EXCURSOES_MAX = 12;  // 12 x 20 s = 4 min
const int   DURACAO_EXCURSAO_MIN = 4;           // leituras
const int   DURACAO_EXCURSAO_MAX = 6;

float desvioTemp = 0;
float desvioUmid = 0;
int   leiturasAteExcursao = 0;
int   excursaoRestante = 0;
float alvoExcursao = 0;
bool  proximaParaCima = true;

DHTesp dht;
WiFiClient wifi;
PubSubClient mqtt(wifi);
unsigned long ultimaLeitura = 0;

// Número aleatório entre -1 e +1
float aleatorio() {
  return random(-1000, 1001) / 1000.0;
}

void atualizarDesvios() {
  if (excursaoRestante > 0) {
    // Em excursão: aproxima rapidamente do alvo fora da faixa
    desvioTemp += (alvoExcursao - desvioTemp) * 0.6 + aleatorio() * 0.3;
    desvioUmid = desvioUmid * RETORNO + (alvoExcursao > 0 ? 8.0 : -4.0) + aleatorio() * PASSO_UMID;
    excursaoRestante--;
  } else {
    // Oscilação normal em torno do valor do sensor
    desvioTemp = desvioTemp * RETORNO + aleatorio() * PASSO_TEMP;
    desvioUmid = desvioUmid * RETORNO + aleatorio() * PASSO_UMID;

    if (--leiturasAteExcursao <= 0) {
      // Começa uma nova excursão, alternando o lado
      excursaoRestante = random(DURACAO_EXCURSAO_MIN, DURACAO_EXCURSAO_MAX + 1);
      alvoExcursao = proximaParaCima ? random(450, 651) / 100.0    // ~9,5 a 11,5 °C
                                     : -random(380, 461) / 100.0;  // ~0,4 a 1,2 °C
      proximaParaCima = !proximaParaCima;
      leiturasAteExcursao = random(LEITURAS_ENTRE_EXCURSOES_MIN, LEITURAS_ENTRE_EXCURSOES_MAX + 1);
      Serial.printf(">> Excursao %s da faixa segura\n", alvoExcursao > 0 ? "ACIMA" : "ABAIXO");
    }
  }
  desvioTemp = constrain(desvioTemp, -7.0f, 7.0f);
  desvioUmid = constrain(desvioUmid, -20.0f, 20.0f);
}

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

  randomSeed(esp_random());
  leiturasAteExcursao = random(LEITURAS_ENTRE_EXCURSOES_MIN, LEITURAS_ENTRE_EXCURSOES_MAX + 1);

  conectarWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  conectarMqtt();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWifi();
  if (!mqtt.connected()) conectarMqtt();
  mqtt.loop();

  if (ultimaLeitura != 0 && millis() - ultimaLeitura < INTERVALO_MS) return;
  ultimaLeitura = millis();

  TempAndHumidity leitura = dht.getTempAndHumidity();
  if (dht.getStatus() != DHTesp::ERROR_NONE) {
    Serial.printf("Erro no sensor: %s\n", dht.getStatusString());
    return;
  }

  atualizarDesvios();
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