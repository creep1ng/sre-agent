# Sanitization note

The public bundle contains allowlisted response metadata and measured SQL counters only. It excludes raw logs, credentials, environment files, request payloads, prompts/instructions, user data, and private inventory. All eleven PNGs were visually inspected. The public test helper replaces its private synthetic fixture marker with a neutral sentinel. SHA256SUMS binds every distributed artifact.

The deterministic text/data scan found no private absolute paths, authorization credentials, database URLs, provider keys, or original synthetic payload sentinel. The two renderer helpers intentionally contain detection-regex strings (not matching values) as part of their input rejection policy; those source files were manually inspected. PNGs were individually visually inspected, including the corrected full-page #397 rerender.
