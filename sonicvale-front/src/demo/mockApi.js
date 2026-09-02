const sourceText = `雨已经下了三个小时。林默站在没有亮灯的楼道里，手里攥着一封没有寄出的信。楼下传来脚步声，停在门外。

“你还在等那封信吗？”周岚问。
“她说今晚会回来。”林默没有回头。`

const project = {
  id: 1,
  name: '雨夜来信',
  description: '小说片段改编 · 静态体验项目',
  created_at: '2026-09-02T10:00:00+08:00',
  updated_at: '2026-09-02T10:20:00+08:00',
  llm_model: 'Demo / 已完成解析',
  llm_provider_id: 1,
  tts_provider_id: 1,
  prompt_id: 1,
  project_root_path: 'Auralis Demo',
}

const roles = [
  { id: 1, draft_id: 'role-lin', name: '林默', identity: '等待来信的年轻人', speech_style: '克制、低声，句尾略有迟疑', voice_type: '青年男声', selected: true, default_voice_id: 1 },
  { id: 2, draft_id: 'role-zhou', name: '周岚', identity: '突然到访的旧友', speech_style: '直接、敏锐，语速略快', voice_type: '青年女声', selected: true, default_voice_id: 2 },
  { id: 3, draft_id: 'role-narrator', name: '旁白', identity: '场景叙述', speech_style: '平静、克制，留出环境声空间', voice_type: '中性旁白', selected: true, default_voice_id: 3 },
]

const script = {
  title: '雨夜来信 · 第一场',
  logline: '一封没有寄出的信，让两个等待答案的人在雨夜重新相遇。',
  scenes: [{
    title: '楼道 · 夜 · 内',
    lines: [
      { track: 'sfx', type: 'sfx', speaker: '环境', soundPrompt: '持续雨声，偶尔有远处闷雷，楼道空旷混响。' },
      { track: 'narration', type: 'narration', speaker: '旁白', text: '雨声。', productionNote: '平静，语速稍慢。' },
      { track: 'voice', type: 'dialogue', speaker: '周岚', text: '你还在等那封信吗？', productionNote: '压低声音，试探。' },
      { track: 'voice', type: 'dialogue', speaker: '林默', text: '她说今晚会回来。', productionNote: '克制，停顿后回答。' },
      { track: 'sfx', type: 'sfx', speaker: '环境', soundPrompt: '门外脚步停住，纸张被攥紧的轻响。' },
    ],
  }],
}

const lines = [
  { id: 1, chapter_id: 1, scene_title: '楼道 · 夜 · 内', line_order: 1, track: 'sfx', line_type: 'sfx', role_id: null, should_speak: 0, text_content: '持续雨声，偶尔有远处闷雷。', sound_prompt: '持续雨声，偶尔有远处闷雷，楼道空旷混响。', status: 'done' },
  { id: 2, chapter_id: 1, scene_title: '楼道 · 夜 · 内', line_order: 2, track: 'narration', line_type: 'narration', role_id: 3, should_speak: 1, text_content: '雨声。', emotion_id: 1, strength_id: 1, production_note: '平静，语速稍慢，给雨声留出空间。', status: 'done', audio_versions: [{ id: 'demo-2', label: '版本 1' }], active_audio_version_id: 'demo-2', audio_variants: [] },
  { id: 3, chapter_id: 1, scene_title: '楼道 · 夜 · 内', line_order: 3, track: 'voice', line_type: 'dialogue', role_id: 2, should_speak: 1, text_content: '你还在等那封信吗？', emotion_id: 2, strength_id: 2, production_note: '压低声音，带一点试探。', status: 'done', audio_versions: [{ id: 'demo-3', label: '版本 1' }], active_audio_version_id: 'demo-3', audio_variants: [] },
  { id: 4, chapter_id: 1, scene_title: '楼道 · 夜 · 内', line_order: 4, track: 'voice', line_type: 'dialogue', role_id: 1, should_speak: 1, text_content: '她说今晚会回来。', emotion_id: 3, strength_id: 1, production_note: '克制，短暂停顿后回答。', status: 'done', audio_versions: [{ id: 'demo-4', label: '版本 1' }], active_audio_version_id: 'demo-4', audio_variants: [] },
  { id: 5, chapter_id: 1, scene_title: '楼道 · 夜 · 内', line_order: 5, track: 'sfx', line_type: 'sfx', role_id: null, should_speak: 0, text_content: '门外脚步停住，纸张被攥紧的轻响。', sound_prompt: '脚步停止，纸张轻响。', status: 'done' },
]

let stage = 'awaiting_role_confirmation'

function snapshot() {
  return {
    session_id: 'demo-session',
    project_id: 1,
    title: '雨夜来信',
    source_text: sourceText,
    created_at: '2026-09-02T10:05:00+08:00',
    updated_at: '2026-09-02T10:20:00+08:00',
    current_stage: stage,
    status: stage === 'completed' ? 'completed' : 'active',
    chapter_id: stage === 'completed' ? 1 : null,
    draft_revision: 2,
    pending_confirm: { revision: 2 },
    role_drafts: { roles },
    script_draft: ['awaiting_script_confirmation', 'script_draft_ready', 'completed'].includes(stage) ? script : null,
    script_review: ['awaiting_script_confirmation', 'script_draft_ready', 'completed'].includes(stage)
      ? { passed: true, score: 92, repair_applied: true, summary: '已减少解释性旁白，并补充可直接制作的环境声提示。', issues: [] }
      : null,
    script_revisions: ['awaiting_script_confirmation', 'script_draft_ready', 'completed'].includes(stage)
      ? [{ revision: 1, label: '初稿', status: 'kept', script }, { revision: 2, label: '审查返修稿', status: 'approved', script, review: { passed: true, score: 92 } }]
      : [],
  }
}

function bodyOf(config) {
  if (!config.data) return {}
  if (typeof config.data === 'string') {
    try { return JSON.parse(config.data) } catch { return {} }
  }
  return config.data
}

const ok = (data, message = 'ok') => ({ code: 200, message, data })

export async function handleDemoRequest(config) {
  const method = String(config.method || 'get').toLowerCase()
  const url = String(config.url || '').replace(/^https?:\/\/[^/]+/, '').split('?')[0].replace(/\/$/, '') || '/'
  const body = bodyOf(config)

  await new Promise((resolve) => setTimeout(resolve, method === 'get' ? 70 : 420))

  if (method === 'get' && url === '/projects') return ok([project])
  if (method === 'get' && url === '/projects/1') return ok(project)
  if (method === 'get' && url === '/projects/1/readiness') return ok({ readiness_score: 86, ready_for_adaptation: true, ready_for_generation: true, ready_for_export: true, ready_for_final_export: false, counts: { chapters: 1, roles: 3, lines: 5, audio_done: 3 } })
  if (method === 'get' && url === '/chat/sessions') return ok([snapshot()])
  if (method === 'get' && url === '/chat/sessions/demo-session') return ok(snapshot())
  if (method === 'get' && url === '/chat/sessions/demo-session/history') return ok([])
  if (method === 'post' && url === '/chat/sessions/demo-session/confirm') {
    if (body.action === 'confirm_roles') stage = 'awaiting_script_confirmation'
    if (body.action === 'confirm_script') stage = 'script_draft_ready'
    return ok(snapshot())
  }
  if (method === 'post' && url === '/chat/sessions/demo-session/commit') { stage = 'completed'; return ok(snapshot()) }
  if (method === 'post' && url === '/chat/sessions/demo-session/message') return ok({ user_message_id: `demo-${Date.now()}` })
  if (method === 'get' && url === '/tts_providers') return ok([{ id: 1, name: 'Auralis Demo Voice', model: '预置中文音色', provider_type: 'edge', status: 1 }])
  if (method === 'get' && url === '/llm_providers') return ok([{ id: 1, name: 'Demo LLM', model_list: '["已完成解析"]', status: 1 }])
  if (method === 'get' && url === '/prompts') return ok([{ id: 1, name: '声音优先改编' }])
  if (method === 'get' && url === '/voices/tts/1') return ok([
    { id: 1, name: '云希 · 青年男声', description: '克制、低沉', tts_provider_id: 1 },
    { id: 2, name: '晓伊 · 青年女声', description: '清晰、直接', tts_provider_id: 1 },
    { id: 3, name: '晓晓 · 中性旁白', description: '平静、自然', tts_provider_id: 1 },
  ])
  if (method === 'get' && url === '/roles/project/1') return ok(roles)
  if (method === 'get' && url === '/lines/lines/1') return ok(lines)
  if (method === 'get' && url === '/emotions') return ok([{ id: 1, name: '平静' }, { id: 2, name: '疑惑' }, { id: 3, name: '克制' }])
  if (method === 'get' && url === '/strengths') return ok([{ id: 1, name: '轻' }, { id: 2, name: '中等' }])
  if (method === 'get' && url === '/chat/sessions/demo-session/audio-tasks') return ok({ total: 3, completed: 3, counts: { done: 3 }, tasks: [2, 3, 4].map((lineId) => ({ id: `task-${lineId}`, line_id: lineId, status: 'done' })) })
  if (method === 'post' && url === '/chat/sessions/demo-session/audio-tasks/generate') return ok({ created: 0 }, '演示音频已预置')
  if (method === 'post' && /\/chat\/sessions\/demo-session\/audio-tasks\/lines\/\d+\/regenerate/.test(url)) return ok({ queued: true })
  if (method === 'post' && url === '/chapters/add-smart-role-and-voice/1/1') return ok(true)
  if (method === 'put' && /\/lines\/\d+$/.test(url)) {
    const line = lines.find((item) => url.endsWith(`/${item.id}`))
    if (line) Object.assign(line, body)
    return ok(line)
  }
  return ok(null, `静态 Demo 已忽略 ${method.toUpperCase()} ${url}`)
}

export function resetDemo() { stage = 'awaiting_role_confirmation' }
