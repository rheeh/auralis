export const sceneImages = [
  { id: 'rain', lineId: '01', anchorText: '晚上十一点十七分，林澈的公寓。', title: '雨夜公寓', caption: '23:17 · 雨声遮住了楼道的动静', file: 'rain-apartment.png' },
  { id: 'envelope', lineId: '04', anchorText: '等一下。封口，三个蓝点。三年前那封，也是。', title: '匿名信封', caption: '三个蓝点 · 三年前的来信再次出现', file: 'anonymous-envelope.png' },
  { id: 'phone', lineId: '08', anchorText: '信封里……有手机？', title: '门外来客', caption: '灯灭之后 · 电话与门外传来同样的节奏', file: 'phone-and-door.png' },
]

export function sceneAtTime(scenes, seconds) {
  return [...scenes].filter(scene => Number.isFinite(scene.start) && scene.start <= seconds)
    .sort((a, b) => b.start - a.start)[0] || scenes[0] || null
}

export function demoSceneSchedule(clips) {
  return sceneImages.map((scene, index) => ({ ...scene, start: index === 0 ? 0 : clips.find(clip => clip.kind === 'voice' && clip.id === scene.lineId)?.start ?? Infinity }))
}

export function nativeSceneSchedule(tracks) {
  const clips = tracks.flatMap(track => track.clips || [])
  if (!clips.some(clip => clip.line?.text_content === sceneImages[0].anchorText)) return []
  return sceneImages.map((scene, index) => ({ ...scene, start: index === 0 ? 0 : (clips.find(clip => clip.line?.text_content === scene.anchorText)?.start_ms ?? Infinity) / 1000 }))
}
