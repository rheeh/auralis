from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from app.dto.speech_dto import ProjectSpeechSettings
from app.models.po import ProjectSpeechProfilePO
from app.workflows.drama.performance import ScenePerformancePlan, LinePerformanceCue


def project_performance_brief(db, project):
    row = db.get(ProjectSpeechProfilePO, project.id) if db is not None and getattr(project, 'id', None) else None
    settings = ProjectSpeechSettings.model_validate(row.settings if row else {})
    return {'story_background': settings.story_background or getattr(project, 'description', '') or '',
            'delivery_style': settings.delivery_style,
            'instruction': '背景只用于理解，事实仍以原文为准。共同基调覆盖场景的默认表演风格。'}


def evidence_matches(evidence, source_text, instruction=''):
    evidence = ''.join(str(evidence or '').split())
    return bool(evidence) and any(evidence in ''.join(str(text or '').split()) for text in (source_text, instruction))


def performance_issues(script, source_text, instruction=''):
    issues = []
    for scene in script.get('scenes', []):
        if not scene.get('performancePlan'):
            continue  # historical drafts are not retroactively invalidated
        for index, line in enumerate(scene.get('lines', []), 1):
            cue = line.get('performanceCue') or {}
            if cue.get('turningPoint') and not evidence_matches(cue.get('evidence'), source_text, instruction):
                issues.append({'severity': 'error', 'category': '表演转折依据', 'scene_title': scene.get('title', ''),
                    'line_index': index, 'evidence': f"第 {index} 行转折引用未在原文或用户要求中找到：{cue.get('evidence', '')}",
                    'suggestion': '引用原文或用户要求的直接依据；没有依据时关闭 turningPoint，保持原有表演基调。'})
    return issues


def source_fingerprint(lines, role_names):
    # Audio generation/status/version changes do not invalidate the plan.
    fields = ('text_content', 'role_id', 'line_type', 'track', 'should_speak', 'scene_title',
              'production_note', 'voice_profile', 'emotion_id', 'strength_id')
    values = [{**{key: getattr(line, key, None) for key in fields}, 'id': line.id,
               'speaker': role_names.get(line.role_id, '')} for line in lines]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def bind_scene_performance(scene, lines, role_names, source_text='', instruction=''):
    """Called inside the script commit transaction after line IDs are allocated."""
    if len(scene.get('lines', [])) != len(lines):
        raise ValueError('表演设计与写入台词数量不一致')
    plan = ScenePerformancePlan.model_validate(scene['performancePlan']).model_dump() if scene.get('performancePlan') else None
    cues = {}
    for raw, line in zip(scene.get('lines', []), lines):
        if raw.get('performanceCue'):
            cue = LinePerformanceCue.model_validate(raw['performanceCue']).model_dump()
            reply = cue.get('respondsTo')
            if reply is not None and not 1 <= reply <= len(lines):
                raise ValueError('表演接话对象超出场景范围')
            cue['responds_to_line_id'] = lines[reply - 1].id if reply else None
            cue['turning_point_verified'] = bool(cue['turningPoint'] and evidence_matches(cue['evidence'], source_text, instruction))
            cues[str(line.id)] = cue
    return {'id': uuid4().hex, 'title': scene.get('title') or '未命名场景', 'plan': plan, 'cues': cues,
            'line_ids': [line.id for line in lines], 'source_fingerprint': source_fingerprint(lines, role_names)}


def save_chapter_performances(chapter, scenes, replace=True):
    previous = [] if replace else (chapter.performance_plan or {}).get('scenes', [])
    chapter.performance_plan = {'version': 1, 'scenes': [*previous, *scenes]}


def resolve_scene_performance(chapter, rows, position, role_names):
    """Use stable line IDs; duplicate scene titles cannot leak future context."""
    scenes = (chapter.performance_plan or {}).get('scenes', [])
    owners = {line_id: scene for scene in scenes for line_id in scene.get('line_ids', [])}
    selected = owners.get(rows[position].id)
    start, end = position, position + 1
    title = rows[position].scene_title or ''
    def belongs_to_current_scope(item):
        owner = owners.get(item.id)
        return (item.scene_title or '') == title and (owner is None or owner is selected)
    while start and belongs_to_current_scope(rows[start - 1]):
        start -= 1
    while end < len(rows) and belongs_to_current_scope(rows[end]):
        end += 1
    if not selected or not selected.get('plan'):
        return start, end, {'status': 'missing', 'message': '此场景没有整场表演设计，沿用项目基调和相邻台词。'}, {}
    if source_fingerprint(rows[start:end], role_names) != selected.get('source_fingerprint'):
        return start, end, {'status': 'stale', 'scene_id': selected['id'],
            'message': '台词、角色、顺序或声音指导已改变，旧整场表演设计已停用。可在台本返修时重新生成并审阅。'}, {}
    return start, end, {'status': 'current', 'scene_id': selected['id'], 'plan': selected['plan'],
                       'cue': selected.get('cues', {}).get(str(rows[position].id))}, selected.get('cues', {})
