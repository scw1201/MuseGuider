// frontend/src/net/ASRClient.ts
import { PCMRecorder } from './PCMRecorder'

const CHUNK_SAMPLES = 1600   // 100ms @ 16kHz
const SEND_INTERVAL = 100   // ms

export class ASRClient {
  private ws!: WebSocket
  private recorder!: PCMRecorder
  private timer!: number

  private finalText = ''
  private resolveFinal?: (t: string) => void
  private onPartial?: (t: string) => void

  constructor(onPartial?: (t: string) => void) {
    this.onPartial = onPartial
  }

  setOnPartial(handler?: (t: string) => void) {
    this.onPartial = handler
  }

  start() {
    console.log('[ASR] start() called')

    this.finalText = ''

    this.ws = new WebSocket('ws://localhost:9001')
    this.ws.binaryType = 'arraybuffer'

    this.ws.onmessage = (ev) => {
      console.log('[ASR] recv from server:', ev.data)

      if (typeof ev.data === 'string') {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'partial') {
            this.onPartial?.(msg.text || '')
            return
          }
          if (msg?.type === 'final') {
            this.finalText = msg.text || ''
            this.resolveFinal?.(this.finalText)
            return
          }
        } catch {
          // fall back to plain text
        }
        this.finalText = ev.data
        this.resolveFinal?.(this.finalText)
      }
    }

    this.ws.onopen = async () => {
      console.log('[ASR][WS] connected')

      this.recorder = new PCMRecorder()
      await this.recorder.start()

      this.timer = window.setInterval(() => {
        const pcm = this.recorder.pull(CHUNK_SAMPLES)
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(pcm.buffer)
        }
      }, SEND_INTERVAL)
    }
  }

  stopAndGetFinalText(): Promise<string> {
    console.log('[ASR] stopAndGetFinalText() called')

    clearInterval(this.timer)
    this.recorder.stop()

    // 🔥 一定要先发 STOP，再等返回
    this.ws.send(new Uint8Array([0]))

    return new Promise(resolve => {
      this.resolveFinal = resolve
    })
  }
}
