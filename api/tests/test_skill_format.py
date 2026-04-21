"""
test_skill_format.py — Unit tests for skill format() and parse helper functions.

All functions under test are pure (no I/O), so no mocking is needed.
These tests guard against silent regressions in the data transformation layer —
if format() changes structure, the LLM gets garbage context and produces wrong answers.
"""

import pytest
from app.skills import tech_news, cve, virustotal


# ── tech_news.format() ────────────────────────────────────────────────────────

class TestTechNewsFormat:
    def test_empty_list_returns_fallback(self):
        result = tech_news.format([])
        assert "No stories" in result

    def test_single_story_contains_title(self):
        stories = [{"title": "Python 4.0 Released", "score": 500,
                    "descendants": 200, "by": "guido", "url": "https://python.org"}]
        result = tech_news.format(stories)
        assert "Python 4.0 Released" in result

    def test_single_story_contains_score_and_comments(self):
        stories = [{"title": "Test", "score": 123, "descendants": 45,
                    "by": "author", "url": "https://example.com"}]
        result = tech_news.format(stories)
        assert "123" in result
        assert "45" in result

    def test_single_story_contains_author_and_url(self):
        stories = [{"title": "Test", "score": 1, "descendants": 0,
                    "by": "testauthor", "url": "https://test.com"}]
        result = tech_news.format(stories)
        assert "testauthor" in result
        assert "https://test.com" in result

    def test_story_missing_optional_fields_no_crash(self):
        # url and descendants are optional — should fall back gracefully
        stories = [{"title": "Minimal Story", "score": 10, "by": "user"}]
        result = tech_news.format(stories)
        assert "Minimal Story" in result

    def test_multiple_stories_all_included(self):
        stories = [
            {"title": f"Story {i}", "score": i, "descendants": 0,
             "by": "u", "url": "https://x.com"}
            for i in range(3)
        ]
        result = tech_news.format(stories)
        for i in range(3):
            assert f"Story {i}" in result


# ── cve._parse_cve() ──────────────────────────────────────────────────────────

class TestParseCve:
    def _make_cve(self, cve_id="CVE-2025-1234", metric_key="cvssMetricV31",
                  score=9.8, severity="CRITICAL", description="A critical bug."):
        return {
            "id": cve_id,
            "published": "2025-01-01T00:00:00",
            "descriptions": [{"lang": "en", "value": description}],
            "metrics": {
                metric_key: [{"cvssData": {"baseScore": score, "baseSeverity": severity}}]
            },
        }

    def test_v31_metrics_parsed(self):
        parsed = cve._parse_cve(self._make_cve())
        assert parsed["id"] == "CVE-2025-1234"
        assert parsed["score"] == 9.8
        assert parsed["severity"] == "CRITICAL"
        assert "critical bug" in parsed["description"].lower()

    def test_v2_fallback_when_v31_absent(self):
        raw = self._make_cve(metric_key="cvssMetricV2", score=7.5, severity="HIGH")
        parsed = cve._parse_cve(raw)
        assert parsed["score"] == 7.5
        assert parsed["severity"] == "HIGH"

    def test_no_metrics_returns_unknown(self):
        raw = {
            "id": "CVE-2025-9999",
            "descriptions": [{"lang": "en", "value": "No score yet."}],
            "metrics": {},
        }
        parsed = cve._parse_cve(raw)
        assert parsed["score"] is None
        assert parsed["severity"] == "UNKNOWN"

    def test_no_english_description_uses_default_fallback(self):
        # _parse_cve uses a literal fallback string when no English description exists
        raw = {
            "id": "CVE-2025-1111",
            "descriptions": [{"lang": "es", "value": "Vulnerabilidad crítica."}],
            "metrics": {},
        }
        parsed = cve._parse_cve(raw)
        assert parsed["description"] == "No description available."


# ── cve.format() ─────────────────────────────────────────────────────────────

class TestCveFormat:
    def test_empty_list_returns_fallback(self):
        result = cve.format([])
        assert "No CVEs" in result

    def test_critical_before_high_before_medium(self):
        cves = [
            {"id": "CVE-M", "severity": "MEDIUM",   "score": 5.0, "description": "medium"},
            {"id": "CVE-C", "severity": "CRITICAL",  "score": 9.8, "description": "critical"},
            {"id": "CVE-H", "severity": "HIGH",      "score": 7.5, "description": "high"},
        ]
        result = cve.format(cves)
        pos_c = result.index("CVE-C")
        pos_h = result.index("CVE-H")
        pos_m = result.index("CVE-M")
        assert pos_c < pos_h < pos_m

    def test_higher_score_first_within_same_severity(self):
        cves = [
            {"id": "CVE-LOW-SCORE",  "severity": "HIGH", "score": 7.0, "description": "low"},
            {"id": "CVE-HIGH-SCORE", "severity": "HIGH", "score": 8.9, "description": "high"},
        ]
        result = cve.format(cves)
        assert result.index("CVE-HIGH-SCORE") < result.index("CVE-LOW-SCORE")

    def test_cve_ids_present_in_output(self):
        cves = [{"id": "CVE-2025-4242", "severity": "LOW", "score": 2.0, "description": "minor"}]
        result = cve.format(cves)
        assert "CVE-2025-4242" in result


# ── virustotal._extract_target() ─────────────────────────────────────────────

class TestExtractTarget:
    def test_sha256_64_chars(self):
        sha256 = "a" * 64
        target, kind = virustotal._extract_target(f"scan {sha256}")
        assert target == sha256
        assert kind == "hash"

    def test_sha1_40_chars(self):
        sha1 = "b" * 40
        target, kind = virustotal._extract_target(f"check {sha1}")
        assert target == sha1
        assert kind == "hash"

    def test_md5_32_chars(self):
        md5 = "c" * 32
        target, kind = virustotal._extract_target(f"is {md5} safe?")
        assert target == md5
        assert kind == "hash"

    def test_sha256_prioritised_over_md5_substring(self):
        # The 64-char hash contains a 32-char substring — SHA-256 must win
        sha256 = "d" * 64
        target, kind = virustotal._extract_target(sha256)
        assert len(target) == 64
        assert kind == "hash"

    def test_url_extraction(self):
        target, kind = virustotal._extract_target("check https://evil.example.com/malware")
        assert target == "https://evil.example.com/malware"
        assert kind == "url"

    def test_url_trailing_comma_stripped(self):
        target, kind = virustotal._extract_target("go to https://example.com,")
        assert not target.endswith(",")

    def test_no_hash_or_url_returns_none(self):
        target, kind = virustotal._extract_target("is this file safe?")
        assert target is None
        assert kind is None


# ── virustotal._verdict() ────────────────────────────────────────────────────

class TestVerdict:
    def test_malicious(self):
        result = virustotal._verdict({"malicious": 3, "suspicious": 0, "harmless": 60, "undetected": 9})
        assert "MALICIOUS" in result
        assert "3" in result

    def test_suspicious_only(self):
        result = virustotal._verdict({"malicious": 0, "suspicious": 2, "harmless": 40, "undetected": 8})
        assert "SUSPICIOUS" in result

    def test_safe(self):
        result = virustotal._verdict({"malicious": 0, "suspicious": 0, "harmless": 70, "undetected": 2})
        assert "SAFE" in result


# ── virustotal._top_labels() ─────────────────────────────────────────────────

class TestTopLabels:
    def test_returns_up_to_5_labels(self):
        results = {
            f"engine_{i}": {"category": "malicious", "result": f"Trojan.{i % 3}"}
            for i in range(20)
        }
        labels = virustotal._top_labels(results, limit=5)
        assert len(labels) <= 5

    def test_sorted_by_frequency(self):
        results = {
            "e1": {"category": "malicious", "result": "Rare"},
            "e2": {"category": "malicious", "result": "Common"},
            "e3": {"category": "malicious", "result": "Common"},
        }
        labels = virustotal._top_labels(results)
        assert labels[0] == "Common"

    def test_ignores_non_malicious_engines(self):
        results = {
            "clean_engine": {"category": "harmless", "result": "Clean"},
            "bad_engine":   {"category": "malicious", "result": "Virus"},
        }
        labels = virustotal._top_labels(results)
        assert labels == ["Virus"]
        assert "Clean" not in labels


# ── virustotal.format() ───────────────────────────────────────────────────────

class TestVirusTotalFormat:
    def test_error_key_returns_error_string(self):
        result = virustotal.format({"error": "Not found in VirusTotal."})
        assert "VirusTotal lookup failed" in result
        assert "Not found" in result

    def test_full_result_contains_verdict(self):
        data = {
            "target": "a" * 64,
            "kind": "hash",
            "verdict": "MALICIOUS (3/72 engines flagged)",
            "stats": {"malicious": 3, "suspicious": 0, "harmless": 60, "undetected": 9},
            "labels": ["Trojan.GenericKD"],
            "scanned_at": "2025-01-01",
            "name": "evil.exe",
        }
        result = virustotal.format(data)
        assert "MALICIOUS" in result
        assert "evil.exe" in result
        assert "3" in result

    def test_full_result_contains_vt_url(self):
        data = {
            "target": "b" * 64,
            "kind": "hash",
            "verdict": "SAFE (0/72 engines flagged)",
            "stats": {"malicious": 0, "suspicious": 0, "harmless": 72, "undetected": 0},
            "labels": [],
            "scanned_at": "2025-01-01",
            "name": "safe.exe",
        }
        result = virustotal.format(data)
        assert "virustotal.com" in result
