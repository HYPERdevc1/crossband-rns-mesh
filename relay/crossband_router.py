#!/usr/bin/env python3
import argparse
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

try:
    import serial
except ImportError:
    serial = None
try:
    import RNS
except ImportError:
    RNS = None

from codec2_chunker import MODE_700C, MODE_1200, ChunkReassembler, chunk_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("crossband_relay")

@dataclass
class BandMetrics:
    name: str
    freq_mhz: int
    rssi_dbm: float = -95.0
    snr_db: float = 2.0
    tx_bytes: int = 0
    rx_bytes: int = 0
    last_rx_ts: float = 0.0
    snr_history: Deque[float] = field(default_factory=lambda: deque(maxlen=12))

    def record_sample(self, rssi: float, snr: float) -> None:
        self.rssi_dbm, self.snr_db, self.last_rx_ts = rssi, snr, time.time()
        self.snr_history.append(snr)

    @property
    def ewma_snr(self) -> float:
        if not self.snr_history:
            return self.snr_db
        w = range(1, len(self.snr_history) + 1)
        return sum(x * s for x, s in zip(w, self.snr_history)) / sum(w)

class CrossbandCognitiveRelay:
    SNR_900_MIN_DB = -6.5
    SNR_900_RECOVER_DB = -4.0
    STALE_LINK_SEC = 45.0
    LARGE_PAYLOAD_THRESHOLD = 96

    def __init__(self, esp32_port: str = "/dev/ttyAMA0", esp32_baud: int = 115200):
        self.band_900 = BandMetrics("Heltec_900MHz_RNode", 915)
        self.band_433 = BandMetrics("Arduino_433MHz_TNC", 433)
        self.active_band = 915
        self.reassembler = ChunkReassembler()
        self.esp32_port = esp32_port
        self.esp32_baud = esp32_baud
        self._esp_serial = None

    def choose_band(self, payload_len: int, is_voice: bool = False) -> int:
        age_900 = time.time() - self.band_900.last_rx_ts if self.band_900.last_rx_ts else 0.0
        snr_900 = self.band_900.ewma_snr
        thresh = self.SNR_900_MIN_DB if self.active_band == 915 else self.SNR_900_RECOVER_DB
        link_ok = (snr_900 >= thresh) and (self.band_900.last_rx_ts == 0.0 or age_900 < self.STALE_LINK_SEC)
        if not link_ok:
            self.active_band = 433
            return 433
        if is_voice or payload_len >= self.LARGE_PAYLOAD_THRESHOLD:
            self.active_band = 915
            return 915
        if snr_900 < -2.0 and self.band_433.ewma_snr > -11.0:
            return 433
        self.active_band = 915
        return 915

    def dispatch_payload(self, raw_data: bytes, is_voice: bool = False) -> int:
        band = self.choose_band(len(raw_data), is_voice=is_voice)
        mode = MODE_1200 if band == 915 else MODE_700C
        chunks = chunk_payload(raw_data, band_mhz=band, is_voice=is_voice, codec_mode=mode)
        for pkt in chunks:
            if band == 915:
                self.band_900.tx_bytes += len(pkt)
            else:
                self.band_433.tx_bytes += len(pkt)
        log.info("Routed %dB (%d chunks) via %dMHz [SNR900=%.1fdB, SNR433=%.1fdB]", len(raw_data), len(chunks), band, self.band_900.ewma_snr, self.band_433.ewma_snr)
        return band
