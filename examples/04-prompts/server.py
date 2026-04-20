"""MCP-сервер с тремя prompts. Идея главы — prompts выбирает пользователь
(slash-команды), а не модель. Сравнение семантики с tools — в README.md.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import AssistantMessage, Message, UserMessage

mcp = FastMCP("prompts")


@mcp.prompt(title="Review code")
def review_code(code: str) -> str:
    """Провести подробное ревью фрагмента кода: баги, неидиоматичные места, конкретные правки."""
    return (
        "Посмотри код ниже. Укажи баги, неидиоматичные места и граничные случаи. "
        "Предлагай конкретные правки, а не общие рассуждения.\n\n"
        f"```python\n{code}\n```"
    )


@mcp.prompt(title="Debug an error")
def debug_error(error: str) -> list[Message]:
    """Заготовка разговора про разбор ошибки: user кидает стектрейс, assistant задаёт уточнения."""
    return [
        UserMessage("Я ловлю такую ошибку:"),
        UserMessage(error),
        AssistantMessage(
            "Давай сузим. Какой командой ты это воспроизвёл, "
            "и раньше этот код работал? Были ли недавние обновления зависимостей?"
        ),
    ]


@mcp.prompt(title="Commit message")
def commit_message(diff: str, tone: str = "нейтральный") -> str:
    """Составить commit-сообщение для diff.

    `tone` — опциональный: "нейтральный" (по умолчанию), "сухой" или "шутливый".
    """
    return (
        f"Напиши commit-сообщение для diff ниже. Тон: {tone}. "
        "Формат conventional commits, первая строка ≤72 символов, тело переносится по 80.\n\n"
        f"```diff\n{diff}\n```"
    )


if __name__ == "__main__":
    mcp.run()
