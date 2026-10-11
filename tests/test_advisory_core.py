"""Advisory core tests: templates, prompt, parser. Offline — no boto3, no Bedrock."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import advisory, rules  # noqa: E402


class TestTemplates:
    def test_en_template_is_the_same_source_as_the_api(self):
        """EN advisory must equal rules.advisory_text — one source of truth."""
        for band in rules.ACTIONS:
            assert advisory.template_advisory(band, "en") == rules.advisory_text(band)

    def test_all_langs_present_and_readable_for_every_band(self):
        for band in rules.ACTIONS:
            t = advisory.all_templates(band)
            assert set(t) == {"en", "hi", "te"}
            for lang, text in t.items():
                assert isinstance(text, str) and len(text) > 10, f"{band}/{lang}"

    def test_hi_te_are_actually_localized(self):
        t = advisory.all_templates("poor")
        assert t["hi"] != t["en"] and t["te"] != t["en"]
        assert any("\u0900" <= c <= "\u097f" for c in t["hi"]), "hi lacks Devanagari"
        assert any("\u0c00" <= c <= "\u0c7f" for c in t["te"]), "te lacks Telugu script"

    def test_every_lang_carries_a_disclaimer(self):
        for lang, text in advisory.all_templates("severe").items():
            assert len(text.split("।")) > 1 or "." in text  # multi-sentence
            # each translation must mention it is an estimate/not a measurement
            assert any(k in text for k in ("अनुमान", "అంచనా", "estimate")), lang

    def test_unknown_band_falls_back_to_english_moderate(self):
        t = advisory.template_advisory("not_a_band", "hi")
        assert rules.ACTIONS["moderate"] in t


class TestParser:
    VALID = '{"en": "Wear a mask.", "hi": "मास्क पहनें।", "te": "మాస్క్ ధరించండి."}'

    def test_plain_json(self):
        assert advisory.parse_model_json(self.VALID)["en"] == "Wear a mask."

    def test_code_fenced_json(self):
        assert advisory.parse_model_json(f"```json\n{self.VALID}\n```") is not None

    def test_prose_wrapped_json(self):
        assert advisory.parse_model_json(f"Here you go: {self.VALID} Hope that helps!") is not None

    def test_missing_key_returns_none(self):
        assert advisory.parse_model_json('{"en": "x", "hi": "y"}') is None

    def test_empty_value_returns_none(self):
        assert advisory.parse_model_json('{"en": "x", "hi": " ", "te": "z"}') is None

    def test_non_string_value_returns_none(self):
        assert advisory.parse_model_json('{"en": 1, "hi": "y", "te": "z"}') is None

    def test_garbage_returns_none(self):
        assert advisory.parse_model_json("no json at all") is None
        assert advisory.parse_model_json(None) is None


class TestPrompt:
    def test_prompt_carries_action_school_and_languages(self):
        p = advisory.build_user_prompt("poor", rules.ACTIONS["poor"], "DPS Mathura Road", "Delhi")
        assert rules.ACTIONS["poor"] in p
        assert "DPS Mathura Road" in p
        assert "English" in p and "Hindi" in p and "Telugu" in p

    def test_system_prompt_forbids_changing_the_action(self):
        assert "NOT change" in advisory.SYSTEM_PROMPT
