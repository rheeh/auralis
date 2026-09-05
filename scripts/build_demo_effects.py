#!/usr/bin/env python3
"""Package licensed effects and original Foley synthesis for the browser demo."""
import array
import json
import math
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'sonicvale-front/public/demo-night/sfx'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / 'assets/audio/cc0/catalog.json').read_text())
    records = []
    for name, label, source, path, duration in [
        ('rain', '雨敲窗', 'rain_window', 'supplemental/ambience_rain_window.wav', 16),
        ('doorbell', '门铃', 'doorbell', 'supplemental/foley_doorbell.ogg', 2.4),
        ('paper', '纸张翻动', 'book_flip', 'supplemental/foley_page_turn_01.wav', 1.5),
        ('steps', '木地板脚步', 'rubberduck_sfx100_v2', 'rubberduck-sfx100-v2/sfx100v2_footstep_wood_01.ogg', 1),
        ('clock', '钟表滴答', 'clock_tick', 'supplemental/foley_clock_tick.ogg', 4),
    ]:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(ROOT / 'assets/audio/cc0' / path),
                        '-t', str(duration), '-ar', '44100', '-ac', '1', '-af', 'loudnorm=I=-18:TP=-2:LRA=7',
                        '-b:a', '128k', str(OUT / f'{name}.mp3')], check=True)
        records.append({'id': name, 'label': label, 'file': f'sfx/{name}.mp3', **catalog['sources'][source]})
    # Original, deterministic signals: same three knocks appear first in the call, then at the door.
    sample_rate = 44100
    for name, label, seconds in [('knock', '敲门 · 一慢两快', 2.6), ('vibration', '手机振动', 1.8)]:
        frames = array.array('h')
        for i in range(round(seconds * sample_rate)):
            t = i / sample_rate
            value = 0
            if name == 'knock':
                for onset in (0.05, 1.25, 1.62):
                    d = t - onset
                    if 0 <= d < 0.38:
                        value += 0.65 * math.exp(-d * 25) * (math.sin(2 * math.pi * 160 * d) + 0.3 * math.sin(2 * math.pi * 431 * d))
            else:
                for onset in (0.08, 0.75):
                    d = t - onset
                    if 0 <= d < 0.45:
                        envelope = min(1, d * 70, (0.45 - d) * 70)
                        value += 0.28 * envelope * (math.sin(2 * math.pi * 135 * d) + 0.35 * math.sin(2 * math.pi * 270 * d))
            frames.append(round(max(-0.95, min(0.95, value)) * 32767))
        with wave.open(str(OUT / f'{name}.wav'), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(frames.tobytes())
        records.append({'id': name, 'label': label, 'file': f'sfx/{name}.wav', 'author': 'Auralis',
                        'license': 'CC0-1.0', 'source': 'Original procedural Foley, scripts/build_demo_effects.py'})
    (OUT / 'credits.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    print(f'Prepared {len(records)} effects and credits in {OUT}')


if __name__ == '__main__':
    main()
