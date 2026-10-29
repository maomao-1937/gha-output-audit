# Local validation

Observed on 2026-10-29, Asia/Singapore:

- CPython 3.11.15, Windows x86-64, MSC v.1944.
- OS reported by `platform.platform()`: `Windows-10-10.0.26300-SP0`.
- Standard library only; no dependency installation.

## Red to green

Tests were written before `gha_output_audit.py`. The initial actual command
`python -m unittest -v test_gha_output_audit.CliTests.test_assignment_final_without_newline`
failed: the child process exited 2 rather than the expected 0 because the
product script did not yet exist. The full preimplementation command
`python -m unittest -v` ran 40 test methods and failed with 50 assertion
failures and one JSON-decoding error across subtests. These were missing-product
failures; no synthetic regression or hosted-runner result is claimed.

After implementation, `python -m unittest -v` passed all 40 methods. Tests were
then moved into `tests/` for shared CI discovery. The final recorded command
`python -m unittest discover -s tests -v` passed all 40 methods in 5.343 seconds
with `OK`. Each method exercises actual
CLI subprocesses (some run multiple subcases), not a mocked parser.

Covered behavior:

- Assignment/heredoc marker precedence, additional equals, empty values,
  Unicode/space-containing names, case sensitivity, body lines versus headers.
- LF, CRLF, mixed endings, empty versus whitespace-only lines, exact/case-sensitive
  delimiters, empty multiline body, closing delimiter without final newline,
  missing closing delimiter, final body line without newline, header at EOF.
- Duplicates across both forms with record/line locations; expected-set missing
  and extra counts; repeated expectations; suppressing checks on partial parse.
- Strict encoding, UTF BOMs, NUL, lone CR, byte/line/record bounds and invalid flags.
- Secret-like sentinel in names, values, delimiters, malformed lines, custom
  expectations and input paths; generic errors and deterministic human output.
- Successful static help; closed stdout pipes during help and JSON reporting
  produce exit 2 and no traceback on this Windows environment.
- A valid unexpected assignment passes without an expected set, explicitly
  exercising the limitation that syntax alone cannot detect injection.

## Fixture checks

`checks.json` contains 10 actual CLI cases. All passed with their declared exit
codes in a local sequential subprocess harness:

| Capture / options | Exit |
| --- | ---: |
| `clean-lf.txt --json` | 0 |
| `clean-crlf.txt --json` | 0 |
| `duplicate.txt --json` | 1 |
| `missing-delimiter.txt --json` | 1 |
| `closing-no-newline.txt --json` | 0 |
| `body-no-newline.txt --json` | 1 |
| `clean-lf.txt --expect-name result --expect-name details --json` | 0 |
| `clean-lf.txt --expect-name result --json` | 1 |
| `clean-lf.txt --max-bytes 4 --json` | 2 |
| `invalid-utf8.bin --json` | 2 |

Fixtures are synthetic public examples. `.gitattributes` preserves their exact
bytes (`fixtures/** -text`), including 50-byte CRLF data and missing final
newlines. Clean LF is 45 bytes; the duplicate example is 18 bytes. README
example reports use those actual observed fixtures.

## Reproduce

```console
python --version
python -m unittest discover -s tests -v
python gha_output_audit.py fixtures/clean-lf.txt
python gha_output_audit.py fixtures/duplicate.txt --json
```

The last command intentionally exits 1. Each `checks.json` entry's `args`
excludes the Python executable; a shared check runner should prepend only its
Python executable and compare the process exit code with `exit`.

## Validation boundaries

No hosted Actions run, .NET runner, Linux or macOS execution, downstream output
consumer, real secret-bearing capture, masking behavior, shell generation,
workflow YAML validation, production usage or performance benchmark was tested.
Sources inform the local profile; tests do not establish runner equivalence.
No network access or live `GITHUB_OUTPUT` environment-file writes are performed
by the product or tests. Test subprocesses invoke only the local Python script.
