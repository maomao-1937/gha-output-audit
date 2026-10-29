# Evidence and scope

Reviewed 2026-10-29. This is an original stdlib implementation, not a copy of
upstream source. Sources below informed a deliberately bounded audit profile.

## Observations from primary sources

- [GitHub workflow commands documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands)
  specifies UTF-8 environment files, the assignment form for output parameters,
  and the delimiter form for multiline output. It warns that a delimiter must
  not occur on its own line inside an arbitrary value. It describes workflow
  generation, rather than this tool's local CLI.
- [actions/runner FileCommandManager.cs](https://github.com/actions/runner/blob/main/src/Runner.Worker/FileCommandManager.cs),
  inspected `EnvFileKeyValuePairs` and its line reader on the mutable `main`
  branch: parsing chooses the earlier assignment/heredoc marker, skips empty
  lines, compares delimiters exactly, and requires a newline on nonclosing body
  lines. The matching closing line can end at EOF. CRLF handling is conditional
  on a Windows build. The assignment branch's empty-name guard checks the full
  line; the heredoc branch checks split fields. These are source observations,
  not results of running a .NET or hosted runner.
- [Community discussion 106666](https://github.com/orgs/community/discussions/106666)
  reports trouble preserving multiline output after switching command forms.
  This is a user report, not a reproduced runner defect, a benchmark, or proof
  of demand. We did not reproduce that workflow.

## Inferences and deliberate choices

An offline capture can expose framing mistakes before a workflow is rerun.
That is an inferred use case; there is no adoption or measured time-saving
claim. Strict UTF-8 without BOM/NUL/lone CR, nonempty names, finite limits,
content-free reports, and exact expected-set checks are this project's policy.
Accepting CRLF on every host makes fixtures portable but differs from the
examined runner on non-Windows. Names remain broader than shell identifiers.
No real runner was executed, and downstream name/context behavior is untested.

A successful parse cannot attribute an assignment to intended output versus
injected or accidentally concatenated data. A full expected set helps identify
unexpected keys while leaving values unverified. Captures and CLI expectation
arguments can themselves be sensitive; reporting does not make raw evidence
safe to publish.

## Alternatives and complementarity

- [actionlint](https://github.com/rhysd/actionlint) checks GitHub Actions workflow
  definitions; use it for YAML/expression/static workflow validation. This tool
  checks captured bytes and does not replace it.
- [GitHub Actions runner](https://github.com/actions/runner) is the authoritative
  execution implementation. Use an actual controlled runner integration test
  when runner/platform/downstream behavior must be established.
- A direct text/hex inspection can diagnose bytes but risks exposing values in
  logs. This tool's narrow benefit is count/location reporting without echoes.

The linked `main` branch can change. Recheck source behavior before broadening
compatibility claims; current tests establish only the documented local profile.
