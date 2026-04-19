"""
Интерактивный разбор lifecycle: запускает server.py как subprocess и шлёт ему
по очереди initialize → initialized → tools/list → tools/call, pretty-printing
каждое сообщение в обе стороны.

Запуск:
    uv run python demo.py

Между шагами — пауза до Enter, чтобы не читать всё залпом.
Нули внешних зависимостей (stdlib).
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def pretty(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def step(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def wait() -> None:
    try:
        input("\n[Enter] — следующий шаг, Ctrl-C — выход: ")
    except EOFError:
        pass


def send(proc: subprocess.Popen, message: dict) -> None:
    print(f"\n>>> Клиент → сервер:\n{pretty(message)}")
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict | None:
    line = proc.stdout.readline()
    if not line:
        return None
    response = json.loads(line)
    print(f"\n<<< Сервер → клиент:\n{pretty(response)}")
    return response


def main() -> None:
    proc = subprocess.Popen(
        ["uv", "run", "python", str(HERE / "server.py")],
        cwd=HERE,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    try:
        step("Шаг 1. initialize — клиент предлагает версию и capabilities")
        send(proc, {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "demo", "version": "0.1.0"},
            },
            "id": 1,
        })
        recv(proc)
        wait()

        step("Шаг 2. notifications/initialized — клиент: готов. Без ответа.")
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        print("\n(Это notification: у неё нет поля id, ответа сервер не шлёт.)")
        wait()

        step("Шаг 3. tools/list — клиент спрашивает каталог tool'ов")
        send(proc, {"jsonrpc": "2.0", "method": "tools/list", "id": 2})
        recv(proc)
        wait()

        step("Шаг 4. tools/call — клиент зовёт echo(text='hello, MCP')")
        send(proc, {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hello, MCP"}},
            "id": 3,
        })
        recv(proc)
        wait()

        step("Готово. Закрываем stdin сервера — сервер увидит EOF и завершится.")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
