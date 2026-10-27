#include <SPI.h>
#include <LoRa.h>
#include <avr/wdt.h>

#define FEND  0xC0
#define FESC  0xDB
#define TFEND 0xDC
#define TFESC 0xDD
#define CMD_DATA 0x00
#define CMD_SETHARDWARE 0x06
#define PIN_LORA_SS   10
#define PIN_LORA_RST  9
#define PIN_LORA_DIO0 2
#define PIN_PTT_LED   4
#define LORA_FREQ_HZ  433175000L

static uint8_t kiss_buf[252];
static uint16_t kiss_len = 0;
static bool in_frame = false, escaped = false;

void send_kiss_byte(uint8_t b) {
    if (b == FEND) { Serial.write(FESC); Serial.write(TFEND); }
    else if (b == FESC) { Serial.write(FESC); Serial.write(TFESC); }
    else Serial.write(b);
}

void setup() {
    pinMode(PIN_PTT_LED, OUTPUT);
    Serial.begin(57600);
    LoRa.setPins(PIN_LORA_SS, PIN_LORA_RST, PIN_LORA_DIO0);
    if (!LoRa.begin(LORA_FREQ_HZ)) {
        while (true) { digitalWrite(PIN_PTT_LED, !digitalRead(PIN_PTT_LED)); delay(120); }
    }
    LoRa.setSignalBandwidth(125000L);
    LoRa.setSpreadingFactor(9);
    LoRa.setCodingRate4(6);
    LoRa.setTxPower(17);
    LoRa.enableCrc();
    LoRa.receive();
    wdt_enable(WDTO_4S);
}

void loop() {
    wdt_reset();
    while (Serial.available() > 0) {
        uint8_t b = (uint8_t)Serial.read();
        if (b == FEND) {
            if (in_frame && kiss_len > 1 && (kiss_buf[0] & 0x0F) == CMD_DATA) {
                digitalWrite(PIN_PTT_LED, HIGH);
                if (LoRa.beginPacket()) { LoRa.write(&kiss_buf[1], kiss_len - 1); LoRa.endPacket(false); }
                digitalWrite(PIN_PTT_LED, LOW);
                LoRa.receive();
            }
            in_frame = true; escaped = false; kiss_len = 0; continue;
        }
        if (!in_frame) continue;
        if (b == FESC) { escaped = true; continue; }
        if (escaped) { b = (b == TFEND) ? FEND : (b == TFESC ? FESC : b); escaped = false; }
        if (kiss_len < sizeof(kiss_buf)) kiss_buf[kiss_len++] = b;
    }
    int pktLen = LoRa.parsePacket();
    if (pktLen > 0) {
        Serial.write(FEND); Serial.write(CMD_DATA);
        while (LoRa.available()) send_kiss_byte((uint8_t)LoRa.read());
        Serial.write(FEND);
    }
}
