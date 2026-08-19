"""Tests for the response validator."""

from __future__ import annotations

import pytest

from acdyon.ingestion.validator import ResponseValidator, detect_schema_drift


class TestResponseValidator:
    """Tests for ResponseValidator.validate_raw."""

    def _validator(self, **kwargs):
        return ResponseValidator(source_id="test", **kwargs)

    def test_valid_response_passes(self):
        raw = [{"id": "1", "title": "Dev", "company": "Acme", "url": "https://example.com"}]
        result = self._validator(
            min_items=1,
            required_keys=frozenset({"id", "title", "company", "url"}),
        ).validate_raw(raw)
        assert result.ok is True
        assert result.reason is None

    def test_empty_list_fails(self):
        result = self._validator(min_items=1).validate_raw([])
        assert result.ok is False
        assert "few items" in result.reason.lower()

    def test_non_list_fails(self):
        result = self._validator().validate_raw({"data": []})  # type: ignore[arg-type]
        assert result.ok is False
        assert "Expected list" in result.reason

    def test_missing_required_key_fails(self):
        raw = [{"id": "1", "title": "Dev"}]   # missing "url"
        result = self._validator(
            required_keys=frozenset({"id", "title", "url"}),
        ).validate_raw(raw)
        assert result.ok is False
        assert "url" in str(result.details.get("missing", []))

    def test_min_items_threshold(self):
        raw = [{"id": "1"}]
        assert self._validator(min_items=1).validate_raw(raw).ok is True
        assert self._validator(min_items=2).validate_raw(raw).ok is False

    def test_all_items_checked_for_keys(self):
        """The first item passes but the second is missing a key."""
        raw = [
            {"id": "1", "url": "https://a.com"},
            {"id": "2"},   # missing "url"
        ]
        result = self._validator(
            required_keys=frozenset({"id", "url"}),
        ).validate_raw(raw)
        assert result.ok is False


class TestBlockPageDetection:
    """Tests for ResponseValidator.validate_text_response."""

    def _validator(self):
        return ResponseValidator(source_id="test")

    def test_captcha_page_detected(self):
        html = "<html><title>Captcha Required</title><body>Are you human?</body></html>"
        result = self._validator().validate_text_response(html)
        assert result.ok is False

    def test_cloudflare_challenge_detected(self):
        html = "Just a moment... Ray ID: abc123"
        result = self._validator().validate_text_response(html)
        assert result.ok is False

    def test_normal_json_page_passes(self):
        # A normal response won't contain block phrases.
        text = '[{"id": "1", "position": "Engineer"}]'
        result = self._validator().validate_text_response(text)
        assert result.ok is True

    def test_access_denied_detected(self):
        html = "<html><body>403 Forbidden - Access Denied</body></html>"
        result = self._validator().validate_text_response(html)
        assert result.ok is False


class TestSchemaDriftDetection:
    """Tests for detect_schema_drift."""

    _BASE_FIELDS = {"source", "external_id", "title", "company", "url"}

    def _docs(self, **extra):
        base = {k: "value" for k in self._BASE_FIELDS}
        base.update(extra)
        return [base, base.copy()]

    def test_no_drift_when_all_fields_present(self):
        docs = self._docs()
        result = detect_schema_drift(docs, self._BASE_FIELDS, source_id="test")
        assert result.ok is True

    def test_drift_detected_when_field_missing(self):
        # Remove "company" from all docs.
        docs = [{k: "v" for k in self._BASE_FIELDS if k != "company"} for _ in range(3)]
        result = detect_schema_drift(docs, self._BASE_FIELDS, source_id="test")
        assert result.ok is False
        assert result.reason == "schema_drift"
        assert "company" in result.details.get("drifted", [])

    def test_no_drift_when_no_known_fields(self):
        """Empty known_fields snapshot → skip drift check."""
        result = detect_schema_drift(self._docs(), set(), source_id="test")
        assert result.ok is True

    def test_no_drift_when_no_docs(self):
        result = detect_schema_drift([], self._BASE_FIELDS, source_id="test")
        assert result.ok is True

    def test_minority_missing_does_not_trigger_drift(self):
        """Field missing from only 1 of 4 docs (< 50%) should not trigger drift."""
        good = {k: "v" for k in self._BASE_FIELDS}
        bad = {k: "v" for k in self._BASE_FIELDS if k != "company"}
        docs = [good, good, good, bad]
        result = detect_schema_drift(docs, self._BASE_FIELDS, source_id="test", sample_size=4)
        assert result.ok is True
