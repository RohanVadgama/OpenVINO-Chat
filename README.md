# OpenVINO Chat

Double-click **Start Chat.cmd**. Choose a model, click **Load model**, then chat.

- The first model load may take a minute for GPU compilation. Later loads can use the on-disk compilation cache.
- **GPU** uses your Intel Arc graphics. CPU is also available.
- **Thinking** is off by default. It is passed through the model's chat template; models without that capability may ignore it.
- LaTeX (`\(inline\)`, `\[display\]`, `$inline$`, `$$display$$`), Markdown and code blocks render locally, with no CDN or network required after setup.
- Chats and preferences are saved in this browser's local storage. Delete individual chats with the × button.
- **Unload model** releases model memory. Closing the browser tab does not unload the model; use Unload before closing if you want the RAM back.
- Settings lets you add other downloaded OpenVINO model folders. Folders need config.json plus OpenVINO XML/BIN files. Image attachments work with vision models; architecture support depends on the installed OpenVINO Model Server. It does not convert GGUF files or download new models.
- Long conversations are capped by text length to limit memory use. Start a fresh chat when prompted. This is not an exact tokenizer-based context limit.
- Stop cancels the browser stream; the backend is disconnected on its next output. A long prefill may take longer to stop.

## Existing models

The app discovers AI Playground's OpenVINO model directory and the Qwen3.5 benchmark model in this task's `work/qwen35-openvino` directory. Models are referenced in place, not copied. If you move this app, add the Qwen folder again in Settings.

The app uses AI Playground's installed `resources/OpenVINO/ovms/ovms.exe` and Python runtime. Keep those installed. App data and compilation caches are under `data/`; model-server diagnostics are in `data/backend.log`.

## Measurements

Completed responses show server-reported output tokens, time to first streamed text, and estimated generation tokens/sec from first to last streamed text. Output token count may include thinking. Stream buffering can affect the estimate. Model loading is excluded.

## Local access

The interface listens only on `127.0.0.1:48200`; the model server uses another loopback-only port. A per-process request token and host/origin validation protect mutation endpoints from ordinary cross-site browser requests. No accounts or cloud inference are used. Browser extensions and other programs on your machine remain outside this boundary.

## Rendering libraries

Bundled locally: KaTeX 0.16.22, Marked 15.0.12 and DOMPurify 3.2.6. Licenses are in `static/vendor/`. Model-generated HTML is sanitized; remote images and embedded frames are blocked.

## Benchmark context

On this Core Ultra 9 185H laptop:

| Model / backend | Generation speed |
| --- | ---: |
| Qwen3-4B-Thinking-2507 Q4_K_M / Vulkan | 14.46 ± 0.09 tok/s |
| Qwen3.5-4B INT4 / OpenVINO GPU | 23.3–23.8 tok/s |
| Phi-3.5 Mini INT4 / OpenVINO GPU | 27.7–28.3 tok/s |

Qwen3 used a synthetic 128-token llama-bench test. Qwen3.5 and Phi used a short summary prompt and 128 output tokens; these are different models and test protocols, not an isolated backend comparison.

## Generation settings and saving
Settings includes a 1–32,768 output-token limit, temperature (0–2), Top P (0.01–1), and repetition penalty (1–2). Changes apply to the next response. Larger outputs remain subject to model context and RAM limits. Save conversation exports the current chat as Markdown; automatic browser-local history continues separately.


## Manual compaction
Compact context becomes available with six unsummarized messages. It summarizes older messages with the loaded model and keeps the latest four messages verbatim. Full visible history and Markdown exports are preserved. Restore full context removes the summary from future requests. Summaries are lossy; verify important equations and numbers. Interrupted or truncated summaries are not applied. Earlier images remain in model context when text is compacted.


## Images

Choose a vision model such as Qwen3.5 4B. Click **+ Image** or paste an image into the message box. PNG/JPEG/WebP inputs up to 20 MB are resized to a maximum 1,600-pixel edge and stored as JPEG in `data/images/`. Up to eight images per conversation are supported. Resizing can reduce small-text detail. Text-only models cannot process images.

Saved chats reference local image files. Keep `data/images/` for attachments to remain available. Deleting a chat does not delete its image files. Markdown exports embed attached images as data URLs; support for these varies by Markdown viewer.

## Uploading to GitHub

Use the source-only ZIP supplied alongside this folder, or use Git with the included `.gitignore`. GitHub browser uploads do not automatically filter local files using `.gitignore`: do not drag the entire runtime folder into the browser. Exclude `data/` (private images, logs and local model paths), `__pycache__/`, and all model weights. Include `static/vendor/` and its licenses. No repository has been created or pushed automatically.
