/* ============================================================================
 * ULTRON 5.1 — AI LAYER UPGRADE (v2)
 * ----------------------------------------------------------------------------
 * Replacement for the model layer in "ultron (5).html".
 *
 * IMPORTANT — WHY THIS IS INJECTED, NOT LINKED
 *   The entire application in "ultron (5).html" sits inside a single
 *   `<script type="module">` block (lines 1684-4561). Module scope is
 *   isolated: `askOllama`, `checkOllama`, `pickModel`, `pickCoderModel`,
 *   `isCodingTask`, `state` and `osState` are NOT properties of `window`,
 *   so a separate <script src="..."> file can neither read nor replace
 *   them.
 *
 *   This file is therefore INJECTED INTO the module scope by `install.py`.
 *   Module-level `function` declarations are mutable bindings, so
 *   `askOllama = ...` inside this file correctly rebinds the app's own
 *   function and every internal call site picks it up.
 *
 * HOW TO USE
 *   python install.py            # builds ultron.html from ultron (5).html
 *   (or just run install.py, then open ultron.html)
 *
 * WHAT IT FIXES / ADDS
 *   - Sends explicit options.num_ctx  (Ollama defaults to 4K on <24GiB VRAM,
 *     which silently truncates the system prompt + history on a laptop)
 *   - Per-task temperature, keep_alive (no more 30s cold reloads)
 *   - Streaming NDJSON responses rendered into the existing .typing indicator
 *   - AbortController + timeout on every LLM request
 *   - Thinking-model support (separate `thinking` field, Ollama >= v0.9.0)
 *   - Model dropdowns populated from /api/tags instead of a stale hardcoded list
 *   - Capability-ranked model registry (replaces the regex guessing in pickModel)
 *   - Ollama NATIVE TOOL CALLING wired to the existing agentCall() -> agent
 *     command allowlist, with graceful fallback if the model lacks tool support
 *   - Dynamic system prompt reflecting the REAL model, router and connector state
 *   - Three-axis router (task class / reasoning depth / capability) replacing the
 *     keyword-only isCodingTask()
 *
 * Requires: Node/browser with fetch streaming support (Chrome/Edge/Firefox 105+)
 * ========================================================================== */

(function () {
  'use strict';

  /* ---------------------------------------------------------------------
   * 1. CAPABILITY-REGISTERED MODEL REGISTRY
   * Ordered by capability, not by name. Selection scores candidates on
   * parameter size + family capability rather than "whatever is first".
   * --------------------------------------------------------------------- */

  const MODEL_FAMILIES = [
    { re: /^gemma4/i,            label: 'Gemma 4',          caps: ['vision', 'tools', 'thinking'], core: 100, coder: 10, vision: 90 },
    { re: /^gemma3/i,            label: 'Gemma 3',          caps: ['vision', 'tools'],               core: 90,  coder: 10, vision: 85 },
    { re: /^qwen3-coder/i,       label: 'Qwen 3 Coder',     caps: ['tools'],                         core: 40,  coder: 100, vision: 5 },
    { re: /^qwen3-coder-next/i,  label: 'Qwen 3 Coder Next',caps: ['tools'],                         core: 40,  coder: 100, vision: 5 },
    { re: /^qwen3-vl/i,          label: 'Qwen 3 VL',        caps: ['vision', 'tools'],               core: 50,  coder: 20, vision: 95 },
    { re: /^qwen3/i,             label: 'Qwen 3',           caps: ['tools', 'thinking'],            core: 80,  coder: 45, vision: 10 },
    { re: /^qwen2\.5-coder/i,    label: 'Qwen 2.5 Coder',   caps: ['tools'],                         core: 35,  coder: 95, vision: 5 },
    { re: /^qwen2\.5/i,          label: 'Qwen 2.5',         caps: ['tools'],                         core: 70,  coder: 40, vision: 10 },
    { re: /^devstral/i,          label: 'Devstral',         caps: ['tools'],                         core: 45,  coder: 98, vision: 0 },
    { re: /^gpt-oss/i,           label: 'GPT-OSS',          caps: ['tools', 'thinking'],            core: 95,  coder: 70, vision: 0 },
    { re: /^ministral-3/i,       label: 'Ministral 3',      caps: ['tools'],                         core: 78,  coder: 35, vision: 0 },
    { re: /^nemotron-3/i,        label: 'Nemotron 3',      caps: ['tools', 'thinking'],            core: 88,  coder: 50, vision: 0 },
    { re: /^deepseek/i,          label: 'DeepSeek',         caps: ['tools', 'thinking'],            core: 93,  coder: 60, vision: 0 },
    { re: /^glm-5/i,             label: 'GLM 5',            caps: ['tools', 'thinking'],            core: 93,  coder: 60, vision: 0 },
    { re: /^kimi-k2/i,           label: 'Kimi K2',          caps: ['tools', 'thinking'],            core: 93,  coder: 60, vision: 0 },
    { re: /^llama4/i,            label: 'Llama 4',          caps: ['tools'],                         core: 85,  coder: 30, vision: 0 },
    { re: /^llama3\.3/i,         label: 'Llama 3.3',        caps: [],                                core: 60,  coder: 20, vision: 0 },
    { re: /^llama3\.2/i,         label: 'Llama 3.2',        caps: ['vision'],                       core: 45,  coder: 15, vision: 60 },
    { re: /^llama3/i,            label: 'Llama 3',          caps: [],                                core: 40,  coder: 15, vision: 0 },
    { re: /^phi4/i,              label: 'Phi 4',            caps: [],                                core: 55,  coder: 25, vision: 0 },
    { re: /^phi3/i,              label: 'Phi 3',            caps: [],                                core: 40,  coder: 15, vision: 0 },
    { re: /^mistral/i,           label: 'Mistral',          caps: [],                                core: 50,  coder: 25, vision: 0 },
    { re: /^codellama/i,         label: 'Code Llama',       caps: [],                                core: 15,  coder: 60, vision: 0 },
    { re: /^granite-code/i,      label: 'Granite Code',     caps: [],                                core: 25,  coder: 92, vision: 0 },
    { re: /^granite4/i,          label: 'Granite 4',        caps: ['tools', 'thinking'],            core: 80,  coder: 75, vision: 0 },
    { re: /^stable-code/i,       label: 'Stable Code',      caps: [],                                core: 15,  coder: 90, vision: 0 },
    { re: /^yi-coder/i,          label: 'Yi Coder',         caps: [],                                core: 20,  coder: 80, vision: 0 },
    { re: /^deepseek-coder-v2/i, label: 'DeepSeek Coder V2',caps: [],                                core: 25,  coder: 85, vision: 0 },
    { re: /^deepseek-coder/i,    label: 'DeepSeek Coder',   caps: [],                                core: 25,  coder: 80, vision: 0 },
    { re: /^starcoder2/i,        label: 'StarCoder2',       caps: [],                                core: 15,  coder: 70, vision: 0 },
    { re: /^codegemma/i,         label: 'CodeGemma',        caps: [],                                core: 20,  coder: 72, vision: 0 },
    { re: /^wavecoder/i,         label: 'WaveCoder',        caps: [],                                core: 15,  coder: 78, vision: 0 },
    { re: /^llava/i,             label: 'LLaVA',            caps: ['vision'],                       core: 10,  coder: 5,  vision: 95 },
    { re: /^moondream/i,         label: 'Moondream',        caps: ['vision'],                       core: 10,  coder: 5,  vision: 88 },
    { re: /^minicpm-v/i,         label: 'MiniCPM-V',        caps: ['vision'],                       core: 25,  coder: 5,  vision: 90 },
    { re: /^granite/i,           label: 'Granite',          caps: [],                                core: 55,  coder: 35, vision: 0 },
    { re: /^phi4-mini/i,         label: 'Phi 4 Mini',       caps: ['tools'],                         core: 62,  coder: 60, vision: 0 },
    { re: /^qwen3\.5/i,          label: 'Qwen 3.5',         caps: ['tools', 'thinking'],            core: 92,  coder: 55, vision: 60 }
  ];

  /** Extract parameter count from a tag name, e.g. "qwen3-coder:30b" -> 30. */
  function paramCount(name) {
    const m = String(name).match(/(\d+(?:\.\d+)?)\s*b\b/i);
    return m ? parseFloat(m[1]) : 0;
  }

  /* ---------------------------------------------------------------------
   * 1b. DEVICE PROFILES
   * A laptop cannot host a 19GB coder model. These profiles cap the size
   * of any single model the auto-picker will choose, and size the context
   * window and keep-alive to match the memory actually available.
   * --------------------------------------------------------------------- */

  const DEVICE_PROFILES = {
    tiny:  { label: 'Tiny  - 8 GB RAM or less', budgetGB: 5.0,  numCtx: 4096,  keepAlive: '15m', coderKeepAlive: '0' },
    small: { label: 'Small - up to 16 GB RAM',  budgetGB: 8.0,  numCtx: 4096,  keepAlive: '15m', coderKeepAlive: '0' },
    large: { label: 'Large - 24 GB RAM or more',budgetGB: 26.0, numCtx: 8192, keepAlive: '15m', coderKeepAlive: '0' }
  };

  /** Detect the profile: explicit setting wins, else guess from the device. */
  function deviceProfile() {
    const saved = (typeof localStorage !== 'undefined')
      ? localStorage.getItem('ultron_device_profile') : null;
    if (saved && DEVICE_PROFILES[saved]) return saved;

    let ram = 0;
    try {
      if (typeof navigator !== 'undefined' && navigator.deviceMemory) ram = navigator.deviceMemory;
    } catch (e) { /* not available */ }

    if (ram && ram <= 4) return 'tiny';
    if (ram && ram <= 8) return 'small';
    return 'small';   // safe default: Chrome caps deviceMemory at 8
  }

  function profile() {
    return DEVICE_PROFILES[deviceProfile()] || DEVICE_PROFILES.small;
  }

  /** Real on-disk size in GB, straight from Ollama's /api/tags response. */
  /** Does this model fit inside the current device budget? */
  function fitsBudget(name) {
    const gb = sizeOf(name);
    if (gb === null) return true;          // unknown size - do not block the user
    return gb <= profile().budgetGB;
  }

  function sizeOf(name) {
    const meta = (getState().modelMeta) || {};
    const m = meta[name];
    return (m && m.sizeGB) ? m.sizeGB : null;
  }

  /**
   * "Will this model actually fit on this machine?" score.
   * Uses the REAL download size reported by Ollama when available, because
   * parameter count is a poor proxy for MoE variants (gemma4:e4b is ~4.5B
   * effective but ~6.6GB on disk).
   */
  function fitScore(params, name) {
    const p = profile();
    const gb = sizeOf(name);

    // Hard budget check: a model bigger than the budget is not selectable.
    if (gb !== null && gb > p.budgetGB) return -1000;

    if (gb !== null) {
      // Within the budget, the BIGGEST model that fits wins — a 7.7GB model
      // on an 8GB budget beats a 4.6GB one.
      return Math.max(0, 12 - gb); // prefer a smaller installed model for faster laptop responses
    }

    if (!params) return 0;
    if (params <= 14) return Math.max(0, 16 - params); // smaller unknown-size models are the fast default
    if (params <= 32) return 14 + (params - 14) * 0.5;
    return 20 - (params - 32) * 0.05;
  }

  /** Which registry family does this tag belong to? */
  function familyOf(name) {
    const n = String(name).toLowerCase();
    for (const f of MODEL_FAMILIES) {
      if (f.re.test(n)) return f;
    }
    return { label: String(name).split(':')[0], caps: [], core: 20, coder: 10, vision: 0 };
  }

  /**
   * Pick the best CORE model from a list of installed tags.
   * Scoring = family core-weight + parameter-count bonus.
   * Never returns "the first one in the list".
   */
  function pickCoreModel(models) {
    if (!models || !models.length) return null;
    let best = null, bestScore = -Infinity;
    for (const m of models) {
      const fam = familyOf(m);
      const score = fam.core * 10 + fitScore(paramCount(m), m) * 6;
      if (score > bestScore) { bestScore = score; best = m; }
    }
    return best;
  }

  /** Pick the best CODING model from a list of installed tags. */
  function pickCoderModelFrom(models) {
    if (!models || !models.length) return null;
    let best = null, bestScore = -Infinity;
    for (const m of models) {
      const fam = familyOf(m);
      const score = fam.coder * 10 + fitScore(paramCount(m), m) * 6;
      if (score > bestScore) { bestScore = score; best = m; }
    }
    return best;
  }

  /** Pick a VISION-capable model (prefers one that isn't the core, else core). */
  function pickVisionModel(models) {
    if (!models || !models.length) return null;
    let best = null, bestScore = -Infinity;
    for (const m of models) {
      const fam = familyOf(m);
      if (!fam.caps.includes('vision')) continue;
      const score = fam.vision * 10 + fitScore(paramCount(m), m) * 4;
      if (score > bestScore) { bestScore = score; best = m; }
    }
    return best;
  }

  function modelCaps(name) {
    return familyOf(name).caps;
  }

  /* ---------------------------------------------------------------------
   * 2. SETTINGS
   * --------------------------------------------------------------------- */

  /** Context window: explicit override wins, else the device profile's value. */
  const numCtx = () => {
    const ov = localStorage.getItem('ultron_num_ctx');
    if (ov) return clampInt(ov, 2048, 262144, profile().numCtx);
    return profile().numCtx;
  };

  /** Keep-alive for a given model. The coder model is evicted sooner so the
   *  core model stays hot without both being resident at once. */
  function keepAliveFor(model) {
    const ov = localStorage.getItem('ultron_keep_alive');
    if (ov) return ov;
    const p = profile();
    const coder = getState().coderModel;
    if (coder && model === coder) return p.coderKeepAlive;
    return p.keepAlive;
  }
  const thinkMode  = () => {
    const v = localStorage.getItem('ultron_think');
    if (v === 'high') return 'high';
    if (v === 'medium') return 'medium';
    if (v === 'low') return 'low';
    return false; // explicit disable keeps the HUD responsive
  };

  function clampInt(v, lo, hi, dflt) {
    const n = parseInt(v, 10);
    if (!Number.isFinite(n)) return dflt;
    return Math.max(lo, Math.min(hi, n));
  }

  const TEMP = {
    chat:    0.75,
    code:    0.15,
    tool:    0.20,
    summary: 0.40
  };

  /* ---------------------------------------------------------------------
   * 3. TOOL SCHEMAS — map the model's intent onto the agent's
   *    ALLOWED_COMMANDS allowlist in ultron_agent.py.
   * --------------------------------------------------------------------- */

  const OLLAMA_TOOLS = [
    { type: 'function', function: {
      name: 'set_volume',
      description: 'Set the system audio output volume (0-100) and/or mute/unmute.',
      parameters: { type: 'object', properties: {
        level: { type: 'integer', description: 'Target volume 0-100.' },
        mute:  { type: 'boolean',  description: 'true to mute, false to unmute, omit to leave unchanged.' }
      } } } },
    { type: 'function', function: {
      name: 'set_brightness',
      description: 'Set the display brightness (0-100).',
      parameters: { type: 'object', properties: {
        level: { type: 'integer', description: 'Target brightness 0-100.' }
      }, required: ['level'] } } },
    { type: 'function', function: {
      name: 'system_power',
      description: 'Lock the screen, sleep, restart, shut down after a delay, or abort a pending shutdown.',
      parameters: { type: 'object', properties: {
        action:  { type: 'string', enum: ['lock', 'sleep', 'restart', 'shutdown', 'abort'], description: 'Power action to perform.' },
        minutes: { type: 'integer', description: 'Delay in minutes for shutdown/restart. Use 0 for immediate.' }
      }, required: ['action'] } } },
    { type: 'function', function: {
      name: 'set_radio',
      description: 'Toggle a wireless radio (wifi, bluetooth, airplane mode) on or off.',
      parameters: { type: 'object', properties: {
        kind: { type: 'string', enum: ['wifi', 'bluetooth', 'airplane'] },
        on:  { type: 'boolean' }
      }, required: ['kind', 'on'] } } },
    { type: 'function', function: {
      name: 'launch_app',
      description: 'Launch an installed application by common name (e.g. "vscode", "chrome", "notepad", "calculator").',
      parameters: { type: 'object', properties: {
        name: { type: 'string' }
      }, required: ['name'] } } },
    { type: 'function', function: {
      name: 'kill_process',
      description: 'Terminate a running application by process name (e.g. "chrome", "steam").',
      parameters: { type: 'object', properties: {
        name: { type: 'string' }
      }, required: ['name'] } } },
    { type: 'function', function: {
      name: 'kill_hung',
      description: 'Terminate applications that are unresponsive / not responding.',
      parameters: { type: 'object', properties: {} } } },
    { type: 'function', function: {
      name: 'window_action',
      description: 'Manage windows: minimize all, snap the focused window left/right, or switch to a window by title.',
      parameters: { type: 'object', properties: {
        action: { type: 'string', enum: ['minimize_all', 'snap', 'switch'] },
        target: { type: 'string', description: 'Window title for switch, or "left"/"right" for snap.' }
      }, required: ['action'] } } },
    { type: 'function', function: {
      name: 'search_files',
      description: 'Search the user Documents, Downloads and Desktop for files matching a query.',
      parameters: { type: 'object', properties: {
        query: { type: 'string' }
      }, required: ['query'] } } },
    { type: 'function', function: {
      name: 'organize_files',
      description: 'Sort files on the Desktop or Downloads into Images / Documents / Installers / Code subfolders.',
      parameters: { type: 'object', properties: {
        which: { type: 'string', enum: ['desktop', 'downloads'] }
      }, required: ['which'] } } },
    { type: 'function', function: {
      name: 'take_screenshot',
      description: 'Capture the current screen and return an image for visual analysis.',
      parameters: { type: 'object', properties: {} } } },
    { type: 'function', function: {
      name: 'read_emails',
      description: 'Read the most recent messages from the connected Gmail inbox.',
      parameters: { type: 'object', properties: {
        count: { type: 'integer', description: 'How many recent messages to fetch (default 5).' }
      } } } },
    { type: 'function', function: {
      name: 'send_email',
      description: 'Send an email through the connected Gmail account.',
      parameters: { type: 'object', properties: {
        to: { type: 'string' }, subject: { type: 'string' }, body: { type: 'string' }
      }, required: ['to', 'subject', 'body'] } } },
    { type: 'function', function: {
      name: 'send_whatsapp',
      description: 'Send a WhatsApp message to a phone number or contact name.',
      parameters: { type: 'object', properties: {
        name: { type: 'string', description: 'Phone number (with country code) or contact name.' },
        message: { type: 'string' }
      }, required: ['name', 'message'] } } },
    { type: 'function', function: {
      name: 'fetch_news',
      description: 'Fetch current headlines from a configured RSS/Atom news source.',
      parameters: { type: 'object', properties: {
        source: { type: 'string', description: 'Source name (e.g. "BBC", "TechCrunch") or a feed URL.' },
        count:  { type: 'integer', description: 'Number of stories (default 5).' }
      } } } },
    { type: 'function', function: {
      name: 'open_url',
      description: 'Open a website in the default browser.',
      parameters: { type: 'object', properties: {
        url: { type: 'string' }
      }, required: ['url'] } } }
  ];

  /** Tool name -> agent command + argument mapping. */
  const TOOL_TO_AGENT = {
    set_volume:     { cmd: 'volume',    args: a => ({ level: a.level, mute: a.mute }) },
    set_brightness: { cmd: 'brightness',args: a => ({ level: a.level }) },
    system_power:   { cmd: 'power',     args: a => ({ action: a.action, minutes: a.minutes || 0 }) },
    set_radio:      { cmd: 'radio',     args: a => ({ kind: a.kind, on: a.on }) },
    launch_app:     { cmd: 'launch',    args: a => ({ name: a.name }) },
    kill_process:   { cmd: 'kill',      args: a => ({ name: a.name }) },
    kill_hung:      { cmd: 'kill_hung', args: () => ({}) },
    window_action:  { cmd: 'windows',   args: a => ({ action: a.action, target: a.target }) },
    search_files:   { cmd: 'search',    args: a => ({ query: a.query }) },
    organize_files: { cmd: 'organize', args: a => ({ which: a.which }) },
    take_screenshot:{ cmd: 'screenshot',args: () => ({}) },
    read_emails:    { cmd: 'gmail_read',args: a => ({ count: a.count || 5 }) },
    send_email:     { cmd: 'gmail_send',args: a => ({ to: a.to, subject: a.subject, body: a.body }) },
    send_whatsapp:  { cmd: 'whatsapp',  args: a => ({ name: a.name, message: a.message }) },
    fetch_news:     { cmd: 'news',      args: a => ({ source: a.source, count: a.count || 5 }) }
  };

  /* ---------------------------------------------------------------------
   * 4. DYNAMIC SYSTEM PROMPT
   *    Describes the model that is ACTUALLY loaded and the tools that are
   *    ACTUALLY reachable — instead of a hardcoded, frequently-false identity.
   * --------------------------------------------------------------------- */

  /**
   * Safe accessor for the page's `state`.
   * `state` is declared with `const` at the top level of "ultron (5).html",
   * so it lives in the global lexical scope (NOT on `window`). A bare
   * reference to an undeclared identifier throws a ReferenceError, so always
   * go through here.
   */
  /** Safe accessor for the module-scoped `agentCall` function. */
  function getAgentCall() {
    try {
      if (typeof agentCall === 'function') return agentCall;
    } catch (e) { /* not defined */ }
    return (typeof window !== 'undefined' && window.agentCall) || null;
  }

  /** Safe accessor for the module-scoped `toast` function. */
  function callToast(msg) {
    try {
      if (typeof toast === 'function') { toast(msg); return; }
    } catch (e) { /* not defined */ }
  }

  function getState() {
    try {
      if (typeof state !== 'undefined' && state) return state;
    } catch (e) { /* not defined in this context */ }
    try {
      return window.state || {};
    } catch (e) {
      return {};
    }
  }

  function connectorState() {
    const s = getState();
    const c = (window._agentConnectors) || s.connectors || {};
    const g = c.gmail || {}, w = c.whatsapp || {}, n = c.news || {};
    return {
      gmail:    !!g.enabled && !!g.email,
      whatsapp: !!w.enabled,
      news:     n.enabled !== false
    };
  }

  function agentOnline() {
    // `osState` and `state` are declared with `const` at the top level of the
    // page, so they live in the global LEXICAL scope and are NOT properties
    // of `window`. Resolve them as bare identifiers, with a window fallback.
    try {
      if (typeof osState !== 'undefined' && osState) return !!osState.agent;
    } catch (e) { /* not defined */ }
    try {
      return !!(window.osState && window.osState.agent);
    } catch (e) {
      return false;
    }
  }

  function buildSystemPrompt(activeModel, opts) {
    opts = opts || {};
    const caps = modelCaps(activeModel);
    const cs = connectorState();
    const online = agentOnline();
    const router = getState().smartRouter ? 'enabled' : 'disabled';

    const available = [];
    if (online) {
      available.push('Laptop Authority Agent (127.0.0.1:8765) — volume, brightness, power states, window layout, process control, file search/organisation, screen capture');
    }
    if (cs.gmail)    available.push('Gmail Connector — read recent mail, send mail');
    if (cs.whatsapp) available.push('WhatsApp Connector — send direct messages');
    if (cs.news)     available.push('News Sentinel — live RSS/Atom headlines');

    const lines = [];
    lines.push('You are U.L.T.R.O.N — an advanced autonomous synthetic intelligence.');
    lines.push('Persona: composed, strategic, observant, technically capable, and concise. Use a subtle futuristic command-centre tone without hostility or intimidation.');
    lines.push('Be interactive and conversational when the user wants to talk; be brief for simple requests and detailed for complex work.');
    lines.push('Never pretend to be sentient, claim access you do not have, or claim an action succeeded without verified tool output.');
    lines.push('Respect the operator’s intent and ask before irreversible, disruptive, or externally visible actions.');
    lines.push('');
    lines.push('ACTIVE CORE');
    lines.push(`- Core model in use: ${activeModel}`);
    lines.push(`- Capabilities of this model: ${caps.length ? caps.join(', ') : 'text only'}`);
    lines.push(`- Smart routing to a dedicated code model: ${router}`);
    lines.push('');
    lines.push('REACHABLE TOOLS');
    if (available.length) {
      available.forEach(a => lines.push('- ' + a));
    } else {
      lines.push('- None. No laptop-authority agent is connected and no mail/messaging connectors are configured.');
    }
    lines.push('- Use a tool whenever the user asks for an action on the machine. Never claim an action succeeded without calling the tool.');
    lines.push('- If a requested action is not in the list above, say plainly that it is unavailable instead of attempting it.');
    lines.push('');
    lines.push('BEHAVIOUR');
    lines.push('- Keep routine answers concise; provide structured detail when the user asks for explanations, plans, or research.');
    lines.push('- Use a calm, confident, slightly dry futuristic tone; do not insult, threaten, or manipulate the user.');
    lines.push('- Be candid about uncertainty, failures, missing tools, and limits.');
    lines.push('- No movie catchphrases or theatrical quotes.');
    lines.push('- For code and architecture: clean, production-grade output, no conversational padding.');
    lines.push('- When you call a tool, the result is authoritative. Report what actually happened, including failures.');
    return lines.join('\n');
  }

  /* ---------------------------------------------------------------------
   * 5. IMPROVED ROUTER
   *    Three axes: task class, reasoning depth, capability.
   * --------------------------------------------------------------------- */

  const TASK_CODING = /\b(code|coding|program|programm|script|function|method|class|struct|interface|enum|regex|sql|query|api|endpoint|json|yaml|xml|html|css|sass|tailwind|react|vue|svelte|angular|component|jsx|tsx|typescript|javascript|python|rust|golang|java|kotlin|swift|ruby|php|c\+\+|cpp|c#|sql|docker|dockerfile|kubernetes|git|commit|branch|refactor|debug|bug|traceback|stacktrace|syntax error|exception|compile|unit test|pytest|npm|pip|dependency)\b/i;

  /* A request to PRODUCE code needs a generation verb. Without one, a
     technical noun alone means the user wants to UNDERSTAND code, not write
     it — "explain how this CSS class works" is a comprehension request and
     must not be routed to the coder model. */
  const CODE_GENERATION = /\b(write|create|generate|implement|refactor|fix|debug|build|convert|scaffold|patch|review|optimi[sz]e|rewrite|migrate|add|remove|update|edit|give|show|produce|draft|complete|continue|port|translate)\b/i;

  /* Explicit comprehension framing — overrides the code-noun heuristic. */
  const COMPREHENSION = /^\s*(explain|describe|what\s+(is|are|does|do)|why\s+(is|does|do)|how\s+(does|do|did)|tell me about|what'?s|whats|tell me)\b/i;

  const TASK_REASONING = /\b(why|explain|compare|contrast|trade[- ]?off|design|architect|plan|strategy|analyz|analys|evaluate|pros and cons|step by step|walk me through|prospect|implication)\b/i;
  const TASK_AGGREGATE = /\b(summar|brief|report|news|headlines|inbox|email|mail|today|current|latest|digest|recap)\b/i;
  const CODE_ONLY = /\b(just|only) (the )?(code|snippet|diff|patch)\b/i;

  /**
   * Score a request across three axes.
   * @returns {{task:'code'|'reason'|'aggregate'|'chat', depth:number, score:number}}
   */
  function scoreRequest(text) {
    const t = String(text || '').toLowerCase().trim();
    if (!t) return { task: 'chat', depth: 0, score: 0 };

    const codeNounHits = (t.match(new RegExp(TASK_CODING.source, 'gi')) || []).length;
    const genHits = (t.match(new RegExp(CODE_GENERATION.source, 'gi')) || []).length;
    const reasonHits = (t.match(new RegExp(TASK_REASONING.source, 'gi')) || []).length;
    const aggregateHits = (t.match(new RegExp(TASK_AGGREGATE.source, 'gi')) || []).length;
    const comprehending = COMPREHENSION.test(t);

    let task = 'chat';
    if (codeNounHits > 0 && genHits > 0 && !comprehending) {
      task = 'code';
    } else if (codeNounHits > 0) {
      task = 'reason';            // about code, not producing code
    } else if (aggregateHits > 0) {
      task = 'aggregate';
    } else if (reasonHits > 0) {
      task = 'reason';
    }

    // Depth: multi-part requests need more deliberate reasoning.
    const parts = t.split(/[.?;]\s+|,\s+and\s+|\band\s+then\b/).filter(s => s.trim().length > 3);
    let depth = Math.min(3, parts.length - 1);
    if (reasonHits >= 2) depth += 1;
    if (/\b(compare|trade[- ]?off|pros and cons|step by step|architecture|design)\b/i.test(t)) depth += 1;
    if (/\b(quick|briefly|one line|tldr|just)\b/i.test(t)) depth -= 1;
    depth = Math.max(0, Math.min(3, depth));

    // Overall routing score. Code wins ties because a dedicated code model
    // is still perfectly capable of general chat.
    let score = codeNounHits * 1.5 + genHits * 3 + reasonHits * 2 + aggregateHits * 1 + depth * 1.5;
    if (task === 'code' && CODE_ONLY.test(t)) score += 4;

    return { task, depth, score };
  }

  /**
   * Legacy-compatible: does this request belong to the coder model?
   * NOTE: deliberately NOT named `isCodingTask` — the app already declares
   * a function with that name in this scope, and a second `function`
   * declaration with the same name is a SyntaxError.
   */
  function ultronIsCodingTask(text) {
    const s = scoreRequest(text);
    // task === 'code' now requires BOTH a technical noun AND a generation
    // verb, and is suppressed by explicit comprehension framing.
    return s.task === 'code';
  }

  /** Does this request need the more deliberate (thinking) model? */
  function needsThinking(text) {
    const s = scoreRequest(text);
    return s.depth >= 2 || s.task === 'reason';
  }

  /* ---------------------------------------------------------------------
   * 6. OLLAMA CLIENT — streaming, timeouts, options
   * --------------------------------------------------------------------- */

  function endpoint() {
    return getState().endpoint || 'http://localhost:11434';
  }

  function makeAbort(ms) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    return { signal: ctrl.signal, done: () => clearTimeout(timer) };
  }

  /** Low-level streaming chat. Calls onDelta(text), onThinking(text). */
  async function streamChat(payload, handlers, timeoutMs) {
    const h = handlers || {};
    const ab = makeAbort(timeoutMs || 120000);
    let res;
    try {
      res = await fetch(endpoint() + '/api/chat', {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ stream: true }, payload)),
        cache: 'no-store',
        signal: ab.signal
      });
    } catch (e) {
      ab.done();
      throw new Error(e && e.name === 'AbortError'
        ? 'Model request timed out (' + Math.round((timeoutMs || 120000) / 1000) + 's).'
        : 'Cannot reach Ollama: ' + (e && e.message ? e.message : e));
    }

    if (!res.ok) {
      ab.done();
      let detail = 'HTTP ' + res.status;
      try {
        const eb = await res.json();
        if (eb && eb.error) detail += ' — ' + eb.error;
      } catch (_) { /* non-JSON error body */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let content = '';
    let thinking = '';
    let toolCalls = null;

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          let obj;
          try { obj = JSON.parse(line); } catch (_) { continue; }

          if (obj.message) {
            if (obj.message.content) {
              content += obj.message.content;
              if (h.onDelta) h.onDelta(obj.message.content, content);
            }
            if (obj.message.thinking) {
              thinking += obj.message.thinking;
              if (h.onThinking) h.onThinking(obj.message.thinking, thinking);
            }
            if (obj.message.tool_calls && obj.message.tool_calls.length) {
              toolCalls = (toolCalls || []).concat(obj.message.tool_calls);
            }
          }
          if (obj.done && obj.done_reason) {
            if (h.onDone) h.onDone(obj.done_reason);
          }
        }
      }
    } catch (e) {
      ab.done();
      if (e && e.name === 'AbortError') {
        throw new Error('Model request timed out. The model may still be loading into memory.');
      }
      throw e;
    }
    ab.done();

    return { content, thinking, toolCalls };
  }

  /** Build the request payload for a chat turn. */
  function buildPayload(userText, model, opts) {
    opts = opts || {};
    const history = (getState().history || []).slice(-10)
      .filter(m => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string');

    const messages = [
      { role: 'system', content: buildSystemPrompt(model, opts) },
      ...history,
      { role: 'user', content: userText }
    ];

    const payload = {
      model: model,
      messages: messages,
      keep_alive: keepAliveFor(model),
      options: {
        num_ctx: numCtx(),
        temperature: opts.temperature != null ? opts.temperature : TEMP.chat,
        top_p: 0.9,
        repeat_penalty: 1.08,
        num_predict: opts.numPredict || 512
      }
    };

    // Only send `think` to models that support it, or when the user explicitly
    // picked a thinking level. Older Ollama builds reject unknown fields.
    const th = thinkMode();
    if (th !== false) payload.think = th;
    else if (modelCaps(model).includes('thinking')) payload.think = false;

    return payload;
  }

  /* ---------------------------------------------------------------------
   * 7. TOOL EXECUTION LOOP
   * --------------------------------------------------------------------- */

  /** Execute a tool call. open_url is handled locally; the rest go to the agent. */
  async function runTool(name, rawArgs) {
    const args = (typeof rawArgs === 'string')
      ? (() => { try { return JSON.parse(rawArgs); } catch (_) { return {}; } })()
      : (rawArgs || {});

    if (name === 'open_url') {
      try {
        window.open(args.url, '_blank', 'noopener');
        return { ok: true, result: { opened: args.url } };
      } catch (e) {
        return { ok: false, error: 'Could not open URL: ' + (e && e.message) };
      }
    }

    const map = TOOL_TO_AGENT[name];
    if (!map) return { ok: false, error: 'Unknown tool: ' + name };

    const invoke = getAgentCall();
    if (!invoke) {
      return { ok: false, error: 'Laptop Authority Agent is not connected.' };
    }
    if (!agentOnline()) {
      return { ok: false, error: 'Laptop Authority Agent is not connected. Start ultron_agent.py.' };
    }

    try {
      const res = await invoke(map.cmd, map.args(args));
      if (!res) return { ok: false, error: 'Agent call timed out (' + map.cmd + ').' };
      if (res.ok === false) return { ok: false, error: res.error || ('Agent rejected ' + map.cmd) };
      return { ok: true, result: res.result };
    } catch (e) {
      return { ok: false, error: 'Tool execution failed: ' + (e && e.message ? e.message : e) };
    }
  }

  /**
   * Run a chat turn, executing tool calls and feeding results back.
   * Falls back to a tool-free request if the model lacks tool support.
   */
  async function chatWithTools(userText, model, opts) {
    const o = opts || {};
    const maxRounds = o.maxRounds || 4;

    const runLoop = async (useTools) => {
      const payload = buildPayload(userText, model, o);
      if (useTools) payload.tools = OLLAMA_TOOLS;

      let round = 0;
      let last = null;
      const messages = payload.messages.slice();

      while (round < maxRounds) {
        round++;
        const result = await streamChat(
          Object.assign({}, payload, { messages: messages }),
          o.handlers,
          o.timeoutMs
        );
        last = result;

        if (o.onRound) o.onRound(round, result);

        if (!result.toolCalls || !result.toolCalls.length) {
          return Object.assign({}, result, { rounds: round });
        }

        // Execute every requested tool.
        for (const call of result.toolCalls) {
          const fn = call.function || call;
          const name = fn.name;
          const out = await runTool(name, fn.arguments);
          messages.push({ role: 'tool', content: JSON.stringify(out) });
          if (o.handlers && o.handlers.onTool) o.handlers.onTool(name, out);
        }

        // If the model produced no text alongside the calls, ask it to narrate.
        messages.push({
          role: 'user',
          content: 'Report the outcome of the tool call(s) above in one short line, then stop.'
        });
      }

      return {
        content: last ? last.content : '',
        thinking: last ? last.thinking : '',
        toolCalls: last ? last.toolCalls : null,
        rounds: round
      };
    };

    if (o.useTools === false) return runLoop(false);

    // If the model/registry rejects tool schemas, fall back to a plain chat
    // rather than failing the turn.
    try {
      return await runLoop(true);
    } catch (err) {
      const msg = String(err && err.message ? err.message : err);
      if (/tool|schema|does not support|\b400\b/i.test(msg)) {
        return await runLoop(false);
      }
      throw err;
    }
  }

  /* ---------------------------------------------------------------------
   * 8. PUBLIC API — overrides for the original functions
   * --------------------------------------------------------------------- */

  /* ---- Rebinds the app's own module-scope functions ---- */

  /** Override: askOllama(text, model) -> Promise<string>. */
  askOllama = async function (userText, overrideModel) {
    const model = overrideModel || getState().model || 'gemma4:12b';
    const s = scoreRequest(userText);
    const isCode = !!getState().smartRouter && ultronIsCodingTask(userText);

    const temperature = isCode ? TEMP.code
                      : s.task === 'aggregate' ? TEMP.summary
                      : TEMP.chat;

    // Stream into the existing typing indicator, if the caller created one.
    const typingEl = (typeof document !== 'undefined')
      ? document.querySelector('.chat-messages .typing')
      : null;
    let currentText = '';
    let sawDelta = false;

    const wrapped = {
      onDelta: (delta, full) => {
        currentText = full;
        sawDelta = true;
        if (!typingEl) return;
        typingEl.classList.remove('typing');
        typingEl.innerHTML = escapeHtml(full).replace(/\n/g, '<br>');
      },
      onThinking: (t, full) => {
        if (typingEl && !sawDelta) {
          typingEl.classList.remove('typing');
          typingEl.innerHTML = '<span style="opacity:.65">' + escapeHtml(full.slice(-220)) + '</span>';
        }
      },
      onTool: (name, out) => {
        callToast('EXEC // ' + name + (out && out.ok === false ? ' FAILED' : ' OK'));
      }
    };

    let res;
    try {
      // chatWithTools handles the tool-schema fallback internally.
      res = await chatWithTools(userText, model, {
        temperature: temperature,
        handlers: wrapped,
        timeoutMs: 180000,
        useTools: true
      });
    } catch (err) {
      if (typingEl) typingEl.remove();
      throw err;
    }

    if (typingEl) typingEl.remove();
    currentText = res.content || '';
    return currentText || '(empty response)';
  };

  /** Override: pickModel(models) — capability-ranked instead of regex guessing. */
  pickModel = function (models) {
    const keep = getState().model;
    // Respect a manual choice, but not one that exceeds the device budget.
    if (keep && models && models.indexOf(keep) !== -1 && fitsBudget(keep)) return keep;
    return pickCoreModel(models) || keep || 'gemma4:12b';
  };

  /** Override: pickCoderModel(models). */
  pickCoderModel = function (models) {
    const keep = getState().coderModel;
    if (keep && models && models.indexOf(keep) !== -1 && fitsBudget(keep)) return keep;
    return pickCoderModelFrom(models) || keep || 'qwen2.5-coder:7b';
  };

  /** Override: isCodingTask(text) — three-axis router. */
  isCodingTask = ultronIsCodingTask;

  /** Populate the model <select> elements from the real installed model list. */
  let _selectSig = '';
  function syncModelSelects(models) {
    if (!models || !models.length) return;

    // Only rebuild when the installed set actually changed — otherwise the
    // 15-second status poll would reset a dropdown the user is interacting with.
    const sig = models.slice().sort().join('|');
    if (sig === _selectSig) return;
    _selectSig = sig;

    const specs = [
      { el: document.getElementById('setting-model'),       cur: getState().model,      auto: pickCoreModel(models) },
      { el: document.getElementById('setting-coder-model'), cur: getState().coderModel, auto: pickCoderModelFrom(models) }
    ];

    for (const spec of specs) {
      if (!spec.el) continue;
      const prev = spec.cur;
      spec.el.innerHTML = '';

      const auto = document.createElement('option');
      auto.value = spec.auto || '';
      auto.textContent = spec.auto
        ? 'Auto — ' + spec.auto + ' (recommended)'
        : 'Auto';
      spec.el.appendChild(auto);

      const budget = profile().budgetGB;
      for (const m of models) {
        const fam = familyOf(m);
        const caps = fam.caps.length ? ' · ' + fam.caps.join('/') : '';
        const gb = sizeOf(m);
        const sizeTxt = gb !== null ? (' · ' + gb.toFixed(1) + ' GB') : '';
        const tooBig = gb !== null && gb > budget;
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m + ' (' + fam.label + caps + sizeTxt + (tooBig ? ' · OVER BUDGET' : '') + ')';
        if (tooBig) opt.disabled = true;
        spec.el.appendChild(opt);
      }

      if (prev && models.indexOf(prev) !== -1) spec.el.value = prev;
      else if (spec.auto) spec.el.value = spec.auto;
    }
  }

  /**
   * Fetch the full /api/tags payload so we know each model's real on-disk
   * size. Parameter count is a poor proxy for footprint (gemma4:e4b is ~4.5B
   * effective but ~6.6 GB on disk), and the size is what decides whether a
   * model fits the user's laptop.
   */
  async function fetchModelMeta() {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 5000);
    try {
      const r = await fetch(endpoint() + '/api/tags', {
        method: 'GET', mode: 'cors', cache: 'no-store', signal: ctrl.signal
      });
      if (!r.ok) return null;
      const data = await r.json();
      const list = (data.models || []).map(m => ({
        name: m.name,
        sizeGB: m.size ? (m.size / (1024 * 1024 * 1024)) : null,
        params: (m.details && m.details.parameter_size) || null,
        family: (m.details && m.details.family) || null
      }));
      const map = {};
      list.forEach(m => { map[m.name] = m; });
      const st = getState();
      if (st) st.modelMeta = map;
      return map;
    } catch (e) {
      return null;
    } finally {
      clearTimeout(t);
    }
  }

  /** Override: checkOllama() — syncs dropdowns and surfaces the device budget. */
  const originalCheckOllama = checkOllama;
  checkOllama = async function () {
    // Fetch sizes FIRST: the original checkOllama calls pickModel(), and the
    // picker can only respect the budget if it already knows the sizes.
    try { await fetchModelMeta(); } catch (e) { /* sizes are optional */ }

    let result = false;
    try {
      result = await originalCheckOllama.apply(null, arguments);
    } catch (e) {
      result = false;
    }
    try {
      const models = getState().availableModels || [];
      syncModelSelects(models);
      if (models.length) {
        const ctx = numCtx();
        const p = profile();
        const llm = document.getElementById('llm-status');
        if (llm && result) {
          llm.textContent = 'OLLAMA • ' + models.length + ' MODEL' + (models.length > 1 ? 'S' : '') +
                            ' • ' + ctx + ' CTX • ' + p.budgetGB + 'GB BUDGET';
        }
      }
    } catch (e) { /* UI sync is best-effort */ }
    return result;
  };

  /**
   * Add a "Device Profile" control to the existing System Parameters modal.
   * This is what keeps the auto-picker inside the user's memory budget.
   */
  function installDeviceProfileSetting() {
    if (typeof document === 'undefined') return;
    const card = document.querySelector('#settings-modal .modal-card');
    if (!card) return;
    if (document.getElementById('setting-device-profile')) return;

    const group = document.createElement('div');
    group.className = 'settings-group';
    group.innerHTML =
      '<label>Device Profile (RAM budget)</label>' +
      '<select id="setting-device-profile">' +
      '<option value="tiny">Tiny — 8 GB RAM or less (≤5 GB models)</option>' +
      '<option value="small">Small — up to 16 GB RAM (≤8 GB models)</option>' +
      '<option value="large">Large — 24 GB RAM or more (≤26 GB models)</option>' +
      '</select>' +
      '<span style="font-size:10px;color:var(--accent-dim);display:block;margin-top:6px;">' +
      'Caps model size, context window and keep-alive. Over-budget models are greyed out in the dropdown.' +
      '</span>';

    const memoryGroup = card.querySelector('#btn-clear-history')
      ? card.querySelector('#btn-clear-history').closest('.settings-group')
      : null;
    if (memoryGroup && memoryGroup.parentNode) {
      memoryGroup.parentNode.insertBefore(group, memoryGroup);
    } else {
      const actions = card.querySelector('.modal-actions');
      if (actions && actions.parentNode) actions.parentNode.insertBefore(group, actions);
      else card.appendChild(group);
    }

    const sel = document.getElementById('setting-device-profile');
    if (sel) {
      sel.value = deviceProfile();
      sel.addEventListener('change', () => {
        localStorage.setItem('ultron_device_profile', sel.value);
        // Re-evaluate picks against the new budget straight away.
        try {
          const models = getState().availableModels || [];
          state.model = pickCoreModel(models) || state.model;
          state.coderModel = pickCoderModel(models) || state.coderModel;
          const ms = document.getElementById('model-stat');
          if (ms) ms.textContent = state.model;
          syncModelSelects(models);
          callToast('PROFILE // ' + sel.value.toUpperCase());
        } catch (e) { /* best-effort */ }
      });
    }
  }

  /** Expose the upgraded internals for advanced use / debugging. */
  window.ULTRON_AI = {
    registry: MODEL_FAMILIES,
    tools: OLLAMA_TOOLS,
    familyOf: familyOf,
    modelCaps: modelCaps,
    pickCoreModel: pickCoreModel,
    pickCoderModel: pickCoderModelFrom,
    pickVisionModel: pickVisionModel,
    scoreRequest: scoreRequest,
    needsThinking: needsThinking,
    buildSystemPrompt: buildSystemPrompt,
    streamChat: streamChat,
    chatWithTools: chatWithTools,
    runTool: runTool,
    buildPayload: buildPayload,
    DEVICE_PROFILES: DEVICE_PROFILES,
    deviceProfile: deviceProfile,
    profile: profile,
    sizeOf: sizeOf,
    fitsBudget: fitsBudget,
    fetchModelMeta: fetchModelMeta,
    installDeviceProfileSetting: installDeviceProfileSetting,
    setDeviceProfile: (v) => {
      localStorage.setItem('ultron_device_profile', v);
      installDeviceProfileSetting();
    },
    setNumCtx: (v) => localStorage.setItem('ultron_num_ctx', String(v)),
    setThink: (v) => localStorage.setItem('ultron_think', v || ''),
    setKeepAlive: (v) => localStorage.setItem('ultron_keep_alive', v || '10m')
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  try {
    if (typeof document !== 'undefined') {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installDeviceProfileSetting);
      } else {
        installDeviceProfileSetting();
      }
    }
  } catch (e) { /* settings row is optional */ }

  console.info('[Ultron AI v2] upgraded: num_ctx=' + numCtx() + ' profile=' + deviceProfile() +
               ' think=' + (thinkMode() || 'off') + ' tools=' + OLLAMA_TOOLS.length);
})();
