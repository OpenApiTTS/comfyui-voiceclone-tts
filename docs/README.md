# 截图

全部在 Docker 里的 ComfyUI v0.37.0 真机环境拍摄（见 `../../comfyui-docker/`），深色主题、中文界面。

| 文件 | 内容 | 状态 |
|---|---|---|
| `node-upload.png` | 上传音色节点 | ✅ |
| `node-tts.png` | 合成语音节点（V2.5 + 四川话 + sad 情绪向量，文本里带 `#0.5#` 停顿标记） | ✅ |
| `node-oneclick.png` | 一键合成节点 | ✅ |
| `node-list.png` | 选择已有音色节点（下拉里是账号下的真实音色） | ✅ |
| `../../my-front/public/images/comfyui-voiceclone-nodes.webp` | 整张画布（multi_role 工作流） | ✅ 已接进 /developer/ 文档页 |

## 重拍方法

截图不是手工截的，是用浏览器驱动 ComfyUI 前端 API 建节点 → 定位 → 截屏 → 按节点包围盒裁剪。
规格：单节点图四周留 28px 余量、缩放 1.6–2.2 倍；画布图 1600×900 视口导出 webp。
拍之前记得在设置里关掉 minimap（`Comfy.Minimap.Visible`）和画布统计角标（`Comfy.Graph.CanvasInfo`），并保持 `api_key` 输入框为空。
