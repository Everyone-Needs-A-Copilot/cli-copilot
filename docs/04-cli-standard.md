# CLI understanding and creation standard

Status: required for new and changed first-party CLIs. Applies to standalone tools, integration command groups and maintained operator utilities. Aliases share a contract; retired tools, third-party executables, internal implementation scripts and test fixtures are recorded separately rather than silently counted as compliant.

A user or agent must be able to answer: **What is this for? What calls exist? Which call fits my intent? What do I pass? What happens? How do I know it worked? How do I recover?**

## Required surfaces

Every CLI has one maintained guide, linked from its README and root help. Use `CLI.md` beside the package README, or link an existing equivalent. Do not duplicate a manual solely to satisfy a filename convention. The guide contains these sections:

| Section | Required content |
|---|---|
| Purpose | Intended user, job, boundaries and when to choose another tool. |
| Setup and identity | Installation, executable/module, version or source revision, working directory, config precedence, required credential **names**, account/tenant selection and dependencies. No secret values. |
| Command discovery | Root and nested help syntax; a complete maintained or generated command tree, including aliases, optional integrations and availability conditions. |
| Intent and examples | Outcome → exact invocation → prerequisites/effects → observable result. Cover the main workflow and one failure/recovery path. Label placeholders. |
| Inputs and outputs | Argument/option types, required values, defaults and accepted values via command help/reference; stdin/files; stdout/stderr, structured output location and supported flags; exit behavior and output compatibility. Never imply universal `--json` when it is per-command or unsupported. |
| Effects and verification | Reads, local writes, remote writes, paid calls and destructive operations; preview/dry-run only where implemented; how to inspect the resulting state. A zero exit code alone is not proof of a business outcome. |
| Errors and recovery | Concrete failure → diagnostic → corrective action. Explain safe retry, partial completion and recovery limits where relevant. |
| Maintenance | Canonical source, how to regenerate/check references, and the checks that keep commands and examples accurate. |

CLI help must work without credentials, network access, a database initialization or a business action. Nested help must describe its command's purpose and parameters. A service `health` command may contact a service: it is **not** a substitute for offline help verification. Short scripts may provide their entire manual in help, provided it answers the same questions.

## Creation and change process

1. Inventory existing commands and reuse their parser/registration source. Identify the canonical implementation, aliases and actual consumers before changing anything.
2. State purpose, desired outcomes, inputs, output contract, effects and verification first. Select the smallest compatible interface. Preserve existing command names, argument positions, output shapes and exit codes unless the requested change explicitly requires a migration.
3. Implement help from parser metadata. Keep client creation, credential acquisition and business actions behind command execution. Expose the guide in root help and README. Put machine output on stdout and diagnostics on stderr for new automation interfaces; describe legacy exceptions honestly.
4. Write the guide and intent table. Derive the full command reference from the registered parser where practical. Handwritten references must be checked against it. Integration overlays document their own additions and link to the foundation grammar.
5. Verify discovery in a credential-free, offline context; check nested help, the complete command inventory and example argument parsing without executing actions. Verify changed behavior with focused existing tests and new meaningful cases only where coverage is missing. Test a malformed input and a recovery path at an appropriate isolated boundary.
6. Record exact source/runtime identity, checked commands and remaining limitations. Reject missing commands, invented flags, unsupported output promises, broken guide links and unexplained inventory exclusions. Documentation headings alone do not prove correctness; a reviewer checks intent and effects against implementation.
7. Keep the standard, parser, guide, reference and workflow skill aligned in the same change. CI or the project's fast check must reject structural drift. Publication and local activation are separate from source changes.

## Shared agent guidance

Workflow skills map business intent to commands, explain decisions and sequencing, and name expected results and recovery. They link to the CLI guide and command reference rather than maintaining a second syntax inventory. Claude Copilot and Codex Copilot consume the same canonical guidance; do not create divergent copies.

## Acceptance

A fresh reader can select and form a real invocation using the guide and help, predict its effect, recognize success and recover from the documented failure. All maintained first-party entry points are accounted for. A command list without intent, or a narrative without verified commands, does not pass.

Run `python3 scripts/check-cli-guide.py <guide> [...]` for structural and local-link checks. This check does not execute examples or certify their semantics; include offline parser evidence and a source review in the project's acceptance record.

For parser-derived references, run `python3 scripts/export-cli-reference.py MODULE:APP --name COMMAND --require-purpose` with the selected CLI's dependencies and source on `PYTHONPATH`. For an argparse factory, add `--factory` after reviewing that it only constructs a parser. The purpose check rejects undocumented groups and leaves; export never invokes command callbacks. Compare regenerated output with the checked-in reference as part of command changes. Each consumer repository's `scripts/check-cli-docs.sh` provides its fast structural check; set `CLI_STANDARD_ROOT` when using a development or nondefault foundation checkout.
