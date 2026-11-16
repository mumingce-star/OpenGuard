# Synthetic Metadata transport fixtures

Apache-2.0 project-authored synthetic material, not downloaded Hub metadata.
Unit/security tests construct `synthetic/Model` and `synthetic/Data` HTTP/JSON/DNS
bytes in memory. Public IP strings only exercise address policy and fake dial
arguments; tests do not connect to those addresses.

`synthetic_consumer.py` demonstrates temporary bytes/source descriptor handoff
and checks byte count/hash. It is not B01, does not infer any license or
authorization facts, and is not part of the real 5-model/5-dataset acceptance.
No fixture grants permission to persist production raw payloads.
