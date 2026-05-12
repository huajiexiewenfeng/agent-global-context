# Thinking Skills Chat Runtime Design

## Purpose

Build a lightweight server-side chat runtime that lets a WeChat Mini Program use the existing thinking skills as a safe emotional-support chatbot for close family members.

The product is not a server-side clone of Codex. It is a narrow chat service that loads selected skill instructions, manages conversation context, calls the OpenAI API from the server, and returns emotionally supportive responses to the Mini Program.

## Goals

- Provide a WeChat Mini Program chat experience for family users.
- Keep OpenAI API keys and WeChat secrets on the server only.
- Reuse the existing `thinking-router`, `emotional-support`, and `safety-boundary` skill behavior.
- Support short, warm, low-jargon emotional-support conversations.
- Detect crisis signals and switch to a safety-first response path.
- Allow the Mini Program to cache lightweight session state locally.
- Avoid storing full sensitive chat history on the server by default.

## Non-Goals

- Do not build a full Codex-compatible agent runtime.
- Do not expose shell, filesystem, code-editing, or developer tools to users.
- Do not implement diagnosis, therapy, medical advice, or professional mental-health treatment.
- Do not build payment, admin dashboards, or public user onboarding in the first version.
- Do not support every thinking skill in the first version.
- Do not store long-term psychological profiles.

## Recommended Approach

Implement a lightweight Node.js and TypeScript backend using Fastify. The backend exposes one primary chat endpoint for the WeChat Mini Program and calls the OpenAI Responses API from the server.

SQLite is enough for the first version if server-side storage is needed. The schema should be small and replaceable so the service can move to PostgreSQL later without changing the Mini Program API.

## System Architecture

```text
WeChat Mini Program
  -> Backend Chat API
    -> Request authentication
    -> Session handling
    -> Skill runtime
    -> Safety layer
    -> OpenAI model client
    -> Response post-processing
  -> WeChat Mini Program
```

## Main Request Flow

```text
1. Mini Program sends a message to POST /chat.
2. Backend verifies the request and resolves the user/session.
3. Backend loads the selected thinking skill instructions.
4. Safety layer checks for immediate risk signals.
5. If risk is detected, backend uses the safety response path.
6. If no risk is detected, backend uses emotional-support instructions.
7. Backend assembles model input with recent context or summary.
8. Backend calls the OpenAI Responses API.
9. Backend post-processes the reply for tone and safety.
10. Backend returns the assistant message to the Mini Program.
11. Backend optionally updates a lightweight session summary.
```

## API Surface

### `POST /chat`

Request:

```json
{
  "userId": "family-user-id",
  "sessionId": "local-session-id",
  "message": "User message",
  "recentMessages": [
    {
      "role": "user",
      "content": "Previous user message"
    },
    {
      "role": "assistant",
      "content": "Previous assistant message"
    }
  ]
}
```

Response:

```json
{
  "sessionId": "local-session-id",
  "message": {
    "role": "assistant",
    "content": "Assistant reply"
  },
  "safety": {
    "level": "normal",
    "reason": null
  }
}
```

The response should use a stable envelope from the beginning so the Mini Program can later support safety banners, retry behavior, or handoff suggestions without an API redesign.

## Session Strategy

The Mini Program may cache:

- `userId`
- `sessionId`
- recent visible chat messages
- local UI state
- user preferences

The Mini Program must not cache:

- OpenAI API keys
- WeChat AppSecret
- backend signing secrets
- long-term sensitive labels
- hidden safety classifications

The backend may store:

- session metadata
- short conversation summaries
- timestamps
- model usage metadata

The backend should not store full sensitive chat history by default. If full history is later required, it must be an explicit product decision with user-facing privacy language.

## Skill Runtime

The first version should support a fixed skill set:

- `thinking-router`
- `emotional-support`
- `safety-boundary`

The runtime should treat skill files as server-owned prompt assets. It should load them at startup or on demand, normalize them into model instructions, and keep application logic separate from skill text.

The first version can route most ordinary messages directly to `emotional-support`. `thinking-router` can be used as a lightweight classification step only when the message is ambiguous or when additional domains are added later.

## Safety Behavior

Safety checks happen before ordinary emotional-support generation.

If the user message suggests self-harm, harm to others, abuse, coercion, severe impairment, medical emergency, or immediate danger, the backend must switch to a safety-first response. That response should:

- avoid deep analysis
- avoid diagnosis
- avoid minimizing the situation
- encourage immediate real-world support
- suggest contacting trusted people or local emergency services when appropriate
- keep the tone calm, direct, and brief

The product must not present itself as therapy, diagnosis, medical care, or a replacement for professional support.

## Model Integration

The backend calls the OpenAI API using a server-side API key stored in environment variables.

Required environment variables:

```text
OPENAI_API_KEY
OPENAI_MODEL
```

Optional environment variables:

```text
DATABASE_URL
SESSION_SECRET
WECHAT_APP_ID
WECHAT_APP_SECRET
```

The first version should keep model selection configurable instead of hard-coding a model name throughout the codebase.

## Error Handling

The backend should return stable error shapes.

Expected error categories:

- invalid request body
- unauthorized request
- missing session
- model provider timeout
- model provider error
- safety response fallback
- internal server error

For model failures, the Mini Program should receive a gentle retryable message instead of raw provider errors.

## Privacy and Security

- Keep all provider keys on the backend.
- Never send OpenAI API keys, WeChat AppSecret, or backend secrets to the Mini Program.
- Use HTTPS in production.
- Configure the backend domain as a legal request domain in the WeChat Mini Program console.
- Avoid logging raw user messages in production by default.
- Redact sensitive fields from error logs.
- Add rate limits before sharing beyond the initial family users.

## Testing Strategy

Unit tests:

- request schema validation
- skill loading
- prompt assembly
- safety classification wrapper
- error response formatting

Integration tests:

- `POST /chat` normal emotional-support message
- `POST /chat` crisis-like message uses safety path
- model timeout returns stable fallback
- missing API key fails during startup or health check

Manual verification:

- send a normal family-support conversation from the Mini Program or API client
- confirm no API key appears in frontend code or network responses
- confirm sensitive provider errors are not shown to users
- confirm safety-like messages do not receive ordinary coaching replies

## First Milestone

The first milestone is a local backend MVP with:

- Fastify server
- `POST /chat`
- environment-based OpenAI configuration
- fixed emotional-support prompt assembly
- safety pre-check path
- local session handling
- basic tests
- README instructions for local setup

WeChat Mini Program integration can begin after this backend endpoint is stable.
