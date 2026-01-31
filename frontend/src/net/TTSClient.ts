// src/net/TTSClient.ts
import type { TTSMeta } from './types'

export class TTSClient {
  private url: string

  // 你遇到的 “erasableSyntaxOnly” 不允许 constructor(private url: string)
  constructor(url = 'ws://127.0.0.1:8765') {
    this.url = url
  }

  stream(
    text: string,
    onMeta: (meta: TTSMeta) => void,
    onPCM: (pcm: Int16Array) => void,
    voiceType?: string
  ) {
    const ws = new WebSocket(this.url)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      console.log('[TTSClient] ws open')
      ws.send(JSON.stringify({ text, voice_type: voiceType }))
    }

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data)
        console.log('[TTSClient] meta', msg)
        if (msg.type === 'meta') onMeta(msg as TTSMeta)
        // start/end/error 你想打印也行
        return
      }

      // binary PCM (s16le)
      const pcm = new Int16Array(ev.data)
      console.log('[TTSClient] pcm chunk', pcm.length)
      onPCM(pcm)
    }

    ws.onerror = (e) => {
      console.error('[TTSClient] ws error', e)
    }

    ws.onclose = (ev) => {
      console.log('[TTSClient] ws closed', ev.code, ev.reason)
    }

    return ws
  }
}
