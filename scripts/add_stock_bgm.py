#!/usr/bin/env python3
"""Import four CC0 music selections. Sources verified 2026-09-07; never overwrite audio."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / 'assets/audio/cc0'
TRACKS = [
    ('ghost-piano', '暗室疑云 · 悬疑钢琴', 'KiluaBoy', 'dark-environment-horror-games', 'GoshtPiano2.ogg', ['背景音乐', '悬疑', '神秘', '钢琴', '夜晚']),
    ('emotional-piano', '旧事回忆 · 情绪钢琴', 'Centurion_of_war', 'emotional-piano-0', 'emotional_piano_solo_0.ogg', ['背景音乐', '回忆', '悲伤', '钢琴', '缓慢']),
    ('vaporware', '微光日常 · 平静钢琴', 'The Cynic Project / cynicmusic', 'calm-piano-1-vaporware', '003_Vaporware_2.mp3', ['背景音乐', '平静', '温暖', '钢琴', '都市']),
    ('opening-theme', '悬念开场 · 管弦片头', 'nene', 'opening-theme-actionsuspense', 'opening_theme.wav', ['背景音乐', '悬疑', '片头', '管弦', '紧张']),
]

def main():
    (STOCK / 'bgm').mkdir(exist_ok=True)
    catalog = json.loads((STOCK / 'catalog.json').read_text())
    group = next((g for g in catalog['groups'] if g['id'] == 'bgm'), None)
    if group is None:
        group = {'id': 'bgm', 'items': []}
        catalog['groups'].append(group)
    for key, title, author, page, file, tags in TRACKS:
        target = STOCK / 'bgm' / f'{key}.mp3'
        url = 'https://opengameart.org/sites/default/files/' + file
        if not target.exists():
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / file
                urllib.request.urlretrieve(url, source)
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-ar', '44100', '-ac', '2', '-b:a', '160k', str(target)], check=True)
        catalog['sources']['bgm_' + key] = {'author': author, 'source_url': 'https://opengameart.org/content/' + page, 'download_url': url, 'license': 'CC0-1.0', 'verified_at': '2026-09-07', 'processing': 'Full track encoded MP3 160 kbps, 44.1 kHz stereo; no crop'}
        if not any(i['file'] == f'bgm/{key}.mp3' for i in group['items']):
            group['items'].append({'file': f'bgm/{key}.mp3', 'title': title, 'source': 'bgm_' + key, 'tags': tags})
        print(title, target.stat().st_size, flush=True)
    (STOCK / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    sums = STOCK / 'SHA256SUMS'
    previous = sums.read_text() if sums.exists() else ''
    for key, *_ in TRACKS:
        relative = f'bgm/{key}.mp3'
        if relative not in previous:
            previous += f'{hashlib.sha256((STOCK / relative).read_bytes()).hexdigest()}  {relative}\n'
    sums.write_text(previous)

if __name__ == '__main__':
    main()
