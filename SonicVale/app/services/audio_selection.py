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


def resolve_selected_audio(line, *, original=False):
    """Resolve the actual file and its provenance together, including fallback.

    Preserve selection order: processed -> selected take -> legacy path. Never
    invent a source ID from a missing processed file or from a list position.
    """
    def normalise(raw):
        return os.path.abspath(os.path.expanduser(raw)) if raw else ''
    def available(item):
        path=normalise((item or {}).get('audio_path'))
        return path if path and os.path.isfile(path) else ''
    versions=audio_items(getattr(line,'audio_versions',None))
    variants=audio_items(getattr(line,'audio_variants',None))
    fallback=None
    def result(path, version=None, variant=None):
        source=variant.get('source_audio_version_id') if variant else (version or {}).get('id')
        return {'path':path, 'available':bool(path and os.path.isfile(path)),
                'version_id':source, 'variant_id':(variant or {}).get('id'),
                'source_version_id':source, 'fallback_reason':fallback}
    variant_id=getattr(line,'active_audio_variant_id',None)
    if not original and variant_id:
        variant=next((item for item in variants if item.get('id')==variant_id),None)
        if path:=available(variant):return result(path,variant=variant)
        fallback='selected_variant_missing'
    version_id=getattr(line,'active_audio_version_id',None)
    version=next((item for item in versions if item.get('id')==version_id),None)
    if path:=available(version):return result(path,version=version)
    if version_id:fallback=fallback or 'selected_version_missing'
    path=normalise(getattr(line,'audio_path',None))
    if path and os.path.isfile(path):
        # A canonical legacy pointer may point at another take after loss of a
        # selected file. Only use metadata belonging to this exact file.
        matches=[item for item in versions if normalise(item.get('audio_path'))==path]
        if len(matches)==1:return result(path,version=matches[0])
        processed=[item for item in variants if normalise(item.get('audio_path'))==path]
        if len(processed)==1 and not matches:return result(path,variant=processed[0])
        fallback=fallback or ('ambiguous_source' if matches or processed else 'legacy_source_unknown')
        return result(path)
    fallback='audio_file_missing'
    return result(path)


def selected_audio_path(line, *, original=False):
    return resolve_selected_audio(line,original=original)['path']
