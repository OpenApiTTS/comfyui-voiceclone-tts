# -*- coding: utf-8 -*-
"""ComfyUI 节点定义：上传音色 / 选择已有音色 / 合成语音 / 一键合成。"""

import hashlib
import json
import os
import time

from . import audio as au
from . import client
from .brand import BRAND, display
from .split import split_text

CATEGORY = "audio/VoiceClone"

# ---------------------------------------------------------------- 枚举与映射

STYLES = ["V2.5 情绪版", "V2.0 极速", "方言与多语言"]
STYLE_CODE = {"V2.0 极速": "1", "V2.5 情绪版": "2", "方言与多语言": "3"}

AUTO_SPEECH = "自动 / 不传"
TARGET_SPEECHES = [
    "mandarin", AUTO_SPEECH, "english", "yue", "nan", "sichuan", "northeast",
    "henan", "shaanxi", "ja", "ko", "es", "fr", "de", "ru", "pt", "it",
    "th", "vi", "id", "ms", "ar", "hi", "tr",
]

EMOTION_MODES = ["跟随参考音频", "情绪向量", "情绪参考音频"]
EMOTION_GENRE = {"跟随参考音频": 0, "情绪向量": 1, "情绪参考音频": 2}
EMOTION_TYPES = ["calm", "happy", "angry", "sad", "afraid", "disgusted",
                 "melancholic", "surprised"]

# 方言 / 多语言链路模型语速上限
DIALECT_SPEED_CAP = 1.5
# 这些语言在 V2.0 链路上不可用，服务端会强制改写 style
NON_V2_LANGS = {"ja", "ko", "es", "fr", "de", "ru", "pt", "it",
                "th", "vi", "id", "ms", "ar", "hi", "tr"}

REF_MIN_SECONDS = 3.0
REF_MAX_SECONDS = 60.0

KEY_TOOLTIP = ("留空则读环境变量 %s。注意：导出 workflow.json 时输入框里的密钥会被一起带出去，"
               "分享工作流请用环境变量。" % BRAND["env_key"])


# ---------------------------------------------------------------- 输出目录

def _output_root():
    try:
        import folder_paths
        base = folder_paths.get_output_directory()
    except Exception:
        base = os.path.join(os.getcwd(), "output")
    path = os.path.join(base, BRAND["output_subdir"])
    os.makedirs(path, exist_ok=True)
    return path


def _cache_root():
    path = os.path.join(_output_root(), "_segments")
    os.makedirs(path, exist_ok=True)
    return path


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def _ext_from_url(url, default=".wav"):
    name = url.split("?")[0].rsplit("/", 1)[-1]
    ext = os.path.splitext(name)[1].lower()
    return ext if ext in (".wav", ".mp3", ".m4a", ".flac", ".ogg") else default


# ---------------------------------------------------------------- 参数组装

def build_payload(text, audio_id, style, target_speech, speed,
                  emotion_mode, emotion_type, emotion_strength,
                  emotion_path="", notes=None):
    """组装 /tts 请求体，并把参数保护的提示写进 notes。"""
    notes = notes if notes is not None else []
    style_code = STYLE_CODE[style]

    if target_speech != AUTO_SPEECH and style_code == "1" and target_speech in NON_V2_LANGS:
        notes.append("target_speech=%s 在 V2.0 极速链路不可用，该语言将自动切到多语言模式（style=3）。"
                     % target_speech)
        style_code = "3"

    payload = {
        "content": text,
        "audioId": audio_id,
        "style": style_code,          # 必须是字符串，传数字会报类型错误
    }
    if target_speech != AUTO_SPEECH:
        payload["targetSpeech"] = target_speech

    speed = round(float(speed), 1)
    if style_code == "3" and speed > DIALECT_SPEED_CAP:
        notes.append("方言 / 多语言链路语速上限为 %.1f，已按上限下发（原值 %.1f）。"
                     % (DIALECT_SPEED_CAP, speed))
        speed = DIALECT_SPEED_CAP
    payload["speed"] = speed

    # 情绪控制仅 V2.5 支持；其余链路不带 genre / ext，避免请求静默失效
    if style_code != "2":
        if EMOTION_GENRE[emotion_mode] != 0:
            notes.append("该模式不支持情绪控制（情绪仅 V2.5 情绪版可用），本次请求不带 genre / ext。")
        return payload

    genre = EMOTION_GENRE[emotion_mode]
    if genre == 1:
        payload["genre"] = 1
        payload["ext"] = {emotion_type: round(float(emotion_strength), 2)}
    elif genre == 2:
        if not emotion_path:
            raise client.VoiceApiError("情绪参考音频模式需要 emotion_audio_path，请填写本地音频路径。")
        payload["genre"] = 2
        payload["emotionPath"] = emotion_path
    return payload


def _segment_cache_path(payload):
    """按文本 + 参数哈希缓存分段，重跑时跳过已完成分段、不重复扣额度。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return os.path.join(_cache_root(), hashlib.sha256(blob).hexdigest()[:32] + ".wav")


def _synthesize_once(payload, dest, api_key):
    task_id, voice_url = client.tts(payload, api_key=api_key)
    path = client.download(voice_url, dest + _ext_from_url(voice_url), api_key=api_key)
    return task_id, path


def synthesize(payload, api_key, auto_split=True, log=print):
    """返回 (最终音频路径, 最后一个 task_id, 分段数)。"""
    segments = split_text(payload["content"]) if auto_split else [payload["content"]]
    if not segments:
        raise client.VoiceApiError("text 不能为空。")

    if len(segments) == 1:
        payload = dict(payload, content=segments[0])
        dest = os.path.join(_output_root(), "%s_" % _stamp())
        task_id, path = _synthesize_once(payload, dest, api_key)
        final = os.path.join(_output_root(), "%s_%s%s"
                             % (_stamp(), task_id or "seg", os.path.splitext(path)[1]))
        os.replace(path, final)
        return final, task_id, 1

    total_chars = sum(len(s) for s in segments)
    log("[VoiceClone] 共 %d 段、约 %d 字符，将消耗等量额度。" % (len(segments), total_chars))

    wavs, last_task = [], ""
    for idx, seg in enumerate(segments, 1):
        seg_payload = dict(payload, content=seg)
        cached = _segment_cache_path(seg_payload)
        if os.path.exists(cached):
            log("[VoiceClone] 第 %d/%d 段命中缓存，跳过。" % (idx, len(segments)))
            wavs.append(cached)
            continue
        try:
            task_id, path = _synthesize_once(seg_payload, os.path.splitext(cached)[0] + ".raw", api_key)
        except client.VoiceApiError as e:
            raise client.VoiceApiError(
                "第 %d/%d 段合成失败：%s（前 %d 段已完成并缓存，重跑时会自动跳过）"
                % (idx, len(segments), e, len(wavs)), getattr(e, "code", None))
        last_task = task_id or last_task
        wav = au.ensure_wav(path)
        if wav != cached:
            os.replace(wav, cached)
        wavs.append(cached)
        log("[VoiceClone] 第 %d/%d 段完成。" % (idx, len(segments)))

    final = os.path.join(_output_root(), "%s_%s.wav" % (_stamp(), last_task or "merged"))
    au.concat_wavs(wavs, final)
    return final, last_task, len(segments)


def _emit_notes(notes):
    for n in notes:
        print("[VoiceClone] 提示：%s" % n)


# ---------------------------------------------------------------- 节点 A

class VoiceCloneUploadVoice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "", "multiline": False,
                                    "tooltip": "音色名，留空则用「音色_时间戳」避免重名"}),
            },
            "optional": {
                "audio_path": ("STRING", {"default": "", "multiline": False,
                                          "tooltip": "本地音频路径，3–60 秒干声；Windows 请用正斜杠 /"}),
                "audio": ("AUDIO", {"tooltip": "也可直接接 LoadAudio 的输出"}),
                "describe": ("STRING", {"default": "", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False,
                                       "password": True, "tooltip": KEY_TOOLTIP}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("audio_id",)
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "上传参考音频创建音色，返回 audio_id"

    def run(self, name, audio_path="", audio=None, describe="", api_key=""):
        name = (name or "").strip() or ("音色_%s" % _stamp())
        path = (audio_path or "").strip().replace("\\", "/")

        if not path and audio is not None:
            path = au.save_comfy_audio(audio, os.path.join(_output_root(), "ref_%s.wav" % _stamp()))
        if not path:
            raise client.VoiceApiError("请填写 audio_path 或接入 AUDIO 输入。")
        if not os.path.isfile(path):
            raise client.VoiceApiError("文件不存在：%s（Windows 路径请用正斜杠 /）" % path)

        # 本地先校验时长，不满足直接报错，不发请求
        duration = au.probe_duration(path)
        if duration is not None and not (REF_MIN_SECONDS <= duration <= REF_MAX_SECONDS):
            raise client.VoiceApiError(
                "参考音频时长 %.1f 秒，需在 %.0f–%.0f 秒之间（推荐 3–10 秒清晰干声）。"
                % (duration, REF_MIN_SECONDS, REF_MAX_SECONDS))

        print("[VoiceClone] 上传音色「%s」，密钥 %s"
              % (name, client.mask_key(client.resolve_key(api_key))))
        return (client.reference_upload(path, name, describe, api_key=api_key),)


# ---------------------------------------------------------------- 节点 B

_VOICE_CACHE = {"items": [], "loaded": False}


def _voice_choices(refresh=False):
    if refresh or not _VOICE_CACHE["loaded"]:
        try:
            _VOICE_CACHE["items"] = client.reference_list()
            _VOICE_CACHE["loaded"] = True
        except Exception as e:
            print("[VoiceClone] 音色列表拉取失败：%s" % e)
            return _VOICE_CACHE["items"]
    return _VOICE_CACHE["items"]


class VoiceCloneVoiceList:
    @classmethod
    def INPUT_TYPES(cls):
        names = [it["name"] for it in _voice_choices()] or ["（未加载，请勾选 refresh 后重新执行）"]
        return {
            "required": {
                "voice": (names, {"tooltip": "账号下已有的音色，下拉选择"}),
                "refresh": ("BOOLEAN", {"default": False,
                                        "tooltip": "勾选后本次执行重新拉取列表；刷新完需重开节点菜单才能看到新项"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "multiline": False,
                                       "password": True, "tooltip": KEY_TOOLTIP}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("audio_id", "name")
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "列出账号下已有音色，输出 audio_id"

    @classmethod
    def IS_CHANGED(cls, voice, refresh, api_key=""):
        return time.time() if refresh else voice

    def run(self, voice, refresh=False, api_key=""):
        items = _voice_choices(refresh=refresh)
        for it in items:
            if it["name"] == voice:
                return (it["audioId"], it["name"])
        raise client.VoiceApiError(
            "账号下找不到音色「%s」。勾选 refresh 重新执行以刷新列表，或用「上传音色」节点新建。" % voice)


# ---------------------------------------------------------------- 节点 C

class VoiceCloneTTS:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "audio_id": ("STRING", {"default": "", "forceInput": True}),
                "style": (STYLES, {"default": "V2.5 情绪版"}),
                "target_speech": (TARGET_SPEECHES, {"default": "mandarin"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
                "emotion_mode": (EMOTION_MODES, {"default": "跟随参考音频"}),
                "emotion_type": (EMOTION_TYPES, {"default": "calm",
                                                 "tooltip": "仅 emotion_mode=情绪向量 时生效"}),
                "emotion_strength": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05,
                                               "tooltip": "仅 emotion_mode=情绪向量 时生效"}),
                "auto_split": ("BOOLEAN", {"default": True,
                                           "tooltip": "超过 250 字自动分段、顺序合成后拼接"}),
            },
            "optional": {
                "emotion_audio_path": ("STRING", {"default": "", "multiline": False,
                                                  "tooltip": "仅 emotion_mode=情绪参考音频 时使用"}),
                "api_key": ("STRING", {"default": "", "multiline": False,
                                       "password": True, "tooltip": KEY_TOOLTIP}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "file_path", "task_id")
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "把文本合成为指定音色的语音"

    def run(self, text, audio_id, style, target_speech, speed, emotion_mode,
            emotion_type, emotion_strength, auto_split,
            emotion_audio_path="", api_key=""):
        text = (text or "").strip()
        if not text:
            raise client.VoiceApiError("text 不能为空。")
        if not (audio_id or "").strip():
            raise client.VoiceApiError("audio_id 不能为空，请接「上传音色」或「选择已有音色」节点。")

        emotion_path = ""
        if EMOTION_GENRE[emotion_mode] == 2 and STYLE_CODE[style] == "2":
            local = (emotion_audio_path or "").strip().replace("\\", "/")
            if not os.path.isfile(local):
                raise client.VoiceApiError("情绪参考音频不存在：%s" % local)
            emotion_path = client.upload_emotion_audio(local, api_key=api_key)

        notes = []
        payload = build_payload(text, audio_id.strip(), style, target_speech, speed,
                                emotion_mode, emotion_type, emotion_strength,
                                emotion_path, notes)
        _emit_notes(notes)

        path, task_id, count = synthesize(payload, api_key, auto_split=auto_split)
        print("[VoiceClone] 完成：%s（%d 段）" % (path, count))
        return (au.to_comfy_audio(path), path, task_id)


# ---------------------------------------------------------------- 节点 D

class VoiceCloneOneClick:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_audio_path": ("STRING", {"default": "", "multiline": False,
                                                    "tooltip": "参考音频，3–60 秒干声"}),
                "voice_name": ("STRING", {"default": "", "multiline": False,
                                          "tooltip": "音色名；同名音色已存在时直接复用，不重复上传"}),
                "text": ("STRING", {"default": "", "multiline": True}),
                "style": (STYLES, {"default": "V2.5 情绪版"}),
                "target_speech": (TARGET_SPEECHES, {"default": "mandarin"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
                "auto_split": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "multiline": False,
                                       "password": True, "tooltip": KEY_TOOLTIP}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "file_path", "audio_id")
    FUNCTION = "run"
    CATEGORY = CATEGORY
    OUTPUT_NODE = True
    DESCRIPTION = "参考音频 + 文本，一个节点出音频"

    def run(self, reference_audio_path, voice_name, text, style, target_speech,
            speed, auto_split, api_key=""):
        name = (voice_name or "").strip() or ("音色_%s" % _stamp())

        audio_id = ""
        for it in client.reference_list(api_key=api_key):
            if it["name"] == name:
                audio_id = it["audioId"]
                print("[VoiceClone] 复用已有音色「%s」，不重复上传。" % name)
                break

        if not audio_id:
            audio_id = VoiceCloneUploadVoice().run(name, reference_audio_path, api_key=api_key)[0]

        notes = []
        payload = build_payload(text.strip(), audio_id, style, target_speech, speed,
                                "跟随参考音频", "calm", 0.6, "", notes)
        _emit_notes(notes)

        path, _, count = synthesize(payload, api_key, auto_split=auto_split)
        print("[VoiceClone] 完成：%s（%d 段）" % (path, count))
        return (au.to_comfy_audio(path), path, audio_id)


NODE_CLASS_MAPPINGS = {
    "VoiceCloneUploadVoice": VoiceCloneUploadVoice,
    "VoiceCloneVoiceList": VoiceCloneVoiceList,
    "VoiceCloneTTS": VoiceCloneTTS,
    "VoiceCloneOneClick": VoiceCloneOneClick,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceCloneUploadVoice": display("上传音色"),
    "VoiceCloneVoiceList": display("选择已有音色"),
    "VoiceCloneTTS": display("合成语音"),
    "VoiceCloneOneClick": display("一键合成"),
}
