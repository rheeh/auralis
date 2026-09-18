"""Per-tool validated inputs, independent of model-generated tool selection."""
from typing import Literal
from pydantic import BaseModel, Field

class Empty(BaseModel):
    model_config={'extra':'forbid'}
class LineSelector(Empty):
    line_id:int|None=Field(default=None,gt=0)
    line_order:int|None=Field(default=None,gt=0)
    scene_title:str|None=None
    speaker:str|None=None
    text_contains:str|None=None
class Inspect(LineSelector):
    status:Literal['pending','processing','done','failed']|None=None
    limit:int=Field(default=20,ge=1,le=30)
class Update(LineSelector):
    text:str|None=Field(default=None,min_length=1,max_length=10000)
    production_note:str|None=Field(default=None,max_length=2000)
class Regenerate(LineSelector):
    prompt:str|None=Field(default=None,max_length=2000)
class BindVoice(Empty):
    role_id:int|None=Field(default=None,gt=0)
    role_name:str|None=None
    voice_id:int|None=Field(default=None,gt=0)
    voice_name:str|None=None
class Revise(Empty):
    instruction:str=Field(min_length=1,max_length=10000)
class Play(LineSelector):
    scope:Literal['all','line']='all'

MODELS={'get_project_status':Empty,'list_roles_and_voices':Empty,'inspect_lines':Inspect,
        'update_line':Update,'regenerate_line_audio':Regenerate,'bind_role_voice':BindVoice,
        'revise_current_draft':Revise,'generate_missing_audio':Empty,'retry_failed_audio':Empty,'play_audio':Play}
WRITE_TOOLS={'update_line','bind_role_voice','revise_current_draft','generate_missing_audio','regenerate_line_audio','retry_failed_audio'}

def validate_arguments(name,arguments):
    return MODELS[name].model_validate(arguments).model_dump(exclude_unset=True)
