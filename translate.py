import json
from itertools import islice

from openai import OpenAI

from config import AppConfig
from transcribe import TranscriptSegment

TRANSLATION_SYSTEM_MESSAGE = (
    "你是专业字幕翻译助手。输出必须是合法 JSON，"
    "只能返回翻译结果，不要添加解释、备注或代码块。"
)


def _chunked(items: list[TranscriptSegment], size: int):
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _build_prompt(scene: str, batch: list[TranscriptSegment]) -> str:
    payload = [{"id": item.index, "text": item.text} for item in batch]
    return f"""
你是一名专业字幕翻译，需要把输入英文翻译成适合中文字幕阅读的自然中文。
翻译情景：{scene}

要求：
1. 自然达意优先，中文要顺口、准确、适合字幕阅读。
2. 不得漏译、误译，不得擅自扩写或改变事实。
3. 结合上下文理解同批次内容里的指代、语气、情绪和场景术语，再决定措辞。
4. 保留人物称呼、专有名词、术语和语气强弱；必要时用更自然的中文表达同样意思。
5. 只输出翻译，不要加括号说明、解释性补充或自由发挥。
6. 返回 JSON 对象，格式必须是 {{"items": [{{"id": 1, "translation": "..."}}]}}。
7. 输出条目数量必须和输入完全一致，id 必须一一对应。

待翻译内容：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def build_translation_messages(scene: str, batch: list[TranscriptSegment]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TRANSLATION_SYSTEM_MESSAGE},
        {"role": "user", "content": _build_prompt(scene, batch)},
    ]


def translate_segments(
    segments: list[TranscriptSegment],
    scene: str,
    config: AppConfig,
) -> list[str]:
    if not config.llm_api_key:
        raise ValueError("缺少 LLM_API_KEY 环境变量，请先在 .env 中配置 API Key。")
    if not config.llm_base_url:
        raise ValueError("缺少 LLM_BASE_URL 环境变量，请先在 .env 中配置模型接口地址。")
    if not config.llm_model:
        raise ValueError("缺少 LLM_MODEL 环境变量，请先在 .env 中配置模型名称。")

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
            messages=build_translation_messages(scene, batch),
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
