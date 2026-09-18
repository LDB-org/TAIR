# Bound complete-action task experiment: interrupted by mixed-batch dtype failure

Three arms complete the same argparse default edit and independent AST/behavior
oracle: stock Pi read/edit/reply, a specialized one-request JSON generator, and
a specialized one-request whole-action classifier. Candidates use fixed values
2, 4, 6, 8, 10 plus NONE; expected target is not used to preselect the answer.
Specialized paths include cold tokenization and candidate binding. Their Python
interpreter/import startup is excluded, while Pi startup is included. The native
comparison changes orchestration as well as representation. It is not a general
coding benchmark.

Twelve tasks were attempted. Only the first triple completed successfully:
generate 3.787 s, native 21.568 s, classify 17.991 s. During the fourth task the
shared engine failed; remaining records include HTTP 500, disconnected requests
and incomplete Pi runs. These durations cannot support a speed comparison and
must not count fast error returns as performance gains. All original records
are retained. The runner now stops after a request/runtime failure in future runs.

The live traceback points to classify_v2 assigning ordinary sampler FP32 logits
into a BF16 cloned logits tensor during a mixed batch. The container automatically
restarted (restart_count=1), watchdog remained active, health returned 200, and a
real standard generation request returned RECOVERED. No configuration change or
manual restart was performed. The defective helper remains deployed; no further
classification requests were issued after diagnosis.

Local fix promotes the combined processed logits tensor to the ordinary sampler
output dtype before assignment, preserving FP32 precision. Regression tests
reproduce the prior failure for BF16 and FP16 and cover FP32; after the fix all
206 tests pass. Fix source snapshots are stored separately from the experiment
source snapshots. Deploying the fix requires a separately authorized maintenance
restart under repository instructions; this experiment does not claim live repair.

See incident.json, engine-events.jsonl, recovery-native-smoke.json and rows.jsonl.
