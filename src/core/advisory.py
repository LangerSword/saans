"""Advisory core: deterministic templates + the Bedrock prompt. Pure and offline.

THE INVARIANT, restated because this module is where it could be broken: the
tier and its action are decided by rules.py from measured bands. This module
only words and localizes that decision. It never changes it. If the model is
unavailable (quota, network, anything), the deterministic templates below
produce the same advisory in EN/HI/TE — the alert still goes out.

The HI/TE fallback translations are draft-grade: readable for a principal, and
marked as fallback-grade in the blog. The Bedrock path produces the polished
wording; the templates keep the demo safe when it cannot.
"""
from core import rules

LANGS = ("en", "hi", "te")

# Localized action strings per band; EN is single-sourced from rules.ACTIONS.
LOCALIZED_ACTIONS = {
    "hi": {
        "good": "सामान्य दिन।",
        "moderate": "संवेदनशील छात्र (अस्थमा) बाहर व्यायाम सीमित करें।",
        "poor": "खेल और भोजन-अवकाश घर के अंदर। बाहर सभा नहीं। मास्क की सलाह।",
        "very_poor": "केवल घर के अंदर। दिन छोटा करें या ऑनलाइन पढ़ाई। अभिभावकों को सूचित करें।",
        "severe": "स्कूल बंद या ऑनलाइन कक्षाओं की सिफारिश। प्रशासन को सूचित करें।",
    },
    "te": {
        "good": "సాధారణ రోజు.",
        "moderate": "సున్నితమైన విద్యార్థులు (ఆస్తమా) బయట వ్యాయామం తగ్గించాలి.",
        "poor": "ఆట మరియు విరామం లోపలే. బయట సభలు వద్దు. మాస్క్ సలహా.",
        "very_poor": "లోపలే ఉండాలి. రోజు తగ్గించండి లేదా ఆన్లైన్. తల్లిదండ్రులకు తెలియజేయండి.",
        "severe": "పాఠశాల మూసివేత లేదా ఆన్లైన్ తరగతులకు సిఫార్సు. అధికారులకు తెలియజేయండి.",
    },
}

# Fallback-grade translations of rules.ESTIMATE_DISCLAIMER.
DISCLAIMERS = {
    "en": rules.ESTIMATE_DISCLAIMER,
    "hi": "यह एक क्षेत्रीय मॉडल (~11 किमी) से अनुमान है, आपके स्कूल पर माप नहीं। "
          "स्थानीय रीडिंग के साथ अपने विवेक से उपयोग करें।",
    "te": "ఇది ప్రాంతీయ మోడల్ (~11 కిమీ) నుండి అంచనా, మీ పాఠశాల వద్ద కొలత కాదు. "
          "స్థానిక రీడింగ్‌తో పాటు మీ వివేకాన్ని ఉపయోగించండి.",
}


def template_advisory(band: str, lang: str) -> str:
    """Deterministic advisory in one language. Same source of truth as the API."""
    if lang == "en":
        return rules.advisory_text(band)          # action + ESTIMATE_DISCLAIMER
    action = LOCALIZED_ACTIONS.get(lang, {}).get(band)
    if action is None:
        # Unknown band or language -> fall back to EN so the principal still gets something.
        return rules.advisory_text(band)
    return f"{action} {DISCLAIMERS[lang]}"


def all_templates(band: str) -> dict:
    """The full EN/HI/TE bundle from templates alone."""
    return {lang: template_advisory(band, lang) for lang in LANGS}


SYSTEM_PROMPT = (
    "You write short school air-quality advisories for principals in India. "
    "You are given a band and its fixed action. You must NOT change the action's "
    "meaning or add new instructions — you only phrase it clearly and translate it. "
    "You reply with strict JSON only: {\"en\": \"...\", \"hi\": \"...\", \"te\": \"...\"}. "
    "Each value: the action sentence phrased warmly and clearly, in that language, "
    "plus one short sentence noting this is a modeled estimate (~11 km grid), not a "
    "measurement at the school."
)


def build_user_prompt(band: str, action_en: str, school_name: str, city: str) -> str:
    """The single user turn. Deterministic given its inputs (testable offline)."""
    return (
        f"Band: {band}\n"
        f"Fixed action (do not change its meaning): {action_en}\n"
        f"School: {school_name} ({city})\n"
        "Write the advisory in English, Hindi, and Telugu. Keep each to 2-3 short "
        "sentences. Return strict JSON with keys en, hi, te."
    )


def parse_model_json(text: str):
    """Extract the {en,hi,te} JSON from a model reply, or None on any doubt.

    Tolerates code fences and surrounding prose; requires all three keys to be
    non-empty strings. Returning None is the contract: the caller falls back to
    templates rather than shipping half-parsed text.
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):] if "{" in s else s
    lo, hi = s.find("{"), s.rfind("}")
    if lo == -1 or hi == -1 or hi <= lo:
        return None
    import json
    try:
        data = json.loads(s[lo:hi + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    for k in LANGS:
        v = data.get(k)
        if not isinstance(v, str) or not v.strip():
            return None
    return {k: data[k].strip() for k in LANGS}
