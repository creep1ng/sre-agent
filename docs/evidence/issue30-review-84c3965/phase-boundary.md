# Pre-NULL review snapshot

This directory's README, captures and 21-case results are preserved as-of the
18:34/18:36 UTC review phase. They are not the final full-event assessment.
Its 4-valid/5-invalid results used recursive JSON-null omission, which could hide
invalid stored JSONB values. Raw SQL is unchanged. The final observer omits only
optional top-level SQL NULL and now correctly reports 0-valid/9-invalid, plus
absent401. The separate post-NULL verification unit contains the final matrix,
new runs and the additional pre-fix22nd-case RED/GREEN. No prior capture/result/SHA
is rewritten; publishing this snapshot does not accept #30 or implement a producer fix.
