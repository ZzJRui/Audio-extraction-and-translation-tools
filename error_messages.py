def build_gui_error_message(exc: Exception) -> tuple[str, str | None]:
    if isinstance(exc, FileNotFoundError):
        return (
            f"处理失败：找不到音频文件：{exc}",
            "建议：请检查路径是否正确，Windows 路径可以直接粘贴，带引号也可以。",
        )
    if isinstance(exc, PermissionError):
        return (
            "处理失败：文件正在被占用，或者当前程序没有访问权限。",
            "建议：请关闭占用该文件的程序后重试。",
        )
    if isinstance(exc, ValueError):
        return (f"处理失败：{exc}", None)
    return (
        f"处理失败：{exc}",
        "建议：请重试一次；如果问题持续存在，再把错误提示发给我。",
    )


def parse_backend_error(stderr_text: str) -> tuple[str, str | None]:
    text = stderr_text.strip() or "后端返回了空错误信息。"
    if text.startswith("FileNotFoundError:"):
        return build_gui_error_message(FileNotFoundError(text.split(":", 1)[1].strip()))
    if text.startswith("ValueError:"):
        return build_gui_error_message(ValueError(text.split(":", 1)[1].strip()))
    lowered = text.lower()
    if "authentication" in lowered or "api key" in lowered or "unauthorized" in lowered:
        return ("处理失败：翻译接口认证失败。", "建议：请检查 .env 里的 LLM_API_KEY 是否正确。")
    if "timeout" in lowered or "connection" in lowered:
        return ("处理失败：无法连接翻译服务。", "建议：请检查当前网络，或稍后再试。")
    if "rate limit" in lowered or "quota" in lowered:
        return ("处理失败：翻译接口请求过于频繁，或当前额度不足。", "建议：请稍后重试，或检查 API 账户额度。")
    if "ffmpeg" in lowered:
        return ("处理失败：未检测到可用的 ffmpeg。", "建议：请确认项目的 ffmpeg 工具目录完整，或把 ffmpeg 加入 PATH。")
    return (f"处理失败：{text}", "建议：请检查网络、模型配置和依赖环境后重试。")
