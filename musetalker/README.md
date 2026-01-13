# MuseTalker 项目运行指南

多进程系统（LLM + TTS + 前端实时音频播放），适用于博物馆数字导览，支持：
- 文本输入 → LLM 结构化理解
- 实时 TTS 流式语音合成
- 浏览器端无缝音频播放

本 README 用于快速恢复运行环境。

## 一、项目结构
```
MuseTalker/
├── dev.sh                 # 一键启动脚本（TTS worker + API）
├── .env                   # 环境变量（不入库）
├── musetalker/
│   ├── api/               # FastAPI 接口（LLM）
│   ├── llm/               # LLM orchestrator
│   └── tts/               # TTS worker（WebSocket + 流式 PCM）
└── frontend/
    ├── src/               # 前端源码（Vite + TS）
    └── npm run dev        # 前端开发服务器
```

## 二、首次运行前准备
**Python 环境**
- Python 3.10，推荐 conda / venv

**Node.js 环境**
- Node >= 18，npm 或 pnpm 均可

**安装后端依赖（示例）**
```bash
pip install fastapi uvicorn websockets pyyaml python-docx volcengine-sdk
```

**安装前端依赖**
```bash
cd frontend
npm install
```

## 三、配置 .env（重要）
在 MuseTalker 根目录创建 `.env` 文件（与 `dev.sh` 同目录）：
```
TTS_APPID=你的火山TTS_APPID
TTS_ACCESS_TOKEN=你的火山TTS_ACCESS_TOKEN
TTS_VOICE_TYPE=zh_female_cancan_mars_bigtts
TTS_ENCODING=wav

ARK_API_KEY=你的豆包/火山大模型API_KEY
```
- `.env` 不要提交到 git。

## 四、启动后端
```bash
chmod +x dev.sh
./dev.sh
```
会启动：
1. TTS Worker（WebSocket + 实时 PCM 输出）
2. FastAPI LLM 服务（http://127.0.0.1:8000）

看到以下日志即成功：
- `TTS Worker listening on 127.0.0.1:8765`
- `Uvicorn running on http://127.0.0.1:8000`

## 五、启动前端
```bash
cd frontend
npm run dev
```

浏览器访问 `http://localhost:5173`，前端会：
- 调用 `/api/llm` 获取 LLM 结构化结果
- 将 `tts_text` 发送给 TTS worker
- 实时播放流式语音

## 六、常见问题
- 报错 TTS_APPID / TTS_ACCESS_TOKEN 未设置：检查 `.env` 是否在根目录，`dev.sh` 是否 `source .env`。
- 前端请求被 CORS 拦截：FastAPI 已配 CORS；仍有问题时确认请求地址 `http://127.0.0.1:8000`。
- 听不到声音：确认浏览器已点击按钮（AudioContext 需用户交互），控制台是否有 META / enqueuePCM 日志。

## 七、最小启动流程
- 终端 1：
  ```bash
  cd MuseTalker
  ./dev.sh
  ```
- 终端 2：
  ```bash
  cd frontend
  npm run dev
  ```
- 浏览器：`http://localhost:5173`

——如果未来出现问题，按上述步骤自检。本项目是工程系统，不是一条一次性脚本。
