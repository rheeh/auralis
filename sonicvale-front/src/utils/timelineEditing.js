export const MAX_TIMELINE_MS = 4 * 60 * 60 * 1000
export const isMaterialClip = clip => ['bgm', 'sfx'].includes(clip.track_type)
export const durationLimit = clip => isMaterialClip(clip) ? MAX_TIMELINE_MS : Number(clip.asset?.duration_ms || clip.source_duration_ms || clip.duration_ms || 1)
const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

// Compare both moving edges with actual clip edges, measured in screen pixels.
export function dragClip(origin, mode, delta, clips = [], snap = true, tolerance = 100) {
  const start = Number(origin.start_ms), duration = Number(origin.duration_ms)
  const anchors = [0, ...clips.filter(c => c.id !== origin.id).flatMap(c => [Number(c.start_ms), Number(c.start_ms) + Number(c.duration_ms)])]
  const raw = mode === 'resize-right' ? start + duration + delta : start + delta
  const edges = mode === 'move' ? [raw, raw + duration] : [raw]
  let correction = 0, distance = Infinity, guide = null
  if (snap) {
    for (const edge of edges) for (const anchor of anchors) {
      if (Math.abs(anchor - edge) <= tolerance && Math.abs(anchor - edge) < distance) {
        correction = anchor - edge; distance = Math.abs(correction); guide = anchor
      }
    }
  }
  const position = guide === null && snap ? Math.round(raw / 100) * 100 : raw + correction
  const limit = durationLimit(origin), minimum = Math.min(100, limit)
  let nextStart = start, nextDuration = duration
  if (mode === 'move') nextStart = clamp(position, 0, MAX_TIMELINE_MS - duration)
  else if (mode === 'resize-right') nextDuration = clamp(position - start, minimum, Math.min(limit, MAX_TIMELINE_MS - start))
  else {
    const end = start + duration
    nextStart = clamp(position, Math.max(0, end - limit), end - minimum)
    nextDuration = end - nextStart
  }
  const fadeIn = Math.min(Number(origin.fade_in_ms || 0), nextDuration)
  return { start_ms: Math.round(nextStart), duration_ms: Math.round(nextDuration), fade_in_ms: fadeIn,
    fade_out_ms: Math.min(Number(origin.fade_out_ms || 0), nextDuration - fadeIn),
    guide: [nextStart, nextStart + nextDuration].includes(guide) ? guide : null }
}

export function alignClip(clip, reference, mode) {
  const end = Number(reference.start_ms) + Number(reference.duration_ms)
  const duration = mode === 'span' ? Number(reference.duration_ms) : Number(clip.duration_ms)
  const start = mode === 'end' ? end - duration : mode === 'after' ? end : Number(reference.start_ms)
  if (start < 0) throw new Error('终点对齐会使片段超出时间线起点，请先缩短片段')
  if (duration > durationLimit(clip) || start + duration > MAX_TIMELINE_MS) throw new Error('片段长度超出允许范围')
  const fadeIn = Math.min(Number(clip.fade_in_ms || 0), duration)
  return { start_ms: start, duration_ms: duration, fade_in_ms: fadeIn, fade_out_ms: Math.min(Number(clip.fade_out_ms || 0), duration - fadeIn) }
}

export function packClipLanes(clips) {
  const ends = [], lanes = {}
  for (const clip of [...clips].sort((a,b) => a.start_ms - b.start_ms || a.id - b.id)) {
    let lane = ends.findIndex(end => end <= clip.start_ms)
    if (lane < 0) lane = ends.length
    ends[lane] = clip.start_ms + clip.duration_ms
    lanes[clip.id] = lane
  }
  return {lanes, count: Math.max(1, ends.length)}
}
