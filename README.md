# ComfyUI VoiceClone TTS

在 ComfyUI 画布里直接完成**声音克隆**与**语音合成**：上传一段 3–60 秒干声得到音色，再把文本合成为该音色的语音，输出原生 `AUDIO`，可直接接 PreviewAudio / SaveAudio 或数字人口型节点。支持 14 种中文方言与 100+ 语种、8 维情绪控制、长文本自动分段拼接。适合**漫剧配音、短剧多角色配音、数字人、有声书**等工作流。

关键词：ComfyUI、声音克隆、语音合成、TTS、voice clone、text to speech、方言、多角色、漫剧配音、数字人。

> English README: [README.en.md](README.en.md)

---

## 30 秒安装

无需 `pip install`，只依赖 Python 3 标准库（torch / torchaudio 用 ComfyUI 自带的）。

**方式一：git clone**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/OpenApiTTS/comfyui-voiceclone-tts
# 重启 ComfyUI
```

**方式二：下载 zip**

下载仓库 zip 解压到 `ComfyUI/custom_nodes/comfyui-voiceclone-tts/`，重启 ComfyUI。
注意目录层级：`custom_nodes/comfyui-voiceclone-tts/__init__.py` 必须存在，不能多套一层。

**方式三：ComfyUI-Manager**

Manager → Install via Git URL → 填 `https://github.com/OpenApiTTS/comfyui-voiceclone-tts` → Restart。

**配置密钥**（推荐，见下文「密钥安全」）：

```bash
# macOS / Linux
export VOICE_API_KEY="你的密钥"

# Windows PowerShell
$env:VOICE_API_KEY = "你的密钥"
```

设置后**重启 ComfyUI**，环境变量在启动时读取。密钥请到语音服务商的开发者后台获取。

---

## 四个节点

全部在 `audio/VoiceClone` 分类下。

| 节点 | 作用 | 输出 |
|---|---|---|
| **AI语音克隆 上传音色** | 上传 3–60 秒参考音频创建音色（本地先校验时长，不合格不发请求） | `audio_id` |
| **AI语音克隆 选择已有音色** | 列出账号下所有音色，下拉选择 | `audio_id`、`name` |
| **AI语音克隆 合成语音** | 文本 + `audio_id` → 语音，含情绪 / 方言 / 语速 / 自动分段 | `audio`、`file_path`、`task_id` |
| **AI语音克隆 一键合成** | 参考音频 + 文本，一个节点出音频（同名音色自动复用，不重复上传） | `audio`、`file_path`、`audio_id` |

> 截图位：`docs/node-upload.png`、`docs/node-list.png`、`docs/node-tts.png`、`docs/node-oneclick.png`

---

## 示例工作流

`workflows/` 目录下拖进画布即可运行：

- `basic_tts.json` —— 一键合成 → PreviewAudio。
- `multi_role.json` —— 两个角色各说一句（一个带 `sad` 情绪），各接一个 SaveAudio。

---

## 参数表（合成语音节点）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | 多行文本 | — | 必填。可插停顿标记 `#0.3#` `#0.5#` `#1.0#` `#1.5#` `#2.0#` `#3.0#` |
| `audio_id` | STRING | — | 来自上传音色 / 选择已有音色节点 |
| `style` | 下拉 | V2.5 情绪版 | V2.0 极速 / V2.5 情绪版 / 方言与多语言。**只有 V2.5 支持情绪控制** |
| `target_speech` | 下拉 | mandarin | mandarin、english、yue、nan、sichuan、northeast、henan、shaanxi、ja、ko、es、fr、de、ru、pt、it、th、vi、id、ms、ar、hi、tr，以及「自动 / 不传」 |
| `speed` | FLOAT | 1.0 | 0.5–2.0，步长 0.1。方言 / 多语言链路上限 1.5，超出自动压到 1.5 并提示 |
| `emotion_mode` | 下拉 | 跟随参考音频 | 跟随参考音频 / 情绪向量 / 情绪参考音频 |
| `emotion_type` | 下拉 | calm | happy / angry / sad / afraid / disgusted / melancholic / surprised / calm，仅「情绪向量」生效 |
| `emotion_strength` | FLOAT | 0.6 | 0–1，仅「情绪向量」生效 |
| `emotion_audio_path` | STRING | 空 | 仅「情绪参考音频」使用，节点会先上传得到 `emotionPath` |
| `auto_split` | BOOLEAN | True | 见下文长文本 |
| `api_key` | STRING | 空 | 留空读环境变量 `VOICE_API_KEY` |

**节点内置的参数保护**（控制台会给出中文提示，而不是让请求静默失效）：

- `style` 选「方言与多语言」时，情绪参数不生效 → 提示「该模式不支持情绪控制」，请求里不带 `genre` / `ext`。
- `target_speech` 是 ja / es / ar 等非 V2.0 支持语言而 `style` 选了 V2.0 → 提示「该语言将自动切到多语言模式」。
- 方言 / 多语言链路 `speed` 超过 1.5 → 按上限下发并提示。

---

## 长文本自动分段（auto_split）

- ≤ 250 字：直接合成。
- 超过时：先按自然段切；段落仍超 250 字则按句末标点（。！？；）切，目标每段 150–250 字，**不在句中切断**。
- 用同一个 `audio_id`、同一组参数**顺序**合成（不并发，语气更连贯），标准库 `wave` 拼接，段间插 0.3 秒静音。
- 各段采样率 / 声道 / 位深不一致时以第一段为准并报错，**不做静默重采样**。
- 任一段失败：已完成分段保留在 `output/voiceclone/_segments/`（按文本 + 参数哈希命名），报出失败的是第几段及服务端原因；**重跑自动跳过已完成分段，不重复扣额度**。
- 执行前控制台会打印「共 N 段、约 M 字符，将消耗等量额度」。

输出文件在 `ComfyUI/output/voiceclone/`，命名 `{时间戳}_{taskId}.wav`（服务端返回 mp3 时按实际扩展名）。

---

## 调试表

| 现象 | 原因 | 处理 |
|---|---|---|
| `sign无效` / `会员已过期` | 密钥错误或套餐到期 | 到服务商开发者后台重新获取密钥 |
| `code=1001` | 单次超 10,000 字符 | 打开 `auto_split` |
| `暂不支持该语言` | `target_speech` 不在枚举内 | 选「自动 / 不传」，并把 `style` 设为「方言与多语言」 |
| 搜不到节点 | 目录层级不对或未重启 | 确认在 `custom_nodes/comfyui-voiceclone-tts/`，重启 ComfyUI |
| 节点无输出 | 未接输出节点 | 接 PreviewAudio / SaveAudio，或用「一键合成」节点（已设为输出节点） |
| 情绪没变化 | `style` 不是 V2.5 | 情绪控制仅「V2.5 情绪版」支持 |
| Windows 路径报文件不存在 | 反斜杠转义 | 用正斜杠 `/`，如 `D:/voice/ref.wav` |
| 选择已有音色下拉是空的 | 启动时还没配密钥 | 配好环境变量后重启 ComfyUI；或勾选 `refresh` 执行一次再重开节点菜单 |
| 输出 AUDIO 报「没有 torchaudio」 | 精简环境缺 torchaudio | 改用 `file_path` 输出接下游，或安装 torchaudio |

---

## 密钥安全

- 读取顺序：**节点输入框 → 环境变量 `VOICE_API_KEY` → 报错**。
- ⚠️ **导出 `workflow.json` 时，填在输入框里的密钥会被一起带出去。** 要分享工作流请把 `api_key` 留空、改用环境变量。输入框已设为密码样式（不明文回显）。
- 节点日志不打印完整密钥，只保留前 4 位。

---

## 合规声明

仅可克隆**本人声音或已获得明确授权的声音**。请勿用于伪造他人身份、诈骗、诽谤或任何违反当地法律法规的用途。生成的音频依规定带有 AI 标识。具体条款以所用语音服务商的声音克隆规则为准。

---

## 多站点

站点差异全部收敛在仓库根目录的 `brand.json`（`base_url`、节点显示名前缀、环境变量名、文档链接、克隆规则链接），代码只维护一份。私有化联调可用环境变量 `VOICE_API_BASE` 覆盖 `base_url`。

## 接口文档

REST 接口与 OpenAPI 3.0 规范请查阅所用语音服务商的开发者文档。

## License

MIT
