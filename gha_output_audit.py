#!/usr/bin/env python3
"""Audit a bounded, offline GITHUB_OUTPUT capture without revealing its content."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys


class AuditError(Exception):
    """Carries a fixed public code, never an input-dependent message."""


class HelpExit(Exception):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise AuditError("ARGUMENT_ERROR")

    def exit(self, status=0, message=None):
        if status:
            raise AuditError("ARGUMENT_ERROR")
        raise HelpExit()


def positive_limit(maximum):
    def convert(value):
        # A length check also bounds integer conversion work on older Pythons.
        if not value.isascii() or not value.isdecimal() or len(value) > 9:
            raise AuditError("ARGUMENT_ERROR")
        number = int(value)
        if not 1 <= number <= maximum:
            raise AuditError("ARGUMENT_ERROR")
        return number
    return convert


def arguments(argv):
    parser = SafeParser(prog="gha-output-audit", allow_abbrev=False,
                        description="Audit an offline capture; reports never include capture content.")
    parser.add_argument("capture", help="path of a local regular byte file (read only)")
    parser.add_argument("--json", action="store_true", help="emit a value-free JSON report")
    parser.add_argument("--expect-name", action="append", default=[], metavar="NAME",
                        help="repeat to assert an exact, case-sensitive set of names")
    parser.add_argument("--max-bytes", type=positive_limit(67108864), default=1048576,
                        metavar="N", help="byte limit; default 1048576, maximum 67108864")
    parser.add_argument("--max-lines", type=positive_limit(1000000), default=100000,
                        metavar="N", help="physical line limit; default 100000, maximum 1000000")
    parser.add_argument("--max-records", type=positive_limit(100000), default=10000,
                        metavar="N", help="completed record limit; default 10000, maximum 100000")
    args = parser.parse_args(argv)
    if (len(args.expect_name) > 100000 or sum(map(len, args.expect_name)) > 1048576
            or any(not name or any(c in name for c in "\r\n\0") for name in args.expect_name)):
        raise AuditError("ARGUMENT_ERROR")
    return args


def read_capture(args):
    try:
        path = Path(args.capture)
        if not path.is_file():
            raise AuditError("INPUT_ERROR")
        with path.open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise AuditError("INPUT_ERROR")
            data = stream.read(args.max_bytes + 1)
    except (OSError, ValueError):
        raise AuditError("INPUT_ERROR") from None
    if len(data) > args.max_bytes:
        raise AuditError("BYTE_LIMIT")
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\0\0\xfe\xff")):
        raise AuditError("BOM_UNSUPPORTED")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError:
        raise AuditError("ENCODING_UNSUPPORTED") from None
    if "\0" in text:
        raise AuditError("NUL_UNSUPPORTED")
    if "\r" in text.replace("\r\n", ""):
        raise AuditError("LONE_CR_UNSUPPORTED")
    line_count = text.count("\n") + int(bool(text) and not text.endswith("\n"))
    if line_count > args.max_lines:
        raise AuditError("LINE_LIMIT")
    # Split only LF. Other Unicode line separators are ordinary data.
    parts = text.split("\n")
    lines = [(part[:-1] if part.endswith("\r") else part, True) for part in parts[:-1]]
    if parts[-1]:
        lines.append((parts[-1], False))
    return len(data), lines


def blank_report():
    return dict(status="clean", complete=True, bytes=0, lines=0, records=0,
                unique_names=0, duplicates=0, expected_names=0, expectations_checked=False,
                missing_names=0, extra_names=0, diagnostics=[])


def audit(byte_count, lines, expected, max_records):
    report = blank_report()
    report.update(bytes=byte_count, lines=len(lines), expected_names=len(set(expected)))
    seen = {}
    index = 0
    while index < len(lines):
        header, _ = lines[index]
        line_number = index + 1
        index += 1
        if header == "":
            continue
        if report["records"] >= max_records:
            raise AuditError("RECORD_LIMIT")
        eq = header.find("=")
        hd = header.find("<<")
        code = None
        name = ""
        if eq >= 0 and (hd < 0 or eq < hd):
            name = header[:eq]
            if not name:
                code = "EMPTY_NAME"
        elif hd >= 0 and (eq < 0 or hd < eq):
            name, delimiter = header[:hd], header[hd + 2:]
            if not name:
                code = "EMPTY_NAME"
            elif not delimiter:
                code = "EMPTY_DELIMITER"
            else:
                while index < len(lines):
                    body, terminated = lines[index]
                    index += 1
                    if body == delimiter:
                        break
                    if not terminated:
                        code = "BODY_NEWLINE_MISSING"
                        break
                else:
                    code = "MISSING_DELIMITER"
        else:
            code = "INVALID_HEADER"
        ordinal = report["records"] + 1
        if code:
            report["diagnostics"].append(dict(code=code, line=line_number, record=ordinal))
            report["complete"] = False
            break  # Framing is uncertain: do not invent later records.
        report["records"] = ordinal
        if name in seen:
            report["duplicates"] += 1
            report["diagnostics"].append(dict(code="DUPLICATE_NAME", line=line_number,
                                              record=ordinal, first_record=seen[name]))
        else:
            seen[name] = ordinal
    report["unique_names"] = len(seen)
    if expected and report["complete"]:
        report["expectations_checked"] = True
        wanted = set(expected)
        report["missing_names"] = len(wanted - seen.keys())
        report["extra_names"] = len(seen.keys() - wanted)
        if report["missing_names"]:
            report["diagnostics"].append(dict(code="MISSING_EXPECTED_NAMES", count=report["missing_names"]))
        if report["extra_names"]:
            report["diagnostics"].append(dict(code="EXTRA_NAMES", count=report["extra_names"]))
    if report["diagnostics"]:
        report["status"] = "findings"
    return report


def emit(report, as_json):
    if as_json:
        print(json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(",", ":")))
        return
    print("status=" + report["status"] + " complete=" + str(report["complete"]).lower())
    print(" ".join(f"{key}={report[key]}" for key in
                   ("bytes", "lines", "records", "unique_names", "duplicates", "expected_names",
                    "missing_names", "extra_names")))
    print("expectations_checked=" + str(report["expectations_checked"]).lower())
    for diagnostic in report["diagnostics"]:
        print(diagnostic["code"] + "".join(f" {key}={value}" for key, value in diagnostic.items()
                                          if key != "code"))


def cli(argv):
    try:
        args = arguments(argv)
        byte_count, lines = read_capture(args)
        report = audit(byte_count, lines, args.expect_name, args.max_records)
        status = 1 if report["status"] == "findings" else 0
    except HelpExit:
        return 0
    except AuditError as error:
        report = blank_report()
        report.update(status="error", complete=False, diagnostics=[dict(code=error.args[0])])
        status = 2
    emit(report, "--json" in argv)
    return status


def main():
    try:
        status = cli(sys.argv[1:])
        sys.stdout.flush()
        return status
    except (BrokenPipeError, OSError):
        # Suppress a second failure during interpreter shutdown, including --help.
        try:
            with open(os.devnull, "w") as sink:
                os.dup2(sink.fileno(), sys.stdout.fileno())
        except OSError:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
