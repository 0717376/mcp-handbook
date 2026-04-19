"""Интерактивный разбор: demo поднимает REST-сервис и MCP-сервер,
проходит handshake и вызывает несколько tool'ов, печатая весь wire-трафик.

Запуск:
    uv run python demo.py

Ожидает свободные порт 8765 (REST) и пустую stdin (для MCP через subprocess).
Handshake-шаги здесь сокращены — полный разбор см. в 01-hello/.
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
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        try:
            step("Шаг 1. Handshake (initialize + initialized)")
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
            print("\n(initialized — notification, ответа нет. Переходим в operation phase.)")
            wait()

            step("Шаг 2. tools/list — ловим annotations")
            send(mcp_proc, {"jsonrpc": "2.0", "method": "tools/list", "id": 2})
            recv(mcp_proc)
            wait()

            step("Шаг 3. create_task — POST, видим structuredContent как Task")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_task",
                    "arguments": {"title": "write chapter 02"},
                },
                "id": 3,
            })
            response = recv(mcp_proc)
            created_id = response["result"]["structuredContent"]["id"]
            wait()

            step("Шаг 4. list_tasks — readOnly, structuredContent как массив")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "list_tasks", "arguments": {}},
                "id": 4,
            })
            recv(mcp_proc)
            wait()

            step("Шаг 5. delete_task — destructive + idempotent")
            send(mcp_proc, {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "delete_task",
                    "arguments": {"task_id": created_id},
                },
                "id": 5,
            })
            recv(mcp_proc)
            wait()

            step("Готово. Завершаем оба процесса.")
        finally:
            try:
                mcp_proc.stdin.close()
            except Exception:
                pass
            try:
                mcp_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()
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
