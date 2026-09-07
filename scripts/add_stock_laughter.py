#!/usr/bin/env python3
"""Import two CC0 Freesound public HQ previews; no account or cloning required."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'assets/audio/cc0'
SOUNDS = [
    ('female-short-laugh', '女声短笑 · 单人', 'OwlStorm / Ashe Kirk', 'https://freesound.org/people/OwlStorm/sounds/151223/', 'https://cdn.freesound.org/previews/151/151223_140737-hq.mp3', ['笑声', '女声', '单人', '短促']),
    ('crowd-laugh', '群体笑声 · 剧场反应', 'kikorurelas', 'https://freesound.org/people/kikorurelas/sounds/767470/', 'https://cdn.freesound.org/previews/767/767470_6252416-hq.mp3', ['笑声', '人群', '观众', '背景反应']),
]

def main():
    catalog = json.loads((ROOT / 'catalog.json').read_text())
    group = next(g for g in catalog['groups'] if g['id'] == 'human')
    group.setdefault('items', [])
    (ROOT / 'laughter').mkdir(exist_ok=True)
    sums = (ROOT / 'SHA256SUMS').read_text()
    for key, title, author, page, url, tags in SOUNDS:
        relative = f'laughter/{key}.mp3'
        target = ROOT / relative
        if not target.exists():
            with urllib.request.urlopen(url, timeout=60) as stream:
                data = stream.read(8 * 1024 * 1024)
            target.write_bytes(data)
        catalog['sources'][key] = {'author': author, 'source_url': page, 'download_url': url, 'license': 'CC0-1.0', 'verified_at': '2026-09-07', 'processing': 'Public HQ MP3 preview, complete preview, original bytes unchanged; source recording is CC0'}
        if not any(i['file'] == relative for i in group['items']):
            group['items'].append({'file': relative, 'title': title, 'source': key, 'tags': tags})
        if relative not in sums:
            sums += f'{hashlib.sha256(target.read_bytes()).hexdigest()}  {relative}\n'
        print(title, target.stat().st_size, flush=True)
    (ROOT / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'SHA256SUMS').write_text(sums)

if __name__ == '__main__':
    main()
