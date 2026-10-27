#include <Arduino.h>
#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>

#define AP_SSID "RNS-CROSSBAND-MESH"
#define PI_UART_RX_PIN 16
#define PI_UART_TX_PIN 17
#define VBAT_ADC_PIN   34

static DNSServer dnsServer;
static WebServer server(80);
static char *msg_ring = nullptr;
static String latest_telem = "{\"band\":915,\"r900\":-84,\"snr900\":3.5,\"r433\":-94,\"snr433\":-1.5}";

void setup() {
    Serial.begin(115200);
    Serial2.begin(115200, SERIAL_8N1, PI_UART_RX_PIN, PI_UART_TX_PIN);
    msg_ring = (char *)(psramFound() ? ps_malloc(12288) : malloc(12288));
    WiFi.mode(WIFI_AP);
    WiFi.setTxPower(WIFI_POWER_15dBm);
    IPAddress apIP(192, 168, 4, 1);
    WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
    WiFi.softAP(AP_SSID);
    dnsServer.start(53, "*", apIP);
    server.on("/api/status", HTTP_GET, []() { server.send(200, "application/json", latest_telem); });
    server.on("/api/tx", HTTP_POST, []() {
        Serial2.println("{\"type\":\"tx_msg\",\"user\":\"" + server.arg("user") + "\",\"text\":\"" + server.arg("text") + "\"}");
        server.send(200, "application/json", "{\"ok\":true}");
    });
    server.begin();
}

void loop() {
    dnsServer.processNextRequest();
    server.handleClient();
    if (Serial2.available()) {
        String line = Serial2.readStringUntil('\n');
        if (line.indexOf("telemetry") >= 0) latest_telem = line;
    }
}
