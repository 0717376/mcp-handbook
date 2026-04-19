# 11 — OAuth 2.1

HTTP-сервер из `10-http/` становится OAuth 2.1 resource server. Обязательные элементы по спеке 2025-06-18+:

- Discovery через `.well-known/oauth-protected-resource`.
- PKCE для authorization code flow.
- Dynamic client registration (RFC 7591).
- `Authorization: Bearer <token>` на всех MCP-запросах.
- Сценарий 401 → client идёт в authorization server → retry с токеном.

stdio-транспорт авторизацию не использует — там доверие даётся тем, кто запустил процесс.

_TBD: минимальный auth server (или интеграция с готовым — Keycloak в Docker), resource server, полный flow в wire-дампах._