# gha-output-audit

[![tests](https://github.com/maomao-1937/gha-output-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/gha-output-audit/actions/workflows/tests.yml)

Audit a saved GitHub Actions `GITHUB_OUTPUT` byte file locally. Find malformed
multiline framing, repeated names, and an unexpected set of output names without
printing the file's names, values, delimiters, or invalid lines.

Python 3.11+; standard library only. Download this directory and run the script.
There is no installation step, package dependency, network request, subprocess,
or automatic lookup of the `GITHUB_OUTPUT` environment variable in the product.

## Quick start

Use a separately saved, completed capture. Examples below use public fixtures;
do not commit real output captures, which can contain secrets.

```console
python gha_output_audit.py fixtures/clean-lf.txt
python gha_output_audit.py fixtures/clean-crlf.txt --json
python gha_output_audit.py fixtures/duplicate.txt --json
python gha_output_audit.py fixtures/clean-lf.txt --expect-name result --expect-name details
python -m unittest discover -s tests -v
```

The first command exits 0 and prints:

```text
status=clean complete=true
bytes=45 lines=5 records=2 unique_names=2 duplicates=0 expected_names=0 missing_names=0 extra_names=0
expectations_checked=false
```

The duplicate fixture exits 1. Its JSON report includes only fixed fields,
counts, booleans, codes, and source locations:

```json
{"bytes":18,"complete":true,"diagnostics":[{"code":"DUPLICATE_NAME","first_record":1,"line":2,"record":2}],"duplicates":1,"expectations_checked":false,"expected_names":0,"extra_names":0,"lines":2,"missing_names":0,"records":2,"status":"findings","unique_names":1}
```

`--expect-name NAME` is repeatable and asserts an exact set. Comparison is
case-sensitive; repeated expectations collapse into one. Missing and extra
**unique** name counts are reported, never the names. Empty expectations or
expectations containing NUL, CR, or LF are argument errors. Omitting the option
disables the check; this interface cannot assert an empty set. Argument values
may remain visible in shell history/process listings even though this program
does not print them.

## Input profile and limits

| Rule | Behavior |
| --- | --- |
| Encoding | Strict UTF-8; initial UTF-8/UTF-16/UTF-32 BOMs rejected. An embedded U+FEFF is ordinary data. |
| Line endings | Accept LF, CRLF, and mixtures on every host; reject lone CR and NUL anywhere. Other Unicode separators are ordinary data. |
| Assignment | First `=` wins only when it precedes the first `<<`; remaining characters are the value. Empty values are valid. |
| Multiline | First `<<` wins when it precedes `=`; the remainder is the exact, nonempty delimiter, including spaces or `=`. |
| Delimiter | Exact, case-sensitive whole-line match; no trimming. Closing delimiter may end at EOF without a final newline. |
| Missing close | A nonclosing final body line without LF is `BODY_NEWLINE_MISSING`; reaching EOF otherwise is `MISSING_DELIMITER`. A bare header at EOF has no closing line. |
| Names | Nonempty, case-sensitive, unrestricted by shell identifier syntax; whitespace and Unicode are retained. Empty assignment names are rejected by this conservative profile. |
| Empty lines | Skip only zero-length logical lines between records. Whitespace-only lines are malformed headers. Body blank lines remain body content. |
| Syntax error | Stop at the first malformed header/body. Counts cover only completed prefix records; expectations are not checked. |
| Duplicate | Count each completed occurrence after the first; point to its header line, record ordinal, and first record ordinal. |

The parser counts framing and names internally; it does not export reconstructed
values. It never prints names, values, delimiters, raw malformed lines, input
paths, or custom expectation values. Operational and argument errors use generic
fixed codes. Human and JSON reports are deterministic. Diagnostics use 1-based
physical header lines and record ordinals; a body failure points to its header.
JSON uses one object per invocation. All reports go to stdout, stderr stays empty.
`--help` prints static usage text.

| Option | Default | Allowed range |
| --- | ---: | ---: |
| `--max-bytes N` | 1,048,576 | 1..67,108,864 |
| `--max-lines N` | 100,000 | 1..1,000,000 |
| `--max-records N` | 10,000 | 1..100,000 |

Reads at most `max-bytes + 1` bytes, then rejects over-limit files. Physical
lines include blank/body/delimiter lines; a trailing LF adds no phantom line.
Line limits are checked before building the line list. Record limits count
completed records, including duplicates; encountering another nonempty header
after the cap is a bounds error. Expectations are capped at 100,000 arguments
and 1,048,576 total characters. Only local regular files are accepted; symlinks
to regular files are followed. Use a stable snapshot: this tool does not lock
against concurrent writers or guarantee race-free pathname resolution.

| Exit | Meaning |
| --- | --- |
| 0 | Supported capture with no findings, or successful help |
| 1 | Malformed framing, duplicate names, or expected-set mismatch |
| 2 | Unsupported byte profile, I/O failure, bounds/argument error, or broken stdout pipe |

Exit 2 reports contain zero counts and `complete=false`; do not interpret them
as an empty successful capture. Broken pipes suppress output errors and
tracebacks, including during help. A closed consumer might receive no report.

## What this can establish

This is a capture auditor, **not an injection detector**. If unintended content
forms a syntactically valid extra assignment, the file alone cannot establish
where it came from. An expected-name set can find extra keys but cannot detect
a replaced value, deliberate permitted-name reuse with only one occurrence, or
application-level value corruption. A delimiter collision can terminate a body
early; subsequent valid assignments are not proof of malicious intent.

This project does not parse workflow YAML, shell quoting, expressions, old
`::set-output` log commands, runner secret masking, downstream output contexts,
or hosted-runner output quotas. It does not execute a runner or claim runner
equivalence. In particular, the upstream line reader handles CRLF under its
Windows build conditional, while this portable profile accepts CRLF everywhere.
The examined upstream assignment branch checks the whole line rather than the
split name; our empty-name rejection is an explicit conservative difference.
See [RESEARCH.md](RESEARCH.md) for evidence and alternatives.

## 中文快速使用

需要 Python 3.11 或更高版本，无第三方依赖。下载本目录后，在终端执行：

```console
python gha_output_audit.py fixtures/clean-lf.txt --json
python gha_output_audit.py fixtures/clean-lf.txt --expect-name result --expect-name details
python -m unittest discover -s tests -v
```

将示例路径替换成已保存且停止写入的输出文件。程序只读该文件，不读取或写入
`GITHUB_OUTPUT` 环境变量指向的位置。退出码 0 表示本工具支持的格式中未发现问题，
1 表示格式、重复名称或预期名称集合不匹配，2 表示编码、文件读取、参数或大小限制问题。
报告只输出数量、行号、序号和固定错误代码，不回显文件内容或路径。

支持 UTF-8、LF/CRLF；拒绝 BOM、NUL 和独立 CR。`--expect-name` 可重复使用，区分
大小写并检查完整名称集合。默认最多读取 1 MiB，可用上表中的限制选项调整。
真实文件可能包含密钥，请保留在本地；合法格式的意外赋值无法仅靠文件判断来源，
本工具不声称能检测注入，也不等同于真实 GitHub runner 验证。

MIT license, copyright 2026 maomao-1937.
