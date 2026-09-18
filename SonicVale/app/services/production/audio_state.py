"""A file's existence, input applicability and user selection are distinct facts."""
import os
from app.models.po import ChapterPO
from app.services.audio_selection import selected_audio_path, audio_items


def generation_state(db,line):
    path=selected_audio_path(line)
    has_audio=bool(path and os.path.isfile(path))
    versions=audio_items(line.audio_versions)
    version_id=line.active_audio_version_id
    variant=next((v for v in audio_items(line.audio_variants) if v.get('id')==line.active_audio_variant_id),None)
    if variant:version_id=variant.get('source_audio_version_id') or version_id
    selected=next((v for v in versions if v.get('id')==version_id),None)
    fingerprint=(selected or {}).get('input_fingerprint')
    applicable=None
    if fingerprint:
        from app.services.speech.request import prepare_request
        chapter=db.get(ChapterPO,line.chapter_id)
        try:
            _,_,current=prepare_request(db,chapter.project_id,line.id)
            applicable=fingerprint==current
        except ValueError:
            applicable=False
    # Legacy files keep existing compatibility state; their provenance is unknown.
    ready=has_audio and (applicable if applicable is not None else line.status=='done' and line.is_done==1)
    return {'has_audio':has_audio,'input_current':applicable,'needs_generation':not ready,
            'selected_version_id':version_id,'selected_variant_id':line.active_audio_variant_id}
