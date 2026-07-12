import { createProject, fetchProjects, importChapters } from './project'
import { createTTSProvider, fetchLLMProviders, fetchTTSProviders } from './provider'

export const SETUP_STATUS = {
  NOT_STARTED: 'not_started',
  LLM_MISSING: 'llm_missing',
  TTS_MISSING: 'tts_missing',
  STORAGE_MISSING: 'storage_missing',
  READY: 'ready',
  SKIPPED: 'skipped',
}

export const SETUP_STORAGE_KEY = 'auralis_setup_default_storage'
export const SETUP_SKIPPED_KEY = 'auralis_setup_skipped'

export function getDefaultStoragePath() {
  return localStorage.getItem(SETUP_STORAGE_KEY) || ''
}

export function setDefaultStoragePath(path) {
  const value = String(path || '').trim()
  if (value) {
    localStorage.setItem(SETUP_STORAGE_KEY, value)
  } else {
    localStorage.removeItem(SETUP_STORAGE_KEY)
  }
}

export function markSetupSkipped(skipped = true) {
  if (skipped) localStorage.setItem(SETUP_SKIPPED_KEY, '1')
  else localStorage.removeItem(SETUP_SKIPPED_KEY)
}

export async function fetchSetupSnapshot() {
  const [projects, llmProviders, ttsProviders] = await Promise.all([
    fetchProjects().catch(() => []),
    fetchLLMProviders().catch(() => []),
    fetchTTSProviders().catch(() => []),
  ])

  const activeLLMProviders = Array.isArray(llmProviders)
    ? llmProviders.filter((item) => item.status !== 0)
    : []
  const activeTTSProviders = Array.isArray(ttsProviders)
    ? ttsProviders.filter((item) => item.status !== 0)
    : []
  const defaultStoragePath = getDefaultStoragePath()
  const skipped = localStorage.getItem(SETUP_SKIPPED_KEY) === '1'

  let status = SETUP_STATUS.READY
  if (!activeLLMProviders.length) status = SETUP_STATUS.LLM_MISSING
  else if (!activeTTSProviders.length) status = SETUP_STATUS.TTS_MISSING
  else if (!defaultStoragePath) status = SETUP_STATUS.STORAGE_MISSING
  else if (!projects.length && !skipped) status = SETUP_STATUS.NOT_STARTED
  if (skipped && status !== SETUP_STATUS.READY) status = SETUP_STATUS.SKIPPED

  return {
    status,
    skipped,
    projects,
    llmProviders: Array.isArray(llmProviders) ? llmProviders : [],
    ttsProviders: Array.isArray(ttsProviders) ? ttsProviders : [],
    activeLLMProviders,
    activeTTSProviders,
    defaultStoragePath,
  }
}

export async function ensureEdgeTTSProvider() {
  const providers = await fetchTTSProviders().catch(() => [])
  const activeEdge = Array.isArray(providers)
    ? providers.find((item) => item.status !== 0 && item.provider_type === 'edge')
    : null
  if (activeEdge) return activeEdge

  const response = await createTTSProvider({
    name: `Edge-TTS 免费配音 ${Date.now()}`,
    provider_type: 'edge',
    api_base_url: '',
    api_key: '',
    model: '',
    custom_params: '{}',
    status: 1,
  })
  if (response?.code !== 200) throw new Error(response?.message || '创建 Edge-TTS 失败')
  return response.data
}

export async function createDemoProject() {
  const edgeProvider = await ensureEdgeTTSProvider()
  const projectName = `Auralis Demo ${new Date().toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).replace(/[/:]/g, '-')}`
  const response = await createProject({
    name: projectName,
    description: '轻量 Demo 工程：用 Edge-TTS 跑通章节、台本检查和配音流程。',
    tts_provider_id: edgeProvider.id,
    llm_provider_id: null,
    llm_model: null,
    prompt_id: null,
    is_precise_fill: 0,
    project_root_path: getDefaultStoragePath() || null,
  })
  if (response?.code !== 200) throw new Error(response?.message || '创建 Demo 工程失败')

  const project = response.data
  const demoContent = [
    '第一章 茶店夜谈',
    '雨声把老街压得很低。林舟推开茶店的门，看见吧台后那盏灯还亮着。',
    '“别敲了。”柜台后的人说，“再敲，整条街都知道我们在这里。”',
    '林舟停在门口，把湿透的信封放到桌上。远处传来一声闷雷，像有什么东西正从城市背面醒来。',
  ].join('\n')

  try {
    await importChapters(project.id, { content: demoContent })
  } catch {
    // Demo 章节导入失败时仍保留项目，用户可以在工作台继续粘贴正文。
  }

  return project
}
