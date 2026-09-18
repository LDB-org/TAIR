# Post-fix bound-action pilot

Eight attempts were recorded before the harness stopped on a semantic rejection:
classification selected NONE on repeat 1, target value 6. Seven tasks passed. The
engine remained healthy with restart_count=0; this was not another engine failure.
Raw rows, response and prompts are retained. Only two complete matched triples
exist, so no headline speed result is derived from this pilot.

The prompt asks to select one edit but repeats the full read/edit/reply task. That
may contribute to rejection; causality is not established by this single event.
The follow-up C run clarifies that the runner handles source reading, validation
and DONE, leaving only edit selection to the model. It also fixes the harness to
stop on transport/runtime failures, not an otherwise completed semantic rejection.
B and C are not pooled. The native Pi task prompt remains unchanged.
