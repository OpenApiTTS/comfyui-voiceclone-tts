# ComfyUI VoiceClone TTS

Voice cloning and text-to-speech **inside the ComfyUI canvas**. Upload 3–60 seconds of clean reference audio to create a voice, then synthesize any text in that voice. Outputs native `AUDIO`, so it wires straight into PreviewAudio / SaveAudio or a digital-human lip-sync node. Supports 14 Chinese dialects and 100+ languages, 8-dimension emotion control, and automatic long-text segmentation with seamless concatenation. Built for **anime-drama dubbing, multi-character short drama, digital humans and audiobooks**.

Keywords: ComfyUI, voice clone, voice cloning, text to speech, TTS, dialect, multi-character, anime dubbing, digital human.

> 中文说明：[README.md](README.md)

---

## Install in 30 seconds

No `pip install` required — Python 3 standard library only (torch / torchaudio come with ComfyUI).

**Option 1 — git clone**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/OpenApiTTS/comfyui-voiceclone-tts
# restart ComfyUI
```

**Option 2 — zip**

Unzip into `ComfyUI/custom_nodes/comfyui-voiceclone-tts/`. `custom_nodes/comfyui-voiceclone-tts/__init__.py` must exist — don't nest an extra folder. Restart ComfyUI.

**Option 3 — ComfyUI-Manager**

Manager → Install via Git URL → `https://github.com/OpenApiTTS/comfyui-voiceclone-tts` → Restart.

**API key** (recommended way):

```bash
export VOICE_API_KEY="your-key"          # macOS / Linux
$env:VOICE_API_KEY = "your-key"          # Windows PowerShell
```

Restart ComfyUI afterwards — environment variables are read at startup. Get a key from your voice service provider's developer console.

---

## Nodes

All under the `audio/VoiceClone` category.

| Node | What it does | Outputs |
|---|---|---|
| **Upload Voice** | Upload 3–60s reference audio to create a voice (duration validated locally before any request) | `audio_id` |
| **Voice List** | Dropdown of every voice on your account | `audio_id`, `name` |
| **TTS** | Text + `audio_id` → speech, with emotion / dialect / speed / auto-split | `audio`, `file_path`, `task_id` |
| **One-Click** | Reference audio + text in a single node (reuses an existing voice of the same name instead of re-uploading) | `audio`, `file_path`, `audio_id` |

---

## Example workflows

Drag any file from `workflows/` onto the canvas:

- `basic_tts.json` — One-Click → PreviewAudio.
- `multi_role.json` — two characters, one line each (one with `sad` emotion), each into a SaveAudio.

---

## Parameters (TTS node)

| Param | Type | Default | Notes |
|---|---|---|---|
| `text` | multiline | — | Required. Pause markers supported: `#0.3#` `#0.5#` `#1.0#` `#1.5#` `#2.0#` `#3.0#` |
| `audio_id` | STRING | — | From Upload Voice / Voice List |
| `style` | combo | V2.5 | V2.0 fast / V2.5 emotion / Dialect & multilingual. **Only V2.5 supports emotion.** |
| `target_speech` | combo | mandarin | mandarin, english, yue, nan, sichuan, northeast, henan, shaanxi, ja, ko, es, fr, de, ru, pt, it, th, vi, id, ms, ar, hi, tr, plus "auto / omit" |
| `speed` | FLOAT | 1.0 | 0.5–2.0, step 0.1. Dialect/multilingual pipeline caps at 1.5 — the node clamps and warns. |
| `emotion_mode` | combo | follow reference | follow reference / emotion vector / emotion reference audio |
| `emotion_type` | combo | calm | happy, angry, sad, afraid, disgusted, melancholic, surprised, calm — emotion-vector mode only |
| `emotion_strength` | FLOAT | 0.6 | 0–1, emotion-vector mode only |
| `emotion_audio_path` | STRING | empty | Emotion-reference mode only; uploaded automatically |
| `auto_split` | BOOLEAN | True | See below |
| `api_key` | STRING | empty | Falls back to `VOICE_API_KEY` |

**Built-in guards** (printed to the console in plain language instead of silently failing):

- Dialect/multilingual style → emotion params are dropped from the request, with a warning.
- A non-V2.0 language (ja / es / ar …) selected while style is V2.0 → auto-switched to multilingual, with a warning.
- `speed` above the dialect pipeline's 1.5 cap → clamped, with a warning.

---

## Long text (auto_split)

- ≤ 250 chars: synthesized in one call.
- Longer: split by paragraph first, then by sentence-ending punctuation, targeting 150–250 chars per segment — **never mid-sentence**.
- Segments are synthesized **sequentially** with the same `audio_id` and parameters (sequential keeps prosody consistent), concatenated with the stdlib `wave` module, with 0.3s of silence between them.
- Mismatched sample rate / channels / bit depth → error against the first segment's format. **No silent resampling.**
- If a segment fails, finished segments stay in `output/voiceclone/_segments/` (named by a hash of the text + params). The error names which segment failed and why; **re-running skips finished segments so you aren't charged twice**.
- Before running, the console prints "N segments, ~M characters, will consume the same amount of quota".

Output lands in `ComfyUI/output/voiceclone/` as `{timestamp}_{taskId}.wav` (or the actual extension when the server returns mp3).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `sign invalid` / membership expired | Wrong key or expired plan | Get a new key from the provider's developer console |
| `code=1001` | Over 10,000 chars in one call | Turn on `auto_split` |
| "language not supported" | `target_speech` outside the enum | Pick "auto / omit" and set `style` to dialect & multilingual |
| Nodes not found | Wrong folder depth or no restart | Confirm `custom_nodes/comfyui-voiceclone-tts/`, restart ComfyUI |
| Node produces nothing | No output node attached | Attach PreviewAudio / SaveAudio, or use One-Click (already an output node) |
| Emotion has no effect | `style` isn't V2.5 | Emotion control is V2.5-only |
| "File not found" on Windows | Backslash escaping | Use forward slashes: `D:/voice/ref.wav` |
| Voice List dropdown is empty | Key wasn't set at startup | Set the env var and restart; or tick `refresh`, run once, reopen the node menu |
| "torchaudio missing" on AUDIO output | Stripped-down environment | Use the `file_path` output instead, or install torchaudio |

---

## Key safety

- Resolution order: **node input → `VOICE_API_KEY` env var → error**.
- ⚠️ **Exporting `workflow.json` exports whatever you typed into the `api_key` field.** Leave it empty and use the environment variable before sharing a workflow. The field is rendered as a password input.
- Logs never print the full key — only the first 4 characters.

---

## Compliance

Clone only your own voice or a voice you have explicit permission to use. Do not use this for impersonation, fraud, defamation, or anything unlawful in your jurisdiction. Generated audio carries an AI marker as required. The binding terms are your voice service provider's own voice cloning policy.

---

## Multi-site

All site-specific values live in `brand.json` at the repo root (`base_url`, node display-name prefix, env var name, doc and policy links) — one codebase. `VOICE_API_BASE` overrides `base_url` for private deployments.

## API docs

REST endpoints and the OpenAPI 3.0 spec: see your voice service provider's developer documentation.

## License

MIT
