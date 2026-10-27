#!/usr/bin/env python3
import os
import struct
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

HEADER_FMT = "!BBBBBB"
HEADER_LEN = 6
MAGIC_VOICE = 0xC2
MAGIC_TEXT = 0x74
MODE_1200 = 0x01
MODE_700C = 0x02
FLAG_EOT = 0x80
MTU_900MHZ = 180
MTU_433MHZ = 96

def crc8_maxim(data: bytes) -> int:
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def chunk_payload(payload: bytes, band_mhz: int = 900, is_voice: bool = True, codec_mode: int = MODE_1200, stream_id: Optional[int] = None) -> List[bytes]:
    if stream_id is None:
        stream_id = int(time.time() * 10) & 0xFF
    max_body = MTU_900MHZ if band_mhz >= 868 else MTU_433MHZ
    magic = MAGIC_VOICE if is_voice else MAGIC_TEXT
    if not payload:
        return []
    slices = [payload[i : i + max_body] for i in range(0, len(payload), max_body)]
    total = min(len(slices), 255)
    packets: List[bytes] = []
    for seq, body in enumerate(slices[:total]):
        flags = (codec_mode & 0x0F) | (FLAG_EOT if seq == total - 1 else 0)
        hdr = struct.pack(HEADER_FMT, magic, stream_id, seq, total, flags, crc8_maxim(body))
        packets.append(hdr + body)
    return packets

@dataclass
class StreamBuffer:
    stream_id: int
    total: int
    is_voice: bool
    codec_mode: int
    created_at: float = field(default_factory=time.monotonic)
    chunks: Dict[int, bytes] = field(default_factory=dict)

    def is_complete(self) -> bool:
        return len(self.chunks) >= self.total

    def reassemble(self) -> bytes:
        pad = b"\x00" * (6 if self.codec_mode == MODE_1200 else 7)
        return b"".join(self.chunks.get(i, pad) for i in range(self.total))

class ChunkReassembler:
    def __init__(self, timeout_sec: float = 12.0):
        self.timeout_sec = timeout_sec
        self.streams: Dict[int, StreamBuffer] = {}

    def push_frame(self, frame: bytes) -> Optional[Tuple[bool, int, bytes]]:
        if len(frame) <= HEADER_LEN:
            return None
        magic, sid, seq, total, flags, expected_crc = struct.unpack(HEADER_FMT, frame[:HEADER_LEN])
        body = frame[HEADER_LEN:]
        if magic not in (MAGIC_VOICE, MAGIC_TEXT) or crc8_maxim(body) != expected_crc:
            return None
        if sid not in self.streams:
            self.streams[sid] = StreamBuffer(sid, max(total, 1), magic == MAGIC_VOICE, flags & 0x0F)
        buf = self.streams[sid]
        buf.chunks[seq] = body
        if buf.is_complete():
            return (buf.is_voice, sid, self.streams.pop(sid).reassemble())
        return None
