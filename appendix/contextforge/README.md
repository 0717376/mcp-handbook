# Appendix — ContextForge case study

[IBM ContextForge (`mcp-context-forge`)](https://github.com/IBM/mcp-context-forge) — популярный open-source MCP-gateway: агрегирует несколько downstream MCP-серверов и выставляет клиенту единый endpoint. Цель раздела — на конкретике показать, где gateway ломает capability negotiation из §3 README. После этого любой другой gateway можно оценивать по тому же чек-листу.

Разбор по состоянию на `main`-ветку репо на момент написания. Конкретные номера строк могут сдвинуться — ищи по именам файлов и функций.

## 1. `initialize` возвращает захардкоженные capabilities

Когда клиент подключается и шлёт `initialize`, CF **не опрашивает downstream-серверы** в момент handshake. Вместо этого возвращает статический объект — всегда один и тот же, одинаковый для всех клиентов и независимо от того, какие серверы подключены:

```python
# mcpgateway/cache/session_registry.py:2164-2173
capabilities = ServerCapabilities(
    prompts={"listChanged": True},
    resources={"subscribe": True, "listChanged": True},
    tools={"listChanged": True},
    logging={},
    completions={},
    # experimental — только для OAuth
)
```

Downstream-серверы опрашиваются один раз при регистрации в gateway (фоновый процесс, `mcpgateway/services/gateway_service.py:3885`), результаты складываются в БД (`gateway.capabilities`) и клиенту **не транслируются**.

**Последствие.** Клиент не имеет способа узнать, что у реальных downstream-серверов есть. Если один из них не умеет `subscribe` по resources — CF всё равно заявит клиенту, что умеет. Если другой поддерживает что-то за пределами этого списка — клиент не узнает.

## 2. `sampling/createMessage` не проксируется — мокается

Когда downstream-сервер хочет попросить клиента сгенерировать ответ через LLM (паттерн из `examples/08-sampling/`), он шлёт `sampling/createMessage`. CF его **перехватывает и отвечает заглушкой**:

```python
# mcpgateway/handlers/sampling.py:221
# TODO: Implement actual model sampling - currently returns mock response
```

Переворот симметрии протокола, который в §3 подан как ключевая фича MCP, **через CF не работает**. Downstream-серверы, рассчитывающие на sampling как агентный паттерн, через CF не функционируют — и клиент об этом узнаёт только по странностям в поведении.

## 3. `roots/list` возвращает roots gateway, а не клиентские

Другой server→client request: `roots/list`, чтобы downstream-сервер понял, какие директории ему разрешено трогать. В CF этот endpoint обслуживается **собственным** `root_service`, который возвращает roots самого gateway, а не спрашивает upstream-клиента:

```
mcpgateway/main.py:8173 → root_service.list_roots()
```

Результат: downstream-сервер получает не те roots, которые видит пользователь.

## 4. `*/list_changed` notifications молча дропаются

`notifications/tools/list_changed`, `notifications/resources/list_changed`, `notifications/prompts/list_changed` определены в моделях (`mcpgateway/common/models.py:1085-1108`), но в основном dispatcher'е попадают в catch-all ветку и возвращают `method not found` (`mcpgateway/main.py:10464-10465`).

То есть если downstream-сервер обновил каталог инструментов — клиент об этом не узнает и будет держать в контексте устаревший `tools/list`.

## 5. `elicitation/create` — частично работает

Единственный server→client request, который CF реально маршрутизирует — `elicitation/create`, через `mcpgateway/services/elicitation_service.py`. Роутинг идёт по session affinity, **без явной проверки capability'и клиента**. Если клиент не заявил `elicitation` в своих capabilities, CF всё равно попробует передать ему запрос — клиент просто ответит ошибкой. Мягче, чем молчаливый drop, но концептуально не лучше.

## 6. Client capabilities игнорируются почти полностью

`client_capabilities`, которые клиент прислал в `initialize`, сохраняются в сессии (`session_registry.py:2149-2151`), но используются только для детекции поддержки elicitation (`session_registry.py:2201-2214`). Про `sampling` и `roots` CF не спрашивает и поведение не меняет.

## Что из этого выносим

1. **Gateway — не прозрачный прокси.** Любой MCP-gateway, который встречаешь, оценивай по пунктам выше — шанс, что хотя бы один из них сломан, высокий.
2. **Для корпоративного деплоя** (централизованный OAuth + audit) CF тем не менее работоспособен: client→server направление (`tools/call`, `resources/read`, `prompts/get`) проксируется корректно. Но заявленный в `initialize` набор возможностей доверия не заслуживает.
3. **Для фич вокруг symmetry** (sampling, subscriptions, live обновления каталогов) через CF идти не стоит — либо подключайся к нужному MCP-серверу напрямую, либо принимай, что эти фичи не работают.
4. **Если пишешь свой gateway** — capability aggregation и честный forwarding server→client requests должны быть в первом релизе, не потом.

## TODO

- Добавить конкретные сценарии: «когда CF действительно помогает» (корп-прокси с OAuth, централизованный каталог, client→server без фич симметрии) vs «когда не стоит его ставить» (агентные паттерны с sampling, подписки на изменения resources, server-side elicitation как основной UX). По одному живому примеру на каждую сторону.

## Источники

- Репозиторий: [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge).
- Ключевые файлы: `mcpgateway/cache/session_registry.py`, `mcpgateway/handlers/sampling.py`, `mcpgateway/services/elicitation_service.py`, `mcpgateway/services/gateway_service.py`, `mcpgateway/main.py`.
- Разбор сделан по `main`-ветке. Открытые вопросы и частично-реализованные фичи см. в `CHANGELOG.md` и `FOLLOWUPS.md` репо.
