"""Local tag matching. This module never constructs an LLM/provider client."""
from app.core.sound_tags import VOCABULARY, normalize_tags, infer_tags, rank_assets
from app.models.po import LinePO
from app.services.sound_library_service import SoundLibraryService

class SoundTagService:
    def __init__(self,db,library=None):
        self.db=db
        self.library=library or SoundLibraryService(db)

    def match(self,dto):
        line=self.db.get(LinePO,dto.line_id)
        if not line or line.chapter_id!=dto.chapter_id:
            raise ValueError('请选择当前章节中的音效或台词')
        stored=getattr(line,'sound_tags',None)
        tags=normalize_tags(dto.tags if dto.tags is not None else stored) if dto.tags is not None or stored is not None else infer_tags(line.sound_prompt or line.text_content)
        assets=self.library.list_assets()
        matches=rank_assets(assets,tags,dto.limit)
        return {'tags':tags,'tag_source':'custom' if dto.tags is not None else 'script' if stored is not None else 'local',
                'available_tags':list(VOCABULARY),'matches':matches,
                'missing_tags':[tag for tag in tags if not any(tag in a['matched_tags'] for a in matches)],
                'candidate_count':len(assets)}
