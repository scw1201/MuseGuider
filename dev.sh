#!/bin/bash
set -e

# ============================
# 进入项目根目录
# ============================
cd "$(dirname "$0")"

echo "📁 Working dir: $(pwd)"

# ============================
# 启动前清理占用端口
# ============================
kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "🧹 Killing processes on port $port: $pids"
    kill -9 $pids || true
  fi
}

kill_port 9001
kill_port 8765
kill_port 8000

# ============================
# 退出时清理本次启动的进程
# ============================
cleanup() {
  echo "🧹 Cleaning up..."
  if [ -n "${ASR_PID:-}" ]; then kill "$ASR_PID" 2>/dev/null || true; fi
  if [ -n "${TTS_PID:-}" ]; then kill "$TTS_PID" 2>/dev/null || true; fi
  if [ -n "${API_PID:-}" ]; then kill "$API_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

# ============================
# secrets.yaml 优先（如需临时覆盖再手动 export）
# ============================
echo "🔐 Using musetalker/configs/secrets.yaml for credentials"

# ============================
# 启动 ASR WebSocket Server
# ============================
echo "🎙 Starting ASR WebSocket server (9001)..."
python -m musetalker.asr.ws_server &

ASR_PID=$!
echo "   ↳ ASR PID: $ASR_PID"

# ============================
# 启动 TTS Worker (v3)
# ============================
echo "🔊 Starting TTS worker (v3)..."
python -m musetalker.tts.worker_v3 &

TTS_PID=$!
echo "   ↳ TTS PID: $TTS_PID"

# ============================
# 启动 API Server
# ============================
echo "🌐 Starting API server (8000)..."
uvicorn musetalker.api.server:app --reload --port 8000 &

API_PID=$!
echo "   ↳ API PID: $API_PID"

# ============================
# 等待（Ctrl+C 时一起结束）
# ============================
echo "✅ All services started."
echo "🛑 Press Ctrl+C to stop all."

wait
