class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) return true

    const channel = input[0]
    if (!channel) return true

    const pcm16 = new Int16Array(channel.length)

    for (let i = 0; i < channel.length; i++) {
      const s = Math.max(-1, Math.min(1, channel[i]))
      pcm16[i] = s * 32767
    }

    // 🔥 只发“真实有内容”的帧
    this.port.postMessage(pcm16.buffer)
    return true
  }
}

registerProcessor('pcm-processor', PCMProcessor)