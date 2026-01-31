# MuseGuide

面向博物馆数字导览的多进程语音交互系统，集成 ASR + LLM + TTS，并提供前端实时播放与交互。本文档概述系统特点、功能模块、启动方式与关键文件，便于维护与扩展。

## 系统特点
- 多通道实时链路：ASR → LLM → TTS → 前端实时播放
- 角色化导览：多人物设定（语气 + 音色 + 视频形象）
- 空间感知导览：基于展区/展品/位置先验构建导览情境
- 状态驱动渲染：导览动作状态驱动视频切换与 UI 状态提示
- 低耦合模块：ASR/LLM/TTS/前端可独立替换与升级

## 功能模块
1) 语音识别（ASR）
   - 浏览器录音 → WebSocket 流式识别 → 文本
2) 语言理解（LLM）
   - 结构化输出：guide_state / tts_text / guide_zone / focus_exhibit / guide_stage / user_intent
3) 语音合成（TTS）
   - WebSocket 流式合成 → PCM 实时播放
4) 导览情境（Learning Context）
   - UI 展示“当前位置/导览阶段/关注展品/用户意图”
5) 前端交互
   - 人物侧边栏 + 数字典藏页 + 实时字幕 + 状态徽标

## 功能概览
- 语音识别：浏览器录音 → WebSocket 流式 ASR
- 语言理解：LLM 结构化理解与导览动作决策
- 语音合成：TTS 流式 PCM 输出
- 前端展示：Vite + TS，浏览器实时音频播放 + 视频状态切换

## 服务与端口
- ASR WebSocket Server：`ws://127.0.0.1:9001`
- TTS Worker：`ws://127.0.0.1:8765`
- API Server：`http://127.0.0.1:8000`
- Frontend Dev Server：`http://localhost:5173`

## 环境要求
- Python 3.10
- Node.js 18+

## 安装依赖
后端依赖（示例）：
```bash
pip install fastapi uvicorn websockets pyyaml python-docx volcengine-sdk
```

前端依赖：
```bash
cd frontend
npm install
```

## 配置说明
统一在 `museguide/configs/secrets.yaml` 维护密钥与 API 配置：
- LLM：`doubao.api_key`
- TTS：`tts.*`
- ASR：`asr.*`
- Billing：`billing.*`（可选）

生产环境请替换并避免提交真实密钥。

## 启动方式
后端：
```bash
chmod +x dev.sh
./dev.sh
```

前端：
```bash
cd frontend
npm run dev
```

## 关键文件与作用

### 根目录
- `dev.sh`：一键启动 ASR WebSocket、TTS Worker（v3）与 FastAPI 服务。
- `MuseGuide_运行指南.docx`：更完整的运行说明文档。
- `zh_female_cancan_mars_bigtts.wav`：TTS 语音示例音频。
- `README.md`：本说明。

### 后端入口与核心逻辑（museguide/）
- `museguide/api/server.py`：FastAPI 入口，提供 `/api/llm`，负责 CORS 与请求封装。
- `museguide/llm/orchestrator.py`：LLM 业务编排核心，加载配置与先验，构建 system prompt，解析 JSON 输出并映射到前端可用的状态。
- `museguide/llm/prompts.py`：LLM 的系统提示词模板。
- `museguide/llm/client.py`：Ark SDK 简单封装（备用/实验用）。
- `museguide/llm/domain_prompt.py`：构建展品先验的提示词（备用/实验用）。
- `museguide/llm/context_store.py`：导览上下文缓存与读取（会话状态）。
- `museguide/llm/utils.py`：通用文本提取工具。
- `museguide/tts/worker_v3.py`：TTS WebSocket Worker v3（当前默认），连接火山引擎并向浏览器流式发送 PCM。
- `museguide/tts/worker.py`：TTS WebSocket Worker v2（保留/对比用）。
- `museguide/tts/service.py`：通过 TCP 与 TTS Worker 通信的服务端客户端封装，便于后端或脚本复用。
- `museguide/tts/client.py`：简化版 TTS Worker 客户端（一次性调用）。
- `museguide/tts/run_binary_tts.py`：调用火山二进制示例脚本的封装（当前为注释示例）。
- `museguide/asr/ws_server.py`：浏览器 ASR WebSocket 服务，接收 PCM 并调用 BigModel ASR。
- `museguide/asr/v3_bigmodel_client.py`：火山 ASR BigModel 客户端与协议解析。
- `museguide/asr/session.py`：ASR v2 协议的 streaming session 实现（调试/对比用）。
- `museguide/asr/protocol.py`：ASR v2 协议封装与解析工具。
- `museguide/asr/streaming_client.py`：简化版 ASR streaming 客户端（一次性识别 PCM）。
- `museguide/asr/server.py`：最小可跑的 ASR 本地测试入口（读 wav）。
- `museguide/asr/streaming_asr_demo.py`：官方示例脚本（参考用）。
- `museguide/scripts/test_doubao.py`：LLM + TTS 链路延迟测试脚本。

### 配置与数据（museguide/configs/, museguide/data/）
- `museguide/configs/llm.yaml`：LLM 模型、温度、max tokens 等配置。
- `museguide/configs/tts.yaml`：TTS 默认 endpoint 与音色编码。
- `museguide/configs/guide_states.yaml`：导览员动作状态的单一真源，定义 video_state 与 tts 开关。
- `museguide/configs/personas.yaml`：导览员人设与提示词、音色配置。
- `museguide/configs/domain_prior.json`：展区/展品/位置先验（LLM 空间感知）。
- `museguide/configs/secrets.yaml`：密钥与 API 配置（当前默认读取）。
- `museguide/data/exhibits.yaml`：早期展品先验示例（未启用）。

### 前端逻辑（frontend/src/）
- `frontend/src/main.ts`：前端入口，初始化 UI 与控制器，处理键盘与语音按钮。
- `frontend/src/app/controller.ts`：核心流程控制，串联 LLM 请求、TTS 流式播放与视频状态切换。
- `frontend/src/app/ui.ts`：UI DOM 结构与状态更新函数。
- `frontend/src/app/personas.ts`：前端展示的人物信息配置（头像/简介/状态描述）。
- `frontend/src/audio/AudioEngine.ts`：PCM 播放引擎，队列式播放与结束回调。
- `frontend/src/video/VideoEngine.ts`：视频状态切换（IDLE / LISTENING / EXPLAIN 等）。
- `frontend/src/net/ASRClient.ts`：浏览器 ASR 客户端，录音与 WebSocket 推流。
- `frontend/src/net/PCMRecorder.ts`：录音与音频 worklet 管理。
- `frontend/src/net/pcm-worklet.js`：AudioWorklet，将浮点音频转换为 int16 PCM。
- `frontend/src/net/TTSClient.ts`：TTS Worker WebSocket 客户端，接收 meta + PCM。
- `frontend/src/net/types.ts`：TTS/PCM 类型定义。
- `frontend/src/style.css`：页面样式与状态标识。

### 前端资源与构建（frontend/）
- `frontend/index.html`：Vite 入口 HTML。
- `frontend/package.json` / `frontend/package-lock.json`：前端依赖与脚本。
- `frontend/tsconfig.json`：TS 配置。
- `frontend/public/logo.png`：页面 Logo。
- `frontend/public/videos/*.mp4`：导览员动作视频，文件名与 `guide_states.yaml` 的 `video_state` 对应。
- `frontend/public/videos/siyang_fangzun/*`：分展品的视频素材。
- `frontend/public/test1.wav` / `frontend/public/test2.wav`：音频测试文件。
- `frontend/public/domain_prior.json`：数字典藏页面数据源（前端用）。

### 火山引擎示例（volcengine_binary_demo/）
- `volcengine_binary_demo/examples/volcengine/binary.py`：官方二进制 TTS 示例。
- `volcengine_binary_demo/setup.py` / `pyproject.toml`：示例 SDK 依赖配置。
- `volcengine_binary_demo/protocols/*`：二进制协议封装。

## 相关文档
- `museguide/README.md`
