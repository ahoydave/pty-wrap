#!/usr/bin/env python3
"""
pty-wrap: A PTY wrapper enabling interaction with interactive programs via files.

This tool bridges the gap between atomic command execution (pipes) and true
interactive terminal communication (PTY). It runs a program in a pseudo-terminal
and exposes I/O through files, allowing agents to read output, think, and respond
across multiple command invocations.
"""

import argparse
import os
import pty
import select
import shutil
import sys
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser(
        prog="pty-wrap",
        description="Run interactive programs with file-based I/O.",
        epilog="""
Examples:
  # Auto-generate session files:
  pty-wrap -- python3 quiz.py &
  # Prints:
  #   output: /tmp/pty-wrap-abc123/output.txt
  #   input:  /tmp/pty-wrap-abc123/input.fifo
  
  # Interact:
  cat /tmp/pty-wrap-abc123/output.txt
  echo "answer" > /tmp/pty-wrap-abc123/input.fifo
  cat /tmp/pty-wrap-abc123/output.txt

  # If you need to read final output after program exits, use --no-cleanup:
  pty-wrap --no-cleanup -- python3 quiz.py &
  # ... interact ...
  # Files persist in /tmp until manually deleted or system cleanup

Cleanup behavior:
  By default, session files are deleted immediately when the program exits.
  This means you may not be able to read the final output if you're not fast
  enough. Use --no-cleanup if you need to reliably read output after exit.
  Files in /tmp are cleaned by the system periodically anyway.

How it works:
  The program runs inside a PTY (pseudo-terminal), so it behaves exactly as if
  a human were typing in a terminal. All output is appended to the output file.
  Input is read from the FIFO and sent to the program as keystrokes.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="File to write program output to. If not specified, auto-generated.",
    )
    
    parser.add_argument(
        "-i", "--input",
        metavar="FIFO",
        help="FIFO to read input from. If not specified, auto-generated.",
    )
    
    parser.add_argument(
        "-m", "--marker",
        default="[pty-wrap: process exited]",
        metavar="TEXT",
        help="Marker written to output when program exits (default: %(default)s)",
    )
    
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't delete session files on exit (useful for debugging)",
    )
    
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="Command to run (use -- before command if it has flags)",
    )
    
    args = parser.parse_args()
    
    # Handle the -- separator
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    
    if not command:
        parser.error("No command specified")
    
    # Determine if we're auto-generating paths
    auto_generated = args.output is None and args.input is None
    session_dir = None
    
    if auto_generated:
        # Create a unique session directory
        session_id = uuid.uuid4().hex[:8]
        session_dir = os.path.join(tempfile.gettempdir(), f"pty-wrap-{session_id}")
        os.makedirs(session_dir)
        
        output_file = os.path.join(session_dir, "output.txt")
        input_fifo = os.path.join(session_dir, "input.fifo")
        
        # Create the FIFO
        os.mkfifo(input_fifo)
        
        # Print paths for the agent to use
        print(f"output: {output_file}", flush=True)
        print(f"input:  {input_fifo}", flush=True)
        
        cleanup = not args.no_cleanup
    else:
        if args.output is None or args.input is None:
            parser.error("Must specify both -o and -i, or neither (for auto-generation)")
        output_file = args.output
        input_fifo = args.input
        cleanup = False  # Don't clean up user-specified files
    
    try:
        run_wrapper(
            output_file=output_file,
            input_fifo=input_fifo,
            command=command,
            exit_marker=args.marker,
        )
    finally:
        if cleanup and session_dir:
            shutil.rmtree(session_dir, ignore_errors=True)


def run_wrapper(output_file: str, input_fifo: str, command: list[str], exit_marker: str):
    """Run a command in a PTY with file-based I/O."""
    
    # Validate input FIFO exists
    if not os.path.exists(input_fifo):
        sys.exit(f"Error: Input FIFO does not exist: {input_fifo}\nCreate it with: mkfifo {input_fifo}")
    
    # Create PTY
    master_fd, slave_fd = pty.openpty()
    
    pid = os.fork()
    
    if pid == 0:
        # Child: run the command
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        os.execvp(command[0], command)
    
    else:
        # Parent: bridge between PTY, output file, and input FIFO
        os.close(slave_fd)
        
        out_f = open(output_file, "a")
        in_fd = os.open(input_fifo, os.O_RDONLY | os.O_NONBLOCK)
        
        try:
            while True:
                ready, _, _ = select.select([master_fd, in_fd], [], [], 0.1)
                
                for fd in ready:
                    if fd == master_fd:
                        try:
                            data = os.read(master_fd, 4096)
                            if data:
                                out_f.write(data.decode("utf-8", errors="replace"))
                                out_f.flush()
                            else:
                                raise EOFError
                        except OSError:
                            raise EOFError
                    
                    elif fd == in_fd:
                        try:
                            data = os.read(in_fd, 4096)
                            if data:
                                os.write(master_fd, data)
                        except OSError:
                            pass
                
                # Check if child exited
                result = os.waitpid(pid, os.WNOHANG)
                if result[0] != 0:
                    drain_pty(master_fd, out_f)
                    break
        
        except EOFError:
            pass
        
        finally:
            if exit_marker:
                out_f.write(f"\n{exit_marker}\n")
            out_f.close()
            os.close(in_fd)
            os.close(master_fd)


def drain_pty(master_fd, out_f):
    """Read any remaining output from PTY."""
    while True:
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if not ready:
            break
        try:
            data = os.read(master_fd, 4096)
            if data:
                out_f.write(data.decode("utf-8", errors="replace"))
                out_f.flush()
            else:
                break
        except OSError:
            break


if __name__ == "__main__":
    main()
