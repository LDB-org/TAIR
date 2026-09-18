# Authorized dtype-fix maintenance

Only one line was added to the original deployed helper: promote processed logits
to the ordinary sampler output dtype before mixed-batch assignment. Container
configuration/image/restart policy and max-num-seqs=4 remain unchanged. The newer
classification timing helper in the local repository was not deployed.

Original and patched helper SHA256 are in deployment.json. Private remote backup:
/opt/openjev-toolcall/maintenance/dtype-20260918/. Full Docker inspection stays
private on that host. The watchdog timer/service were paused during the stop/start;
the timer was restored after native inference and two mixed-batch rounds passed.
Eight concurrent requests returned exact actions. Audit records include actual
classification mixed with normal sampled rows (multiple events can correspond to
one request due to distributed execution). No restart or OOM occurred after the
manual start at acceptance. Final runtime check is recorded separately.

The first ordinary smoke returned DTYPE_OK without the requested trailing period;
it is preserved as native-smoke.json. An unambiguous prompt subsequently returned
exact DTYPE_OK in native-smoke2.json. Neither is a performance sample.
