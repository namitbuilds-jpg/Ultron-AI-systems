#!/usr/bin/env python3
"""
ULTRON 5.1 — SELF TEST
=======================
Checks that the whole stack is actually ready before you spend time guessing
why something is not working.

    python selftest.py

Checks
  1. Python version
  2. Ollama reachable at the configured endpoint
  3. Which models are installed + their real download size
  4. Whether those models fit the selected device profile
  5. The Laptop Authority Agent listening on 127.0.0.1:8765
  6. The built ultron.html has the AI upgrade injected
  7. The venv + dependencies exist
"""

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENDPOINT = os.environ.get("ULTRON_ENDPOINT", "http://localhost:11434")
AGENT_HOST, AGENT_PORT = "127.0.0.1", 8765

GB = 1024 ** 3
PROFILES = {
    "tiny":  (5.0,  "8 GB RAM or less"),
    "small": (8.0,  "up to 16 GB RAM"),
    "large": (26.0, "24 GB RAM or more"),
}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = DIM = RESET = ""

results = []


def check(ok, label, detail=""):
    results.append(ok)
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def warn(label, detail=""):
    print(f"  [{YELLOW}WARN{RESET}] {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def read_profile():
    """Read the device profile the page would use (localStorage is per-origin,
    so we accept an override here and default to 'small')."""
    return os.environ.get("ULTRON_PROFILE", "small")


def main():
    print()
    print("=" * 66)
    print("  ULTRON 5.1 - SELF TEST")
    print("=" * 66)

    # 1. python
    print("\n  Python")
    v = sys.version_info
    check(v >= (3, 9), f"Python {v.major}.{v.minor}.{v.micro}",
          "" if v >= (3, 9) else "needs 3.9+ (3.10+ recommended)")

    # 2. ollama
    print("\n  Ollama")
    models = []
    try:
        with urllib.request.urlopen(ENDPOINT.rstrip("/") + "/api/tags", timeout=6) as r:
            data = json.loads(r.read().decode())
        models = data.get("models", [])
        check(True, f"reachable at {ENDPOINT}", f"{len(models)} model(s)")
    except Exception as e:
        check(False, f"not reachable at {ENDPOINT}", str(e))
        warn("Start Ollama:  ollama serve")

    # 3 + 4. models vs budget
    if models:
        profile = read_profile()
        budget, profile_desc = PROFILES.get(profile, PROFILES["small"])
        print(f"\n  Installed models  (profile: {profile} - {profile_desc}, "
              f"budget {budget} GB per model)")
        for m in models:
            gb = (m.get("size") or 0) / GB
            det = m.get("details") or {}
            fits = gb <= budget
            flag = f"{GREEN}fits{RESET}" if fits else f"{RED}over budget{RESET}"
            print(f"    {m.get('name','?'):<28} {gb:>6.2f} GB   "
                  f"{DIM}{det.get('parameter_size','')} {det.get('quantization_level','')}{RESET}   [{flag}]")
        if not any((m.get("size") or 0) / GB <= budget for m in models):
            warn("No installed model fits the budget.",
                 "Pick a smaller model, or set ULTRON_PROFILE=large to override.")

    # 5. agent
    print("\n  Laptop Authority Agent")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((AGENT_HOST, AGENT_PORT))
        check(True, f"agent listening on ws://{AGENT_HOST}:{AGENT_PORT}")
    except Exception as e:
        check(False, f"agent not reachable on {AGENT_HOST}:{AGENT_PORT}", str(e))
        warn("Start it:  start_ultron_agent.bat")
    finally:
        s.close()

    # 6. built page
    print("\n  Built page")
    page = HERE / "ultron.html"
    if page.exists():
        text = page.read_text(encoding="utf-8", errors="replace")
        check("ULTRON-AI-UPGRADE-BEGIN" in text,
              "ultron.html has the AI upgrade injected")
        check("ULTRON AGENT FIXES" in (HERE / "ultron_agent.py").read_text(
            encoding="utf-8", errors="replace")
            if (HERE / "ultron_agent.py").exists() else False,
              "ultron_agent.py has the backend fixes spliced")
    else:
        check(False, "ultron.html not found", "run:  python install.py")

    # 7. venv
    print("\n  Environment")
    venv = HERE / ".venv"
    if venv.exists():
        check(True, "virtual environment present", str(venv / "Scripts" if os.name == "nt" else "bin"))
    else:
        warn("no .venv yet", "start_ultron_agent.bat creates it on first run")

    # summary
    passed = sum(1 for r in results if r)
    total = len(results)
    print()
    print("=" * 66)
    if passed == total:
        print(f"  {GREEN}ALL GOOD{RESET} - {passed}/{total} checks passed")
    else:
        print(f"  {YELLOW}{passed}/{total} checks passed{RESET} - see the FAIL lines above")
    print("=" * 66)
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
