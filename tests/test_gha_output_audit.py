"""Black-box tests; fixture content and paths must never reach reports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "gha_output_audit.py"
SENTINEL = "PRIVATE_SENTINEL_71b!::error::"


class CliTests(unittest.TestCase):
    def run_capture(self, data=b"", *args, expected=0):
        with tempfile.TemporaryDirectory(prefix=SENTINEL.replace(':', '_')) as tmp:
            path = Path(tmp) / "capture.txt"
            path.write_bytes(data)
            result = subprocess.run([sys.executable, str(SCRIPT), str(path), "--json", *args],
                                    capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn(SENTINEL, result.stdout)
        self.assertNotIn(str(path), result.stdout)
        return json.loads(result.stdout)

    def test_empty(self):
        r = self.run_capture()
        self.assertEqual((r["records"], r["lines"], r["unique_names"]), (0, 0, 0))

    def test_assignment_final_without_newline(self):
        r = self.run_capture(b"a=x")
        self.assertEqual((r["records"], r["lines"]), (1, 1))

    def test_empty_value(self):
        self.assertEqual(self.run_capture(b"a=\n")["records"], 1)

    def test_first_equals_precedes_heredoc(self):
        self.assertEqual(self.run_capture(b"a=value<<delimiter\n")["records"], 1)

    def test_first_heredoc_precedes_equals(self):
        self.assertEqual(self.run_capture(b"a<<D=X\nv=1\nD=X\n")["records"], 1)

    def test_additional_equals_in_value(self):
        self.assertEqual(self.run_capture(b"a=b=c=d\n")["records"], 1)

    def test_lf_multiline(self):
        self.assertEqual(self.run_capture(b"a<<E\nfirst\nsecond\nE\n")["records"], 1)

    def test_crlf_multiline(self):
        self.assertEqual(self.run_capture(b"a<<E\r\nfirst\r\nE\r\nb=x\r\n")["records"], 2)

    def test_mixed_newlines(self):
        self.assertEqual(self.run_capture(b"a<<E\r\nx\nE\r\nb=y")["records"], 2)

    def test_closing_delimiter_final_without_newline(self):
        self.assertEqual(self.run_capture(b"a<<E\nvalue\nE")["records"], 1)

    def test_immediate_closing_empty_multiline(self):
        self.assertEqual(self.run_capture(b"a<<E\nE")["records"], 1)

    def test_missing_closing_after_terminated_body(self):
        r = self.run_capture(b"a<<E\nx\n", expected=1)
        self.assertEqual(r["diagnostics"][0]["code"], "MISSING_DELIMITER")
        self.assertFalse(r["complete"])

    def test_unterminated_nonclosing_body(self):
        r = self.run_capture(b"a<<E\nx", expected=1)
        self.assertEqual(r["diagnostics"][0]["code"], "BODY_NEWLINE_MISSING")

    def test_unterminated_header(self):
        r = self.run_capture(b"a<<E", expected=1)
        self.assertEqual(r["diagnostics"][0]["code"], "MISSING_DELIMITER")

    def test_delimiter_exact_no_trim(self):
        r = self.run_capture(b"a<<E\nx\n E\n", expected=1)
        self.assertEqual(r["diagnostics"][0]["code"], "MISSING_DELIMITER")

    def test_delimiter_case_sensitive(self):
        self.run_capture(b"a<<E\ne\n", expected=1)

    def test_blank_lines_only_are_skipped(self):
        self.assertEqual(self.run_capture(b"\n\r\na=x\n\n")["records"], 1)

    def test_whitespace_only_line_invalid(self):
        r = self.run_capture(b" \n", expected=1)
        self.assertEqual(r["diagnostics"][0]["line"], 1)

    def test_non_shell_names_preserved(self):
        r = self.run_capture(" has spaces .-中 =secret\n".encode(), "--expect-name", " has spaces .-中 ")
        self.assertEqual(r["unique_names"], 1)

    def test_names_case_sensitive(self):
        r = self.run_capture(b"a=x\nA=y\n")
        self.assertEqual((r["unique_names"], r["duplicates"]), (2, 0))

    def test_duplicate_across_styles(self):
        r = self.run_capture(b"a=x\na<<E\ny\nE\na=z\n", expected=1)
        self.assertEqual((r["records"], r["unique_names"], r["duplicates"]), (3, 1, 2))
        self.assertEqual(r["diagnostics"], [
            {"code": "DUPLICATE_NAME", "line": 2, "record": 2, "first_record": 1},
            {"code": "DUPLICATE_NAME", "line": 5, "record": 3, "first_record": 1}])

    def test_expect_name_exact_set_counts(self):
        r = self.run_capture(b"a=x\nb=y\n", "--expect-name", "a", "--expect-name", "c", expected=1)
        self.assertEqual((r["missing_names"], r["extra_names"]), (1, 1))

    def test_repeated_expectation_is_set(self):
        self.run_capture(b"a=x\n", "--expect-name", "a", "--expect-name", "a")

    def test_expectations_not_evaluated_on_partial_parse(self):
        r = self.run_capture(b"a=x\nbad\n", "--expect-name", "c", expected=1)
        self.assertFalse(r["expectations_checked"])
        self.assertEqual((r["records"], r["missing_names"], r["extra_names"]), (1, 0, 0))

    def test_empty_name_rejected_profile(self):
        self.run_capture(b"=secret\n", expected=1)

    def test_empty_heredoc_name_and_delimiter(self):
        for data in (b"<<E\nx\nE\n", b"a<<\nx\n"):
            with self.subTest(data=data):
                self.run_capture(data, expected=1)

    def test_no_echo_any_input_content(self):
        for data in ((SENTINEL + "=secret\n" + SENTINEL + "=secret\n").encode(),
                     (SENTINEL + "\n").encode(), ("a<<" + SENTINEL + "\nsecret").encode()):
            with self.subTest(data=data):
                self.run_capture(data, "--expect-name", SENTINEL, expected=1)

    def test_valid_injected_assignment_cannot_be_detected(self):
        self.assertEqual(self.run_capture(b"a=x\ninjected=y\n")["records"], 2)

    def test_nul_unsupported(self):
        r = self.run_capture(b"a=x\0\n", expected=2)
        self.assertEqual(r["diagnostics"][0]["code"], "NUL_UNSUPPORTED")

    def test_lone_cr_unsupported(self):
        self.run_capture(b"a=x\rb=y\n", expected=2)

    def test_invalid_utf8_unsupported(self):
        self.run_capture(b"a=\xff\n", expected=2)

    def test_boms_unsupported(self):
        for data in (b"\xef\xbb\xbfa=x\n", b"\xff\xfea\0=\0x\0", b"\xfe\xff\0a"):
            with self.subTest(data=data):
                self.run_capture(data, expected=2)

    def test_byte_limit_exact_and_over(self):
        self.run_capture(b"a=x\n", "--max-bytes", "4")
        self.run_capture(b"a=x\n", "--max-bytes", "3", expected=2)

    def test_line_limit_counts_body_and_blanks(self):
        self.run_capture(b"a<<E\nx\nE\n", "--max-lines", "3")
        self.run_capture(b"a<<E\nx\nE\n", "--max-lines", "2", expected=2)

    def test_record_limit(self):
        self.run_capture(b"a=x\nb=y\n", "--max-records", "1", expected=2)

    def test_invalid_flags_do_not_echo(self):
        for args in (("--max-bytes", SENTINEL), ("--max-lines", "0"),
                     ("--max-records", "100001"), ("--" + SENTINEL,),
                     ("--expect-name", ""), ("--expect-name", SENTINEL + "\n")):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("ARGUMENT_ERROR", result.stdout + result.stderr)
                self.assertNotIn(SENTINEL, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_missing_file_does_not_echo(self):
        result = subprocess.run([sys.executable, str(SCRIPT), SENTINEL, "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["diagnostics"][0]["code"], "INPUT_ERROR")

    def test_human_output_value_free_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture"
            path.write_text(SENTINEL + "=x\n" + SENTINEL + "=y\n", encoding="utf-8")
            command = [sys.executable, str(SCRIPT), str(path)]
            a = subprocess.run(command, capture_output=True, text=True)
            b = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(a.returncode, 1)
        self.assertEqual(a.stdout, b.stdout)
        self.assertNotIn(SENTINEL, a.stdout + a.stderr)
        self.assertIn("DUPLICATE_NAME line=2 record=2 first_record=1", a.stdout)

    def test_help_static(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--expect-name", result.stdout)

    def test_broken_pipe_help_and_report_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture"
            path.write_bytes(b"a=x\n")
            for args in (["--help"], [str(path), "--json"]):
                with self.subTest(args=args):
                    process = subprocess.Popen([sys.executable, str(SCRIPT), *args], stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    process.stdout.close()
                    errors = process.stderr.read()
                    status = process.wait()
                    process.stderr.close()
                    self.assertEqual(status, 2)
                    self.assertEqual(errors, b"")


if __name__ == "__main__":
    unittest.main()
