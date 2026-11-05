# copilot CLI guide

## Purpose

Operate infrastructure, databases, files and service APIs through one consistent CLI. This is a client of those services; business workflows belong in their owning products or workflow skills.

## Setup and identity

Install the package as described in [setup](docs/01-setup.md). `copilot --version` identifies the installed release; `cli_copilot` is an alias. Configuration comes from `COPILOT_ENV_FILE`, otherwise the nearest `.env` walking upward from the working directory. The resolved tier manifest determines optional integrations; `copilot layers` explains their provenance. Each service reference names its required configuration. Help does not need service credentials.

## Command discovery

Start with `copilot --help`, then `copilot docker --help`, then the selected command's `--help`. The [complete parser-generated reference](CLI-commands.md) includes registered groups, commands, aliases and parameters. Optional installed extensions can change the available tree; the installed help is authoritative for that installation.

## Intent and examples

| Intent | Command | Prerequisites, effects and expected result |
|---|---|---|
| Find available services | `copilot --help` | Offline; lists the resolved command groups. |
| Inspect containers | `copilot --json docker ps` | Reads the configured Docker daemon; returns the container list. |
| Understand a database query | `copilot db query --help` | Offline; shows database selection and SQL arguments before any query. |
| Check service reachability | `copilot docker health` | Contacts Docker; reports availability, not the success of an unrelated operation. |

## Inputs and outputs

Place the global output flag before the service: `copilot --json docker ps`. Human mode uses Rich tables/panels. Service commands inherit shared output helpers, but health and some legacy paths can include human diagnostics; do not assume every output is one clean JSON value. Inspect the particular service reference before automation. Help describes exact arguments, defaults and choices. Parser usage errors exit nonzero; service errors use the shared error hierarchy.

## Effects and verification

Listing, health and database reads can contact services. `fs write`, Git staging/commits and configuration commands write locally. Container lifecycle, SQL, secret changes and integration writes affect the selected service. SQL effects depend on the statement. No universal dry-run exists. Verify a write by reading the exact resource and account afterward; a health pass proves reachability only.

## Errors and recovery

Unknown command: run root help and `copilot layers` to check whether the required tier is loaded. Missing configuration: use the named service guide and set the exact required variable in the selected config source. Authentication failure: confirm the target account and credential scope. Connection failure: check the selected service endpoint and its health. After a timeout on a write, inspect the resource before retrying to avoid duplication.

## Maintenance

Follow the [shared CLI creation standard](https://github.com/Everyone-Needs-A-Copilot/cli-copilot/blob/main/docs/04-cli-standard.md). [Usage](docs/02-usage.md) and [service-specific contracts](docs/services/00-service-index.md). Regenerate this command reference from the selected source and parser environment with the foundation's `scripts/export-cli-reference.py`; verify offline help and example parsing, then run `scripts/check-cli-guide.py` on this guide. References describe the checked-out source, not a claim that a release is installed.

Fast documentation check from this repository: `CLI_STANDARD_ROOT=/path/to/cli-copilot sh scripts/check-cli-docs.sh`. Select the foundation checkout containing the standard; `PYTHON_BIN` selects a working Python 3.
