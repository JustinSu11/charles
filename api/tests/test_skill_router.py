"""
test_skill_router.py — Unit tests for the keyword-based skill routing logic.

All functions under test are pure Python with no I/O, so no mocking is needed.
These tests protect against silent regressions in routing that would cause
Charles to skip fetching live data (or fetch the wrong data) for every request.
"""

import pytest
from app.services.skill_router import (
    _should_fetch_news,
    _should_fetch_cve,
    _should_fetch_virustotal,
    route,
)


# ── _should_fetch_news ────────────────────────────────────────────────────────

class TestShouldFetchNews:
    # Direct source mentions
    def test_hacker_news_exact(self):
        assert _should_fetch_news("what's on hacker news") is True

    def test_hn_with_spaces(self):
        # The router checks " hn " (padded) so it doesn't match "python" etc.
        assert _should_fetch_news("any hn posts today") is True

    # "news" + context word combos
    def test_news_plus_tech(self):
        assert _should_fetch_news("any tech news?") is True

    def test_news_plus_latest(self):
        assert _should_fetch_news("latest news") is True

    def test_news_plus_today(self):
        assert _should_fetch_news("news today") is True

    def test_news_plus_dev(self):
        assert _should_fetch_news("dev news this week") is True

    # "news" alone — no context word → should NOT trigger
    def test_news_alone_false(self):
        assert _should_fetch_news("news") is False

    def test_sports_news_false(self):
        assert _should_fetch_news("sports news") is False

    # trending/latest tier
    def test_trending_with_tech(self):
        assert _should_fetch_news("what's trending in tech") is True

    def test_trending_with_ai(self):
        assert _should_fetch_news("trending in ai") is True

    def test_latest_programming(self):
        assert _should_fetch_news("latest programming news") is True

    # "trending" alone — no tech context → False
    def test_trending_alone_false(self):
        assert _should_fetch_news("what's trending") is False

    # Unrelated message
    def test_unrelated_false(self):
        assert _should_fetch_news("hello charles") is False


# ── _should_fetch_cve ─────────────────────────────────────────────────────────

class TestShouldFetchCve:
    # Tier 1 — direct CVE mention
    def test_cve_id_mention(self):
        assert _should_fetch_cve("show me cve-2025-1234") is True

    def test_cve_generic(self):
        assert _should_fetch_cve("any new cves?") is True

    def test_cve_uppercase(self):
        # router normalises to lowercase before calling
        assert _should_fetch_cve("cve") is True

    # Tier 2 — vuln vocab + context
    def test_vulnerability_latest(self):
        assert _should_fetch_cve("latest vulnerabilities") is True

    def test_exploit_recent(self):
        assert _should_fetch_cve("recent exploits") is True

    def test_zero_day_new(self):
        assert _should_fetch_cve("any new zero-day today?") is True

    # vuln vocab alone — no context word → False
    def test_vulnerability_alone_false(self):
        assert _should_fetch_cve("vulnerability") is False

    def test_patch_no_context_false(self):
        assert _should_fetch_cve("patch notes for the game") is False

    # Tier 3 — "security" + recency
    def test_security_advisory(self):
        assert _should_fetch_cve("latest security advisory") is True

    def test_security_recent(self):
        assert _should_fetch_cve("recent security news") is True

    # "security" alone — no recency word → False
    def test_security_alone_false(self):
        assert _should_fetch_cve("security") is False

    # Unrelated
    def test_unrelated_false(self):
        assert _should_fetch_cve("hello charles") is False


# ── _should_fetch_virustotal ──────────────────────────────────────────────────

class TestShouldFetchVirusTotal:
    # Tier 1 — direct name mention
    def test_virustotal_explicit(self):
        assert _should_fetch_virustotal("check virustotal for this") is True

    def test_virus_total_spaced(self):
        assert _should_fetch_virustotal("run a virus total scan") is True

    def test_vt_scan(self):
        assert _should_fetch_virustotal("vt scan this file") is True

    # Hash detection
    def test_md5_32_chars(self):
        md5 = "d" * 32
        assert _should_fetch_virustotal(f"is {md5} safe?") is True

    def test_sha1_40_chars(self):
        sha1 = "a" * 40
        assert _should_fetch_virustotal(f"check {sha1}") is True

    def test_sha256_64_chars(self):
        sha256 = "b" * 64
        assert _should_fetch_virustotal(f"scan {sha256}") is True

    def test_sha256_takes_priority_over_md5_substring(self):
        # A 64-char hex contains a 32-char sub-string — should still match
        sha256 = "c" * 64
        assert _should_fetch_virustotal(sha256) is True

    # Boundary: too short / too long → no match
    def test_31_chars_false(self):
        short = "e" * 31
        assert _should_fetch_virustotal(short) is False

    def test_65_chars_false(self):
        long_ = "f" * 65
        assert _should_fetch_virustotal(long_) is False

    # Intent words
    def test_malware_intent(self):
        assert _should_fetch_virustotal("is this malware?") is True

    def test_is_this_safe(self):
        assert _should_fetch_virustotal("is this safe to run?") is True

    # Unrelated
    def test_unrelated_false(self):
        assert _should_fetch_virustotal("hello charles") is False


# ── route() integration ───────────────────────────────────────────────────────

class TestRoute:
    def test_returns_empty_for_greeting(self):
        assert route("hello") == []

    def test_returns_tech_news_for_hn(self):
        result = route("what's on hacker news?")
        assert "tech_news" in result

    def test_returns_cve_for_vulnerabilities(self):
        result = route("any new cves today?")
        assert "cve" in result

    def test_returns_virustotal_for_hash(self):
        sha256 = "a" * 64
        result = route(f"scan {sha256}")
        assert "virustotal" in result

    def test_two_skills_activated_simultaneously(self):
        # A SHA-256 hash + mention of CVE → both skills activate
        sha256 = "9" * 64
        result = route(f"check cve and also scan this hash {sha256}")
        assert "cve" in result
        assert "virustotal" in result

    def test_all_returned_names_exist_in_skills(self):
        from app.skills import SKILLS
        result = route("hacker news latest cves " + "a" * 64)
        for name in result:
            assert name in SKILLS

    def test_input_normalized_to_lowercase(self):
        # Mixed-case input must route identically to lowercase
        assert route("HACKER NEWS") == route("hacker news")
        assert route("CVE-2025-0001") == route("cve-2025-0001")
