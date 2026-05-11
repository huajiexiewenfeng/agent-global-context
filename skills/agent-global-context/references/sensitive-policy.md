# Sensitive Policy

## Rule

Sensitive or high-impact personal memory must not be silently committed.

## Requires Confirmation

Ask before writing:

- Real names, contact information, addresses, accounts.
- Government IDs, financial, medical, family, or private relationship details.
- Secrets, tokens, passwords, private keys, credentials.
- Company secrets or confidential business information.
- Psychological, personality, motivation, or emotional-state inferences.

## Never Store

Do not store:

- Passwords.
- API keys.
- Private keys.
- Authentication tokens.
- Recovery codes.

If the user asks to store secrets, explain that this memory system is Markdown-based and not suitable for secret storage.

## Confirmation Prompt

Use a short prompt:

```text
This may be sensitive long-term context. Should I write it to the global context, stage it for review, or skip it?
```

