# Full Agent diagnostic before routing clarification

This run completed 18 real Pi 0.85.1 tasks over the 5090 backend with schema/preset/exact-replay/local-routing flags off. No nested compact edit was chosen in any task: the outer tool classifier used ordinary edit/write. All 18 final implementation behavior oracles passed, but one generation-arm summary task omitted the requested additional tests. No cache hits occurred.

The initial harness incorrectly demanded byte-identical tests even for summary_bug, whose prompt explicitly requests adding coverage. Raw rows and the original summary are retained unchanged. adjudication.json and adjudicated-summary.json correct that verdict using preserved original test-method ASTs plus at least one added test. The generation warm summary task did not add any test, so it remains an actual incomplete task. Adjudicated results: native 6/6, generation 5/6, c4 6/6.

The c4 total was 75.06 seconds versus native 66.76 seconds, with zero nested reuse. This diagnostic motivated a separate routing-prompt/tool-description revision: explicitly identify supported compact operations and batch related edits, while keeping unsupported edits on ordinary tools. It does not establish full-Agent acceleration. A separate final run preserves its own source snapshot and corrected task-integrity checker.
