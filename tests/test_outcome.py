"""Tests for worker output outcome detection."""

from ringmaster.worker.outcome import (
    Outcome,
    detect_outcome,
    parse_test_results,
)


class TestOutcomeDetection:
    """Tests for detect_outcome function."""

    def test_completion_signal_success(self):
        """Completion signal indicates success."""
        output = "Running task...\nDone!\n<promise>COMPLETE</promise>"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.is_success
        assert not result.is_failure
        assert result.signals.has_completion_signal
        assert result.confidence >= 0.9

    def test_success_marker_with_exit_zero(self):
        """Success marker plus exit code 0."""
        output = "Building project...\n✓ Build successful\nAll done!"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.signals.has_success_marker
        assert result.signals.exit_code_success

    def test_failure_marker_detected(self):
        """Explicit failure marker takes priority."""
        output = "Compiling...\nError: Cannot find module\nBuild failed"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.FAILED
        assert result.is_failure
        assert result.signals.has_failure_marker

    def test_tests_failed_detected(self):
        """Test failures indicate failure outcome."""
        output = "Running tests...\n5 tests passed, 3 tests failed\nDone"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.FAILED
        assert result.signals.tests_failed
        assert "Test failures" in result.reason

    def test_tests_passed_with_exit_zero(self):
        """Tests passed with good exit code."""
        output = "Running tests...\n10 tests passed\nAll green!"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.signals.tests_passed
        assert not result.signals.tests_failed

    def test_tests_passed_without_exit_code(self):
        """Tests passed but no exit code - likely success."""
        output = "Running tests...\n10 tests passed"
        result = detect_outcome(output, exit_code=None)

        assert result.outcome == Outcome.LIKELY_SUCCESS
        assert result.signals.tests_passed

    def test_decision_needed_takes_priority(self):
        """Decision marker takes highest priority."""
        output = "Working on task...\n✓ Build successful\n? Decision needed: Choose database"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert result.needs_human_input
        assert result.decision_question == "Choose database"
        assert result.signals.has_decision_marker

    def test_blocked_marker(self):
        """BLOCKED: marker indicates decision needed."""
        output = "Analyzing requirements...\nBLOCKED: Missing API credentials"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert result.decision_question == "Missing API credentials"

    def test_should_i_question(self):
        """'Should I' questions indicate decision needed."""
        output = "Found multiple options. Should I use Redis or Memcached?"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert "Redis or Memcached?" in result.decision_question or "Redis or Memcached" in result.decision_question

    def test_exit_zero_only_likely_success(self):
        """Exit code 0 alone is only likely success."""
        output = "Some output with no markers"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.LIKELY_SUCCESS
        assert result.confidence == 0.6
        assert "no explicit markers" in result.reason.lower()

    def test_exit_nonzero_only_likely_failed(self):
        """Non-zero exit alone is only likely failed."""
        output = "Some output with no markers"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.LIKELY_FAILED
        assert result.confidence == 0.6

    def test_no_signals_unknown(self):
        """No exit code and no markers is unknown."""
        output = "Some output"
        result = detect_outcome(output, exit_code=None)

        assert result.outcome == Outcome.UNKNOWN
        assert result.confidence == 0.0

    def test_multiple_success_markers(self):
        """Multiple success markers increase confidence."""
        output = "✓ Build successful\n✓ All tests passing\n<promise>COMPLETE</promise>"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.signals.has_success_marker
        assert result.signals.has_completion_signal

    def test_failure_overrides_success_markers(self):
        """Failure markers override success markers."""
        output = "✓ Build successful\nError: Test failed\nFAILED"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.FAILED
        # Success marker is still detected
        assert result.signals.has_success_marker
        # But failure marker takes priority
        assert result.signals.has_failure_marker

    def test_case_insensitive_markers(self):
        """Markers should be case-insensitive (mostly)."""
        output = "successfully completed the task"
        result = detect_outcome(output, exit_code=0)

        assert result.signals.has_success_marker

    def test_case_sensitive_promise_marker(self):
        """<promise> marker should be case-sensitive."""
        output = "<PROMISE>COMPLETE</PROMISE>"
        result = detect_outcome(output, exit_code=0)

        # Should not detect the completion signal (case mismatch)
        assert not result.signals.has_completion_signal

    def test_pytest_output_passed(self):
        """Detect pytest passing output."""
        output = """
============================= test session starts ==============================
platform linux -- Python 3.11
collected 50 items

test_app.py .................................................... [100%]

============================== 50 passed in 2.35s ==============================
"""
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.signals.tests_passed
        assert not result.signals.tests_failed

    def test_pytest_output_failed(self):
        """Detect pytest failing output."""
        output = """
============================= test session starts ==============================
collected 50 items

test_app.py ........F..F.....F................................ [100%]

FAILED test_app.py::test_something - AssertionError

============================== 3 failed, 47 passed in 4.12s ===================
"""
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.FAILED
        assert result.signals.tests_failed

    def test_jest_output_passed(self):
        """Detect Jest passing output."""
        output = """
PASS  src/app.test.ts
  ✓ should render correctly (45 ms)
  ✓ should handle click (12 ms)

Test Suites: 1 passed, 1 total
Tests:       15 passed, 15 total
"""
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.signals.tests_passed


class TestOutcomeResultProperties:
    """Tests for OutcomeResult properties."""

    def test_is_success_for_success_outcomes(self):
        """is_success returns True for success outcomes."""
        output = "<promise>COMPLETE</promise>"

        result = detect_outcome(output, exit_code=0)
        assert result.is_success

        result = detect_outcome("some output", exit_code=0)
        assert result.is_success  # LIKELY_SUCCESS is also success

    def test_is_failure_for_failure_outcomes(self):
        """is_failure returns True for failure outcomes."""
        result = detect_outcome("Error: failed", exit_code=1)
        assert result.is_failure

        result = detect_outcome("some output", exit_code=1)
        assert result.is_failure  # LIKELY_FAILED is also failure

    def test_needs_human_input(self):
        """needs_human_input only for NEEDS_DECISION."""
        result = detect_outcome("? Decision needed: which db?", exit_code=0)
        assert result.needs_human_input

        result = detect_outcome("success", exit_code=0)
        assert not result.needs_human_input


class TestParseTestResults:
    """Tests for parse_test_results function."""

    def test_parse_pytest_results(self):
        """Parse pytest-style results."""
        output = "============================== 47 passed, 3 failed in 4.12s ==============="
        results = parse_test_results(output)

        assert results["passed"] == 47
        assert results["failed"] == 3

    def test_parse_jest_results(self):
        """Parse Jest-style results."""
        output = "Tests: 10 passed, 2 failed, 1 skipped"
        results = parse_test_results(output)

        assert results["passed"] == 10
        assert results["failed"] == 2
        # Note: skipped detection may vary

    def test_parse_passing_only(self):
        """Parse output with only passing tests."""
        output = "15 tests passed"
        results = parse_test_results(output)

        assert results["passed"] == 15
        assert results["failed"] is None

    def test_parse_no_test_results(self):
        """Return None when no test results found."""
        output = "Building project..."
        results = parse_test_results(output)

        assert results["passed"] is None
        assert results["failed"] is None
        assert results["skipped"] is None

    def test_parse_mocha_style(self):
        """Parse Mocha-style results."""
        output = "20 passing (1.2s)\n2 failing"
        results = parse_test_results(output)

        assert results["passed"] == 20
        assert results["failed"] == 2


class TestDecisionQuestionExtraction:
    """Tests for decision question extraction."""

    def test_extract_decision_needed_format(self):
        """Extract from '? Decision needed: <question>' format."""
        output = "Working...\n? Decision needed: Should we use PostgreSQL or MySQL?"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert "PostgreSQL or MySQL" in result.decision_question

    def test_extract_blocked_format(self):
        """Extract from 'BLOCKED: <reason>' format."""
        output = "Analyzing...\nBLOCKED: Need AWS credentials to proceed"
        result = detect_outcome(output, exit_code=1)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert "AWS credentials" in result.decision_question

    def test_extract_should_i_format(self):
        """Extract from 'Should I <action>?' format."""
        output = "Found old config. Should I migrate the data?"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.NEEDS_DECISION
        assert "migrate" in result.decision_question.lower()

    def test_no_decision_question_when_none(self):
        """No decision_question when outcome is not NEEDS_DECISION."""
        output = "<promise>COMPLETE</promise>"
        result = detect_outcome(output, exit_code=0)

        assert result.outcome == Outcome.SUCCESS
        assert result.decision_question is None
