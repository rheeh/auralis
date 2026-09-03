const projectId = 7
const chapterId = 4
const sessionId = 'sess_57786eca321d46f198d50d479aedd63a'

const sourceText = `早读课的铃声还没响，教室里已经坐了大半的人。林小满踩着点从后门溜进来，把书包往椅子上一扔，整个人瘫在座位上，发出一声长长的叹息。
"你又迟到了。"同桌陈屿头也没抬，手里转着一支中性笔，面前摊着一张数学卷子，空白处画满了火柴人打仗。
"没迟到，铃声不是还没响吗。"林小满从书包里掏出一个塑料袋，里面装着两个包子，热气把袋子内壁糊了一层白雾，"老张今天站在走廊那头，我绕了远路从厕所那边过来的，差点撞上教导主任。"
"教导主任今天抓仪容仪表，你头发扎了吗？"
林小满下意识摸了摸后脑勺，皮筋松松垮垮地套在手腕上，头发散了一半。
"完了，我说怎么一直挡眼睛。"她咬着包子，含含糊糊地说，"你带多余的皮筋没？"
陈屿从笔袋里翻出一根黑色的，递过去。林小满接过来看了一眼，上面还缠着几根棕色的长头发。
"这谁的？"
"我妹的，昨天落我笔袋里了。"
"你妹头发这么长？"
"她留了一年了，说要捐给癌症病人做假发。"陈屿继续画他的火柴人，"你快点吃，老张马上进来了，他上次说谁在教室吃早餐就罚扫一周厕所。"
林小满三两口把第一个包子塞进嘴里，腮帮子鼓得像仓鼠，伸手去够第二个的时候发现袋子已经空了。
"我包子呢？"
"什么？"
"我买了两个肉包，怎么只剩一个了？"
陈屿的笔尖顿了一下，面前的火柴人刚好被画上一把剑。
"可能你记错了吧，或者掉路上了。"`

const project = {
  id: projectId,
  name: 'test4',
  description: '',
  created_at: '2026-07-12T06:22:26.101863',
  updated_at: '2026-07-12T12:50:15.031978',
  llm_model: 'qwen3.6-flash-2026-04-16',
  llm_provider_id: 1,
  tts_provider_id: 1,
  prompt_id: 1,
  is_precise_fill: 0,
  project_root_path: 'Auralis Demo',
  workspace_kind: 'project',
}

const femaleVoiceProfile = '年轻女性声线，音色清亮偏柔，节奏轻快松弛，遇到疑点时音调会不自觉微升'
const maleVoiceProfile = '年轻男性声线，音色偏低沉温润，节奏舒缓平稳，尾音处理柔和且留白'

const roleDrafts = [
  { draft_id: 'r1', name: '林小满', identity: '高中生 / 主角视角人物', personality: ['随性', '迷糊', '直觉敏锐'], relationships: ['与陈屿为同桌，日常互动频繁但隐含微妙张力'], speech_style: '语速偏快且带慵懒感，遇到疑点时音调微升，语气中带有试探与警觉。', voice_type: femaleVoiceProfile, selected: true, default_voice_id: 40, avatar_path: null },
  { draft_id: 'r2', name: '陈屿', identity: '高中生 / 配角悬念源', personality: ['冷静', '专注', '微妙回避型'], relationships: ['与林小满为同桌，表面平静克制，对话中常留有余地与停顿'], speech_style: '语调平稳克制，用词简练，句尾常伴随轻微拖音或短暂停顿。', voice_type: maleVoiceProfile, selected: true, default_voice_id: 5, avatar_path: null },
]

const roles = [
  { id: 19, project_id: projectId, name: '音效', default_voice_id: null, role_importance: 'supporting', tts_route: 'auto', edge_voice: null },
  { id: 20, project_id: projectId, name: '陈屿', default_voice_id: 5, role_importance: 'supporting', tts_route: 'auto', edge_voice: null },
  { id: 21, project_id: projectId, name: '林小满', default_voice_id: 40, role_importance: 'supporting', tts_route: 'auto', edge_voice: null },
]

const completedLineIds = new Set([110, 111, 113, 114, 115, 118, 119, 120, 121, 123, 124, 125, 127])

function dialogue(id, lineOrder, roleId, text, productionNote, options = {}) {
  const done = completedLineIds.has(id)
  return { id, chapter_id: chapterId, scene_title: '教室座位区：错位与疑云', line_order: lineOrder, track: 'voice', line_type: 'dialogue', role_id: roleId, voice_id: null, should_speak: 1, text_content: text, sound_prompt: null, voice_profile: roleId === 20 ? maleVoiceProfile : femaleVoiceProfile, production_note: productionNote, emotion_id: 8, strength_id: options.strengthId || 3, audio_path: done ? `./demo-audio/line-${id}.mp3` : null, status: done ? 'done' : 'pending', is_done: done ? 1 : 0, audio_events: options.audioEvents || [], audio_variants: options.audioVariants || [], active_audio_variant_id: options.activeVariantId || null, audio_versions: null, active_audio_version_id: null }
}

function sfx(id, lineOrder, text, soundPrompt, audioEvents = []) {
  return { id, chapter_id: chapterId, scene_title: '教室座位区：错位与疑云', line_order: lineOrder, track: 'sfx', line_type: 'sfx', role_id: 19, voice_id: null, should_speak: 0, text_content: text, sound_prompt: soundPrompt, voice_profile: null, production_note: '无', emotion_id: null, strength_id: null, audio_path: null, status: 'pending', is_done: 0, audio_events: audioEvents, audio_variants: [], active_audio_variant_id: null, audio_versions: null, active_audio_version_id: null }
}

const lines = [
  sfx(109, 1, '入场动作与环境底噪', '后门推入、书包砸椅、瘫坐叹息与远处预备铃底噪', [
    { timing: '开场', type: 'amb', content: '远处隐约预备铃底噪，零星桌椅挪动与人声低语', volume_db: '-28dB' },
    { timing: '台词后', type: 'sfx', content: '帆布书包砸向木质椅面的重音，伴随布料摩擦声', volume_db: '-15dB' },
  ]),
  dialogue(110, 2, 20, '你又迟到了。', '语速平缓，句尾轻微拖音，保持视线不抬起的状态感。', { audioEvents: [{ timing: '台词前', type: 'sfx', content: '中性笔在指间匀速转动并轻敲卷纸边缘', volume_db: '-22dB' }] }),
  dialogue(111, 3, 21, '没迟到，铃声不是还没响吗。', '语速偏快，带着刚跑完的微喘，语气自然放松。', { audioEvents: [{ timing: '台词前', type: 'sfx', content: '拉链快速拉开，塑料袋被抽出的窸窣声', volume_db: '-20dB' }], audioVariants: [{ id: '1647934c3303', label: '0.8x 局部变速 0.044–0.609s · 1x 音量', speed: 0.8, volume: 1, start_ms: 44, end_ms: 609, current_ms: 1151, region_action: 'speed' }], activeVariantId: '1647934c3303' }),
  dialogue(112, 4, 21, '老张今天站在走廊那头，我绕了远路从厕所那边过来的，差点撞上教导主任。', '气息略紧，强调绕路和差点撞上的细节，语速加快。'),
  dialogue(113, 5, 20, '教导主任今天抓仪容仪表，你头发扎了吗？', '语调平稳，关注点突然转移，句末稍作停顿等待回应。', { audioEvents: [{ timing: '台词前', type: 'sfx', content: '笔尖在纸上用力划下的短促沙沙声', volume_db: '-22dB' }], audioVariants: [{ id: '415524f35dce', label: '1.1x 局部变速 0.111–2.57s · 1x 音量', speed: 1.1, volume: 1, start_ms: 111, end_ms: 2570, current_ms: 4557, region_action: 'speed' }], activeVariantId: '415524f35dce' }),
  dialogue(114, 6, 21, '完了，我说怎么一直挡眼睛。', '音调微升，带着恍然大悟的无奈。', { strengthId: 4 }),
  dialogue(115, 7, 21, '你带多余的皮筋没？', '咬字因嘴里含着食物而略显含糊，语速放缓。', { audioEvents: [{ timing: '全程', type: 'sfx', content: '持续的低频咀嚼与吞咽声', volume_db: '-18dB' }] }),
  sfx(116, 8, '笔袋翻找与传递', '拉链开合，指尖捏取皮筋的细微摩擦，递送物体时的空气流动'),
  dialogue(117, 9, 21, '这谁的？', '语气骤然收紧，音调微升，带有明显的探究意味。'),
  dialogue(118, 10, 20, '我妹的，昨天落我笔袋里了。', '回答干脆，没有任何迟疑，声线保持平稳。'),
  dialogue(119, 11, 21, '你妹头发这么长？', '语速放慢，着重强调长度异常，潜台词带有审视。'),
  dialogue(120, 12, 20, '她留了一年了，说要捐给癌症病人做假发。', '语气平淡如水，仿佛在说明一件再普通不过的事。'),
  dialogue(121, 13, 20, '你快点吃，老张马上进来了，他上次说谁在教室吃早餐就罚扫一周厕所。', '语速略微加快，压低声音制造紧迫感。', { audioEvents: [{ timing: '全程', type: 'bgm', content: '极简低频弦乐或心跳节拍悄然切入，铺底营造潜流感', volume_db: '-28dB' }] }),
  sfx(122, 14, '进食与摸索', '大口咀嚼、快速吞咽、塑料袋被捏扁挤压的窸窣声'),
  dialogue(123, 15, 21, '我包子呢？', '声音陡然拔高，带着难以置信的停顿。'),
  dialogue(124, 16, 20, '什么？', '简短有力，尾音上扬，制造节奏空白。'),
  dialogue(125, 17, 21, '我买了两个肉包，怎么只剩一个了？', '咬字清晰，语气加重，步步紧逼。'),
  sfx(126, 18, '笔尖停滞与重划', '笔尖突然停止摩擦，随即重重压入纸张划下的一道锐利长线', [
    { timing: '开场', type: 'sfx', content: '中性笔尖突然停滞的细微摩擦声', volume_db: '-18dB' },
    { timing: '停顿期间', type: 'sfx', content: '笔尖用力划破纸面的尖锐重音', volume_db: '-12dB' },
  ]),
  dialogue(127, 19, 20, '可能你记错了吧，或者掉路上了。', '语速恢复平稳，但刻意拉长连接词，留出呼吸空隙以掩盖心虚。', { audioEvents: [{ timing: '台词后', type: 'break', content: '短暂静默两秒', volume_db: '-30dB' }] }),
]

const script = {
  title: '早读前的暗流',
  logline: '早读课前，女生林小满匆忙赶到教室与同桌陈屿互动，却在发现皮筋上的长发和丢失的包子后察觉异样。',
  characters: [{ name: '林小满', voiceProfile: femaleVoiceProfile }, { name: '陈屿', voiceProfile: maleVoiceProfile }],
  scenes: [{ title: '教室座位区：错位与疑云', location: '高中教室后排靠窗座位', mood: '日常轻松渐转为微疑与紧绷', lines: lines.map((line) => ({ type: line.line_type, track: line.track, shouldSpeak: line.should_speak !== 0, speaker: roles.find((role) => role.id === line.role_id)?.name || '音效', text: line.text_content, voiceProfile: line.voice_profile || '', soundPrompt: line.sound_prompt || '', productionNote: line.production_note || '', audioEvents: line.audio_events || [] })) }],
}

const audioTasks = lines.filter((line) => line.should_speak !== 0).map((line) => ({ id: `test4-${line.id}`, task_id: `test4-${line.id}`, line_id: line.id, status: completedLineIds.has(line.id) ? 'done' : 'pending', review_status: 'pending' }))
let stage = 'awaiting_role_confirmation'

function snapshot() {
  const hasScript = ['awaiting_script_confirmation', 'script_draft_ready', 'completed'].includes(stage)
  return { session_id: sessionId, project_id: projectId, title: '早读前的暗流', source_text: sourceText, instruction: '旁白克制，优先用对白、音效和音乐推进情节。', created_at: '2026-07-12T06:25:35.152931', updated_at: '2026-07-12T12:50:15.031978', current_stage: stage, status: stage === 'completed' ? 'completed' : 'active', chapter_id: stage === 'completed' ? chapterId : null, draft_revision: 1, pending_confirm: { revision: 1 }, role_drafts: { roles: roleDrafts }, script_draft: hasScript ? script : null, script_review: null, script_revisions: hasScript ? [{ revision: 1, label: '原始生成稿', status: 'approved', script }] : [] }
}

function bodyOf(config) {
  if (!config.data) return {}
  if (typeof config.data === 'string') { try { return JSON.parse(config.data) } catch { return {} } }
  return config.data
}

const ok = (data, message = 'ok') => ({ code: 200, message, data })

export async function handleDemoRequest(config) {
  const method = String(config.method || 'get').toLowerCase()
  const url = String(config.url || '').replace(/^https?:\/\/[^/]+/, '').split('?')[0].replace(/\/$/, '') || '/'
  const body = bodyOf(config)
  await new Promise((resolve) => setTimeout(resolve, method === 'get' ? 70 : 420))

  if (method === 'get' && url === '/projects') return ok([project])
  if (method === 'get' && url === `/projects/${projectId}`) return ok(project)
  if (method === 'get' && url === `/projects/${projectId}/readiness`) return ok({ readiness_score: 84, ready_for_adaptation: true, ready_for_generation: true, ready_for_export: false, ready_for_final_export: false, counts: { chapters: 1, roles: 3, lines: 19, audio_done: 13 } })
  if (method === 'get' && url === '/chat/sessions') return ok([snapshot()])
  if (method === 'get' && url === `/chat/sessions/${sessionId}`) return ok(snapshot())
  if (method === 'get' && url === `/chat/sessions/${sessionId}/history`) return ok([])
  if (method === 'post' && url === `/chat/sessions/${sessionId}/confirm`) {
    if (body.action === 'confirm_roles') stage = 'awaiting_script_confirmation'
    if (body.action === 'confirm_script') stage = 'script_draft_ready'
    return ok(snapshot())
  }
  if (method === 'post' && url === `/chat/sessions/${sessionId}/commit`) { stage = 'completed'; return ok(snapshot()) }
  if (method === 'post' && url === `/chat/sessions/${sessionId}/message`) return ok({ user_message_id: `test4-demo-${Date.now()}` })
  if (method === 'get' && url === '/tts_providers') return ok([{ id: 1, name: 'edge', provider_type: 'edge', model: '', status: 1 }, { id: 2, name: 'aliyun-cosyvoice-instruct', provider_type: 'cloud', model: 'cosyvoice-v3-flash', status: 1 }])
  if (method === 'get' && url === '/llm_providers') return ok([{ id: 1, name: 'aliyun', model_list: '["qwen3.6-flash-2026-04-16"]', status: 1 }])
  if (method === 'get' && url === '/prompts') return ok([{ id: 1, name: '默认拆分台词提示词' }])
  if (method === 'get' && url === '/voices/tts/1') return ok([{ id: 5, name: '少年男声', description: '预设 · Edge-TTS · 男 · 少年 · 活泼', tts_provider_id: 1 }])
  if (method === 'get' && url === '/voices/tts/2') return ok([{ id: 40, name: '元气女声·龙安欢', description: '预置 · CosyVoice-v3 · 女 · 青年', tts_provider_id: 2 }])
  if (method === 'get' && url === `/roles/project/${projectId}`) return ok(roles)
  if (method === 'get' && url === `/lines/lines/${chapterId}`) return ok(lines)
  if (method === 'get' && url === '/emotions') return ok([{ id: 8, name: '平静' }])
  if (method === 'get' && url === '/strengths') return ok([{ id: 3, name: '中等' }, { id: 4, name: '较强' }])
  if (method === 'get' && url === `/chat/sessions/${sessionId}/audio-tasks`) return ok({ total: audioTasks.length, completed: completedLineIds.size, counts: { done: completedLineIds.size, pending: audioTasks.length - completedLineIds.size }, tasks: audioTasks })
  if (method === 'post' && url === `/chat/sessions/${sessionId}/audio-tasks/generate`) return ok({ created: 0 }, 'test4 的现有音频已载入')
  if (method === 'post' && new RegExp(`/chat/sessions/${sessionId}/audio-tasks/lines/\\d+/regenerate`).test(url)) return ok({ queued: true })
  if (method === 'post' && url === `/chapters/add-smart-role-and-voice/${projectId}/${chapterId}`) return ok(true)
  if (method === 'put' && /\/lines\/\d+$/.test(url)) {
    const line = lines.find((item) => url.endsWith(`/${item.id}`))
    if (line) Object.assign(line, body)
    return ok(line)
  }
  return ok(null, `静态 Demo 已忽略 ${method.toUpperCase()} ${url}`)
}

export function resetDemo() { stage = 'awaiting_role_confirmation' }
