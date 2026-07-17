---
title: Discord Handoffs
category: service
last-updated: 2026-07-02
---

# 22 — Discord Handoffs

Discord handoffs and tmux bridge control for active local Codex or Claude Code
sessions.

This service is for a session that already started in a terminal. When the user
says something like "let me know on Discord" or "I'm stepping away," the
`UserPromptSubmit` hook creates or reuses one Discord thread and arms away-mode.
If the current terminal is already tmux-backed, that same session becomes the
Discord-controllable session. If the current terminal is a normal non-tmux
Codex/Claude session, the hook automatically launches a tmux-backed bridge
continuation, delivers the user's prompt into it, and tells the original
terminal that the bridged continuation is taking over. When the bridged assistant
reaches a stopping point, the `Stop` hook posts status to Discord and releases
the terminal.

Only when the bridge cannot be launched does the hook fall back to a
`NOT-BRIDGED` notify-only / notification-only thread.

It does not start unrelated cloud sessions from Discord.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Bot token used to create threads, read replies, and send fallback messages |
| `DISCORD_CHANNEL_ID` | Yes | Parent channel where handoff threads are created |
| `DISCORD_ALLOWED_USER_IDS` | Yes | Comma-separated Discord user IDs allowed to steer handoffs |
| `DISCORD_WEBHOOK_URL` | No | Webhook used for branded outbound posts when available |
| `DISCORD_WEBHOOK_USERNAME` | No | Override webhook display name |
| `DISCORD_WEBHOOK_AVATAR_URL` | No | Override webhook avatar |
| `COPILOT_DISCORD_LEGACY_BLOCKING_WAIT` | No | Opt-in escape hatch for the old blocking Stop-hook wait loop |
| `COPILOT_DISCORD_WAIT_TIMEOUT` | No | Seconds for the legacy blocking wait; ignored by the default non-blocking flow |

Hook shims export `COPILOT_ENV_FILE` automatically when the installer can find
the CLI Copilot `.env`.

## Install

Install once per machine for both supported local harnesses:

```bash
COPILOT_ENV_FILE=/path/to/cli-copilot/.env \
  copilot discord install-hook --scope user --harness all
```

This writes:

```text
~/.claude/hooks/discord-user-prompt-submit.sh
~/.claude/hooks/discord-stop.sh
~/.claude/settings.json

~/.codex/hooks/discord-user-prompt-submit.sh
~/.codex/hooks/discord-stop.sh
~/.codex/hooks.json
```

Claude Code uses the installed hooks directly. Codex may require a one-time
`/hooks` review because non-managed command hooks are intentionally trust-gated
by Codex. After the hook definitions are trusted, they run on future sessions.

## User Flow

For the normal user experience:

1. Install and start the worker once with `copilot discord bridge install` and
   `copilot discord bridge start`.
2. Start Codex or Claude Code normally in the project.
3. Say "I'm stepping away" or "let me know on Discord."
4. If the session is not already bridge-backed, the hook launches a bridged
   continuation automatically and injects the current prompt into that tmux pane.
5. Reply in the Discord thread to inject the next instruction into the
   tmux-backed local session.
6. Reply `/return`, `/resume-local`, or `/stop` to end away-mode.

Manual `copilot discord bridge launch codex` / `claude` remains available for
debugging or for users who prefer to start directly inside tmux.

If auto-launch fails, the hooks still post stopping points to Discord without
blocking the terminal. Those fallback threads are `NOT-BRIDGED` /
notification-only: replies will not reach the local terminal, and
`copilot discord doctor` flags them so they cannot be mistaken for controllable
sessions.

The model no longer needs to remember to run `notify`, `listen`, or `wait`.
Those commands remain available for manual debugging and fallback. `notify` is
thread-only: with `--thread-id` it posts to that thread, and without
`--thread-id` it may reuse the single open handoff for the current working
directory. It refuses parent-channel posts. To start a new Discord conversation,
use `handoff`, which creates a new thread.

## Commands

```bash
copilot discord health

copilot discord install-hook --scope user --harness all
copilot discord uninstall-hook --scope user --harness all

copilot discord hook user-prompt-submit --harness codex
copilot discord hook stop --harness codex

copilot discord bridge install
copilot discord bridge start
copilot discord bridge launch codex
copilot discord bridge launch claude
copilot discord bridge status
copilot discord doctor

copilot discord handoff "Manual handoff." --title "Codex handoff" --harness codex
copilot discord notify "Manual update." --thread-id 1234567890123456789
copilot discord listen 1234567890123456789 --timeout 0
copilot discord wait 1234567890123456789 --timeout 0
copilot discord ack 1234567890123456789 1234567890123456790
copilot discord close 1234567890123456789 --message "Closing this handoff."
```

## Thread Model

Each active local session gets one Discord thread under `DISCORD_CHANNEL_ID`.
The local registry lives at `~/.copilot-cli/discord/handoffs.json`.

```text
Discord thread A -> local Codex session A
Discord thread B -> local Claude Code session B
Discord thread C -> local Codex session C
```

Replies are routed by thread ID, filtered to `DISCORD_ALLOWED_USER_IDS`, and read
after the registry's `last_seen_message_id`.

In bridge mode, the launchd worker holds the Gateway connection and injects
authorized thread replies into the registered tmux pane. The Stop hook is only
responsible for mirroring clean assistant output back to Discord. `listen` and
`wait` remain manual debugging commands; `wait` is the REST polling fallback.

## Escape Hatches

```bash
COPILOT_DISCORD_LOOP=off
COPILOT_SAFETY=off
```

Either variable lets a terminal session stop normally without the Discord bridge.
