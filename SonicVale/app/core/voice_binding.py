"""Machine voice identifiers; legacy human descriptions are read-only fallback."""
import re

def legacy_voice_keys(description, kind=None):
    prefixes = r'edge_voice' if kind=='edge' else r'cosyvoice_voice|qwen_voice' if kind=='cloud' else r'edge_voice|cosyvoice_voice|qwen_voice'
    return set(re.findall(r'(?:'+prefixes+r')\s*:\s*([^,\s]+)',description or ''))

def resolve_voice_key(voice,kind=None):
    explicit=(getattr(voice,'provider_voice_id',None) or '').strip()
    if explicit:return explicit
    values=legacy_voice_keys(getattr(voice,'description',None),kind)
    if len(values)>1:raise ValueError('历史音色标记存在歧义，请重新绑定明确音色 ID')
    return next(iter(values),None)
