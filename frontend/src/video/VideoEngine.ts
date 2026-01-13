// frontend/src/video/VideoEngine.ts

export class VideoEngine {
  private video: HTMLVideoElement
  private currentState: string | null = null

  private videoDir = 'default'
  private videoPrefix = 'default'

  setPersona(dir: string, prefix?: string) {
    this.videoDir = dir || 'default'
    this.videoPrefix = prefix || dir || 'default'
    // Force reload on next setState even if state name is unchanged.
    this.currentState = null
  }

  constructor(videoEl: HTMLVideoElement) {
    this.video = videoEl

    // 基础视频属性
    this.video.muted = true
    this.video.loop = true
    this.video.playsInline = true
    this.video.autoplay = true

    // 防止浏览器策略阻止
    this.video.setAttribute('webkit-playsinline', 'true')
  }

  /**
   * 切换视频状态
   * state 示例：
   * - "IDLE"
   * - "LISTENING"
   * - "EXPLAIN_CALM"
   */
  setState(state: string) {
    if (!state) return
    if (this.currentState === state) return

    const src = `/videos/${this.videoDir}/${this.videoPrefix}_${state}.mp4`
    console.log('[VideoEngine] switch →', src)

    this.currentState = state

    // 强制刷新视频源
    this.video.pause()
    this.video.src = src
    this.video.load()

    const playPromise = this.video.play()
    if (playPromise) {
      playPromise.catch(err => {
        console.warn('[VideoEngine] play blocked:', err)
      })
    }
  }

  /**
   * 强制回到 IDLE
   */
  idle() {
    this.setState('IDLE')
  }

  /**
   * 当前状态
   */
  getState() {
    return this.currentState
  }
}
