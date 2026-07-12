import hashlib
import math
import os
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

from app.dto.line_dto import LineAudioVariantDTO
from app.services.line_service import LineService


class FakeLineRepository:
    def __init__(self, line):
        self.line = line

    def get_by_id(self, line_id):
        return self.line if line_id == self.line.id else None

    def update(self, line_id, values):
        for key, value in values.items():
            setattr(self.line, key, value)
        return self.line


class AudioVariantTest(unittest.TestCase):
    def test_two_speeds_create_independent_files_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "line.wav")
            sample_rate = 16000
            with wave.open(source, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(sample_rate)
                frames = [struct.pack("<h", int(9000 * math.sin(2 * math.pi * 220 * i / sample_rate))) for i in range(sample_rate)]
                audio.writeframes(b"".join(frames))

            original_hash = hashlib.sha256(Path(source).read_bytes()).hexdigest()
            line = SimpleNamespace(id=7, audio_path=source, audio_variants=[])
            service = LineService(FakeLineRepository(line), None, None, None)
            slow = service.create_audio_variant(7, LineAudioVariantDTO(speed=0.8, volume=1.0))
            fast = service.create_audio_variant(7, LineAudioVariantDTO(speed=1.25, volume=1.0))

            self.assertNotEqual(slow["id"], fast["id"])
            self.assertTrue(os.path.isfile(slow["audio_path"]))
            self.assertTrue(os.path.isfile(fast["audio_path"]))
            self.assertEqual(hashlib.sha256(Path(source).read_bytes()).hexdigest(), original_hash)
            with wave.open(slow["audio_path"], "rb") as audio:
                slow_duration = audio.getnframes() / audio.getframerate()
            with wave.open(fast["audio_path"], "rb") as audio:
                fast_duration = audio.getnframes() / audio.getframerate()
            self.assertGreater(slow_duration, fast_duration)
            self.assertEqual(len(line.audio_variants), 2)

            self.assertTrue(service.delete_audio_variant(7, slow["id"]))
            self.assertFalse(os.path.exists(slow["audio_path"]))
            self.assertEqual([item["id"] for item in line.audio_variants], [fast["id"]])


if __name__ == "__main__":
    unittest.main()
