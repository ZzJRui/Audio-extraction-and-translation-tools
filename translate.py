import json
from itertools import islice

from openai import OpenAI

from config import AppConfig
from transcribe import TranscriptSegment


def _chunked(items: list[TranscriptSegment], size: int):
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _build_prompt(scene: str, batch: list[TranscriptSegment]) -> str:
    payload = [{"id": item.index, "text": item.text} for item in batch]
    return f"""
你是一名专业字幕翻译，需要把输入文本翻译成适合字幕阅读的自然中文。

翻译情景：{scene}

要求：
1. 保留原意，不要遗漏信息。
2. 结合情景使用合适术语和表达风格。
3. 语言自然、简洁，适合字幕阅读。
4. 只翻译文本，不补充解释，不加括号说明。
5. 返回 JSON 对象，格式必须是 {{"items": [{{"id": 1, "translation": "..."}}]}}。
6. 输出条目数量和输入完全一致，id 必须对应。

待翻译内容：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def translate_segments(
    segments: list[TranscriptSegment],
    scene: str,
    config: AppConfig,
) -> list[str]:
    if not config.llm_api_key:
        raise ValueError(
            "缺少 LLM_API_KEY 环境变量，请先配置 DeepSeek 或 OpenAI 兼容接口的 API Key。"
        )

    client = OpenAI(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
    )

    translations: list[str] = []
    for batch in _chunked(segments, config.translation_batch_size):
        completion = client.chat.completions.create(
            model=config.llm_model,
            temperature=config.llm_temperature,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "你是专业字幕翻译助手，输出必须是合法 JSON。",
                },
                {
                    "role": "user",
                    "content": _build_prompt(scene, batch),
                },
            ],
        )

        content = completion.choices[0].message.content or ""
        parsed = json.loads(content)
        items = parsed.get("items", parsed if isinstance(parsed, list) else None)
        if not isinstance(items, list):
            raise ValueError(f"模型返回格式无法解析: {content}")

        mapping = {
            int(item["id"]): str(item["translation"]).strip()
            for item in items
            if "id" in item and "translation" in item
        }

        for segment in batch:
            translation = mapping.get(segment.index)
            if not translation:
                raise ValueError(
                    f"模型返回中缺少第 {segment.index} 条翻译，请重试。原始返回: {content}"
                )
            translations.append(translation)

    if len(translations) != len(segments):
        raise ValueError("翻译数量与识别片段数量不一致。")

    return translations
