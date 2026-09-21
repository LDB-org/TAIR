# Repeated-error recovery prompt: rejected experiment

2026-09-21. A proposed recovery suffix counted consecutive byte-identical error outputs, including after changed commands, and told the model to identify the failing prerequisite before retrying. It reset on success, malformed results, changed errors and new user turns. It did not block tools or alter commands. The change was tested and then removed because it did not demonstrate faster recovery.

Evidence came from `parallel-capabilities-ablation-20260921-a`: a JavaScript check first failed shell quoting, then a temporary test file repeatedly failed its relative import. Changing the shell working directory did not change module-relative import resolution. The existing identical-plan guard allows one retry and cannot prevent a changed command from reproducing the same error.

## Controlled recovery replay

`repeated-recovery-probe-20260921-a` is invalid for comparison: incomplete replacement of macOS `/private/var` and `/var` aliases left stale paths. Retained unchanged for audit; excluded from conclusions.

Corrected `repeated-recovery-probe-20260921-b` rebounded both aliases and regenerated the missing-module error with Node in the actual isolated replay directory. No stale original experiment paths remained. Each arm received the same history cut after three or four failed plans (respectively two or three repeated module errors), with the same existing correct implementation. Four total model requests used the existing Yuesheng GPU service. Only the latest-result suffix differed; native Pi 0.85.1 tools executed the single returned plan. No further Agent turns were run.

Both versions executed their returned tools successfully in both cuts, but neither ran the requested implementation checks. Original generated 81 tokens across the two requests; candidate generated 113. Original chose directory/file inspection; candidate chose find plus ls. Thus recovery completion was 0/2 for each under the predeclared check-output criterion. The generated commands themselves independently confirm inspection only, so the result does not depend on exact stdout formatting. Successful tool execution is not recovery completion. The replay cannot estimate total recovery latency across subsequent turns.

The candidate hint is removed from live `latest_plan_result`, whose function text matches the preceding frozen version exactly. Existing readable failure context and repeated-identical-plan guard remain. The failed candidate is preserved in each frozen probe's source snapshot. The probe now requires an explicit `--candidate-bridge` path so it can evaluate that saved candidate without accidentally comparing restored live code to itself.

This rules out a repetition-count reminder as a demonstrated solution on this example. It does not prove that all forms of recovery context are ineffective. Further work should test whether the model identifies the actual failed dependency and completes checks, rather than rewarding shorter output or successful inspection commands.

Validation: candidate had 554 passing tests; after removal, the original 553-test suite is rerun. Frozen experiment checksums are retained. No vLLM restart, deployment, codebook reset or push was performed.
