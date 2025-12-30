# pty-wrap

A PTY wrapper that exposes interactive program I/O through files.

## The Problem

Interactive programs require back-and-forth communication that's hard to automate:

- Password prompts
- Interactive installers ("Continue? [y/n]")
- REPLs (Python, Node, etc.)
- Programs that behave differently when connected to a terminal

## The Solution

`pty-wrap` runs programs inside a pseudo-terminal (PTY) and exposes I/O through files:

1. **Output file**: All program output is appended here
2. **Input FIFO**: Send input by writing to this named pipe

This allows you to: read output → decide what to send → write input → repeat.

## Installation

**Recommended: uv tool** (isolated environment, consistent Python version)

```bash
uv tool install /path/to/pty-wrap
# Or from git:
uv tool install git+https://github.com/your-username/pty-wrap
```

**Alternative: pip**

```bash
pip install /path/to/pty-wrap
```

**Man page (optional):**

```bash
sudo cp pty-wrap.1 /usr/local/share/man/man1/
```

## Quick Start

```bash
# Start an interactive program (auto-generates session files):
pty-wrap --no-cleanup -- python3 my_program.py &
# Prints:
#   output: /tmp/pty-wrap-abc123/output.txt
#   input:  /tmp/pty-wrap-abc123/input.fifo

# Read what it printed
cat /tmp/pty-wrap-abc123/output.txt

# Send input
echo "hello" > /tmp/pty-wrap-abc123/input.fifo

# Check the response
cat /tmp/pty-wrap-abc123/output.txt

# Clean up when done (or let /tmp auto-cleanup)
rm -rf /tmp/pty-wrap-abc123
```

## Cleanup Behavior

By default, session files are deleted immediately when the program exits. Use `--no-cleanup` if you need to reliably read the final output after the program exits. Files in `/tmp` are cleaned by the system periodically anyway.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                         pty-wrap                             │
│                                                              │
│   ┌─────────┐     ┌─────────────┐     ┌─────────────────┐   │
│   │  Input  │────▶│ PTY Master  │────▶│ Target Program  │   │
│   │  FIFO   │     │             │◀────│ (in PTY slave)  │   │
│   └─────────┘     └─────────────┘     └─────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│                   ┌─────────────┐                            │
│                   │ Output File │                            │
│                   └─────────────┘                            │
└─────────────────────────────────────────────────────────────┘

Workflow:
1. Start pty-wrap (runs in background)
2. cat output.txt        → See what program printed
3. echo "response" > fifo → Send input
4. cat output.txt        → See program's response
5. Repeat until done
```

## Why PTY Instead of Pipes?

| Feature | Pipe | PTY |
|---------|------|-----|
| Input echo | No | Yes |
| `isatty()` returns | False | True |
| Colored output | Usually disabled | Works |
| Line editing | No | Yes |
| Signal chars (Ctrl+C) | No | Yes |

Many programs check `isatty()` and disable interactive features when connected to pipes. With a PTY, they behave exactly as if a human were using a terminal.

## Documentation

```bash
# Built-in help
pty-wrap --help

# Man page (if installed)
man pty-wrap
```

## Platform Support

- **macOS**: ✅ Fully supported
- **Linux**: ✅ Fully supported
- **Windows**: ❌ Not supported (no PTY)

## License

MIT
