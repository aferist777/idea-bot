"""Model access. Anthropic Messages API when a key is set, OpenRouter as the fallback.

Web search on steps 3-4 is Anthropic's server-side tool: no scraping on our side,
and the citations come back attached to the answer.
"""
import asyncio

import aiohttp

from .config import (ANTHROPIC_API_KEY, ANTHROPIC_MODEL, MOCK_LLM, OPENROUTER_API_KEY,
                     OPENROUTER_MODEL, OPENROUTER_URL, WEB_MAX_USES)


class LLMError(Exception):
    pass


# --------------------------------------------------------------------------- anthropic
_client = None

WEB_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_MAX_USES}
MAX_PAUSE_RESTARTS = 4     # a long search turn can stop with stop_reason="pause_turn"


def _anthropic():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _collect(content, text_parts, sources):
    for block in content:
        kind = getattr(block, "type", "")
        if kind == "text":
            text_parts.append(block.text)
        elif kind == "web_search_tool_result":
            body = getattr(block, "content", None)
            # a failed search returns a single error object here instead of a list
            if isinstance(body, list):
                for r in body:
                    url = getattr(r, "url", None)
                    if url and url not in [u for _, u in sources]:
                        sources.append((getattr(r, "title", None) or url, url))


async def _anthropic_chat(system, user, max_tokens, online):
    import anthropic

    client = _anthropic().with_options(timeout=600.0 if online else 300.0)
    kwargs = {
        "model": ANTHROPIC_MODEL,
        # thinking shares this budget, so leave the model room above the prose we want
        "max_tokens": max(4000, max_tokens * 3),
        "system": system,
        "thinking": {"type": "adaptive"},
    }
    if online:
        kwargs["tools"] = [WEB_TOOL]

    messages = [{"role": "user", "content": user}]
    text_parts, sources = [], []
    try:
        for _ in range(MAX_PAUSE_RESTARTS + 1):
            resp = await client.messages.create(messages=messages, **kwargs)
            if resp.stop_reason == "refusal":
                raise LLMError("модель отказалась отвечать на этот запрос")
            _collect(resp.content, text_parts, sources)
            if resp.stop_reason != "pause_turn":
                break
            # server tool hit its per-turn limit; resend so it can finish
            messages = [{"role": "user", "content": user},
                        {"role": "assistant", "content": resp.content}]
        else:
            raise LLMError("поиск не завершился за отведённые попытки")
    except anthropic.AuthenticationError:
        raise LLMError("ANTHROPIC_API_KEY отклонён — проверь ключ")
    except anthropic.RateLimitError:
        raise LLMError("лимит запросов Anthropic исчерпан, попробуй через минуту")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic {e.status_code}: {str(e)[:200]}")
    except anthropic.APIConnectionError as e:
        raise LLMError(f"сеть до Anthropic не отвечает: {str(e)[:150]}")

    text = "\n".join(t.strip() for t in text_parts if t.strip()).strip()
    if not text:
        raise LLMError("пустой ответ модели")
    return text, sources


# --------------------------------------------------------------------------- openrouter
def _or_sources(msg):
    out = []
    for a in msg.get("annotations") or []:
        cite = a.get("url_citation") or {}
        url = cite.get("url")
        if url and url not in [u for _, u in out]:
            out.append((cite.get("title") or url, url))
    return out


async def _openrouter_chat(system, user, max_tokens, online):
    payload = {
        "model": f"{OPENROUTER_MODEL}:online" if online else OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}",
               "Content-Type": "application/json", "X-Title": "idea-bot"}
    timeout = aiohttp.ClientTimeout(total=240 if online else 120)

    last = ""
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(OPENROUTER_URL, json=payload, headers=headers) as r:
                    body = await r.json()
                    if r.status != 200:
                        raise LLMError(str(body.get("error") or body)[:300])
            msg = body["choices"][0]["message"]
            text = (msg.get("content") or "").strip()
            if not text:
                raise LLMError("пустой ответ модели")
            return text, _or_sources(msg)
        except Exception as e:
            last = str(e)[:300]
            if attempt == 2:
                break
            await asyncio.sleep(2 + attempt * 3)
    raise LLMError(last or "unknown error")


async def chat(system, user, max_tokens=1600, online=False, temperature=None):
    """Returns (text, sources). `temperature` is ignored - current models reject it."""
    if MOCK_LLM:
        from . import mock
        return await mock.chat(system, user, max_tokens, online)
    if ANTHROPIC_API_KEY:
        return await _anthropic_chat(system, user, max_tokens, online)
    if OPENROUTER_API_KEY:
        return await _openrouter_chat(system, user, max_tokens, online)
    raise LLMError("нет ключа: заполни ANTHROPIC_API_KEY в .env")
