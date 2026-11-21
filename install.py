#!/usr/bin/env python3
"""
ULTRON 5.1 — BUILD INSTALLER
=============================
Turns the original source files into a runnable Ultron.

What it does
------------
  1. Copies "ultron (5).html" -> ultron.html and INJECTS the AI-layer upgrade
     into the page's <script type="module"> block.

     Why injection and not a <script src> tag: the whole application lives
     inside one module script, so `askOllama`, `checkOllama`, `state` and
     `osState` are module-scoped and invisible to any external file. Module
     function declarations are mutable bindings, so injecting the upgrade
     inside the module is the only way to rebind them.

  2. Copies the already-patched local authority agent. If an unpatched source
     agent and a fixes module are supplied, the fixes are spliced before __main__.

  3. Copies runtime requirements, the Creative Studio, and local launchers.

Usage
-----
  python install.py                      # auto-detect the source HTML
  python install.py "path/to/ultron.html"
  python install.py --out ./build
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

SENTINEL = "/* ULTRON-AI-UPGRADE-BEGIN */"
SENTINEL_END = "/* ULTRON-AI-UPGRADE-END */"

HERE = Path(__file__).resolve().parent

HTML_CANDIDATES = [
    "ultron (5).html",
    "ultron.html",
    "ultron (4).html",
    "index.html",
]


def find_source_html(explicit=None):
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            sys.exit(f"[!] HTML not found: {p}")
        return p

    roots = [HERE / "src", Path.cwd(), HERE, HERE.parent]
    for root in roots:
        if not root.exists():
            continue
        for name in HTML_CANDIDATES:
            p = root / name
            if p.exists():
                return p.resolve()
        # any single .html in the folder (skip our own built output)
        htmls = sorted(x for x in root.glob("*.html") if x.name != "ultron.html")
        if htmls:
            return htmls[0].resolve()

    sys.exit(
        "[!] Could not find the source HTML.\n"
        "    Run:  python install.py \"path/to/ultron (5).html\""
    )


def inject_upgrade(html_text, upgrade_js):
    """Insert the AI upgrade inside the page's module script."""
    if SENTINEL in html_text:
        return html_text, False  # already injected

    # Locate the module script.
    m = re.search(r"<script\s+type=[\"']module[\"']\s*>", html_text)
    if not m:
        sys.exit(
            "[!] No <script type=\"module\"> found in the HTML.\n"
            "    This build of Ultron expects the module-based page."
        )

    body_start = m.end()

    # Inject after the last top-level `import ...` line in the module, so the
    # upgrade's rebinds are in place before any init code runs.
    insert_at = body_start
    for im in re.finditer(r"^import\s.+?;?\s*$", html_text[body_start:], re.MULTILINE):
        insert_at = body_start + im.end()

    block = (
        "\n\n" + SENTINEL + "\n"
        "/* Injected by install.py — Ultron AI Layer v2.\n"
        "   Rebinds the module-scoped askOllama / checkOllama / pickModel /\n"
        "   pickCoderModel / isCodingTask in place. */\n"
        + upgrade_js.rstrip() + "\n"
        + SENTINEL_END + "\n"
    )

    out = html_text[:insert_at] + block + html_text[insert_at:]
    return out, True


def splice_agent(original_text, fixes_text):
    """Insert the fixes block above the __main__ guard."""
    if "ULTRON AGENT FIXES" in original_text and "get_connectors_public" in original_text:
        return original_text, False

    marker = 'if __name__ == "__main__":'
    idx = original_text.rfind(marker)
    if idx == -1:
        sys.exit("[!] Could not find the `if __name__ == \"__main__\":` block.")

    block = (
        "\n\n# =====================================================================\n"
        "# ULTRON AGENT FIXES (injected by install.py)\n"
        "# ---------------------------------------------------------------------\n"
        "# Security + correctness fixes for ultron_agent.py. Placed above the\n"
        "# __main__ guard so the redefinitions take effect before the server\n"
        "# starts. Later definitions shadow the originals.\n"
        "# ======================================================================\n\n"
        + fixes_text.rstrip() + "\n\n\n"
    )
    return original_text[:idx] + block + original_text[idx:], True


def main():
    ap = argparse.ArgumentParser(description="Build a runnable Ultron from the source files.")
    ap.add_argument("html", nargs="?", help="path to the source HTML (auto-detected if omitted)")
    ap.add_argument("--out", default=".", help="output folder (default: current folder)")
    ap.add_argument("--agent", help="path to ultron_agent.py (auto-detected if omitted)")
    ap.add_argument("--fixes", help="path to ultron-agent-fixes.py (auto-detected if omitted)")
    ap.add_argument("--upgrade", help="path to ultron-ai-upgrade.js (auto-detected if omitted)")
    args = ap.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- locate inputs -------------------------------------------------
    def locate(explicit, names, fallback_names=()):
        if explicit:
            p = Path(explicit).expanduser().resolve()
            if not p.exists():
                sys.exit(f"[!] File not found: {p}")
            return p
        for root in (HERE / "src", Path.cwd(), HERE, HERE.parent):
            if not root.exists():
                continue
            for n in list(names) + list(fallback_names):
                p = root / n
                if p.exists():
                    return p.resolve()
        return None

    upgrade_path = locate(args.upgrade, ["ultron-ai-upgrade.js"])
    fixes_path = locate(args.fixes, ["ultron-agent-fixes.py"])
    agent_path = locate(args.agent, ["ultron_agent.py"])

    if not upgrade_path:
        sys.exit("[!] ultron-ai-upgrade.js not found — keep it next to install.py.")
    if not fixes_path and "ULTRON AGENT FIXES" not in agent_path.read_text(encoding="utf-8"):
        sys.exit("[!] No fixes module found and the source agent is not already patched.")
    if not agent_path:
        sys.exit("[!] ultron_agent.py not found — keep it next to install.py.")

    src_html = find_source_html(args.html)

    # --- 1. build the HTML ---------------------------------------------
    html_text = src_html.read_text(encoding="utf-8")
    upgrade_js = upgrade_path.read_text(encoding="utf-8")
    built_html, injected = inject_upgrade(html_text, upgrade_js)
    out_html = out_dir / "ultron.html"
    if out_html.resolve() == src_html.resolve():
        sys.exit("[!] Output would overwrite the source HTML. Use --out <folder>.")
    out_html.write_text(built_html, encoding="utf-8")
    print(f"[+] HTML  : {out_html}  ({'injected' if injected else 'already injected'})")

    # --- 2. build the agent --------------------------------------------
    agent_text = agent_path.read_text(encoding="utf-8")
    fixes_text = fixes_path.read_text(encoding="utf-8") if fixes_path else ""
    built_agent, spliced = splice_agent(agent_text, fixes_text) if fixes_text else (agent_text, False)
    out_agent = out_dir / "ultron_agent.py"
    if out_agent.resolve() == agent_path.resolve():
        sys.exit("[!] Output would overwrite the source agent. Use --out <folder>.")
    out_agent.write_text(built_agent, encoding="utf-8")
    print(f"[+] AGENT : {out_agent}  ({'fixes spliced' if spliced else 'already spliced'})")

    # --- 3. copy the rest ----------------------------------------------
    for extra in (
        "requirements-agent.txt", "requirements-optional.txt", "requirements-media.txt",
        "studio.html", "ultron_media_service.py", ".env.example", ".gitignore",
        "start_hud.bat", "start_ultron_agent.bat", "start_ultron_media.bat",
        "README.md", "START-HERE.txt"
    ):
        p = locate(None, [extra])
        if not p:
            continue
        dest = out_dir / extra
        if p.resolve() != dest.resolve():
            shutil.copy2(p, dest)
        print(f"[+] COPY  : {dest}")

    # --- 4. sanity check the built HTML --------------------------------
    if SENTINEL not in out_html.read_text(encoding="utf-8"):
        sys.exit("[!] Build verification failed — upgrade block missing.")
    print("[+] Build verified.")

    print("")
    print("=" * 62)
    print("  ULTRON BUILT. Next:")
    print("=" * 62)
    print("  1. Copy .env.example to .env and set a unique ULTRON_AGENT_TOKEN.")
    print("     Add your own AGNES_API_KEY only if you want cloud media generation.")
    print("  2. Pull the default core model (one time, needs network):")
    print("       ollama pull gemma4:12b")
    print("     Optional coder: ollama pull qwen2.5-coder:1.5b")
    print("  3. Start the agent:   start_ultron_agent.bat")
    print("  4. Serve the HUD:     start_hud.bat")
    print("  5. Start Creative:    start_ultron_media.bat")
    print("     then open          http://127.0.0.1:8000/ultron.html")
    print("")
    print(f"  Output folder: {out_dir}")
    print("")


if __name__ == "__main__":
    main()
