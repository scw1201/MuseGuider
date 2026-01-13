// frontend/src/net/PCMRecorder.ts
export class PCMRecorder {
  private ctx!: AudioContext
  private stream!: MediaStream
  private source!: MediaStreamAudioSourceNode
  private node!: AudioWorkletNode

  private buffer: Int16Array[] = []

  onData?: (pcm: Int16Array) => void

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.ctx = new AudioContext({ sampleRate: 16000 })
    await this.ctx.resume()

    await this.ctx.audioWorklet.addModule('/src/net/pcm-worklet.js')

    this.source = this.ctx.createMediaStreamSource(this.stream)
    this.node = new AudioWorkletNode(this.ctx, 'pcm-processor')

    this.node.port.onmessage = (e) => {
      const pcm = new Int16Array(e.data)
      this.buffer.push(pcm)
    }

    this.source.connect(this.node)
    this.node.connect(this.ctx.destination)
  }

  pull(samples: number): Int16Array {
    const out = new Int16Array(samples)
    let offset = 0

    while (this.buffer.length && offset < samples) {
      const cur = this.buffer[0]
      const n = Math.min(cur.length, samples - offset)
      out.set(cur.subarray(0, n), offset)
      offset += n

      if (n < cur.length) {
        this.buffer[0] = cur.subarray(n)
      } else {
        this.buffer.shift()
      }
    }

    return out
  }

  stop() {
    this.stream.getTracks().forEach(t => t.stop())
    this.ctx.close()
  }
}