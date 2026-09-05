"""One adopted-take selection rule for playback, processing and timeline rendering."""
import json
import os


def audio_items(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return [item for item in (value or []) if isinstance(item, dict)] if isinstance(value, list) else []


def selected_audio_path(line, *, original=False):
    def available(item):
        raw = (item or {}).get("audio_path") or ""
        path = os.path.abspath(os.path.expanduser(raw)) if raw else ""
        return path if path and os.path.isfile(path) else ""

    if not original:
        variant = next((item for item in audio_items(getattr(line, "audio_variants", None))
                        if item.get("id") == getattr(line, "active_audio_variant_id", None)), None)
        if path := available(variant):
            return path
    versions = audio_items(getattr(line, "audio_versions", None))
    version = next((item for item in versions
                    if item.get("id") == getattr(line, "active_audio_version_id", None)), None)
    if path := available(version):
        return path
    raw = getattr(line, "audio_path", None) or ""
    return os.path.abspath(os.path.expanduser(raw)) if raw else ""
