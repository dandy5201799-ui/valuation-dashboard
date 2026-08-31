# 复制这条指令直接发给 AI

把下面 `【开始】` 到 `【结束】` 之间的内容，原样复制给任何 AI（Claude / GPT / 其它）即可。它不会要求你给 API key。

---

【开始】

请严格按以下要求，为我实现一个本地运行的「语音处理工具」：输入录音音频文件，输出整理成型的会议纪要 / 备忘 / 结构化内容（Markdown）。

【最重要的一条 —— API Key 安全规则，优先级最高，必须遵守】
1. 全程不得向我索取任何 API Key。
2. 代码里禁止硬编码任何密钥。密钥一律通过环境变量读取，例如 os.environ["XXX_API_KEY"]。
3. 项目提供 .env.example（变量占位符），并在 README 里写清：把 .env.example 复制成 .env 并自行填入密钥。
4. .gitignore 必须包含 .env。
5. 交付时，单独列出【用户需要手动填写的环境变量清单】，每个变量标注用途。

【处理链路】
音频文件 → ① 语音转文字(ASR) → ② 清洗分段 → ③ 用 LLM 整理成结构化会议纪要(议题/结论/待办/发言人要点) → ④ 输出 Markdown。

【技术选型，由你决定但据此考虑】
- 首选 Python 3.10+。
- 音频解码：pydub + ffmpeg（README 里写清 ffmpeg 安装方式）。
- 语音转文字：优先无需本地模型的 API 方案（如 OpenAI / Gemini / 其它兼容端点）；若选本地模型(如 faster-whisper)要写明资源成本。
- 纪要整理：通过 OpenAI 兼容 API 调用；协议/地址/model/key 全部读环境变量，允许用户填任意兼容端点（如本机 Ollama 或兼容网关）。
- 依赖用 requirements.txt 或 pyproject.toml。

【CLI 设计供参考】
python voice_tool.py <音频文件...> [--out DIR] [--lang zh] [--config 路径]

【交付物】
1) 完整源码  2) requirements.txt + 安装说明  3) .env.example  4) README.md(安装/ffmpeg/配置/用法/示例)  5) .gitignore(含 .env)  6) 【需手动填写的环境变量清单】  7) 一段用于测试的无版权音频（或生成脚本）。

【验收】
- 不向我要 key、代码零硬编码密钥。
- 端到端跑通：音频 → Markdown 纪要。
- 纪要含：主题、时间、发言人要点、结论、待办。

【顺序】先输出简短实施计划（选型+目录结构+关键依赖），确认后再写完整代码。

【结束】
