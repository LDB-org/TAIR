# Expanded codebook diagnostic A

All 372 edits across 11 families and three arms passed behavioral checks. Each arm completed 124 tasks. The expanded codebook reused 60 actions; previous codebook reused 18. Raw records and source snapshot are retained.

This diagnostic exposed two incomplete optimization paths: adding an alias changed its selector name, losing reuse on the next alias; the catch-operation candidate lacked an explanation of its tuple semantics, causing two correct repeat candidates to be classified NONE and generated again. Both observations informed the separate final run B. This run is not the final implementation measurement. No failed rows were removed.

The scripts execute independent Python workers per task to isolate old/new modules. Current working tree tests are not claimed for this earlier source snapshot. The fixture family/task definitions are in manifest.json; behavior checks and generated edits are preserved with the rows. See the final run report for the full methodology and boundaries.
