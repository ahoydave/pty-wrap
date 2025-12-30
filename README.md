# pty-wrap

Run interactive programs with simple command-based I/O.

## The Problem

Interactive programs require back-and-forth communication that's hard to automate:
- Password prompts
- Interactive installers ("Continue? [y/n]")
- REPLs (Python, Node, etc.)

## The Solution

`pty-wrap` runs programs in a PTY and provides simple subcommands for interaction:

```bash
pty-wrap start -- python3 quiz.py   # Start, get session ID
pty-wrap read <session>              # Read output (never blocks)
pty-wrap send <session> "answer"     # Send input (safe, with timeout)
pty-wrap status <session>            # Check if running/exited
pty-wrap stop <session>              # Clean up
pty-wrap list                        # Show all sessions
```

## Installation

```bash
uv tool install git+https://github.com/ahoydave/pty-wrap
```

## Quick Start

```bash
# Start an interactive program
$ pty-wrap start -- python3 quiz.py
session: abc12345

# Read what it printed
$ pty-wrap read abc12345
What is 42 doubled?

# Send your answer
$ pty-wrap send abc12345 "84"
ok

# Read the response
$ pty-wrap read abc12345
What is 42 doubled?
84
Correct!

[pty-wrap: process exited]

# Clean up
$ pty-wrap stop abc12345
stopped
```

## Why PTY Instead of Pipes?

| Feature | Pipe | PTY |
|---------|------|-----|
| Input echo | No | Yes |
| `isatty()` returns | False | True |
| Colored output | Usually disabled | Works |
| Signal chars (Ctrl+C) | No | Yes |

Many programs check `isatty()` and disable interactive features when connected to pipes. With a PTY, they behave exactly as if a human were using a terminal.

## Platform Support

- **macOS**: ✅ Fully supported
- **Linux**: ✅ Fully supported  
- **Windows**: ❌ Not supported (no PTY)

## License

MIT
