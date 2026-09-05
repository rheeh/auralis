import test from 'node:test'
import assert from 'node:assert/strict'
import { DemoMixer, encodeWav, makeSchedule } from '../src/demo/audioMixer.js'

const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`)
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const audioBuffer = (duration = 1, channels = 1, sampleRate = 100) => ({
  duration, sampleRate, numberOfChannels: channels,
  getChannelData: () => new Float32Array(Math.ceil(duration * sampleRate)),
})
const clip = (options = {}) => ({ id: 'voice', kind: 'voice', file: 'voice.wav', start: 0, duration: 1, gain: 0, ...options })
const schedule = (clips = [clip()]) => ({ duration: 2, clips })

// Small Web Audio boundary doubles: record scheduling/graph commands, do not
// pretend to emulate DSP. Actual browser listening remains a separate check.
function runtime(t) {
  const state = { contexts: [], offlines: [], decoded: 0, fetched: 0 }
  const param = () => ({ value: 1, events: [],
    setValueAtTime(value, time) { this.events.push(['set', value, time]) },
    linearRampToValueAtTime(value, time) { this.events.push(['ramp', value, time]) },
  })
  const node = (kind) => ({ kind, connected: [], disconnected: false,
    connect(target) { this.connected.push(target); return target },
    disconnect() { this.disconnected = true },
  })
  class Context {
    constructor() {
      this.state = 'suspended'; this.currentTime = 10; this.sampleRate = 44100
      this.destination = node('destination'); this.sources = []; this.gains = []; this.compressors = []; this.resumes = 0
    }
    async resume() { this.resumes++; this.state = 'running' }
    async close() { this.state = 'closed' }
    async decodeAudioData() { state.decoded++; return audioBuffer() }
    createBufferSource() {
      const source = Object.assign(node('source'), {
        start(when, offset, duration) {
          assert.ok([when, offset, duration].every(Number.isFinite))
          assert.ok(when >= 0 && offset >= 0 && duration > 0)
          this.started = [when, offset, duration]
        },
        stop() { this.stopped = true },
      })
      this.sources.push(source)
      return source
    }
    createGain() { const gain = Object.assign(node('gain'), { gain: param() }); this.gains.push(gain); return gain }
    createDynamicsCompressor() {
      const compressor = Object.assign(node('compressor'), { threshold: param(), ratio: param() })
      this.compressors.push(compressor)
      return compressor
    }
    createBiquadFilter() { return Object.assign(node('filter'), { frequency: param() }) }
  }
  class Live extends Context { constructor() { super(); state.contexts.push(this) } }
  class Offline extends Context {
    constructor(channels, length, sampleRate) {
      super(); this.currentTime = 0; this.channels = channels; this.length = length; this.sampleRate = sampleRate
      state.offlines.push(this)
    }
    async startRendering() { return audioBuffer(this.length / this.sampleRate, this.channels, this.sampleRate) }
  }
  for (const [name, value] of Object.entries({ AudioContext: Live, OfflineAudioContext: Offline })) {
    const original = Object.getOwnPropertyDescriptor(globalThis, name)
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true })
    t.after(() => original ? Object.defineProperty(globalThis, name, original) : delete globalThis[name])
  }
  t.mock.method(globalThis, 'fetch', async () => {
    state.fetched++
    return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) }
  })
  state.Context = Context
  return state
}

test('schedule retains long ambience tails and preserves dialogue timing when muted', () => {
  const lines = [{ id: 1, role: 'detective', text: '谁在门外？' }]
  const manifest = { lines: { 1: { directed: { file: 'voice.wav', duration: 2 } } } }
  const effects = [{ id: 'door', file: 'door.wav' }, { id: 'rain', file: 'rain.wav' }]
  const cues = [
    { id: 'invalid', asset: 'missing', anchor: 1, placement: 'before', duration: 99 },
    { id: 'door', asset: 'door', anchor: 1, placement: 'before', duration: 1, gain: -6 },
    { id: 'rain', asset: 'rain', anchor: 1, placement: 'with', duration: 10, gain: -18 },
  ]
  const full = makeSchedule(lines, cues, manifest, {}, effects)
  const muted = makeSchedule(lines, cues, manifest, {}, effects, true)
  const voice = full.clips.find(item => item.kind === 'voice')
  near(voice.start, 1.88)
  near(full.duration, 13.18)
  assert.deepEqual(muted.clips, [voice])
  assert.equal(muted.duration, full.duration)
  assert.equal(full.clips.find(item => item.id === 'rain').duration, 10)
})

test('WAV contains interleaved stereo PCM without export-only normalization', async () => {
  const channels = [Float32Array.from([0.5, 2, -0.5]), Float32Array.from([-0.25, -2, NaN])]
  const wav = await encodeWav({ sampleRate: 8000, numberOfChannels: 2, getChannelData: index => channels[index] }).arrayBuffer()
  const header = new DataView(wav)
  assert.equal(new TextDecoder().decode(new Uint8Array(wav, 0, 4)), 'RIFF')
  assert.equal(header.getUint16(22, true), 2)
  assert.equal(header.getUint32(24, true), 8000)
  assert.equal(header.getUint32(28, true), 32000)
  assert.equal(header.getUint16(32, true), 4)
  assert.equal(header.getUint32(40, true), 12)
  assert.equal(wav.byteLength, 56)
  assert.deepEqual(Array.from({ length: 6 }, (_, index) => header.getInt16(44 + index * 2, true)),
    [16384, -8192, 32767, -32768, -16384, 0])
})

test('scene-following rain ends with the natural scene while other long overlays remain intact', () => {
  const lines = [{ id: 1, text: '雨还没停。' }]
  const manifest = { lines: { 1: { directed: { file: 'voice.wav', duration: 2 } } } }
  const effects = [{ id: 'rain', file: 'rain.wav' }, { id: 'clock', file: 'clock.wav' }]
  const rain = { id: 'rain', asset: 'rain', anchor: 1, placement: 'with', duration: 65, gain: -22, follow_scene: true }
  const result = makeSchedule(lines, [rain], manifest, {}, effects)
  near(result.duration, 4.38)
  near(result.clips.find(item => item.id === 'rain').duration, 3.68)
  const extended = makeSchedule(lines, [rain, { ...rain, id: 'clock', asset: 'clock', duration: 10, follow_scene: false }], manifest, {}, effects)
  near(extended.duration, 12)
  near(extended.clips.find(item => item.id === 'clock').duration, 10)
  near(extended.clips.find(item => item.id === 'rain').duration, 11.3)
})

test('short source seeks skip exhausted audio, clip to real duration, and preserve loop phase', t => {
  const state = runtime(t)
  const mixer = new DemoMixer('https://example.test/')
  const ctx = new state.Context()
  const short = audioBuffer(0.5)
  assert.equal(mixer.place(ctx, clip({ duration: 4 }), short, ctx.destination, 0, 0.5), null)
  assert.equal(ctx.sources.length, 0)
  const tail = mixer.place(ctx, clip({ duration: 4 }), short, ctx.destination, 0, 0.45)
  near(tail.started[2], 0.05)
  near(ctx.gains[0].gain.events.at(-1)[2], 0.05)
  const loop = mixer.place(ctx, clip({ kind: 'sfx', duration: 4, loop: true, gain: -6 }), short, ctx.destination, 0, 1.2)
  near(loop.started[1], 0.2)
  near(loop.started[2], 2.8)
  near(ctx.gains[1].gain.events[0][1], 10 ** (-6 / 20))
  const bounded = mixer.place(ctx, clip(), short, ctx.destination, -1, -1)
  assert.deepEqual(bounded.started, [0, 0, 0.5])
  assert.equal(mixer.place(ctx, clip(), audioBuffer(0), ctx.destination, 0), null)
})

test('decode cache deduplicates concurrent loads and retries a failed request', async t => {
  const state = runtime(t)
  const mixer = new DemoMixer('https://example.test/')
  t.after(() => mixer.dispose())
  const [first, second] = await Promise.all([mixer.buffer('voice.wav'), mixer.buffer('voice.wav')])
  assert.equal(first, second)
  assert.equal(state.fetched, 1)
  assert.equal(state.decoded, 1)
  let attempt = 0
  t.mock.method(globalThis, 'fetch', async () => ({ ok: ++attempt > 1, arrayBuffer: async () => new ArrayBuffer(1) }))
  await assert.rejects(mixer.buffer('retry.wav'), /音频读取失败/)
  await mixer.buffer('retry.wav')
  assert.equal(attempt, 2)
})

test('stop during loading prevents late playback while keeping decoded audio reusable', async t => {
  const state = runtime(t)
  const mixer = new DemoMixer('https://example.test/')
  t.after(() => mixer.dispose())
  const entered = deferred(), response = deferred()
  t.mock.method(globalThis, 'fetch', () => { entered.resolve(); return response.promise })
  const pending = mixer.play(schedule())
  await entered.promise
  mixer.stop()
  response.resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(1) })
  assert.equal(await pending, null)
  assert.equal(state.contexts[0].sources.length, 0)
  const ctx = await mixer.play(schedule())
  assert.equal(ctx.sources.length, 1)
  assert.equal(state.decoded, 1)
  mixer.stop()
  assert.equal(ctx.sources[0].stopped, true)
  assert.ok(ctx.sources[0].disconnected)
  assert.ok(ctx.compressors[0].disconnected)
})

test('dispose aborts pending fetches and cannot revive a closed audio context', async t => {
  const state = runtime(t)
  const mixer = new DemoMixer('https://example.test/')
  const entered = deferred()
  let signal
  t.mock.method(globalThis, 'fetch', (_url, options) => {
    signal = options.signal
    entered.resolve()
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError'))))
  })
  const pending = mixer.play(schedule())
  await entered.promise
  mixer.dispose()
  assert.equal(await pending, null)
  assert.equal(signal.aborted, true)
  assert.equal(mixer.cache.size, 0)
  assert.equal(state.contexts[0].state, 'closed')
  assert.equal(state.contexts[0].sources.length, 0)
  await assert.rejects(mixer.buffer('voice.wav'), { name: 'AbortError' })
})

test('playback and export use the same master processing; offline export needs no resume', async t => {
  const state = runtime(t)
  const mixer = new DemoMixer('https://example.test/')
  t.after(() => mixer.dispose())
  const value = schedule([clip({ start: 0.3, duration: 0.4, gain: -12, phone: true })])
  await mixer.render(value)
  const live = state.contexts[0]
  assert.equal(live.resumes, 0)
  await mixer.play(value)
  const offline = state.offlines[0]
  assert.equal(offline.channels, 2)
  assert.equal(live.compressors[0].threshold.value, offline.compressors[0].threshold.value)
  assert.equal(live.compressors[0].ratio.value, offline.compressors[0].ratio.value)
  assert.equal(live.gains[0].gain.value, offline.gains[0].gain.value)
  near(live.sources[0].started[0] - 10.07, offline.sources[0].started[0])
  near(live.sources[0].started[2], offline.sources[0].started[2])
  assert.equal(state.fetched, 1)
  assert.equal(state.decoded, 1)
  assert.equal(await mixer.play(value, value.duration), null)
})
