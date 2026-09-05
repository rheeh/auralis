// A small real Web Audio mixer. The same schedule drives playback and WAV export.
export function makeSchedule(lines, cues, manifest, takes, effects, muted = false) {
  let cursor = 0.7
  const clips = []
  const addEffect = (cue, start) => {
    const asset = effects.find(item => item.id === cue.asset)
    if (!asset?.file || !Number.isFinite(cue.duration) || cue.duration <= 0) return false
    clips.push({ id: cue.id, kind: 'sfx', file: asset.file, start, duration: cue.duration,
      gain: cue.gain, loop: cue.asset === 'rain' || cue.asset === 'clock', label: cue.label,
      phone: cue.id === 'knock-phone', follow_scene: cue.follow_scene === true })
    return true
  }
  for (const line of lines) {
    for (const cue of cues.filter(item => item.anchor === line.id && item.placement === 'before')) {
      if (addEffect(cue, cursor) && !cue.follow_scene) cursor += cue.duration + 0.18
    }
    const take = manifest?.lines?.[line.id]?.[takes[line.id] || 'directed']
    const length = take?.duration || 2.5
    if (take?.file) clips.push({ id: line.id, kind: 'voice', role: line.role, file: take.file, start: cursor,
      duration: length, gain: 0, label: line.text })
    for (const cue of cues.filter(item => item.anchor === line.id && item.placement === 'with')) addEffect(cue, cursor)
    cursor += length + 0.38
    for (const cue of cues.filter(item => item.anchor === line.id && item.placement === 'after')) {
      if (addEffect(cue, cursor) && !cue.follow_scene) cursor += cue.duration + 0.2
    }
  }
  const duration = Math.max(cursor, ...clips.filter(clip => !clip.follow_scene).map(clip => clip.start + clip.duration)) + 1.3
  const boundedClips = clips.map(clip => clip.follow_scene ? { ...clip, duration: Math.max(0, duration - clip.start) } : clip)
  // Muting is an A/B comparison: retain cue timing and the tail, only remove sound.
  return { duration, clips: muted ? boundedClips.filter(clip => clip.kind !== 'sfx') : boundedClips }
}

export function encodeWav(buffer) {
  const channels = Array.from({ length: buffer.numberOfChannels || 1 }, (_, index) => buffer.getChannelData(index))
  const frames = channels[0].length
  const blockAlign = channels.length * 2
  const dataSize = frames * blockAlign
  const bytes = new ArrayBuffer(44 + dataSize)
  const view = new DataView(bytes)
  const string = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)) }
  string(0, 'RIFF'); view.setUint32(4, 36 + dataSize, true); string(8, 'WAVE')
  string(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, channels.length, true)
  view.setUint32(24, buffer.sampleRate, true); view.setUint32(28, buffer.sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true); view.setUint16(34, 16, true); string(36, 'data'); view.setUint32(40, dataSize, true)
  // Both render paths already share a master bus. PCM encoding must not apply
  // a second, export-only normalization or discard stereo ambience.
  for (let frame = 0; frame < frames; frame++) for (let channel = 0; channel < channels.length; channel++) {
    const value = channels[channel][frame]
    const sample = Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0
    view.setInt16(44 + frame * blockAlign + channel * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true)
  }
  return new Blob([bytes], { type: 'audio/wav' })
}

export class DemoMixer {
  constructor(base) {
    this.base = base; this.cache = new Map(); this.nodes = []; this.generation = 0
    this.requests = new Set(); this.disposed = false; this.master = null
  }
  assertActive() {
    if (this.disposed) throw new DOMException('音频操作已取消。', 'AbortError')
  }
  async context(resume = true) {
    this.assertActive()
    if (!this.ctx) this.ctx = new (globalThis.AudioContext || globalThis.webkitAudioContext)()
    if (resume && this.ctx.state === 'suspended') await this.ctx.resume()
    this.assertActive()
    return this.ctx
  }
  async buffer(file) {
    this.assertActive()
    if (!this.cache.has(file)) {
      const controller = new AbortController()
      this.requests.add(controller)
      const task = (async () => {
        try {
          const response = await fetch(new URL(file, this.base), { signal: controller.signal })
          if (!response.ok) throw new Error('音频读取失败，请刷新后重试。')
          const bytes = await response.arrayBuffer()
          this.assertActive()
          // Decoding/export works while suspended; it does not need permission
          // to emit audio after the user's click has left the event loop.
          const decoded = await (await this.context(false)).decodeAudioData(bytes)
          this.assertActive()
          return decoded
        } finally { this.requests.delete(controller) }
      })()
      this.cache.set(file, task)
      task.catch(() => { if (this.cache.get(file) === task) this.cache.delete(file) })
    }
    return this.cache.get(file)
  }
  stop() {
    this.generation++
    this.nodes.forEach(node => { try { node.stop() } catch {} node.onended?.() })
    this.nodes = []
    this.master?.disconnect()
    this.master = null
  }
  masterBus(ctx) {
    const compressor = ctx.createDynamicsCompressor()
    compressor.threshold.value = -2
    compressor.ratio.value = 16
    const output = ctx.createGain()
    output.gain.value = 0.96
    compressor.connect(output).connect(ctx.destination)
    return { input: compressor, disconnect: () => { compressor.disconnect(); output.disconnect() } }
  }
  place(ctx, clip, buffer, destination, when, skip = 0) {
    if (!Number.isFinite(buffer.duration) || buffer.duration <= 0 || !Number.isFinite(clip.duration) || clip.duration <= 0) return null
    const total = clip.loop ? clip.duration : Math.min(clip.duration, buffer.duration)
    skip = Math.max(0, Number.isFinite(skip) ? skip : 0)
    if (skip >= total) return null
    when = Math.max(0, Number.isFinite(when) ? when : 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.loop = !!clip.loop
    const gain = ctx.createGain()
    const volume = 10 ** ((Number.isFinite(clip.gain) ? clip.gain : 0) / 20)
    const length = total - skip
    const fade = Math.min(clip.kind === 'sfx' && clip.loop ? 0.7 : 0.02, total / 3)
    const level = Math.min(1, skip / fade, (total - skip) / fade)
    gain.gain.setValueAtTime(volume * level, when)
    if (skip < fade) gain.gain.linearRampToValueAtTime(volume, when + fade - skip)
    if (skip < total - fade) gain.gain.setValueAtTime(volume, when + total - fade - skip)
    gain.gain.linearRampToValueAtTime(0, when + length)
    const connections = [source, gain]
    if (clip.phone) {
      const high = ctx.createBiquadFilter(); high.type = 'highpass'; high.frequency.value = 600
      const low = ctx.createBiquadFilter(); low.type = 'lowpass'; low.frequency.value = 2800
      connections.push(high, low)
      source.connect(high).connect(low).connect(gain)
    } else source.connect(gain)
    gain.connect(destination)
    let released = false
    source.onended = () => {
      if (released) return
      released = true
      connections.forEach(node => node.disconnect())
    }
    source.start(when, source.loop ? skip % buffer.duration : skip, length)
    return source
  }
  async play(schedule, offset = 0) {
    this.stop()
    const token = this.generation
    offset = Math.max(0, Number.isFinite(offset) ? offset : 0)
    if (offset >= schedule.duration) return null
    try {
      const ctx = await this.context()
      if (token !== this.generation) return null
      const clips = schedule.clips.filter(clip => clip.start + clip.duration > offset)
      const buffers = await Promise.all(clips.map(clip => this.buffer(clip.file)))
      if (token !== this.generation) return null
      this.master = this.masterBus(ctx)
      const start = ctx.currentTime + 0.07
      for (let index = 0; index < clips.length; index++) {
        const clip = clips[index]
        const source = this.place(ctx, clip, buffers[index], this.master.input,
          start + Math.max(0, clip.start - offset), Math.max(0, offset - clip.start))
        if (source) this.nodes.push(source)
      }
      this.startedAt = start - offset
      return ctx
    } catch (error) {
      if (token !== this.generation) return null
      this.stop()
      throw error
    }
  }
  async render(schedule) {
    this.assertActive()
    const buffers = await Promise.all(schedule.clips.map(clip => this.buffer(clip.file)))
    this.assertActive()
    const ctx = new globalThis.OfflineAudioContext(2, Math.max(1, Math.ceil(schedule.duration * 44100)), 44100)
    const master = this.masterBus(ctx)
    try {
      schedule.clips.forEach((clip, index) => this.place(ctx, clip, buffers[index], master.input, clip.start))
      const audio = await ctx.startRendering()
      this.assertActive()
      return encodeWav(audio)
    } finally { master.disconnect() }
  }
  dispose() {
    if (this.disposed) return
    this.disposed = true
    this.stop()
    this.requests.forEach(request => request.abort())
    this.requests.clear()
    this.ctx?.close().catch(() => {})
    this.cache.clear()
  }
}
