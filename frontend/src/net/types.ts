// 🔊 来自 TTS worker 的 meta 信息
export interface TTSMeta {
  type: 'meta'
  format: 'pcm_s16le'
  sample_rate: number
  channels: number
}

// 🔊 PCM chunk（已经 decode 成 Int16Array）
export type PCMChunk = Int16Array

// 回调签名（以后你会感谢这一步）
export type OnMeta = (meta: TTSMeta) => void
export type OnPCM = (pcm: PCMChunk) => void