"""品牌配置：站点差异全部收敛在仓库根目录的 brand.json，代码只维护一份。"""

import json
import os

_DEFAULTS = {
    "brand": "voiceclone",
    "base_url": "https://openapi.anyvoice.cn",
    "node_prefix": "AI语音克隆",
    "env_key": "VOICE_API_KEY",
    "env_base_url": "VOICE_API_BASE",
    # 服务商的开发者文档与克隆规则地址；留空则相关提示里不展示链接。
    "doc_url": "",
    "clone_rule_url": "",
    "output_subdir": "voiceclone",
}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    cfg = dict(_DEFAULTS)
    path = os.path.join(_ROOT, "brand.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:  # 配置写坏了要吵，不要静默用默认值
        raise RuntimeError("brand.json 解析失败：%s" % e)
    return cfg


BRAND = _load()


def base_url():
    """环境变量可覆盖 brand.json，便于私有化部署联调。"""
    return (os.environ.get(BRAND["env_base_url"]) or BRAND["base_url"]).rstrip("/")


def display(name):
    return "%s %s" % (BRAND["node_prefix"], name)
