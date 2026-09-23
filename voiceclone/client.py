"""接口客户端：鉴权、HTTP、轮询、下载。仅依赖 Python 3 标准库。

与官方技能包 scripts/tts.py 同一套端点与参数推导规则；此处为 ComfyUI 侧的等价实现，
改接口时两边需同步。
"""

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .brand import BRAND, base_url

TIMEOUT = 120
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 600

STATUS_RUNNING = 1
STATUS_DONE = 2
STATUS_FAILED = 3


class VoiceApiError(Exception):
    """服务端返回的业务错误，msg 为服务端中文原因，原样抛给用户。"""

    def __init__(self, msg, code=None):
        self.code = code
        super().__init__("[code=%s] %s" % (code, msg) if code is not None else msg)


def mask_key(key):
    """日志里只保留前 4 位。"""
    if not key:
        return "(空)"
    return key[:4] + "****"


def resolve_key(api_key=""):
    """读取顺序：节点输入框 → 环境变量 → 报错。"""
    key = (api_key or "").strip()
    if key:
        return key
    key = (os.environ.get(BRAND["env_key"]) or "").strip()
    if key:
        return key
    msg = (
        "未找到 API 密钥。请在节点的 api_key 输入框填写，或设置环境变量 %s 后重启 ComfyUI。"
        % BRAND["env_key"]
    )
    if BRAND["doc_url"]:
        msg += "密钥在 %s 获取。" % BRAND["doc_url"]
    raise VoiceApiError(msg)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _url(path, query=None):
    url = base_url() + path
    if query:
        clean = {k: v for k, v in query.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url


def _open(req):
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        # 失败时 HTTP 码可能是 200 以外，但响应体仍是业务 JSON，先尝试解析
        body = e.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise VoiceApiError("HTTP %s：%s" % (e.code, body[:200].decode("utf-8", "replace")))
        raise VoiceApiError(payload.get("msg") or "请求失败", payload.get("code"))
    except urllib.error.URLError as e:
        raise VoiceApiError("网络不可达：%s（检查 %s 是否可访问）" % (e.reason, base_url()))


def _unwrap(raw):
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise VoiceApiError("响应不是合法 JSON：%s" % raw[:200].decode("utf-8", "replace"))
    # 失败时 HTTP 状态码可能仍是 200，永远先判 code
    code = payload.get("code")
    if code != 0:
        raise VoiceApiError(payload.get("msg") or "接口返回失败", code)
    return payload.get("data") or {}


def request_json(method, path, query=None, body=None, api_key=""):
    key = resolve_key(api_key)
    data = None
    headers = {"sign": key, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_url(path, query), data=data, headers=headers, method=method)
    with _open(req) as resp:
        return _unwrap(resp.read())


def request_multipart(path, fields, files, api_key=""):
    """files: [(field_name, filepath)]"""
    key = resolve_key(api_key)
    boundary = "----VoiceClone%s" % uuid.uuid4().hex
    buf = bytearray()

    def line(s):
        buf.extend(s.encode("utf-8"))
        buf.extend(b"\r\n")

    for name, value in fields.items():
        if value is None or value == "":
            continue
        line("--" + boundary)
        line('Content-Disposition: form-data; name="%s"' % name)
        line("")
        line(str(value))

    for name, filepath in files:
        filename = os.path.basename(filepath)
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        line("--" + boundary)
        line('Content-Disposition: form-data; name="%s"; filename="%s"' % (name, filename))
        line("Content-Type: " + ctype)
        line("")
        with open(filepath, "rb") as f:
            buf.extend(f.read())
        buf.extend(b"\r\n")

    line("--" + boundary + "--")

    req = urllib.request.Request(
        _url(path),
        data=bytes(buf),
        headers={
            "sign": key,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json",
        },
        method="POST",
    )
    with _open(req) as resp:
        return _unwrap(resp.read())


def download(url, dest, api_key=""):
    """语音下载地址同样需要带 sign。"""
    key = resolve_key(api_key)
    req = urllib.request.Request(url, headers={"sign": key})
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with _open(req) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return dest


# --------------------------------------------------------------------------
# 业务端点
# --------------------------------------------------------------------------

def reference_upload(filepath, name, describe="", api_key=""):
    data = request_multipart(
        "/api/third/reference/upload",
        {"name": name, "describe": describe},
        [("file", filepath)],
        api_key=api_key,
    )
    audio_id = data.get("audioId") or data.get("roleId")
    if not audio_id:
        raise VoiceApiError("上传成功但未返回 audioId，响应：%s" % json.dumps(data, ensure_ascii=False))
    return audio_id


def reference_list(api_key="", page_size=30, max_pages=10):
    """翻完所有页，漫剧账号音色数量常超过一页。"""
    items = []
    page = 1
    while page <= max_pages:
        data = request_json(
            "GET", "/api/third/reference/list",
            query={"page": page, "pageSize": page_size}, api_key=api_key,
        )
        batch = data.get("list") or []
        for it in batch:
            audio_id = it.get("audioId") or it.get("roleId")
            if audio_id:
                items.append({"audioId": audio_id, "name": it.get("name") or audio_id,
                              "describe": it.get("describe") or ""})
        total = data.get("total")
        if not batch or (isinstance(total, int) and len(items) >= total):
            break
        page += 1
    return items


def upload_emotion_audio(filepath, api_key=""):
    """情绪参考音频（genre=2），返回 emotionPath。"""
    data = request_multipart(
        "/api/third/file/uploadCustom", {}, [("file", filepath)], api_key=api_key,
    )
    path = data.get("emotionPath") or data.get("fileName") or data.get("path")
    if not path:
        raise VoiceApiError("情绪音频上传成功但未返回 emotionPath，响应：%s"
                            % json.dumps(data, ensure_ascii=False))
    return path


def tts(payload, api_key="", on_progress=None):
    """提交合成并拿到结果。

    1. 调 /tts/create 创建任务。
    2. 直接返回 status=2 时取 voiceUrl，不再轮询。
    3. status=1 用返回的 taskId 轮询 /tts/result，2 秒一次，不重新创建任务。
    4. status=3 或 code!=0 由 _unwrap / 下方抛出服务端中文 msg。
    """
    data = request_json("POST", "/api/third/tts/create", body=payload, api_key=api_key)

    status = data.get("status")
    task_id = data.get("taskId") or ""

    if status == STATUS_DONE and data.get("voiceUrl"):
        return task_id, data["voiceUrl"]
    if status == STATUS_FAILED:
        raise VoiceApiError(data.get("msg") or "合成失败", data.get("code"))
    if not task_id:
        raise VoiceApiError("接口未返回 taskId，无法继续轮询：%s" % json.dumps(data, ensure_ascii=False))

    return task_id, poll_result(task_id, api_key=api_key, on_progress=on_progress)


def poll_result(task_id, api_key="", on_progress=None):
    deadline = time.time() + POLL_TIMEOUT
    waited = 0.0
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
        data = request_json("GET", "/api/third/tts/result",
                            query={"taskId": task_id}, api_key=api_key)
        status = data.get("status")
        if status == STATUS_DONE and data.get("voiceUrl"):
            return data["voiceUrl"]
        if status == STATUS_FAILED:
            raise VoiceApiError(data.get("msg") or "合成失败", data.get("code"))
        if on_progress:
            on_progress(waited)
    raise VoiceApiError("轮询超过 %d 秒仍未完成，taskId=%s，可稍后用该 taskId 查询 /tts/result"
                        % (POLL_TIMEOUT, task_id))
