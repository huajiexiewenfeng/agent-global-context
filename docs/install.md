# Install

## 1. Copy Skills

Copy the skills you want into your agent skill directory.

For Codex-style local skills, one common location is:

```text
~/.agents/skills/
```

Install the MVP skills:

```text
skills/agent-global-context/
skills/agent-global-context-recall/
skills/agent-global-context-commit/
skills/agent-global-context-capture/
skills/agent-global-context-review/
```

## 2. Create Memory Root

Create the default global context directory:

```text
~/.agent-global-context/
```

Copy the template files from:

```text
templates/memory/
```

## 3. Add Agent Instruction

Add an instruction to your agent profile or project instructions:

```text
At the start of substantial work, use agent-global-context-recall to load relevant global context. When the user asks to remember something or compress a session, use agent-global-context-commit.
When auto capture is enabled, use agent-global-context-capture to write strong candidate memories to staging only. Use agent-global-context-review to promote, reject, or expire staged candidates.
```

## 4. Customize

Edit:

```text
~/.agent-global-context/config.yaml
~/.agent-global-context/index.md
```

Add project mappings for your local workspaces.
