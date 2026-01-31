export class AudioEngine {
  private ctx: AudioContext
  private sampleRate: number
  private queue: Float32Array[] = []
  private playing = false

  // ✅ 播放结束回调
  onFinish?: () => void

  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate
    this.ctx = new AudioContext({ sampleRate })
  }

  async resume() {
    if (this.ctx.state !== 'running') {
      await this.ctx.resume()
      console.log('[Audio] resumed')
    }
    console.log('[Audio] state after', this.ctx.state)
  }

  enqueuePCM(pcm: Int16Array) {
    if (!pcm.length) return
    console.log('[Audio] enqueuePCM', pcm.length, 'state', this.ctx.state)

    const float32 = new Float32Array(pcm.length)
    for (let i = 0; i < pcm.length; i++) {
      float32[i] = pcm[i] / 32768
    }

    this.queue.push(float32)

    if (!this.playing) {
      console.log('[Audio] start play')
      this.playNext()
    }
  }

  private playNext() {
    if (this.queue.length === 0) {
      this.playing = false
      console.log('[Audio] finished')
      this.onFinish?.()   // 🔥 核心
      return
    }

    this.playing = true
    const data = this.queue.shift()!

    // TS-safe，彻底规避 SharedArrayBuffer
    const safe = Float32Array.from(data)

    const buffer = this.ctx.createBuffer(1, safe.length, this.sampleRate)
    buffer.copyToChannel(safe, 0)

    const src = this.ctx.createBufferSource()
    src.buffer = buffer
    src.connect(this.ctx.destination)
    src.onended = () => this.playNext()
    src.start()
  }
}
