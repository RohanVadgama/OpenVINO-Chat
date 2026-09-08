# OpenVINO Chat

Run **Start Chat.cmd**, choose a model and click **Load model**. Uses AI Playground's installed Python and OpenVINO Model Server. Models are referenced in place, not copied.

## One selected conversation datastore

Settings → Conversation storage selects an absolute local folder, including a OneDrive-synced folder. Switching folders saves the current view first, then reads only the new folder. An empty folder opens an empty history. **Reload folder** rereads files. **Disconnect folder** leaves files intact and clears the view.

- `chats/<stable-id-hash>.json`: one file per conversation, including its title, messages, and compaction summary.
- `chat-index.json`: preferences and navigation metadata, not a second copy of conversation messages. The viewer enumerates the actual JSON files under `chats/`.
- `openvino-chat-images/`: image attachments.

Conversation text is held in memory while open; it is not duplicated in browser localStorage. Browser preferences may be stored locally. Writes are debounced; wait for completion before closing. OneDrive performs cloud synchronization. Simultaneous edits from multiple devices are not merged; use one writer at a time. Missing or inaccessible storage produces an error rather than silently saving elsewhere. Existing legacy aggregate backup files are not used by the viewer.

## Image storage and retention

Images go directly into the selected datastore; there is no second app-local copy. OneDrive itself may cache files locally. Existing app-local images were copied and verified before the duplicates were removed.

PNG/JPEG/WebP images up to 20 MB can be attached or pasted. They are resized to a maximum 1,600-pixel edge and encoded as JPEG. A vision model is required. Maximum eight images per conversation context.

Settings provides a size limit (default **5 GB**, 0 disables) and optional age limit in days (default **0**, off). Oldest images are removed first when the limit is exceeded. Retention runs on uploads/saves or via **Apply retention now**. It removes image files, not conversation text. Removed attachments appear as placeholders. Deleting a conversation does not immediately delete its image files; retention manages these too.

## Chat and display controls

Temperature, Top P, repetition penalty, thinking mode, input-text budget, and output limit are configurable. Input and output controls support up to 65,536 tokens, subject to the actual model capacity and RAM. The context meter estimates text only; last-input tokens come from the server. Images add tokens.

Compact context summarizes older text and keeps recent messages plus images; full transcript remains saved. Restore full context reverses compaction. Summaries can lose details: verify important maths and code.

LaTeX, Markdown and code render offline. Conversation width, line spacing, equation spacing, and side-by-side equations are configurable. Themes: grey/black default, blue, AMOLED, green and light. The top bar matches the sidebar. Backup failures appear in red in the sidebar until a save succeeds.

Save conversation exports Markdown with embedded image data URLs (viewer support varies). Chats in the datastore use JSON.

## Runtime

The UI listens only on localhost:48200. Model loading starts a separate loopback-only server. Unload model releases its memory; closing the last tab stops the server after a short grace period. Start Chat is needed after a reboot. Runtime configuration/logs/caches are under `data/`. Keep AI Playground's OpenVINO runtime installed. Additional models can be registered by folder.

## GitHub

Track source, `.gitignore`, and `static/vendor/` including licenses. Do not upload `data/`, model weights, caches, or your datastore. GitHub browser uploads do not apply `.gitignore`; use the supplied clean source ZIP. Bundled libraries: KaTeX 0.16.22, Marked 15.0.12, DOMPurify 3.2.6.

## Window lifecycle and shortcuts
Closing the last chat tab now stops the chat server and its model process after a 15-second refresh grace period. Other open chat tabs keep it alive. Browser crashes or missing close notifications use a roughly three-minute heartbeat timeout. A suspended browser tab can also expire. Reopen using the shortcut if that happens. The launcher starts the server before opening localhost, so it works after a cold boot. Both shortcuts run Start Chat.ps1 in the project folder. If the project is moved, run Create shortcuts.ps1 from its new location to regenerate both links; Start Chat.cmd already resolves its own location.


Generated .lnk shortcuts are ignored because they contain absolute paths. Run Create shortcuts.ps1 after cloning to create local shortcuts with the included icon. Keep all personal folder settings in ignored data/; never force-add datastore files.
