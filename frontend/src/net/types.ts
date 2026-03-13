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

export interface SuggestedAction {
  label: string
  text: string
}

export interface LLMResponse {
  guide_state: string
  video_state?: string
  video_dir?: string
  video_prefix?: string
  tts_text: string
  confidence: number
  guide_zone: string
  guide_venue: string
  guide_floor: string
  guide_area: string
  focus_exhibit: string
  guide_stage: string
  user_intent: string
  reply_text?: string
  follow_up_text?: string
  pending_action_label?: string
  pending_action_text?: string
  pending_action_type?: string
  pending_action_target?: string
  tts_voice_type?: string
  next_step_type?: string
  next_step_target?: string
  tour_event?: string
  current_zone?: string
  current_exhibit?: string
  current_focus_status?: string
  visited_zones?: string[]
  visited_exhibits?: string[]
  zone_progress?: Record<string, string>
  exhibit_progress?: Record<string, string>
  user_interests?: string[]
  suggested_actions?: SuggestedAction[]
}
