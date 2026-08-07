---
title: Git CLI
category: service-reference
last-updated: 2026-02-21
---

# Git CLI

**Command:** `copilot git`
**Source:** `copilot_cli/services/git/`

## Purpose

Git repository operations via GitPython — clone, pull, status, add, and commit.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `git clone` | Clone a repository | `--url`, `--path`, `--branch` |
| `git pull` | Pull latest changes | `--path`, `--remote`, `--branch` |
| `git status` | Show working tree status | `--path` |
| `git add` | Stage files | `--path`, `--files` |
| `git commit` | Commit staged changes | `--path`, `--message`, `--author` |

## Examples

```bash
copilot git clone --url https://github.com/org/repo.git --path ./repo
copilot git pull --path ./repo
copilot git status --path ./repo
copilot git add --path ./repo --files "*.py"
copilot git commit --path ./repo --message "Update config"
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GIT_USER_NAME` | Default git author name | `copilot` |
| `GIT_USER_EMAIL` | Default git author email | `dev@example.com` |
