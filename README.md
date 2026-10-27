# crossband-rns-mesh
Off-grid heterogeneous 900MHz/433MHz LoRa relay mesh using Reticulum (rnsd), Raspberry Pi 5 band routing, Codec2 packet chunking, and ESP32-WROVER-B portal
# crossband-rns-mesh

Off-grid heterogeneous crossband LoRa relay mesh built on top of the Reticulum Network Stack (`rnsd`).

The setup pairs a 900MHz Heltec WiFi LoRa 32 V3 node (flashed as an RNode) with a custom 433MHz Arduino Nano + Ai-Thinker Ra-02 (SX1278) KISS TNC, both attached to a Raspberry Pi 5 acting as a cognitive relay. A companion ESP32-WROVER-B module runs a captive Wi-Fi portal (`192.168.4.1`) over UART so phones or laptops can send text messages and inspect real-time link telemetry without installing client apps.

## Why Two Frequency Bands

During campus stairwell and reinforced-concrete hallway tests (Aug-Oct 2026), 900MHz (`SF7 / 250 kHz`) handled bursty traffic well in line-of-sight and light foliage, easily carrying 1200 bps Codec2 voice chunks. Once two concrete floor slabs were in the path, 900MHz SNR dropped below `-8 dB` and Reticulum link proofs timed out.

The 433MHz channel (`SF9 / 125 kHz` on the SX1278 TNC) stayed usable down to `-12 dB` SNR through the same stairwell, at the cost of much higher airtime and smaller safe MTU. The relay script (`relay/crossband_router.py`) watches rolling EWMA SNR and link age on both interfaces:
- Payloads `>= 96 bytes` and Codec2 `1200` bps voice bursts route over **900MHz** whenever 900MHz EWMA SNR is above `-6.5 dB` (with `-4.0 dB` recovery hysteresis so the relay doesn't flap on multipath fades).
- When 900MHz degrades or times out, traffic fails over to the **433MHz** KISS TNC and `relay/codec2_chunker.py` shrinks the chunk MTU from 180B to 96B (`700C` Codec2 mode).

## Hardware Setup

| Component | Role | Interface to Pi 5 | Notes |
| :--- | :--- | :--- | :--- |
| Raspberry Pi 5 (4GB) | `rnsd` transport node + cognitive router | Host | Runs `rnsd` shared instance + `relay/crossband_router.py` |
| Heltec WiFi LoRa 32 V3 (SX1262) | 900MHz (915 MHz) high-rate bearer | USB (`/dev/ttyLoRa900`) | Flashed with RNode firmware (`SF7`, `BW 250kHz`, `20 dBm`) |
| Arduino Nano + Ra-02 (SX1278) | 433.175MHz high-penetration TNC | USB (`/dev/ttyTNC433`) | Custom KISS TNC firmware (`57600 8N1`, `SF9`, `BW 125kHz`) |
| ESP32-WROVER-B | Captive Wi-Fi portal + telemetry UI | UART0/AMA0 (`115200 8N1`) | Uses PSRAM ring buffer for message backlog; AP SSID `RNS-CROSSBAND-MESH` |

### SX1278 (Ra-02) to Arduino Nano Pinout

- `NSS` -> `D10`
- `RESET` -> `D9`
- `DIO0` -> `D2`
- `SCK` -> `D13`, `MISO` -> `D12`, `MOSI` -> `D11`
- `PTT_LED` -> `D4`

### ESP32-WROVER-B to Raspberry Pi 5 UART

- ESP32 `GPIO16 (RX2)` <- Pi 5 `GPIO14 (TXD0, Pin 8)`
- ESP32 `GPIO17 (TX2)` -> Pi 5 `GPIO15 (RXD0, Pin 10)`
- Common `GND` on Pin 6
- Battery divider tap on `GPIO34` (`100k / 22k` resistor divider)

## Running on the Raspberry Pi 5

```bash
sudo cp config/99-lora-mesh.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
python3 -m venv .venv && source .venv/bin/activate
pip install rns pyserial numpy
mkdir -p ~/.reticulum && cp config/reticulum_config ~/.reticulum/config
rnsd --service &
python3 relay/crossband_router.py --esp-port /dev/ttyAMA0
```
