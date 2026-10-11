"""Notify core tests: dedupe decision + email shape. Offline, pure."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import notify, seed  # noqa: E402

HOUR = 3600


class TestAlertDecision:
    def test_first_advisory_good_tier_does_not_alert(self):
        assert notify.alert_decision(None, 0, 1000)[0] is False

    def test_first_advisory_bad_tier_alerts(self):
        should, reason = notify.alert_decision(None, 2, 1000)
        assert should is True and reason == "first advisory"

    def test_no_change_no_alert(self):
        prev = {"tier": 2, "alerted_at": 1000}
        assert notify.alert_decision(prev, 2, 1000 + 100 * HOUR)[0] is False

    def test_escalation_bypasses_cooldown(self):
        """Air getting worse must alert immediately, even minutes after the last one."""
        prev = {"tier": 1, "alerted_at": 1000}
        should, reason = notify.alert_decision(prev, 2, 1000 + 60)
        assert should is True and reason == "escalation"

    def test_downgrade_within_cooldown_is_held(self):
        prev = {"tier": 2, "alerted_at": 1000}
        should, reason = notify.alert_decision(prev, 1, 1000 + 2 * HOUR)
        assert should is False and "cooldown" in reason

    def test_downgrade_after_cooldown_alerts(self):
        prev = {"tier": 2, "alerted_at": 1000}
        should, reason = notify.alert_decision(prev, 1, 1000 + 13 * HOUR)
        assert should is True and "cooldown elapsed" in reason

    def test_missing_alerted_at_is_treated_as_never_alerted(self):
        prev = {"tier": 3}
        should, _ = notify.alert_decision(prev, 1, 1000 + 13 * HOUR)
        assert should is True


class TestSnsMessage:
    def _item(self):
        return {
            "tier": 1, "band": "moderate", "source": "bedrock",
            "text": {"en": "EN text", "hi": "HI text", "te": "TE text"},
        }

    def test_subject_names_school_and_band(self):
        school = seed.SCHOOLS[0]
        subject, _ = notify.sns_message(school, self._item(), "https://saans.langersword.in")
        assert school["name"] in subject and "moderate" in subject

    def test_body_uses_the_school_language(self):
        hi_school = [s for s in seed.SCHOOLS if s["language"] == "hi"][0]
        _, body = notify.sns_message(hi_school, self._item(), "https://saans.langersword.in")
        assert "HI text" in body and "EN text" not in body

    def test_body_falls_back_to_english_when_lang_missing(self):
        school = dict(seed.SCHOOLS[0], language="fr")
        _, body = notify.sns_message(school, self._item(), "https://saans.langersword.in")
        assert "EN text" in body

    def test_body_carries_dashboard_and_disclaimer(self):
        _, body = notify.sns_message(seed.SCHOOLS[0], self._item(), "https://saans.langersword.in")
        assert "https://saans.langersword.in" in body
        assert "not measurements" in body
