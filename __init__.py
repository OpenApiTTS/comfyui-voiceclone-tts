"""ComfyUI VoiceClone TTS —— 声音克隆与语音合成节点包。

放进 ComfyUI/custom_nodes/ 重启即可用，无需 pip install。
"""

from .voiceclone import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
