# Pinned continuation token equivalence probe

Three live contexts: short instructions, long tool history, Chinese tool history.
With two candidate tool continuations, the warmed cache output exactly matched
full remote tokenization for every case. Initial cache calibration cost is retained.
No model inference was requested in this probe. Runtime caches were temporary and
are not archived. This sample checks equivalence for this pinned template; it is
not a general guarantee across arbitrary templates. Tokenizer and config hashes
were verified live before the full Agent experiment.
