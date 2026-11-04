# copilot command reference

Generated from the registered parser. Command callbacks were not executed. For intent, effects, configuration and recovery, read the companion CLI guide.

## `copilot`

```text
                                                                                                    
 Usage: copilot [OPTIONS] COMMAND [ARGS]...                                                         
                                                                                                    
 Unified CLI for infrastructure, APIs, databases, and monitoring.                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --version             -v                                                                         │
│ --json                          Output as JSON instead of Rich tables.                           │
│ --install-completion            Install completion for the current shell.                        │
│ --show-completion               Show completion for the current shell, to copy it or customize   │
│                                 the installation.                                                │
│ --help                          Show this message and exit.                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ health      Run health checks across all services.                                               │
│ layers      Show the resolved CLI tier chain and per-service provenance.                         │
│ update      Sync each resolved CLI tier's read-only mirror from its declared source.             │
│ git         Git repository operations                                                            │
│ docker      Docker container management                                                          │
│ shell       Shell command execution                                                              │
│ fs          File system operations                                                               │
│ services    System service management (launchctl)                                                │
│ db          PostgreSQL database operations                                                       │
│ docs        Document management                                                                  │
│ bi          Business intelligence                                                                │
│ monitoring  System monitoring                                                                    │
│ infisical   Infisical secrets management                                                         │
│ skill       Skill runtime — discover, execute, verify skills                                     │
│ uspto       USPTO patent and trademark data access                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
                                                                                                    
 Guide: CLI.md in the source repository (purpose, intent, output and recovery).
```

## `copilot health`

```text
                                                                                                    
 Usage: copilot health [OPTIONS]                                                                    
                                                                                                    
 Run health checks across all services.                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot layers`

```text
                                                                                                    
 Usage: copilot layers [OPTIONS]                                                                    
                                                                                                    
 Show the resolved CLI tier chain and per-service provenance.                                       
                                                                                                    
 With no `copilot.layers.yml` resolving a `product: cli` chain, this                                
 reports an empty chain and the base 12 services, each `tier:                                       
 foundation, mode: base` -- the inert Phase-1 state. Control Tower calls                            
 this with `--json` and renders it (invariant #1: parse, never compute).                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot update`

```text
                                                                                                    
 Usage: copilot update [OPTIONS]                                                                    
                                                                                                    
 Sync each resolved CLI tier's read-only mirror from its declared source.                           
                                                                                                    
 Never-destroy (invariant #2/#3): a mirror whose git working tree is                                
 DIRTY -- or clean but carrying unpushed local commits -- is HELD: zero                             
 writes, reported, and skipped. Only a clean or absent mirror is touched,                           
 and only ever cloned or pulled -- this never pushes, and never touches                             
 an author's personal working tree.                                                                 
                                                                                                    
 A semver-RANGE `source.ref` (e.g. the live foundation layer's `^1.4.5`)                            
 is resolved to the HIGHEST matching tag first (`config/semver.py`); if                             
 no tag satisfies the range, the layer is reported `skipped`, never a                               
 crash and never a write. See `config/sync.py` for the per-layer sync                               
 logic this wraps.                                                                                  
                                                                                                    
 Also reports managed-secret-store readiness (presence-only: is store                               
 config declared, are bootstrap credentials present on this machine) --                             
 never provisions, never performs a network auth, never prints a secret                             
 value. See `config/store_readiness.py`.                                                            
                                                                                                    
 `--json` emits a versioned payload (see `docs/schemas/update.schema.                               
 json`) for Control Tower to render (invariant #1: parse, never                                     
 compute); human output stays this compact per-layer summary.                                       
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git`

```text
                                                                                                    
 Usage: copilot git [OPTIONS] COMMAND [ARGS]...                                                     
                                                                                                    
 Git repository operations                                                                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ clone   Clone a remote Git repository.                                                           │
│ pull    Pull latest changes from a remote.                                                       │
│ status  Show the working-tree status of a repository.                                            │
│ add     Stage files for the next commit.                                                         │
│ commit  Commit staged changes.                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git clone`

```text
                                                                                                    
 Usage: copilot git clone [OPTIONS]                                                                 
                                                                                                    
 Clone a remote Git repository.                                                                     
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --url           TEXT  Remote repository URL. [required]                                       │
│ *  --path          TEXT  Local directory for the clone. [required]                               │
│    --branch        TEXT  Branch to check out.                                                    │
│    --help                Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git pull`

```text
                                                                                                    
 Usage: copilot git pull [OPTIONS]                                                                  
                                                                                                    
 Pull latest changes from a remote.                                                                 
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --path          TEXT  Repository path. [default: .]                                              │
│ --remote        TEXT  Remote name. [default: origin]                                             │
│ --branch        TEXT  Branch to pull.                                                            │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git status`

```text
                                                                                                    
 Usage: copilot git status [OPTIONS]                                                                
                                                                                                    
 Show the working-tree status of a repository.                                                      
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --path        TEXT  Repository path. [default: .]                                                │
│ --help              Show this message and exit.                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git add`

```text
                                                                                                    
 Usage: copilot git add [OPTIONS] FILES...                                                          
                                                                                                    
 Stage files for the next commit.                                                                   
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    files      FILES...  Files to stage. [required]                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --path        TEXT  Repository path. [default: .]                                                │
│ --help              Show this message and exit.                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot git commit`

```text
                                                                                                    
 Usage: copilot git commit [OPTIONS]                                                                
                                                                                                    
 Commit staged changes.                                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│    --path             TEXT  Repository path. [default: .]                                        │
│ *  --message  -m      TEXT  Commit message. [required]                                           │
│    --author           TEXT  Author in 'Name <email>' format.                                     │
│    --help                   Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker`

```text
                                                                                                    
 Usage: copilot docker [OPTIONS] COMMAND [ARGS]...                                                  
                                                                                                    
 Docker container management                                                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ ps       List Docker containers.                                                                 │
│ start    Start a stopped container.                                                              │
│ stop     Stop a running container.                                                               │
│ restart  Restart a container.                                                                    │
│ info     Show Docker daemon system information.                                                  │
│ health   Check Docker daemon health.                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker ps`

```text
                                                                                                    
 Usage: copilot docker ps [OPTIONS]                                                                 
                                                                                                    
 List Docker containers.                                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --all   -a        Include stopped containers.                                                    │
│ --help            Show this message and exit.                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker start`

```text
                                                                                                    
 Usage: copilot docker start [OPTIONS] ID                                                           
                                                                                                    
 Start a stopped container.                                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    id      TEXT  Container ID or name. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker stop`

```text
                                                                                                    
 Usage: copilot docker stop [OPTIONS] ID                                                            
                                                                                                    
 Stop a running container.                                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    id      TEXT  Container ID or name. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout  -t      INTEGER  Seconds before kill. [default: 10]                                   │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker restart`

```text
                                                                                                    
 Usage: copilot docker restart [OPTIONS] ID                                                         
                                                                                                    
 Restart a container.                                                                               
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    id      TEXT  Container ID or name. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout  -t      INTEGER  Seconds before kill. [default: 10]                                   │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker info`

```text
                                                                                                    
 Usage: copilot docker info [OPTIONS]                                                               
                                                                                                    
 Show Docker daemon system information.                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docker health`

```text
                                                                                                    
 Usage: copilot docker health [OPTIONS]                                                             
                                                                                                    
 Check Docker daemon health.                                                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot shell`

```text
                                                                                                    
 Usage: copilot shell [OPTIONS] COMMAND [ARGS]...                                                   
                                                                                                    
 Shell command execution                                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ exec  Execute a shell command.                                                                   │
│ run   Run a script from configured script paths.                                                 │
│ find  Find scripts in configured paths.                                                          │
│ ps    List running processes.                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot shell exec`

```text
                                                                                                    
 Usage: copilot shell exec [OPTIONS] COMMAND                                                        
                                                                                                    
 Execute a shell command.                                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    command      TEXT  Shell command to execute. [required]                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout      -t      INTEGER  Timeout in seconds. [default: 300]                               │
│ --working-dir  -d      TEXT     Working directory.                                               │
│ --help                          Show this message and exit.                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot shell run`

```text
                                                                                                    
 Usage: copilot shell run [OPTIONS] SCRIPT_NAME                                                     
                                                                                                    
 Run a script from configured script paths.                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    script_name      TEXT  Script filename to execute. [required]                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout  -t      INTEGER  Timeout in seconds. [default: 3600]                                  │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot shell find`

```text
                                                                                                    
 Usage: copilot shell find [OPTIONS]                                                                
                                                                                                    
 Find scripts in configured paths.                                                                  
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --pattern  -p      TEXT  Glob pattern. [default: *.sh]                                           │
│ --path             TEXT  Directory to search.                                                    │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot shell ps`

```text
                                                                                                    
 Usage: copilot shell ps [OPTIONS]                                                                  
                                                                                                    
 List running processes.                                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --pattern  -p      TEXT  Filter pattern.                                                         │
│ --user     -u      TEXT  Filter by user.                                                         │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs`

```text
                                                                                                    
 Usage: copilot fs [OPTIONS] COMMAND [ARGS]...                                                      
                                                                                                    
 File system operations                                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ read      Read and display a file's contents.                                                    │
│ write     Write content to a file.                                                               │
│ delete    Delete a file.                                                                         │
│ cp        Copy a file.                                                                           │
│ mv        Move a file.                                                                           │
│ ls        List directory contents.                                                               │
│ mkdir     Create a directory.                                                                    │
│ search    Search for files recursively.                                                          │
│ checksum  Calculate a file's checksum.                                                           │
│ meta      Show detailed metadata for a file or directory.                                        │
│ volumes   List configured volumes and their accessibility.                                       │
│ health    Run a health check on the filesystem service.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs read`

```text
                                                                                                    
 Usage: copilot fs read [OPTIONS] PATH                                                              
                                                                                                    
 Read and display a file's contents.                                                                
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the file to read. [required]                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --encoding  -e      TEXT  File encoding. [default: utf-8]                                        │
│ --help                    Show this message and exit.                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs write`

```text
                                                                                                    
 Usage: copilot fs write [OPTIONS] PATH                                                             
                                                                                                    
 Write content to a file.                                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Destination file path. [required]                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --content   -c      TEXT  Content to write. [required]                                        │
│    --encoding  -e      TEXT  File encoding. [default: utf-8]                                     │
│    --force     -f            Overwrite if destination exists.                                    │
│    --help                    Show this message and exit.                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs delete`

```text
                                                                                                    
 Usage: copilot fs delete [OPTIONS] PATH                                                            
                                                                                                    
 Delete a file.                                                                                     
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  File to delete. [required]                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --force  -f        Skip confirmation prompt.                                                     │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs cp`

```text
                                                                                                    
 Usage: copilot fs cp [OPTIONS] SOURCE DEST                                                         
                                                                                                    
 Copy a file.                                                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    source      TEXT  Source file path. [required]                                              │
│ *    dest        TEXT  Destination file path. [required]                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --preserve  -p        Preserve timestamps.                                                       │
│ --force     -f        Overwrite if destination exists.                                           │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs mv`

```text
                                                                                                    
 Usage: copilot fs mv [OPTIONS] SOURCE DEST                                                         
                                                                                                    
 Move a file.                                                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    source      TEXT  Source path. [required]                                                   │
│ *    dest        TEXT  Destination path. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --force  -f        Overwrite if destination exists.                                              │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs ls`

```text
                                                                                                    
 Usage: copilot fs ls [OPTIONS] [PATH]                                                              
                                                                                                    
 List directory contents.                                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│   path      [PATH]  Directory to list. [default: .]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --files-only                Show only files.                                                     │
│ --dirs-only                 Show only directories.                                               │
│ --pattern     -p      TEXT  Glob pattern filter.                                                 │
│ --sort-by     -s      TEXT  Sort by: name, size, modified. [default: name]                       │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs mkdir`

```text
                                                                                                    
 Usage: copilot fs mkdir [OPTIONS] PATH                                                             
                                                                                                    
 Create a directory.                                                                                
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Directory path to create. [required]                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --recursive    --no-recursive      Create parent directories. [default: recursive]               │
│ --help                             Show this message and exit.                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs search`

```text
                                                                                                    
 Usage: copilot fs search [OPTIONS] [PATH]                                                          
                                                                                                    
 Search for files recursively.                                                                      
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│   path      [PATH]  Root directory to search. [default: .]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --ext               TEXT     File extension filter (e.g. .json).                                 │
│ --name      -n      TEXT     File name substring match.                                          │
│ --min-size          INTEGER  Minimum file size in bytes.                                         │
│ --max-size          INTEGER  Maximum file size in bytes.                                         │
│ --help                       Show this message and exit.                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs checksum`

```text
                                                                                                    
 Usage: copilot fs checksum [OPTIONS] PATH                                                          
                                                                                                    
 Calculate a file's checksum.                                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  File to calculate checksum for. [required]                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --algorithm  -a      TEXT  Hash algorithm. [default: sha256]                                     │
│ --help                     Show this message and exit.                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs meta`

```text
                                                                                                    
 Usage: copilot fs meta [OPTIONS] PATH                                                              
                                                                                                    
 Show detailed metadata for a file or directory.                                                    
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  File or directory path. [required]                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs volumes`

```text
                                                                                                    
 Usage: copilot fs volumes [OPTIONS]                                                                
                                                                                                    
 List configured volumes and their accessibility.                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot fs health`

```text
                                                                                                    
 Usage: copilot fs health [OPTIONS]                                                                 
                                                                                                    
 Run a health check on the filesystem service.                                                      
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services`

```text
                                                                                                    
 Usage: copilot services [OPTIONS] COMMAND [ARGS]...                                                
                                                                                                    
 System service management (launchctl)                                                              
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list     List launchctl services.                                                                │
│ status   Get status of a specific service.                                                       │
│ start    Start a launchctl service.                                                              │
│ stop     Stop a launchctl service.                                                               │
│ restart  Restart a launchctl service (stop then start).                                          │
│ load     Load a service plist.                                                                   │
│ unload   Unload a service plist.                                                                 │
│ ps       List running processes.                                                                 │
│ proc     Get detailed information for a specific process.                                        │
│ health   Run a health check on system services.                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services list`

```text
                                                                                                    
 Usage: copilot services list [OPTIONS]                                                             
                                                                                                    
 List launchctl services.                                                                           
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services status`

```text
                                                                                                    
 Usage: copilot services status [OPTIONS] SERVICE                                                   
                                                                                                    
 Get status of a specific service.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    service      TEXT  Service label (e.g. com.apple.Spotlight). [required]                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services start`

```text
                                                                                                    
 Usage: copilot services start [OPTIONS] SERVICE                                                    
                                                                                                    
 Start a launchctl service.                                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    service      TEXT  Service label to start. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services stop`

```text
                                                                                                    
 Usage: copilot services stop [OPTIONS] SERVICE                                                     
                                                                                                    
 Stop a launchctl service.                                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    service      TEXT  Service label to stop. [required]                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services restart`

```text
                                                                                                    
 Usage: copilot services restart [OPTIONS] SERVICE                                                  
                                                                                                    
 Restart a launchctl service (stop then start).                                                     
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    service      TEXT  Service label to restart. [required]                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services load`

```text
                                                                                                    
 Usage: copilot services load [OPTIONS] PATH                                                        
                                                                                                    
 Load a service plist.                                                                              
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the service plist file. [required]                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services unload`

```text
                                                                                                    
 Usage: copilot services unload [OPTIONS] PATH                                                      
                                                                                                    
 Unload a service plist.                                                                            
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the service plist file. [required]                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --domain  -d      TEXT  Service domain: user or system. [default: user]                          │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services ps`

```text
                                                                                                    
 Usage: copilot services ps [OPTIONS]                                                               
                                                                                                    
 List running processes.                                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --filter     -f                 TEXT  Filter by command name substring.                          │
│ --user-only      --all-users          Show only current user processes. [default: user-only]     │
│ --help                                Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services proc`

```text
                                                                                                    
 Usage: copilot services proc [OPTIONS] PID                                                         
                                                                                                    
 Get detailed information for a specific process.                                                   
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    pid      INTEGER  Process ID. [required]                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot services health`

```text
                                                                                                    
 Usage: copilot services health [OPTIONS]                                                           
                                                                                                    
 Run a health check on system services.                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db`

```text
                                                                                                    
 Usage: copilot db [OPTIONS] COMMAND [ARGS]...                                                      
                                                                                                    
 PostgreSQL database operations                                                                     
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ query          Execute a SQL query against a named database.                                     │
│ tables         List tables in a database schema.                                                 │
│ columns        List columns for a table.                                                         │
│ relationships  Show foreign-key relationships.                                                   │
│ schema         Full schema introspection for a database.                                         │
│ explain        Show the execution plan for a query.                                              │
│ stats          Show connection pool statistics.                                                  │
│ backup         Backup table data as JSON.                                                        │
│ vacuum         Run VACUUM and/or ANALYZE on a database or table.                                 │
│ dump           Dump a remote Coolify-managed database to a local file via SSH + docker exec.     │
│ restore        Restore a dump file into a LOCAL database.                                        │
│ pull           Convenience: dump a remote Coolify database, then restore into a local one.       │
│ transition     Copy a database from one environment into a local database.                       │
│ remote-query   Run a query against a remote Coolify-managed DB via SSH tunnel.                   │
│ health         Health-check all configured database connections.                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db query`

```text
                                                                                                    
 Usage: copilot db query [OPTIONS] DATABASE SQL                                                     
                                                                                                    
 Execute a SQL query against a named database.                                                      
                                                                                                    
 Destructive SQL (DROP, TRUNCATE, DELETE, ALTER DROP) on a non-local database                       
 is refused. On a local database, destructive SQL requires --confirm-token                          
 to match the database short-name.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name (e.g. nocodb, n8n). [required]                    │
│ *    sql           TEXT  SQL query to execute. [required]                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout              INTEGER  Statement timeout in milliseconds. [default: 30000]              │
│ --confirm-token        TEXT     For destructive SQL on a local DB, must equal the database       │
│                                 short-name.                                                      │
│ --help                          Show this message and exit.                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db tables`

```text
                                                                                                    
 Usage: copilot db tables [OPTIONS] DATABASE                                                        
                                                                                                    
 List tables in a database schema.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --schema         TEXT  Schema name. [default: public]                                            │
│ --pattern        TEXT  LIKE pattern to filter table names.                                       │
│ --help                 Show this message and exit.                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db columns`

```text
                                                                                                    
 Usage: copilot db columns [OPTIONS] DATABASE TABLE                                                 
                                                                                                    
 List columns for a table.                                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
│ *    table         TEXT  Table name. [required]                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --schema        TEXT  Schema name. [default: public]                                             │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db relationships`

```text
                                                                                                    
 Usage: copilot db relationships [OPTIONS] DATABASE                                                 
                                                                                                    
 Show foreign-key relationships.                                                                    
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --table         TEXT  Filter by table name.                                                      │
│ --schema        TEXT  Schema name. [default: public]                                             │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db schema`

```text
                                                                                                    
 Usage: copilot db schema [OPTIONS] DATABASE                                                        
                                                                                                    
 Full schema introspection for a database.                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db explain`

```text
                                                                                                    
 Usage: copilot db explain [OPTIONS] DATABASE SQL                                                   
                                                                                                    
 Show the execution plan for a query.                                                               
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
│ *    sql           TEXT  SQL query to explain. [required]                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --analyze          Run EXPLAIN ANALYZE (executes the query).                                     │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db stats`

```text
                                                                                                    
 Usage: copilot db stats [OPTIONS]                                                                  
                                                                                                    
 Show connection pool statistics.                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --database        TEXT  Limit to a specific database.                                            │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db backup`

```text
                                                                                                    
 Usage: copilot db backup [OPTIONS] DATABASE TABLE                                                  
                                                                                                    
 Backup table data as JSON.                                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
│ *    table         TEXT  Table to back up. [required]                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --schema        TEXT  Schema name. [default: public]                                             │
│ --where         TEXT  WHERE clause filter (without 'WHERE' keyword).                             │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db vacuum`

```text
                                                                                                    
 Usage: copilot db vacuum [OPTIONS] DATABASE                                                        
                                                                                                    
 Run VACUUM and/or ANALYZE on a database or table.                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    database      TEXT  Logical database name. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --table            TEXT  Target table (omit for all tables).                                     │
│ --operation        TEXT  Operation: vacuum, analyze, or vacuum_analyze.                          │
│                          [default: vacuum_analyze]                                               │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db dump`

```text
                                                                                                    
 Usage: copilot db dump [OPTIONS] COOLIFY_DB                                                        
                                                                                                    
 Dump a remote Coolify-managed database to a local file via SSH + docker exec.                      
                                                                                                    
 The dump runs inside the database's container, so the version of pg_dump                           
 used always matches the server. Output is streamed straight to disk.                               
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    coolify_db      TEXT  Coolify database name or UUID. [required]                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --out          -o      PATH  Output file. Default: <BACKUP_DIR>/<dbname>-<timestamp>.dump        │
│ --format       -F      TEXT  Dump format: 'custom' (pg_restore) or 'plain' (psql).               │
│                              [default: custom]                                                   │
│ --schema-only                Dump DDL only.                                                      │
│ --data-only                  Dump rows only.                                                     │
│ --table        -t      TEXT  Restrict to a single table.                                         │
│ --help                       Show this message and exit.                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db restore`

```text
                                                                                                    
 Usage: copilot db restore [OPTIONS] DUMP_FILE                                                      
                                                                                                    
 Restore a dump file into a LOCAL database.                                                         
                                                                                                    
 The target must be a configured local database whose connection URL points                         
 at loopback. Restores against remote databases are refused unconditionally.                        
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    dump_file      PATH  Path to a pg_dump file. [required]                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --to                   TEXT  Local database short-name (must be configured). [required]       │
│    --clean                      For custom-format dumps: drop existing objects first.            │
│    --confirm-token        TEXT  Non-interactive confirmation token (must equal --to value).      │
│    --help                       Show this message and exit.                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db pull`

```text
                                                                                                    
 Usage: copilot db pull [OPTIONS] COOLIFY_DB                                                        
                                                                                                    
 Convenience: dump a remote Coolify database, then restore into a local one.                        
                                                                                                    
 Equivalent to running ``db dump`` then ``db restore`` in sequence.                                 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    coolify_db      TEXT  Coolify database name or UUID. [required]                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --to                             TEXT  Local database short-name to restore into. [required]  │
│    --keep-dump                            Keep the intermediate dump file.                       │
│    --clean            --no-clean          Drop existing objects in the local target before       │
│                                           restoring.                                             │
│                                           [default: clean]                                       │
│    --confirm-token                  TEXT  Non-interactive confirmation token (must equal --to    │
│                                           value).                                                │
│    --help                                 Show this message and exit.                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db transition`

```text
                                                                                                    
 Usage: copilot db transition [OPTIONS] SOURCE                                                      
                                                                                                    
 Copy a database from one environment into a local database.                                        
                                                                                                    
 *source* may be either a local DB short-name (from configured                                      
 ``*_DATABASE_URL`` env vars) or a Coolify-managed remote DB. Local sources                         
 are detected first; anything else is resolved through the Coolify API.                             
 The target must be a configured local database.                                                    
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    source      TEXT  Source: a local DB short-name OR a Coolify DB name/UUID. [required]       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --to                             TEXT  Target local DB short-name (must be configured).       │
│                                           [required]                                             │
│    --keep-dump                            Keep the intermediate dump file.                       │
│    --clean            --no-clean          Drop existing objects in the target before restoring.  │
│                                           [default: clean]                                       │
│    --confirm-token                  TEXT  Non-interactive confirmation token (must equal --to    │
│                                           value).                                                │
│    --help                                 Show this message and exit.                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db remote-query`

```text
                                                                                                    
 Usage: copilot db remote-query [OPTIONS] COOLIFY_DB SQL                                            
                                                                                                    
 Run a query against a remote Coolify-managed DB via SSH tunnel.                                    
                                                                                                    
 The connection is tagged as tunneled-remote, so the destructive-ops policy                         
 refuses any DROP / TRUNCATE / DELETE / ALTER DROP regardless of flags.                             
 Reads and ordinary writes go through.                                                              
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    coolify_db      TEXT  Coolify database name or UUID. [required]                             │
│ *    sql             TEXT  SQL query to execute. [required]                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --timeout        INTEGER  Statement timeout in ms. [default: 30000]                              │
│ --help                    Show this message and exit.                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot db health`

```text
                                                                                                    
 Usage: copilot db health [OPTIONS]                                                                 
                                                                                                    
 Health-check all configured database connections.                                                  
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs`

```text
                                                                                                    
 Usage: copilot docs [OPTIONS] COMMAND [ARGS]...                                                    
                                                                                                    
 Document management                                                                                
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ search       Search document contents for matching text.                                         │
│ get          Read and display a document.                                                        │
│ create       Create a new document file.                                                         │
│ update       Update an existing document file.                                                   │
│ delete       Delete a document file.                                                             │
│ collections  List subdirectories as document collections.                                        │
│ stats        Show document statistics for the current directory.                                 │
│ health       Check document service health.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs search`

```text
                                                                                                    
 Usage: copilot docs search [OPTIONS] PATH QUERY                                                    
                                                                                                    
 Search document contents for matching text.                                                        
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path       TEXT  Directory to search in. [required]                                         │
│ *    query      TEXT  Text to search for. [required]                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --ext   -e      TEXT  File extension filter (e.g. md, txt).                                      │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs get`

```text
                                                                                                    
 Usage: copilot docs get [OPTIONS] PATH                                                             
                                                                                                    
 Read and display a document.                                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the document file. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs create`

```text
                                                                                                    
 Usage: copilot docs create [OPTIONS] PATH                                                          
                                                                                                    
 Create a new document file.                                                                        
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path for the new document. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --content  -c      TEXT  Text content for the document. [required]                            │
│    --help                   Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs update`

```text
                                                                                                    
 Usage: copilot docs update [OPTIONS] PATH                                                          
                                                                                                    
 Update an existing document file.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the document. [required]                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --content  -c      TEXT  New text content. [required]                                         │
│    --help                   Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs delete`

```text
                                                                                                    
 Usage: copilot docs delete [OPTIONS] PATH                                                          
                                                                                                    
 Delete a document file.                                                                            
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Path to the document. [required]                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --force  -f        Skip confirmation prompt.                                                     │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs collections`

```text
                                                                                                    
 Usage: copilot docs collections [OPTIONS] PATH                                                     
                                                                                                    
 List subdirectories as document collections.                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  Base directory to scan. [required]                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs stats`

```text
                                                                                                    
 Usage: copilot docs stats [OPTIONS]                                                                
                                                                                                    
 Show document statistics for the current directory.                                                
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot docs health`

```text
                                                                                                    
 Usage: copilot docs health [OPTIONS]                                                               
                                                                                                    
 Check document service health.                                                                     
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi`

```text
                                                                                                    
 Usage: copilot bi [OPTIONS] COMMAND [ARGS]...                                                      
                                                                                                    
 Business intelligence                                                                              
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ analyze   Analyze data in a JSON or CSV file.                                                    │
│ patterns  Detect value frequency patterns in a column.                                           │
│ kpis      Calculate KPIs from data.                                                              │
│ summary   Generate a text summary of a dataset.                                                  │
│ health    Check BI service health.                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi analyze`

```text
                                                                                                    
 Usage: copilot bi analyze [OPTIONS] FILE                                                           
                                                                                                    
 Analyze data in a JSON or CSV file.                                                                
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    file      TEXT  Path to a JSON or CSV file. [required]                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --metrics  -m      TEXT  Comma-separated list of numeric columns to analyze.                     │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi patterns`

```text
                                                                                                    
 Usage: copilot bi patterns [OPTIONS] FILE COLUMN                                                   
                                                                                                    
 Detect value frequency patterns in a column.                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    file        TEXT  Path to a JSON or CSV file. [required]                                    │
│ *    column      TEXT  Column name for frequency analysis. [required]                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi kpis`

```text
                                                                                                    
 Usage: copilot bi kpis [OPTIONS] FILE                                                              
                                                                                                    
 Calculate KPIs from data.                                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    file      TEXT  Path to a JSON or CSV file. [required]                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --definitions  -d      TEXT  KPI definitions as JSON string, e.g. '{"revenue": {"column":     │
│                                 "amount", "operation": "sum"}}'.                                 │
│                                 [required]                                                       │
│    --help                       Show this message and exit.                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi summary`

```text
                                                                                                    
 Usage: copilot bi summary [OPTIONS] FILE                                                           
                                                                                                    
 Generate a text summary of a dataset.                                                              
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    file      TEXT  Path to a JSON or CSV file. [required]                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot bi health`

```text
                                                                                                    
 Usage: copilot bi health [OPTIONS]                                                                 
                                                                                                    
 Check BI service health.                                                                           
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot monitoring`

```text
                                                                                                    
 Usage: copilot monitoring [OPTIONS] COMMAND [ARGS]...                                              
                                                                                                    
 System monitoring                                                                                  
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ status  Show current system metrics (CPU, memory, disk).                                         │
│ alerts  Show active alerts based on configured thresholds.                                       │
│ health  Check monitoring service health.                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot monitoring status`

```text
                                                                                                    
 Usage: copilot monitoring status [OPTIONS]                                                         
                                                                                                    
 Show current system metrics (CPU, memory, disk).                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot monitoring alerts`

```text
                                                                                                    
 Usage: copilot monitoring alerts [OPTIONS]                                                         
                                                                                                    
 Show active alerts based on configured thresholds.                                                 
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot monitoring health`

```text
                                                                                                    
 Usage: copilot monitoring health [OPTIONS]                                                         
                                                                                                    
 Check monitoring service health.                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical`

```text
                                                                                                    
 Usage: copilot infisical [OPTIONS] COMMAND [ARGS]...                                               
                                                                                                    
 Infisical secrets management                                                                       
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --json                    Output as JSON                                                         │
│ --yaml                    Output as YAML                                                         │
│ --no-color                Disable colour output                                                  │
│ --verbose   -v            Verbose output                                                         │
│ --org-id            TEXT  Organisation ID override                                               │
│ --help                    Show this message and exit.                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ config    Show Infisical configuration.                                                          │
│ project   Manage Infisical projects.                                                             │
│ folder    Manage Infisical secret folders.                                                       │
│ secret    Manage Infisical secrets.                                                              │
│ identity  Manage Infisical machine identities.                                                   │
│ org       Organisation admin commands.                                                           │
│ access    Verify short-lived shared-store access.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical config`

```text
                                                                                                    
 Usage: copilot infisical config [OPTIONS] COMMAND [ARGS]...                                        
                                                                                                    
 Show Infisical configuration.                                                                      
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ show  Show configuration (credentials masked) and verify authentication.                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical config show`

```text
                                                                                                    
 Usage: copilot infisical config show [OPTIONS]                                                     
                                                                                                    
 Show configuration (credentials masked) and verify authentication.                                 
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical project`

```text
                                                                                                    
 Usage: copilot infisical project [OPTIONS] COMMAND [ARGS]...                                       
                                                                                                    
 Manage Infisical projects.                                                                         
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List all projects.                                                                       │
│ get     Get detailed project information.                                                        │
│ create  Create a new project.                                                                    │
│ delete  Delete a project.                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical project list`

```text
                                                                                                    
 Usage: copilot infisical project list [OPTIONS]                                                    
                                                                                                    
 List all projects.                                                                                 
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical project get`

```text
                                                                                                    
 Usage: copilot infisical project get [OPTIONS] PROJECT_ID                                          
                                                                                                    
 Get detailed project information.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    project_id      TEXT  Project ID [required]                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical project create`

```text
                                                                                                    
 Usage: copilot infisical project create [OPTIONS] NAME                                             
                                                                                                    
 Create a new project.                                                                              
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Project name [required]                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical project delete`

```text
                                                                                                    
 Usage: copilot infisical project delete [OPTIONS] PROJECT_ID                                       
                                                                                                    
 Delete a project.                                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    project_id      TEXT  Project ID [required]                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --force  -f        Skip confirmation                                                             │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical folder`

```text
                                                                                                    
 Usage: copilot infisical folder [OPTIONS] COMMAND [ARGS]...                                        
                                                                                                    
 Manage Infisical secret folders.                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List folders in a project environment.                                                   │
│ create  Create a folder in a project environment.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical folder list`

```text
                                                                                                    
 Usage: copilot infisical folder list [OPTIONS]                                                     
                                                                                                    
 List folders in a project environment.                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug (e.g. dev) [default: dev]                              │
│ --path             TEXT  Folder path [default: /]                                                │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical folder create`

```text
                                                                                                    
 Usage: copilot infisical folder create [OPTIONS] NAME                                              
                                                                                                    
 Create a folder in a project environment.                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Folder name [required]                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug [default: dev]                                         │
│ --path             TEXT  Parent path [default: /]                                                │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical secret`

```text
                                                                                                    
 Usage: copilot infisical secret [OPTIONS] COMMAND [ARGS]...                                        
                                                                                                    
 Manage Infisical secrets.                                                                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List secrets (keys only — use `secret get` to see a value).                              │
│ get     Get a secret value (explicitly requested — value is shown).                              │
│ set     Create or update a secret value.                                                         │
│ delete  Delete a secret.                                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical secret list`

```text
                                                                                                    
 Usage: copilot infisical secret list [OPTIONS]                                                     
                                                                                                    
 List secrets (keys only — use `secret get` to see a value).                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug [default: dev]                                         │
│ --path             TEXT  Secret path [default: /]                                                │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical secret get`

```text
                                                                                                    
 Usage: copilot infisical secret get [OPTIONS] KEY                                                  
                                                                                                    
 Get a secret value (explicitly requested — value is shown).                                        
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    key      TEXT  Secret key name [required]                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug [default: dev]                                         │
│ --path             TEXT  Secret path [default: /]                                                │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical secret set`

```text
                                                                                                    
 Usage: copilot infisical secret set [OPTIONS] KEY VALUE                                            
                                                                                                    
 Create or update a secret value.                                                                   
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    key        TEXT  Secret key name [required]                                                 │
│ *    value      TEXT  Secret value [required]                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug [default: dev]                                         │
│ --path             TEXT  Secret path [default: /]                                                │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical secret delete`

```text
                                                                                                    
 Usage: copilot infisical secret delete [OPTIONS] KEY                                               
                                                                                                    
 Delete a secret.                                                                                   
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    key      TEXT  Secret key name [required]                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --project  -p      TEXT  Project ID                                                              │
│ --env      -e      TEXT  Environment slug [default: dev]                                         │
│ --path             TEXT  Secret path [default: /]                                                │
│ --force    -f            Skip confirmation                                                       │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical identity`

```text
                                                                                                    
 Usage: copilot infisical identity [OPTIONS] COMMAND [ARGS]...                                      
                                                                                                    
 Manage Infisical machine identities.                                                               
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List all machine identities in the organisation.                                         │
│ create  Create a new machine identity in the organisation.                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical identity list`

```text
                                                                                                    
 Usage: copilot infisical identity list [OPTIONS]                                                   
                                                                                                    
 List all machine identities in the organisation.                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical identity create`

```text
                                                                                                    
 Usage: copilot infisical identity create [OPTIONS] NAME                                            
                                                                                                    
 Create a new machine identity in the organisation.                                                 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Identity name [required]                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --role  -r      TEXT  Org role (admin, member, viewer) [default: member]                         │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical org`

```text
                                                                                                    
 Usage: copilot infisical org [OPTIONS] COMMAND [ARGS]...                                           
                                                                                                    
 Organisation admin commands.                                                                       
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ disable-signup  Disable open registration (requires super-admin).                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical org disable-signup`

```text
                                                                                                    
 Usage: copilot infisical org disable-signup [OPTIONS]                                              
                                                                                                    
 Disable open registration (requires super-admin).                                                  
                                                                                                    
 Note: this endpoint requires super-admin privileges. The machine identity                          
 used for API auth must be listed in adminIdentityIds in the admin config.                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --force  -f        Skip confirmation                                                             │
│ --help             Show this message and exit.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical access`

```text
                                                                                                    
 Usage: copilot infisical access [OPTIONS] COMMAND [ARGS]...                                        
                                                                                                    
 Verify short-lived shared-store access.                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ verify  Prove one authorized read and one out-of-scope denial.                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot infisical access verify`

```text
                                                                                                    
 Usage: copilot infisical access verify [OPTIONS]                                                   
                                                                                                    
 Prove one authorized read and one out-of-scope denial.                                             
                                                                                                    
 The report contains a count only. Secret names and values never leave the                          
 Infisical client, and this command refuses the legacy Universal Auth path.                         
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --project        -p      TEXT  Project ID [required]                                          │
│    --env            -e      TEXT  Environment slug [default: prod]                               │
│    --path                   TEXT  Authorized secret path [default: /shared]                      │
│    --negative-path          TEXT  Known-nonempty canary path whose secrets must not be visible   │
│                                   [default: /__control_tower_denied__]                           │
│    --scope                  TEXT  Broker scope to prove (defaults to inherited config)           │
│    --help                         Show this message and exit.                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill`

```text
                                                                                                    
 Usage: copilot skill [OPTIONS] COMMAND [ARGS]...                                                   
                                                                                                    
 Skill runtime — discover, execute, verify skills                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List all discovered skills.                                                              │
│ show    Show detailed information about a skill.                                                 │
│ plan    Dry run — show what a skill execution would do.                                          │
│ run     Execute a skill's steps.                                                                 │
│ verify  Run verification checks for a skill.                                                     │
│ audit   Audit skill(s) against quality standards.                                                │
│ health  Check skill service health.                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill list`

```text
                                                                                                    
 Usage: copilot skill list [OPTIONS]                                                                
                                                                                                    
 List all discovered skills.                                                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --source            TEXT  Filter by source: local, shared, env                                   │
│ --executable              Only show skills with execution specs                                  │
│ --help                    Show this message and exit.                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill show`

```text
                                                                                                    
 Usage: copilot skill show [OPTIONS] NAME                                                           
                                                                                                    
 Show detailed information about a skill.                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Skill name [required]                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill plan`

```text
                                                                                                    
 Usage: copilot skill plan [OPTIONS] NAME                                                           
                                                                                                    
 Dry run — show what a skill execution would do.                                                    
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Skill name [required]                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --param  -p      TEXT  Parameter as KEY=VALUE (repeatable)                                       │
│ --help                 Show this message and exit.                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill run`

```text
                                                                                                    
 Usage: copilot skill run [OPTIONS] NAME                                                            
                                                                                                    
 Execute a skill's steps.                                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Skill name [required]                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --param    -p      TEXT     Parameter as KEY=VALUE (repeatable)                                  │
│ --timeout          INTEGER  Timeout per step in seconds [default: 300]                           │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill verify`

```text
                                                                                                    
 Usage: copilot skill verify [OPTIONS] NAME                                                         
                                                                                                    
 Run verification checks for a skill.                                                               
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Skill name [required]                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --param    -p      TEXT     Parameter as KEY=VALUE (repeatable)                                  │
│ --timeout          INTEGER  Timeout per check in seconds [default: 60]                           │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill audit`

```text
                                                                                                    
 Usage: copilot skill audit [OPTIONS]                                                               
                                                                                                    
 Audit skill(s) against quality standards.                                                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --path        TEXT  Path to skill or skills directory                                            │
│ --help              Show this message and exit.                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot skill health`

```text
                                                                                                    
 Usage: copilot skill health [OPTIONS]                                                              
                                                                                                    
 Check skill service health.                                                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto`

```text
                                                                                                    
 Usage: copilot uspto [OPTIONS] COMMAND [ARGS]...                                                   
                                                                                                    
 USPTO patent and trademark data access                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ health       Check USPTO configuration and API-key connectivity.                                 │
│ products     Show the USPTO product coverage the CLI should support.                             │
│ request      Make a generic authenticated request to the USPTO ODP API.                          │
│ auth         Auth requirements and capture instructions.                                         │
│ patents      Patent search and retrieval.                                                        │
│ trademarks   Trademark search and TSDR retrieval.                                                │
│ assignments  Assignment and ownership lookup.                                                    │
│ copyright    Copyright registry handoff and lookup.                                              │
│ dossier      Cross-source dossier workflows.                                                     │
│ watch        Watchlist management.                                                               │
│ sessions     Imported portal sessions.                                                           │
│ portal       Session-backed portal retrieval.                                                    │
│ tsdr         TSDR trademark retrieval.                                                           │
│ discover     Automated API contract discovery via Playwright browser interception. Opens a real  │
│              browser, intercepts XHR/fetch requests during a search on USPTO portals, and saves  │
│              captured request/response pairs as structured JSON contracts to                     │
│              ~/.copilot-cli/uspto/contracts/. Use these contracts to generate adapter stubs.     │
│              Requires: playwright package with Chromium (pip install playwright && playwright    │
│              install chromium). Workflow: products -> auto/manual -> show -> generate.           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto health`

```text
                                                                                                    
 Usage: copilot uspto health [OPTIONS]                                                              
                                                                                                    
 Check USPTO configuration and API-key connectivity.                                                
                                                                                                    
 Delegated to `report_health` (see `copilot_cli.shared.output`): building the                       
 client reads `USPTO_CLI_API_KEY`, so a signed-out credential raised upstream                       
 of `USPTOClient.health()`'s own guard and escaped as a raw traceback. The                          
 wrapper guards construction AND probe, so this command reports the failure it                      
 cannot recover from instead of crashing.                                                           
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto products`

```text
                                                                                                    
 Usage: copilot uspto products [OPTIONS]                                                            
                                                                                                    
 Show the USPTO product coverage the CLI should support.                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto request`

```text
                                                                                                    
 Usage: copilot uspto request [OPTIONS] PATH                                                        
                                                                                                    
 Make a generic authenticated request to the USPTO ODP API.                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      TEXT  ODP path relative to USPTO_CLI_BASE_URL. [required]                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --method  -X      TEXT  HTTP method. [default: GET]                                              │
│ --params          TEXT  Query params as a JSON object.                                           │
│ --body            TEXT  Request body as a JSON object or array.                                  │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto auth`

```text
                                                                                                    
 Usage: copilot uspto auth [OPTIONS] COMMAND [ARGS]...                                              
                                                                                                    
 Auth requirements and capture instructions.                                                        
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ list    List required auth artifacts, keys, and session types.                                   │
│ show    Show detailed instructions for one auth artifact.                                        │
│ status  Show what is implemented and what you still need to provide.                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto auth list`

```text
                                                                                                    
 Usage: copilot uspto auth list [OPTIONS]                                                           
                                                                                                    
 List required auth artifacts, keys, and session types.                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto auth show`

```text
                                                                                                    
 Usage: copilot uspto auth show [OPTIONS] ARTIFACT_ID                                               
                                                                                                    
 Show detailed instructions for one auth artifact.                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    artifact_id      TEXT  Auth artifact id from `copilot uspto auth list`. [required]          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto auth status`

```text
                                                                                                    
 Usage: copilot uspto auth status [OPTIONS]                                                         
                                                                                                    
 Show what is implemented and what you still need to provide.                                       
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents`

```text
                                                                                                    
 Usage: copilot uspto patents [OPTIONS] COMMAND [ARGS]...                                           
                                                                                                    
 Patent search and retrieval.                                                                       
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ search                Create a normalized patent search handoff.                                 │
│ application           Create a normalized patent application handoff.                            │
│ office-actions        Search Office Action records using the live API.                           │
│ office-action-fields  Fetch the Office Action field schema from the live API.                    │
│ ptab                  Create a normalized PTAB handoff.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents search`

```text
                                                                                                    
 Usage: copilot uspto patents search [OPTIONS] QUERY                                                
                                                                                                    
 Create a normalized patent search handoff.                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Patent search text. [required]                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents application`

```text
                                                                                                    
 Usage: copilot uspto patents application [OPTIONS] IDENTIFIER                                      
                                                                                                    
 Create a normalized patent application handoff.                                                    
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    identifier      TEXT  Application, publication, or patent identifier. [required]            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --type  -t      TEXT  Identifier type. [default: application]                                    │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents office-actions`

```text
                                                                                                    
 Usage: copilot uspto patents office-actions [OPTIONS] [QUERY]                                      
                                                                                                    
 Search Office Action records using the live API.                                                   
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│   query      [QUERY]  Office-action criteria query. [default: *:*]                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --start        INTEGER  Result offset. [default: 0]                                              │
│ --rows         INTEGER  Number of records to return. [default: 25]                               │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents office-action-fields`

```text
                                                                                                    
 Usage: copilot uspto patents office-action-fields [OPTIONS]                                        
                                                                                                    
 Fetch the Office Action field schema from the live API.                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto patents ptab`

```text
                                                                                                    
 Usage: copilot uspto patents ptab [OPTIONS] QUERY                                                  
                                                                                                    
 Create a normalized PTAB handoff.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  PTAB query, identifier, or party name. [required]                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks`

```text
                                                                                                    
 Usage: copilot uspto trademarks [OPTIONS] COMMAND [ARGS]...                                        
                                                                                                    
 Trademark search and TSDR retrieval.                                                               
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ search        Create a normalized trademark search handoff.                                      │
│ status        Fetch normalized trademark status.                                                 │
│ tmog          Create a TMOG handoff.                                                             │
│ id-manual     Create an ID Manual handoff.                                                       │
│ design-codes  Create a Design Search Code Manual handoff.                                        │
│ proceedings   Create a TTAB proceedings handoff.                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks search`

```text
                                                                                                    
 Usage: copilot uspto trademarks search [OPTIONS] QUERY                                             
                                                                                                    
 Create a normalized trademark search handoff.                                                      
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Trademark search text. [required]                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks status`

```text
                                                                                                    
 Usage: copilot uspto trademarks status [OPTIONS] IDENTIFIER                                        
                                                                                                    
 Fetch normalized trademark status.                                                                 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    identifier      TEXT  Trademark serial, registration, ref, or IR number. [required]         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --type  -t      TEXT  Identifier type such as sn, rn, ref, or ir. [default: sn]                  │
│ --help                Show this message and exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks tmog`

```text
                                                                                                    
 Usage: copilot uspto trademarks tmog [OPTIONS] QUERY                                               
                                                                                                    
 Create a TMOG handoff.                                                                             
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Trademark Official Gazette query. [required]                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks id-manual`

```text
                                                                                                    
 Usage: copilot uspto trademarks id-manual [OPTIONS] QUERY                                          
                                                                                                    
 Create an ID Manual handoff.                                                                       
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Goods/services wording query. [required]                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks design-codes`

```text
                                                                                                    
 Usage: copilot uspto trademarks design-codes [OPTIONS] QUERY                                       
                                                                                                    
 Create a Design Search Code Manual handoff.                                                        
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Design-mark search query. [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto trademarks proceedings`

```text
                                                                                                    
 Usage: copilot uspto trademarks proceedings [OPTIONS] QUERY                                        
                                                                                                    
 Create a TTAB proceedings handoff.                                                                 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Trademark proceeding query or party name. [required]                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto assignments`

```text
                                                                                                    
 Usage: copilot uspto assignments [OPTIONS] COMMAND [ARGS]...                                       
                                                                                                    
 Assignment and ownership lookup.                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ search  Create an assignment search handoff.                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto assignments search`

```text
                                                                                                    
 Usage: copilot uspto assignments search [OPTIONS] QUERY                                            
                                                                                                    
 Create an assignment search handoff.                                                               
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Assignor, assignee, reel/frame, or entity query. [required]                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto copyright`

```text
                                                                                                    
 Usage: copilot uspto copyright [OPTIONS] COMMAND [ARGS]...                                         
                                                                                                    
 Copyright registry handoff and lookup.                                                             
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ search  Create a copyright public-records handoff.                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto copyright search`

```text
                                                                                                    
 Usage: copilot uspto copyright search [OPTIONS] QUERY                                              
                                                                                                    
 Create a copyright public-records handoff.                                                         
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query      TEXT  Copyright search text. [required]                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto dossier`

```text
                                                                                                    
 Usage: copilot uspto dossier [OPTIONS] COMMAND [ARGS]...                                           
                                                                                                    
 Cross-source dossier workflows.                                                                    
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ build   Build and save a clearance dossier.                                                      │
│ show    Show a saved dossier.                                                                    │
│ list    List saved dossiers.                                                                     │
│ export  Export a dossier to disk.                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto dossier build`

```text
                                                                                                    
 Usage: copilot uspto dossier build [OPTIONS] NAME SEEDS                                            
                                                                                                    
 Build and save a clearance dossier.                                                                
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name       TEXT  Saved dossier name. [required]                                             │
│ *    seeds      TEXT  Comma-separated seeds to fan out across sources. [required]                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto dossier show`

```text
                                                                                                    
 Usage: copilot uspto dossier show [OPTIONS] NAME                                                   
                                                                                                    
 Show a saved dossier.                                                                              
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Saved dossier name. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto dossier list`

```text
                                                                                                    
 Usage: copilot uspto dossier list [OPTIONS]                                                        
                                                                                                    
 List saved dossiers.                                                                               
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto dossier export`

```text
                                                                                                    
 Usage: copilot uspto dossier export [OPTIONS] NAME OUTPUT                                          
                                                                                                    
 Export a dossier to disk.                                                                          
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name        TEXT  Saved dossier name. [required]                                            │
│ *    output      TEXT  Output file path. [required]                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --format  -f      TEXT  json or md. [default: json]                                              │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto watch`

```text
                                                                                                    
 Usage: copilot uspto watch [OPTIONS] COMMAND [ARGS]...                                             
                                                                                                    
 Watchlist management.                                                                              
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ create  Create a watchlist.                                                                      │
│ list    List watchlists.                                                                         │
│ run     Run a saved watchlist.                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto watch create`

```text
                                                                                                    
 Usage: copilot uspto watch create [OPTIONS] NAME SEEDS                                             
                                                                                                    
 Create a watchlist.                                                                                
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name       TEXT  Watch name. [required]                                                     │
│ *    seeds      TEXT  Comma-separated seeds to monitor. [required]                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto watch list`

```text
                                                                                                    
 Usage: copilot uspto watch list [OPTIONS]                                                          
                                                                                                    
 List watchlists.                                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto watch run`

```text
                                                                                                    
 Usage: copilot uspto watch run [OPTIONS] NAME                                                      
                                                                                                    
 Run a saved watchlist.                                                                             
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Watch name. [required]                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto sessions`

```text
                                                                                                    
 Usage: copilot uspto sessions [OPTIONS] COMMAND [ARGS]...                                          
                                                                                                    
 Imported portal sessions.                                                                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ import   Import a portal session.                                                                │
│ capture  Open a browser and capture authenticated storage state.                                 │
│ list     List imported sessions.                                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto sessions import`

```text
                                                                                                    
 Usage: copilot uspto sessions import [OPTIONS] NAME FILE                                           
                                                                                                    
 Import a portal session.                                                                           
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Session name. [required]                                                    │
│ *    file      TEXT  Path to storage-state or cookie JSON. [required]                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto sessions capture`

```text
                                                                                                    
 Usage: copilot uspto sessions capture [OPTIONS] NAME URL                                           
                                                                                                    
 Open a browser and capture authenticated storage state.                                            
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    name      TEXT  Session name. [required]                                                    │
│ *    url       TEXT  Login or portal URL to open for manual authentication. [required]           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto sessions list`

```text
                                                                                                    
 Usage: copilot uspto sessions list [OPTIONS]                                                       
                                                                                                    
 List imported sessions.                                                                            
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto portal`

```text
                                                                                                    
 Usage: copilot uspto portal [OPTIONS] COMMAND [ARGS]...                                            
                                                                                                    
 Session-backed portal retrieval.                                                                   
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ fetch  Fetch a portal page using an imported session.                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto portal fetch`

```text
                                                                                                    
 Usage: copilot uspto portal fetch [OPTIONS] URL                                                    
                                                                                                    
 Fetch a portal page using an imported session.                                                     
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    url      TEXT  Target portal URL. [required]                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --session       -s      TEXT     Imported session name. [required]                            │
│    --include-html                   Include full HTML content.                                   │
│    --timeout-ms            INTEGER  Navigation timeout. [default: 30000]                         │
│    --help                           Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto tsdr`

```text
                                                                                                    
 Usage: copilot uspto tsdr [OPTIONS] COMMAND [ARGS]...                                              
                                                                                                    
 TSDR trademark retrieval.                                                                          
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ status  Fetch TSDR trademark case status.                                                        │
│ docs    Fetch TSDR case document bundles or metadata.                                            │
│ image   Fetch a trademark image from TSDR.                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto tsdr status`

```text
                                                                                                    
 Usage: copilot uspto tsdr status [OPTIONS] IDENTIFIER                                              
                                                                                                    
 Fetch TSDR trademark case status.                                                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    identifier      TEXT  Trademark serial, registration, ref, or IR number. [required]         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --type    -t      TEXT  Identifier type such as sn, rn, ref, or ir. [default: sn]                │
│ --format  -f      TEXT  json, xml, html, pdf, or zip. [default: json]                            │
│ --help                  Show this message and exit.                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto tsdr docs`

```text
                                                                                                    
 Usage: copilot uspto tsdr docs [OPTIONS] QUERY_VALUE                                               
                                                                                                    
 Fetch TSDR case document bundles or metadata.                                                      
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    query_value      TEXT  Identifier value. [required]                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --query-type  -q      TEXT  sn, rn, ref, or ir. [default: sn]                                    │
│ --format      -f      TEXT  json, xml, pdf, or zip. [default: pdf]                               │
│ --category            TEXT  Document category filter.                                            │
│ --doc-type            TEXT  Document type filter.                                                │
│ --date                TEXT  Exact date YYYY-MM-DD.                                               │
│ --from-date           TEXT  Start date YYYY-MM-DD.                                               │
│ --to-date             TEXT  End date YYYY-MM-DD.                                                 │
│ --sort                TEXT  Sort expression such as date:A.                                      │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto tsdr image`

```text
                                                                                                    
 Usage: copilot uspto tsdr image [OPTIONS] SERIAL_NUMBER                                            
                                                                                                    
 Fetch a trademark image from TSDR.                                                                 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    serial_number      TEXT  Trademark serial number. [required]                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover`

```text
                                                                                                    
 Usage: copilot uspto discover [OPTIONS] COMMAND [ARGS]...                                          
                                                                                                    
 Automated API contract discovery via Playwright browser interception. Opens a real browser,        
 intercepts XHR/fetch requests during a search on USPTO portals, and saves captured                 
 request/response pairs as structured JSON contracts to ~/.copilot-cli/uspto/contracts/. Use these  
 contracts to generate adapter stubs. Requires: playwright package with Chromium (pip install       
 playwright && playwright install chromium). Workflow: products -> auto/manual -> show -> generate. 
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ auto      Run automated contract discovery using a saved product recipe.                         │
│ manual    Open a headed browser for manual API contract discovery.                               │
│ list      List all saved API contracts by product name.                                          │
│ show      Show the full saved API contract for a product.                                        │
│ generate  Generate Python adapter stubs from a saved API contract.                               │
│ products  Show all available product recipes and their confirmation status.                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover auto`

```text
                                                                                                    
 Usage: copilot uspto discover auto [OPTIONS] PRODUCT                                               
                                                                                                    
 Run automated contract discovery using a saved product recipe.                                     
                                                                                                    
 Opens a headed Chromium browser, navigates to the recipe URL, fills the search                     
 field with the sample query, submits, and captures all XHR/fetch API requests.                     
 The highest-scored contract is saved to ~/.copilot-cli/uspto/contracts/<product>.json.             
 Requires: Playwright with Chromium (pip install playwright && playwright install chromium).        
 Use 'copilot uspto discover products' to see all valid product names.                              
 Output: JSON with keys: product, captured (count), top_url, top_method, response_status, saved_to. 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    product      TEXT  Product name from the recipe registry. Valid names: ptab,                │
│                         trademark_search, tmog, id_manual, design_search, assignment_search. Run │
│                         'discover products' to see all.                                          │
│                         [required]                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --session  -s      TEXT  Imported session name to use for auth.                                  │
│ --query    -q      TEXT  Override the recipe sample query.                                       │
│ --help                   Show this message and exit.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover manual`

```text
                                                                                                    
 Usage: copilot uspto discover manual [OPTIONS] URL                                                 
                                                                                                    
 Open a headed browser for manual API contract discovery.                                           
                                                                                                    
 Navigates to the given URL, starts network interception, then waits for you to                     
 perform a search in the browser. Press Enter in the terminal when done. All                        
 intercepted XHR/fetch requests are ranked and the top contract is saved to                         
 ~/.copilot-cli/uspto/contracts/<product>.json.                                                     
 Requires: Playwright with Chromium (pip install playwright && playwright install chromium).        
 Output: JSON with keys: product, captured (count), top_url, top_method, response_status, saved_to. 
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    url      TEXT  Target portal URL to open in the browser. [required]                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --session  -s      TEXT     Imported session name to use for auth.                               │
│ --product  -p      TEXT     Product label to save the contract under. [default: unknown]         │
│ --query    -q      TEXT     Sample query label to embed in the contract.                         │
│ --timeout  -t      INTEGER  Navigation timeout in seconds for the initial page load (default:    │
│                             120).                                                                │
│                             [default: 120]                                                       │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover list`

```text
                                                                                                    
 Usage: copilot uspto discover list [OPTIONS]                                                       
                                                                                                    
 List all saved API contracts by product name.                                                      
                                                                                                    
 Output: Table with column 'product'. Empty table if no contracts saved yet.                        
 Contracts are stored in ~/.copilot-cli/uspto/contracts/.                                           
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover show`

```text
                                                                                                    
 Usage: copilot uspto discover show [OPTIONS] PRODUCT                                               
                                                                                                    
 Show the full saved API contract for a product.                                                    
                                                                                                    
 Output: JSON with fields: product, captured_at, url, method, request_headers,                      
 request_content_type, request_body, response_status, response_content_type,                        
 response_headers, response_body_sample, response_body_size, sample_query, notes.                   
 Prerequisite: Run 'discover auto <product>' or 'discover manual' first.                            
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    product      TEXT  Product name to show the saved contract for. [required]                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover generate`

```text
                                                                                                    
 Usage: copilot uspto discover generate [OPTIONS] PRODUCT                                           
                                                                                                    
 Generate Python adapter stubs from a saved API contract.                                           
                                                                                                    
 Reads the contract saved by 'discover auto' or 'discover manual', then writes                      
 scaffolded client method, Typer command, and test files to the output directory.                   
 Generated files are stubs that need review before merging into the service.                        
 Prerequisite: A saved contract must exist for the given product.                                   
 Output: JSON mapping generated filenames to their absolute paths.                                  
                                                                                                    
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ *    product      TEXT  Product name to generate stubs for. [required]                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --output-dir  -o      TEXT  Directory to write generated files into. [default: .]                │
│ --help                      Show this message and exit.                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `copilot uspto discover products`

```text
                                                                                                    
 Usage: copilot uspto discover products [OPTIONS]                                                   
                                                                                                    
 Show all available product recipes and their confirmation status.                                  
                                                                                                    
 Output: Table with columns: product, url, search_selector, sample_query, confirmed.                
                                                                                                    
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

