# MuseTalker 技术路径说明

本文档聚焦“技术路径”，用于说明实时语音识别、实时音频合成、提示词工程（LLM 控制数字人行为与人格化策略）、以及数字人形象与生成方式在本项目中的落地方式。

## 一、实时语音识别（ASR）链路
1) 浏览器录音  
- 前端通过 `frontend/src/net/PCMRecorder.ts` 采集麦克风音频，利用 `frontend/src/net/pcm-worklet.js` 输出 int16 PCM。

2) WebSocket 流式识别  
- 浏览器通过 `frontend/src/net/ASRClient.ts` 将 PCM 流发送至 ASR WebSocket 服务。  
- 服务端入口：`musetalker/asr/ws_server.py`，内部调用火山 ASR BigModel 客户端 `musetalker/asr/v3_bigmodel_client.py`。

3) 结果输出  
- ASR 返回文本，作为 LLM 输入，用于导览意图与状态判断。

## 二、实时音频合成（TTS）链路
1) LLM 输出 tts_text  
- LLM 输出结构化 JSON，其中 `tts_text` 作为最终播报内容。

2) TTS Worker 流式合成  
- 默认使用 `musetalker/tts/worker_v3.py`，通过 WebSocket 与浏览器建立实时通道。  
- Worker 连接火山 TTS 服务，回传 PCM 流。

3) 浏览器实时播放  
- 前端 `frontend/src/net/TTSClient.ts` 接收 meta + PCM。  
- `frontend/src/audio/AudioEngine.ts` 以队列方式播放，支持流式拼接与结束回调。

## 三、提示词工程（LLM 控制策略）

### 1) 结构化输出：让 LLM 可控
LLM 输出固定结构（`guide_state / tts_text / guide_zone / focus_exhibit / guide_stage / user_intent`），通过结构化字段驱动前端与状态机。

相关文件：
- `musetalker/llm/orchestrator.py`：核心编排，加载配置、构建 prompt、解析 JSON。
- `musetalker/llm/prompts.py`：系统提示词模板。
- `musetalker/configs/guide_states.yaml`：动作状态单一真源（视频状态 + tts 开关）。
- `musetalker/configs/personas.yaml`：人物设定与提示词片段。
- `musetalker/configs/domain_prior.json`：展区/展品/位置先验。

### 2) LLM 控制数字人的哪些东西
LLM 不直接“生成形象”，而是控制“状态与内容”：
- `guide_state`：驱动数字人视频状态（IDLE / LISTEN / EXPLAIN 等）。
- `guide_stage`：导览阶段切换（开场、引导、讲解、收束等）。
- `guide_zone` / `focus_exhibit`：决定当前导览焦点与 UI 呈现。
- `tts_text`：播报文本，体现导览内容与语气。

### 3) 如何做到“理解人格化”和“导览情境”
策略由三部分组成：
- 人设与口吻：来自 `personas.yaml`，约束称呼、语速、情绪强度、用词偏好。  
- 情境先验：来自 `domain_prior.json`（展区/展品/位置），指导内容边界与空间指向。  
- 状态驱动：`guide_states.yaml` 把动作与前端视频状态绑定，促使 LLM 输出可执行状态。

实现要点：
- 口吻只进入 `tts_text`，其余字段保持客观可解析。  
- 先人设，再格式，再示例，避免“风格破坏结构”。  
- 超出先验的内容保持克制或留空，避免虚构。

## 四、数字人形象与生成方式
当前版本以“离线生成 + 状态机切换”为主。

1) 形象素材来源  
- 视频素材存放于 `frontend/public/videos/*.mp4` 与 `frontend/public/videos/siyang_fangzun/*`。

2) 形象驱动方式  
- `guide_state` 对应 `guide_states.yaml` 中的 `video_state`。  
- `frontend/src/video/VideoEngine.ts` 负责按状态切换视频。

3) 数字人生成模型：OmniAvatar  
- 论文：OmniAvatar: Efficient Audio-Driven Avatar Video Generation with Adaptive Body Animation（Qijun Gan, Ruizi Yang, Jianke Zhu, Shaofei Xue, Steven Hoi；Zhejiang University, Alibaba Group）。  
- 能力：音频驱动数字人视频生成，支持身体动作与口型同步，可通过文本提示词控制角色与场景。  
- 推理要点：输入格式为 `[prompt]@@[img_path]@@[audio_path]`，可调 prompt/audio guidance，提升口型一致性。  
- 模型与依赖：提供 Wan2.1-T2V（14B/1.3B）基座 + OmniAvatar LoRA 与音频条件权重 + Wav2Vec 编码器。  
- 适配思路：将本系统的 `tts_text` 或 ASR 音频作为驱动输入，生成视频后由前端 VideoEngine 加载替换预制素材。

## 五、端到端技术路径（简版）
浏览器录音 → ASR WebSocket → 识别文本 → LLM 结构化输出 →  
`guide_state` 驱动视频状态 + `tts_text` 触发 TTS → PCM 流播放

## 六、启动与配置入口
- 一键启动：`dev.sh`（ASR + TTS v3 + API）。  
- 密钥配置：`musetalker/configs/secrets.yaml`。  
- 重要配置：`musetalker/configs/llm.yaml`、`musetalker/configs/tts.yaml`、`musetalker/configs/personas.yaml`。
