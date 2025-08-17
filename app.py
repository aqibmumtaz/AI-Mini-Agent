
# --- IMPORTS ---
import sys
import threading
import subprocess
import os
import signal


 # --- PORT KILLER ---
def kill_process_on_port(port):
    """Kill process running on the given port (cross-platform)."""
    try:
        # macOS/Linux: use lsof
        output = (
            subprocess.check_output(f"lsof -ti tcp:{port}", shell=True).decode().strip()
        )
        if output:
            for pid in output.splitlines():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        # Windows: use netstat and taskkill
        output = (
            subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True)
            .decode()
            .strip()
        )
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                try:
                    subprocess.call(f"taskkill /PID {pid} /F", shell=True)
                except Exception:
                    pass
    except Exception:
        pass


 # --- GRADIO RUNNER ---
def run_gradio():
    from gradio_chatbot import demo

    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, inbrowser=False)


 # --- MCP SERVER RUNNER ---
def run_mcp_server():
    from mcp_server import run_server

    run_server()


if __name__ == "__main__":
    # Kill processes on ports 5000 (Flask) and 7860 (Gradio) before starting
    kill_process_on_port(5000)
    kill_process_on_port(7860)
    # Default to "all" if run from VS Code (no args or run/debug)
    run_mode = None
    if len(sys.argv) > 1:
        run_mode = sys.argv[1]
    else:
        # VS Code "Run" or "Debug" typically runs with no extra args
        run_mode = "all"
    if run_mode == "chatbot":
        run_gradio()
    elif run_mode == "server":
        run_mcp_server()
    elif run_mode == "all":
        t1 = threading.Thread(target=run_mcp_server, daemon=True)
        t1.start()
        run_gradio()
    else:
        print("Usage: python app.py [chatbot|server|all]")
        print("  chatbot: Run the Gradio chatbot UI")
        print("  server : Run the MCP HTTP API server")
        print("  all    : Run both MCP server and Gradio chatbot together")
