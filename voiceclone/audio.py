"""音频工具：时长探测、wav 拼接、ComfyUI AUDIO 类型转换。

拼接只用标准库 wave。torch / torchaudio 是 ComfyUI 自带的，按需 import，
缺失时给出中文提示而不是抛 ImportError 堆栈。
"""

import os
import struct
import wave

SILENCE_SECONDS = 0.3


# --------------------------------------------------------------------------
# 时长探测
# --------------------------------------------------------------------------

_MPEG_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MPEG_BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_MPEG_RATES = {
    3: [44100, 48000, 32000, 0],   # MPEG1
    2: [22050, 24000, 16000, 0],   # MPEG2
    0: [11025, 12000, 8000, 0],    # MPEG2.5
}


def _mp3_duration(path):
    """解析第一帧头 + Xing/Info 帧计算时长；CBR 按文件大小估算。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(min(size, 256 * 1024))

    i = 0
    # 跳过 ID3v2
    if head[:3] == b"ID3" and len(head) > 10:
        tag = struct.unpack(">4B", head[6:10])
        i = 10 + (tag[0] << 21 | tag[1] << 14 | tag[2] << 7 | tag[3])

    while i + 4 <= len(head):
        if head[i] == 0xFF and (head[i + 1] & 0xE0) == 0xE0:
            b1, b2 = head[i + 1], head[i + 2]
            ver = (b1 >> 3) & 0x03
            layer = (b1 >> 1) & 0x03
            bitrate_idx = (b2 >> 4) & 0x0F
            rate_idx = (b2 >> 2) & 0x03
            if ver != 1 and layer == 1 and 0 < bitrate_idx < 15 and rate_idx != 3:
                table = _MPEG_BITRATES_V1_L3 if ver == 3 else _MPEG_BITRATES_V2_L3
                bitrate = table[bitrate_idx] * 1000
                sample_rate = _MPEG_RATES[ver][rate_idx]
                samples_per_frame = 1152 if ver == 3 else 576

                # Xing / Info（VBR）帧计数更准
                xing = head.find(b"Xing", i, i + 200)
                if xing < 0:
                    xing = head.find(b"Info", i, i + 200)
                if xing > 0 and xing + 12 <= len(head):
                    flags = struct.unpack(">I", head[xing + 4:xing + 8])[0]
                    if flags & 0x1:
                        frames = struct.unpack(">I", head[xing + 8:xing + 12])[0]
                        if frames and sample_rate:
                            return frames * samples_per_frame / float(sample_rate)
                if bitrate:
                    return (size - i) * 8 / float(bitrate)
            i += 1
        else:
            i += 1
    raise ValueError("不是可识别的 mp3 文件")


def probe_duration(path):
    """返回秒数；无法识别时返回 None（由调用方决定跳过校验）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as w:
                if w.getframerate():
                    return w.getnframes() / float(w.getframerate())
        except Exception:
            pass
    if ext == ".mp3":
        try:
            return _mp3_duration(path)
        except Exception:
            pass
    try:  # m4a 等交给 torchaudio
        import torchaudio
        info = torchaudio.info(path)
        if info.sample_rate:
            return info.num_frames / float(info.sample_rate)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# 格式转换
# --------------------------------------------------------------------------

def ensure_wav(path):
    """非 wav 转成同目录 wav（拼接需要）。返回 wav 路径。"""
    if os.path.splitext(path)[1].lower() == ".wav":
        return path
    target = os.path.splitext(path)[0] + ".wav"
    if os.path.exists(target):
        return target
    try:
        import torchaudio
    except ImportError:
        raise RuntimeError(
            "服务端返回的是 %s，拼接需要先转成 wav，但当前环境没有 torchaudio。"
            "请关闭 auto_split 单段合成，或在 ComfyUI 环境中安装 torchaudio。"
            % os.path.splitext(path)[1]
        )
    waveform, sample_rate = torchaudio.load(path)
    torchaudio.save(target, waveform, sample_rate)
    return target


def concat_wavs(paths, dest, silence_seconds=SILENCE_SECONDS):
    """顺序拼接 wav，段间插 0.3 秒静音。

    采样率 / 声道 / 位深不一致时以第一段为准并报错，不做静默重采样。
    """
    if not paths:
        raise RuntimeError("没有可拼接的分段")
    if len(paths) == 1:
        return paths[0]

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    first = None
    with wave.open(dest, "wb") as out:
        for idx, path in enumerate(paths):
            with wave.open(path, "rb") as src:
                params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                if first is None:
                    first = params
                    out.setnchannels(params[0])
                    out.setsampwidth(params[1])
                    out.setframerate(params[2])
                elif params != first:
                    raise RuntimeError(
                        "第 %d 段的音频格式与第 1 段不一致"
                        "（第 1 段 %d 声道/%d 位/%d Hz，第 %d 段 %d 声道/%d 位/%d Hz）。"
                        "已保留各分段文件，请重跑该段或改用单段合成。"
                        % (idx + 1, first[0], first[1] * 8, first[2],
                           idx + 1, params[0], params[1] * 8, params[2])
                    )
                else:
                    silent = int(first[2] * silence_seconds)
                    out.writeframes(b"\x00" * (silent * first[0] * first[1]))
                out.writeframes(src.readframes(src.getnframes()))
    return dest


def to_comfy_audio(path):
    """转成 ComfyUI 原生 AUDIO：{"waveform": [B, C, T] float tensor, "sample_rate": int}"""
    try:
        import torch
    except ImportError:
        raise RuntimeError("当前环境没有 torch，无法输出 AUDIO 类型；请改用 file_path 输出。")

    try:
        import torchaudio
        waveform, sample_rate = torchaudio.load(path)
        return {"waveform": waveform.unsqueeze(0), "sample_rate": int(sample_rate)}
    except ImportError:
        pass

    wav_path = path if os.path.splitext(path)[1].lower() == ".wav" else None
    if wav_path is None:
        raise RuntimeError(
            "当前环境没有 torchaudio，无法解码 %s；请改用 file_path 输出接下游节点。"
            % os.path.splitext(path)[1]
        )

    import array
    with wave.open(wav_path, "rb") as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())

    typecode = {1: "B", 2: "h", 4: "i"}.get(width)  # 8-bit wav 是无符号
    if typecode is None:
        raise RuntimeError("不支持的 wav 位深：%d 位" % (width * 8))
    samples = array.array(typecode)
    samples.frombytes(raw)

    tensor = torch.tensor(list(samples), dtype=torch.float32)
    if width == 1:
        tensor = (tensor - 128.0) / 128.0
    else:
        tensor = tensor / float(1 << (width * 8 - 1))
    tensor = tensor.reshape(-1, channels).t().unsqueeze(0)
    return {"waveform": tensor, "sample_rate": int(rate)}


def save_comfy_audio(audio, dest):
    """把上游 AUDIO 输入落盘成 wav，供上传接口使用。"""
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if waveform.dim() == 3:
        waveform = waveform[0]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        import torchaudio
        torchaudio.save(dest, waveform.cpu(), sample_rate)
        return dest
    except ImportError:
        pass

    clipped = waveform.cpu().clamp(-1.0, 1.0)
    ints = (clipped * 32767.0).to("cpu").short().t().reshape(-1).tolist()
    with wave.open(dest, "wb") as out:
        out.setnchannels(waveform.shape[0])
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(struct.pack("<%dh" % len(ints), *ints))
    return dest
