# pijit WSL smoke

Two live complete Pi loops read a local Python file, edit it through compact_edit, execute it and reply through engine-selected reply_user. Cold changes 4 to 6; warm changes 6 to 8. Both preserve the explicit override 3.

The warm request retrieved a candidate but scored about 0.731, below the configured 0.95 gate, so it generated again. There was no live cache hit. The mocked hit-path unit test is not live-model evidence. These runs do not establish acceleration or general correctness.

The client was being finalized during this smoke: later changes shorten tool-result text, clean up cancellation, check post-verifier source changes, and label the TUI header. The logs preserve the exact messages of these runs; no exact final-source replay claim is made.
