import json
from itertools import islice

from openai import OpenAI

from config import AppConfig
from transcribe import TranscriptSegment
from text_safety import sanitize_utf8_text

TRANSLATION_SYSTEM_MESSAGE = (
    "你是专业字幕翻译助手。输出必须是合法 JSON，"
    "只能返回翻译结果，不要添加解释、备注或代码块。"
)
MAX_MISSING_ITEM_RETRIES = 2
TERM_REPLACEMENTS = (
    ("站立飘发球", "站飘发球"),
    ("站立飘球", "站飘发球"),
    ("站飘球", "站飘发球"),
    ("跳飘球", "跳飘发球"),
)


def _chunked(items: list[TranscriptSegment], size: int):
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _build_prompt(scene: str, batch: list[TranscriptSegment]) -> str:
    safe_scene = sanitize_utf8_text(scene)
    payload = [{"id": item.index, "text": sanitize_utf8_text(item.text)} for item in batch]
    return f"""
你是一名专业字幕翻译，需要把输入英文翻译成适合中文字幕阅读的自然中文。
翻译情景：{safe_scene}

要求：
1. 自然达意优先，中文要顺口、准确、适合字幕阅读。
2. 不得漏译、误译，不得擅自扩写或改变事实。
3. 结合上下文理解同批次内容里的指代、语气、情绪和场景术语，再决定措辞。
4. 保留人物称呼、专有名词、URL、站点名、术语和语气强弱；必要时用更自然的中文表达同样意思。
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


def _request_translation_content(
    client: OpenAI,
    scene: str,
    batch: list[TranscriptSegment],
    config: AppConfig,
) -> str:
    completion = client.chat.completions.create(
        model=config.llm_model,
        temperature=config.llm_temperature,
        response_format={"type": "json_object"},
        messages=build_translation_messages(scene, batch),
    )
    return sanitize_utf8_text(completion.choices[0].message.content or "")


def _normalize_translation_terminology(text: str) -> str:
    normalized = sanitize_utf8_text(text).strip()
    for source, target in TERM_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    return normalized


def _parse_translation_mapping(content: str) -> dict[int, str]:
    parsed = json.loads(content)
    items = parsed.get("items", parsed if isinstance(parsed, list) else None)
    if not isinstance(items, list):
        raise ValueError(f"模型返回格式无法解析: {content}")

    mapping: dict[int, str] = {}
    for item in items:
        if "id" not in item or "translation" not in item:
            continue
        try:
            item_id = int(item["id"])
        except (TypeError, ValueError):
            continue

        translation = _normalize_translation_terminology(str(item["translation"]))
        if translation:
            mapping[item_id] = translation
    return mapping


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
        pending_batch = list(batch)
        mapping: dict[int, str] = {}
        last_content = ""

        for _ in range(MAX_MISSING_ITEM_RETRIES + 1):
            last_content = _request_translation_content(client, scene, pending_batch, config)
            batch_mapping = _parse_translation_mapping(last_content)

            for segment in pending_batch:
                translation = batch_mapping.get(segment.index)
                if translation:
                    mapping[segment.index] = translation

            pending_batch = [segment for segment in batch if segment.index not in mapping]
            if not pending_batch:
                break

        if pending_batch:
            missing_ids = ", ".join(str(segment.index) for segment in pending_batch)
            raise ValueError(
                f"模型返回中缺少第 {missing_ids} 条翻译，请重试。原始返回: {last_content}"
            )

        translations.extend(mapping[segment.index] for segment in batch)

    if len(translations) != len(segments):
        raise ValueError("翻译数量与识别片段数量不一致。")

    return translations
