# Attribution and provenance

TAIR extends the idea of reading candidate logits directly, inspired by
[OpenJev](https://github.com/TheoLeeCJ/openjev). The experiments were developed in
an OpenJev checkout at commit `b4782a6c953f05c6255706d7a219f4e032af5b58`.

`src/openjev_phase1/` and its original tests are imported from that MIT-licensed
checkout. Their namespace is retained so older local-model benchmarks continue
to import the same helpers. The upstream copyright and MIT permission notice are
retained in [LICENSE](LICENSE). New engine/protocol code and authored experiment
records are distributed under the same license. The initial imported-file hashes
are listed in [the migration manifest](docs/MIGRATION_MANIFEST.json).

The project experimentally patches vLLM; it does not replace vLLM or claim to have
invented constrained decoding, direct logit scoring, or KV caching. vLLM is a
separate dependency with its own license. Pi tools are loaded from a separately
installed Pi package; its implementation and package license remain upstream.

Model weights, downloaded caches and upstream third-party evaluation records are
not included. Model access and usage remain subject to each model's terms. Exact
model metadata revisions, engine versions and serving settings are retained in
the experiment manifests. Historical deployment aliases and filesystem paths in
frozen records describe the original environment and are not usable credentials
or portable installation instructions.
