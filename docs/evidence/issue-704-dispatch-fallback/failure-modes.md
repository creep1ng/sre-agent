Ways the hand-off of an investigation (or verification) dispatch can fail, written before the fix:
F1 The first attempt fails after its intent was written (the outcome write raises, e.g. the
   database drops mid-dispatch). The fallback must end the run with investigator_failed, the
   real cause, not producer_interrupted.
F2 The fallback fails too (the database still does not answer). The exception must not leave
   the background task: it is logged with incident_id and run_id, the run stays running, and the
   startup sweep ends it.
F3 The first attempt fails before the claim (the agent identity cannot be read): the fallback
   ends the run with investigator_failed (behaviour already on main, kept).
F4 Another live process holds the claim: the fallback leaves the run alone (kept).
