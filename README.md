# MuseGuide 🏛️✨

一个面向博物馆导览场景的多角色数字人系统：
前端可视化 + 实时语音交互 + LLM 导览决策 + TTS 播报，一套跑通完整导览链路。🚀

## 这套系统能做什么？🎯

- 实时语音问答：观众说话后，系统进行 ASR 识别并触发导览回复。
- 多人格导览员：支持女导览、男导览、古风导览、英文导览、儿童导览等多角色切换。
- 状态驱动数字人：LLM 输出 `guide_state`，前端按状态切换视频动作（讲解/指路/聚焦展品）。
- 空间感知导览：结合展区、楼层、区域和展品先验，回复更贴近真实场馆路线。
- 实时字幕与情境面板：展示当前位置、导览阶段、关注展品、用户意图、路径提示。
- 路线页 + 数字典藏页：同一套数据支持导览路线浏览与展品图文浏览。

## 一张图看主流程 🧠➡️🗣️➡️🎬

1. 浏览器录音并上传 PCM（WebSocket）
2. ASR 服务流式识别文本
3. API 调用 LLM 生成结构化导览结果
4. 返回 `video_state` + `tts_text` + 导览上下文字段
5. 前端切换数字人视频状态并通过 TTS 流式播报

核心字段示例：

- `guide_state`
- `video_state`
- `tts_text`
- `guide_zone` / `guide_floor` / `guide_area`
- `focus_exhibit`
- `guide_stage`
- `user_intent`

## 功能亮点（按体验层）🌟

### 1) 角色化导览

- 前端角色配置：`/Users/la/Desktop/MuseGuide/frontend/src/app/personas.ts`
- 后端角色策略：`/Users/la/Desktop/MuseGuide/museguide/configs/personas.yaml`
- 角色可定义：名字、语气、音色、起始文案、自称与称呼方式。

### 2) 导览动作可控

- 动作状态单一真源：`/Users/la/Desktop/MuseGuide/museguide/configs/guide_states.yaml`
- 当前动作覆盖：`GREETING_SELF`、`EXPLAIN_DETAILED`、`POINTING_DIRECTION`、`FOCUS_EXHIBIT`
- 每个状态可配置是否允许播报（`allow_tts`）。

### 3) 空间与展品语义约束

- 先验数据：`/Users/la/Desktop/MuseGuide/museguide/configs/domain_prior.json`
- 支持按展区/楼层/区域组织展品，帮助 LLM 给出更像真实导览的回答。

### 4) 多页面导览体验

- 导览大厅（数字人主交互）
- 展陈路线（按楼层/区域展示）
- 数字典藏（展区+展品图文卡片）

## 技术栈与服务端口 🧩

### 后端

- FastAPI（API）：`http://127.0.0.1:8000`
- ASR WebSocket：`ws://127.0.0.1:9001`
- TTS Worker WebSocket：`ws://127.0.0.1:8765`

### 前端

- Vite + TypeScript
- 默认开发地址：`http://127.0.0.1:5173` 或 `http://localhost:5173`

## 快速启动（建议直接复制）⚡

### 1) 环境准备

- Python 3.10+
- Node.js 18+
- 可用的火山引擎相关密钥（见 `secrets.yaml`）

### 2) 安装依赖

```bash
cd /Users/la/Desktop/MuseGuide
pip install fastapi uvicorn websockets pyyaml python-docx volcengine-sdk
cd frontend
npm install
```

### 3) 配置密钥

在 `/Users/la/Desktop/MuseGuide/museguide/configs/secrets.yaml` 中填写：

- `doubao.api_key`
- `tts.*`
- `asr.*`

### 4) 启动后端三服务

```bash
cd /Users/la/Desktop/MuseGuide
chmod +x dev.sh
./dev.sh
```

这个脚本会自动拉起：

- ASR（9001）
- TTS（8765）
- API（8000）

### 5) 启动前端

```bash
cd /Users/la/Desktop/MuseGuide/frontend
npm run dev
```

打开浏览器后，点击语音按钮即可开始实时交互。🎤

## 关键接口（当前版本）🔌

- `POST /api/llm`
  - 入参：`text`, `persona_id`, `session_id`
  - 出参：导览状态、TTS 文本、空间上下文字段
- `GET /api/domain_prior`
  - 返回展区/展品/位置先验（路线页、典藏页也会使用）
- `GET /api/personas`
  - 返回后端角色配置

## 项目结构速览 📁

- `/Users/la/Desktop/MuseGuide/frontend`
  - 前端页面、交互逻辑、ASR/TTS 客户端、视频状态切换
- `/Users/la/Desktop/MuseGuide/museguide/api`
  - FastAPI 入口
- `/Users/la/Desktop/MuseGuide/museguide/llm`
  - Prompt 组装、LLM 编排、上下文缓存
- `/Users/la/Desktop/MuseGuide/museguide/asr`
  - WebSocket ASR 服务与客户端协议逻辑
- `/Users/la/Desktop/MuseGuide/museguide/tts`
  - TTS WebSocket Worker
- `/Users/la/Desktop/MuseGuide/museguide/configs`
  - 人设、状态、领域先验、密钥配置
- `/Users/la/Desktop/MuseGuide/frontend/public/videos`
  - 数字人动作视频素材

## 当前边界与注意事项 ⚠️

- 当前数字人是“状态切片视频切换”，不是逐帧口型实时生成。
- 前端依赖本地后端地址（`127.0.0.1`），跨机部署需调整 CORS 和 WS 地址。
- `dev.sh` 启动前会清理端口占用，避免旧进程冲突。

## 接下来可扩展方向 🛠️

- 接入实时视频口型模型（如 Wav2Lip 流式改造）
- 加入会话记忆可视化与用户画像
- 支持多语言导览脚本自动切换
- 支持导览质量评估与数据回放

## License

当前仓库未单独声明开源许可证；如需公开发布，建议补充 `LICENSE` 文件。📌
