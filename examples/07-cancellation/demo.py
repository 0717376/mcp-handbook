"""Демонстрация notifications/cancelled на живом сервере.

Порядок действий:
    1. Поднимает rest_api.py в фоне (как в 02/demo.py).
    2. Запускает server.py как MCP-subprocess по stdio.
    3. Проходит handshake.
    4. Делает tools/call slow_cancellable_import(count=10) с progressToken.
    5. Читает STOP_AFTER_PROGRESSES progress-уведомлений — шлёт cancel.
    6. Читает, пока не придёт финальный ответ с id тула.
    7. Дренирует stderr сервера, печатает [cleanup]-строку из try/finally.

Запуск:
    uv run python demo.py

Inspector для этой главы не подходит: он умеет принимать notifications/cancelled,
но сам отправлять их — нет (в UI кнопки cancel нет). Поэтому возвращаемся
к паттерну 01-hello: минимальный скрипт, который делает всё руками.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
REST_PORT = 8765

CALL_ID = 2                    # id нашего tools/call — он же requestId в cancel
PROGRESS_TOKEN = "demo-cancel"
STOP_AFTER_PROGRESSES = 2      # сколько progress читать до отмены


def pretty(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def step(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def send(proc: subprocess.Popen, message: dict) -> None:
    print(f"\n>>> Клиент → сервер:\n{pretty(message)}")
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict | None:
    line = proc.stdout.readline()
    if not line:
        return None
    obj = json.loads(line)
    print(f"\n<<< Сервер → клиент:\n{pretty(obj)}")
    return obj


def wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)
    raise RuntimeError(f"REST API на :{port} не поднялся за {timeout}s")


def main() -> None:
    print(f"→ Запускаю rest_api.py на :{REST_PORT}...")
    rest = subprocess.Popen(
        ["uv", "run", "python", str(HERE / "rest_api.py")],
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(REST_PORT)
        print("→ REST готов. Поднимаю MCP-сервер.")

        mcp_proc = subprocess.Popen(
            ["uv", "run", "python", str(HERE / "server.py")],
            cwd=HERE,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            step("Шаг 1. Handshake — initialize → response → initialized")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "demo", "version": "0.1.0"},
                },
                "id": 1,
            })
            recv(mcp_proc)
            send(mcp_proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            step(f"Шаг 2. tools/call slow_cancellable_import(count=10), id={CALL_ID}")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "slow_cancellable_import",
                    "arguments": {"count": 10},
                    "_meta": {"progressToken": PROGRESS_TOKEN},
                },
                "id": CALL_ID,
            })

            step(f"Шаг 3. Читаем {STOP_AFTER_PROGRESSES} progress — пусть тул поработает")
            seen = 0
            while seen < STOP_AFTER_PROGRESSES:
                msg = recv(mcp_proc)
                if msg and msg.get("method") == "notifications/progress":
                    seen += 1

            step(f"Шаг 4. notifications/cancelled с requestId={CALL_ID}")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {
                    "requestId": CALL_ID,
                    "reason": "demo: пользователь устал ждать",
                },
            })

            step(f"Шаг 5. Читаем, пока не придёт финальный ответ для id={CALL_ID}")
            while True:
                msg = recv(mcp_proc)
                if msg is None:
                    break
                if msg.get("id") == CALL_ID:
                    break

            step("Готово — закрываем stdin сервера")
        finally:
            try:
                mcp_proc.stdin.close()
            except Exception:
                pass
            try:
                mcp_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()

            # Ищем [cleanup]-строку нашего try/finally в stderr.
            # FastMCP туда же пишет свои логи, поэтому фильтруем по префиксу.
            stderr_text = ""
            if mcp_proc.stderr is not None:
                try:
                    stderr_text = mcp_proc.stderr.read()
                except Exception:
                    pass
            cleanup_lines = [line for line in stderr_text.splitlines() if "[cleanup]" in line]
            if cleanup_lines:
                print("\n--- stderr сервера: try/finally сработал после отмены ---")
                for line in cleanup_lines:
                    print(f"  {line}")
    finally:
        rest.terminate()
        try:
            rest.wait(timeout=3)
        except subprocess.TimeoutExpired:
            rest.kill()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
