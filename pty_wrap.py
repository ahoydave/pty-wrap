#!/usr/bin/env python3
"""
pty-wrap: Run interactive programs with simple command-based I/O.

Subcommands:
  start   Start a wrapped program, returns session ID
  read    Read output from a session
  send    Send input to a session (safe, with timeout)
  status  Check if session is still running
  stop    Stop a session and clean up
"""

import argparse
import os
import pty
import select
import shutil
import signal
import sys
import tempfile
import time
import uuid

SESSIONS_DIR = os.path.join(tempfile.gettempdir(), "pty-wrap-sessions")


def main():
    parser = argparse.ArgumentParser(
        prog="pty-wrap",
        description="Run interactive programs with simple command-based I/O.",
        epilog="""
Example flow:
  $ pty-wrap start -- python3 quiz.py
  session: abc12345

  $ pty-wrap read abc12345
  What is 42 doubled?

  $ pty-wrap send abc12345 "84"
  ok

  $ pty-wrap read abc12345
  What is 42 doubled?
  84
  Correct!
  [pty-wrap: process exited]

  $ pty-wrap status abc12345
  exited

  $ pty-wrap stop abc12345
  stopped
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # start
    start_parser = subparsers.add_parser("start", help="Start a wrapped program")
    start_parser.add_argument("program", nargs=argparse.REMAINDER, help="Command to run (use -- before if it has flags)")
    
    # read
    read_parser = subparsers.add_parser("read", help="Read output from a session")
    read_parser.add_argument("session", help="Session ID")
    
    # send
    send_parser = subparsers.add_parser("send", help="Send input to a session")
    send_parser.add_argument("session", help="Session ID")
    send_parser.add_argument("input", help="Input to send (newline added automatically)")
    
    # status
    status_parser = subparsers.add_parser("status", help="Check session status")
    status_parser.add_argument("session", help="Session ID")
    
    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop session and clean up")
    stop_parser.add_argument("session", help="Session ID")
    
    # list
    subparsers.add_parser("list", help="List active sessions")
    
    args = parser.parse_args()
    
    if args.command == "start":
        cmd_start(args)
    elif args.command == "read":
        cmd_read(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "list":
        cmd_list(args)


def get_session_dir(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, session_id)


def cmd_start(args):
    program = args.program
    if program and program[0] == "--":
        program = program[1:]
    
    if not program:
        sys.exit("Error: No command specified")
    
    # Create session
    session_id = uuid.uuid4().hex[:8]
    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    output_file = os.path.join(session_dir, "output.txt")
    input_fifo = os.path.join(session_dir, "input.fifo")
    pid_file = os.path.join(session_dir, "pid")
    cmd_file = os.path.join(session_dir, "cmd")
    
    # Save command for reference
    with open(cmd_file, "w") as f:
        f.write(" ".join(program))
    
    # Create FIFO
    os.mkfifo(input_fifo)
    
    # Fork the wrapper process (double-fork to daemonize)
    pid = os.fork()
    if pid > 0:
        # Parent: wait briefly for child to set up, then print session ID
        time.sleep(0.2)
        print(f"session: {session_id}")
        return
    
    # First child: fork again to daemonize
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)
    
    # Daemon process: run the wrapper
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    
    run_wrapper(output_file, input_fifo, program)
    # Don't auto-cleanup - let user call 'pty-wrap stop' to read final output first


def cmd_read(args):
    session_dir = get_session_dir(args.session)
    output_file = os.path.join(session_dir, "output.txt")
    
    if not os.path.exists(output_file):
        sys.exit(f"Error: Session '{args.session}' not found")
    
    with open(output_file) as f:
        print(f.read(), end="")


def cmd_send(args):
    session_dir = get_session_dir(args.session)
    pid_file = os.path.join(session_dir, "pid")
    input_fifo = os.path.join(session_dir, "input.fifo")
    
    if not os.path.exists(session_dir):
        sys.exit(f"Error: Session '{args.session}' not found")
    
    # Check if process is still running
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Check if alive
    except (FileNotFoundError, ProcessLookupError, ValueError):
        sys.exit(f"Error: Session '{args.session}' is not running")
    
    # Write to FIFO with timeout (fork to avoid blocking main process)
    input_data = args.input + "\n"
    
    child_pid = os.fork()
    if child_pid == 0:
        # Child: write to FIFO
        try:
            fd = os.open(input_fifo, os.O_WRONLY)
            os.write(fd, input_data.encode())
            os.close(fd)
            os._exit(0)
        except Exception:
            os._exit(1)
    else:
        # Parent: wait with timeout
        for _ in range(50):  # 5 second timeout
            result = os.waitpid(child_pid, os.WNOHANG)
            if result[0] != 0:
                if result[1] == 0:
                    print("ok")
                    return
                else:
                    sys.exit("Error: Failed to send input")
            time.sleep(0.1)
        
        # Timeout - kill child and report error
        os.kill(child_pid, signal.SIGKILL)
        os.waitpid(child_pid, 0)
        sys.exit("Error: Timeout sending input (process may have exited)")


def cmd_status(args):
    session_dir = get_session_dir(args.session)
    pid_file = os.path.join(session_dir, "pid")
    
    if not os.path.exists(session_dir):
        print("not_found")
        return
    
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        print("running")
    except (FileNotFoundError, ProcessLookupError, ValueError):
        print("exited")


def cmd_stop(args):
    session_dir = get_session_dir(args.session)
    pid_file = os.path.join(session_dir, "pid")
    
    if not os.path.exists(session_dir):
        sys.exit(f"Error: Session '{args.session}' not found")
    
    # Try to kill the process
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.2)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except (FileNotFoundError, ProcessLookupError, ValueError):
        pass
    
    # Clean up session directory
    shutil.rmtree(session_dir, ignore_errors=True)
    print("stopped")


def cmd_list(args):
    if not os.path.exists(SESSIONS_DIR):
        return
    
    for session_id in os.listdir(SESSIONS_DIR):
        session_dir = get_session_dir(session_id)
        pid_file = os.path.join(session_dir, "pid")
        cmd_file = os.path.join(session_dir, "cmd")
        
        status = "exited"
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            status = "running"
        except (FileNotFoundError, ProcessLookupError, ValueError):
            pass
        
        cmd = ""
        try:
            with open(cmd_file) as f:
                cmd = f.read().strip()
        except FileNotFoundError:
            pass
        
        print(f"{session_id}  {status:8}  {cmd}")


def run_wrapper(output_file: str, input_fifo: str, command: list[str]):
    """Run a command in a PTY with file-based I/O."""
    
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
        # Parent: bridge PTY and files
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
            out_f.write("\n[pty-wrap: process exited]\n")
            out_f.close()
            os.close(in_fd)
            os.close(master_fd)


def drain_pty(master_fd, out_f):
    """Read remaining output from PTY."""
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
