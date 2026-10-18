# Debugging session: "I don't love it" stored as *positive*

This document records the Day 3 debugging exercise: a bug was **introduced on
purpose** in one stage, observed as a wrong value in a *different* stage, and
tracked down with breakpoints, watch expressions and call-stack inspection.

| Item | Where |
|---|---|
| Bug commit (intentional) | `refactor(cleaner): simplify punctuation pattern [INTENTIONAL BUG]` on branch `bugfix/negation-lost-in-cleaner` |
| Reproduction script | [`scripts/debug_session.py`](../scripts/debug_session.py) |
| Failing tests | [`debugging/01_failing_tests.txt`](debugging/01_failing_tests.txt) |
| Debugger transcript | [`debugging/02_pdb_session.txt`](debugging/02_pdb_session.txt) |
| Log trace with bug / after fix | [`03_log_trace_with_bug.jsonl`](debugging/03_log_trace_with_bug.jsonl), [`04_log_trace_fixed.jsonl`](debugging/04_log_trace_fixed.jsonl) |
| Tests after fix | [`debugging/05_tests_after_fix.txt`](debugging/05_tests_after_fix.txt) |
| VS Code launch configs | [`.vscode/launch.json`](../.vscode/launch.json) |

---

## 1. The bug

A "simplification" of the cleaner's punctuation regex:

```diff
-_NON_WORD = re.compile(r"[^\w\s']|_")   # keep apostrophes
+_NON_WORD = re.compile(r"[^\w\s]|_")    # "simplified": apostrophes removed
```

Pre-commit hooks (Black, ruff, mypy) all **passed**: the code is valid, typed
and well formatted. Only tests catch the behavioural change, which is why
the testing pyramid matters.

## 2. Symptom

```
FAILED tests/integration/test_pipeline_postgres.py::test_sentiment_labels_are_persisted[I don't love it-negative]
FAILED tests/integration/test_pipeline_postgres.py::test_full_pipeline_stores_structured_result
FAILED tests/unit/test_cleaner.py::test_normalises_text[I don't like it-i don't like it]
FAILED tests/unit/test_pipeline.py::test_end_to_end_with_real_stages_and_in_memory_storage
4 failed, 117 passed
```

The integration test showed that the row in **PostgreSQL** (stage 3) had
`sentiment = 'positive'` for the input *"I don't love it"*.

## 3. Reading the structured logs first

Each stage logs its state after it finishes, and every line of one run shares
the same `run_id`, so the trace in `03_log_trace_with_bug.jsonl` can be read
top to bottom:

```json
{"message": "stage completed", "stage": "cleaner",  "state": {"cleaned": "i don t love it", "token_count": 5}}
{"message": "stage completed", "stage": "analyzer", "state": {"sentiment": "positive", "score": 1.0, "positive_hits": 1, "negative_hits": 0}}
{"message": "stage completed", "stage": "storer",   "state": {"id": 1, "sentiment": "positive", "score": 1.0}}
```

The analyzer only saw one positive hit and no negation. Already a strong hint
(`"don t"`, 5 tokens instead of 4), but we confirmed it with the debugger.

## 4. Debugger session

Line numbers below refer to the code at the bug commit `aded498`.
The session was driven with `pdb` (full transcript in
[`02_pdb_session.txt`](debugging/02_pdb_session.txt)). The identical steps in
VS Code use the **"Python: Current File"** or **"Pytest: analyzer unit
tests"** launch configuration:

| pdb command | VS Code equivalent |
|---|---|
| `break analyzer.py:139` | click in the gutter → red dot (breakpoint) |
| `display token`, `display negation_left`, `display (positive, negative)` | add the expressions in the **WATCH** panel |
| `continue` | F5 |
| `where` | **CALL STACK** panel |
| `up` / `p data.tokens` | click a frame in CALL STACK, inspect in **VARIABLES** / Debug Console |

### Session A: the symptom, inside `SentimentAnalyzer._count_hits`

Breakpoint on `negated = negation_left > 0`, three watch expressions:

```
display token: 'i'      negation_left: 0   (positive, negative): (0, 0)
display token: 'don'    <- should have been "don't"
display token: 't'
display token: 'love'   negation_left still 0, so "love" counted as POSITIVE
display token: 'it'     (positive, negative): (1, 0)
```

`negation_left` never became non-zero: the negator was never recognised.

**Call stack** (`where`) showed how we got here, crossing three layers:

```
debug_session.py  main()             record = pipeline.run(TEXT, ...)
pipeline.py       run()              analysed = self._run_stage(self.analyzer, cleaned)
pipeline.py       _run_stage()       output = stage.process(data)
analyzer.py       process()          result = self._analyse(data)
analyzer.py       _analyse()         positive, negative = self._count_hits(data.tokens)
analyzer.py       _count_hits()      <- breakpoint
```

Moving `up` one frame and inspecting the input of the stage:

```
(Pdb) p data.tokens   -> ('i', 'don', 't', 'love', 'it')
(Pdb) p data.original -> "I don't love it"
(Pdb) p data.cleaned  -> 'i don t love it'
(Pdb) p 'don' in self.lexicon.negators, "don't" in self.lexicon.negators
(False, True)
```

**Conclusion A:** the analyzer works correctly. It received bad input. The
problem is upstream, in the cleaner.

### Session B: the root cause, inside `TextCleaner._clean`

Breakpoint right after the punctuation substitution (`cleaner.py:115`):

```
(Pdb) p data                     -> "I don't love it"
(Pdb) p text                     -> 'i don t love it'      <- apostrophe gone
(Pdb) p _NON_WORD.pattern        -> '[^\\w\\s]|_'
(Pdb) p _NON_WORD.sub(" ", "don't")                         -> 'don t'
(Pdb) p re.compile(r"[^\w\s']|_").sub(" ", "don't")         -> "don't"
```

Evaluating the old and new pattern side by side in the debug console proved
the regex change was the root cause.

## 5. Fix

```diff
-# Anything that is not a letter/digit or whitespace (simplified pattern).
-_NON_WORD = re.compile(r"[^\w\s]|_")
+# Anything that is not a letter/digit, whitespace or an apostrophe. Apostrophes
+# must survive cleaning: the analyzer relies on negators such as "don't".
+_NON_WORD = re.compile(r"[^\w\s']|_")
```

Plus a dedicated regression test,
`test_preserves_negation_contractions`, covering `don't`, `isn't`, `can't`,
`won't` and `wasn't`. After the fix, all tests pass and the log trace shows
`"cleaned": "i don't love it"` → `sentiment: negative`, `score: -1.0`.

## 6. Lessons learned

* **The failing stage is not always the faulty stage.** The wrong value was
  visible in the database (stage 3) and computed by the analyzer (stage 2), but
  caused by the cleaner (stage 1). Logging the state after every stage made the
  hand-off point obvious.
* **Watch expressions beat print statements**: they show how a value evolves
  across iterations (`token`, `negation_left`) without editing code.
* **The call stack shows the contract boundaries**: walking `up` from the
  analyzer to `_run_stage` showed exactly which object crossed the boundary.
* **Static checks do not catch behavioural bugs**: the bug passed Black, ruff
  and mypy. Unit tests and integration tests caught it.
* Side observation: pdb's `restart` raises an exception (`pdb.Restart`)
  inside the program. Our defensive `except Exception` in the analyzer wrapped
  it as `AnalysisError`. To restart a session, quit and relaunch instead.
* A second, *real* bug was found earlier during development the same way: in
  `"not bad, it's great"` the negation window also flipped `great`. It was
  fixed in `fix(analyzer): limit negation to the first sentiment word in its
  window`.

## 7. Recording a video / screenshots

The transcripts above are the text evidence. For the Loom video or
screenshots the submission asks for, repeat sessions A and B in VS Code:

1. `git checkout aded498 -- src/text_pipeline/stages/cleaner.py` (puts the
   buggy version back temporarily).
2. Open `src/text_pipeline/stages/analyzer.py` and set a breakpoint on the
   line `negated = negation_left > 0` inside `_count_hits`.
3. Run **"Python: Current File"** on `scripts/debug_session.py` (or the
   **"Pytest: analyzer unit tests"** config).
4. Add `token`, `negation_left`, `(positive, negative)` to **WATCH**; press F5 a
   few times; capture the **CALL STACK** panel.
5. Repeat with a breakpoint in `cleaner.py` after `_NON_WORD.sub(...)`.
6. `git checkout HEAD -- src/text_pipeline/stages/cleaner.py` to restore the fix.
