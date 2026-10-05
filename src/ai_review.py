import json
import os
from pathlib import Path
import re
import urllib.request

import pandas as pd

ASSESSMENTS = {"supported", "probably_supported", "unsupported", "ambiguous"}
CODE_TO_REASON = {
    "DOA-REPL": "defect or dead on arrival",
    "LOST-TRANSIT": "lost or damaged delivery",
    "DUP-PAYMENT": "duplicate or failed payment",
    "CANCEL": "cancellation before dispatch",
    "PRICE-ADJ": "price or coupon adjustment",
    "RETURN-QC-OK": "returned product received and passed quality check",
    "WTY-BUYBACK": "warranty claim or buy-back",
    "GW-OTHER": "goodwill or another reason not represented by a dedicated code",
}
REASON_PATTERNS = {
    "Cancellation": r"\b(cancel(?:led|ed|lation)?|cancel ord|stop (?:the )?(?:shipment|dispatch)|change of mind|ordered by mistake)\b",
        "Cancellation": r"\b(cancel(?:led|ed|lation)?|cancel ord|don't ship|dont ship|stop (?:the )?(?:shipment|dispatch)|change of mind|ordered by mistake)\b",
    "Payment": r"(?s)\b(duplicate payment|charged twice|double charge|payment (?:failed|debited)|amount deducted|utr|gateway|paid.{0,20}no order|payment.{0,40}(?:no order|without an order)|payment went through|upi shows success)\b",
        "Payment": r"(?s)\b(duplicate payment|charged twice|charged two times|double charge|payment (?:failed|debited)|amount deducted|utr|gateway|paid.{0,20}no order|payment.{0,40}(?:no order|without an order)|payment went through|upi shows success)\b",
    "Transit": r"(?s)\b(lost in transit|undelivered|never arrived|tracking stuck|courier lost|empty (?:box|envelope)|damaged in transit|parcel damaged|crushed (?:box|packaging)|unit (?:received|rcvd) damaged|delivery delayed|delivery delay|stuck on shipped|out for delivery|(?:order|package|parcel).{0,30}(?:not received|never arrived)|haven't received (?:my )?order)\b",
    "Return": r"\b(reverse pickup|reverse pkp|money for (?:the )?return|return (?:was )?accepted|return pickup|return received|qc passed|picked up|pickup (?:missed|scheduled)|sent back|returned (?:the item|the product|the unit))\b",
    "Warranty": r"\b(warranty|\bwty\b|rma|dead on arrival|\bdoa\b|not charging|no charge|faulty|defect|buyback|battery drain|not working|crack(?:ed)?|pairing fails|not discoverable|intermittent disconnect|disconnects during calls|loses connection|losing connection|losing my phone|strap broke|strap pin issue)\b",
    "Price adjustment": r"\b(price drop|price difference|coupon|discount not applied|cashback|promo(?:tion)?)\b",
    "Goodwill": r"\b(goodwill|courtesy|appeasement|token credit|goodwill credit)\b",
}
REASON_CODE_PATTERNS = {
    "DOA-REPL": ("Warranty",),
    "LOST-TRANSIT": ("Transit",),
    "DUP-PAYMENT": ("Payment",),
    "CANCEL": ("Cancellation",),
    "PRICE-ADJ": ("Price adjustment",),
    "RETURN-QC-OK": ("Return",),
    "WTY-BUYBACK": ("Warranty",),
    "GW-OTHER": ("Goodwill",),
}


def _local_assessment(customer_message: str, agent_notes: str, reason_code: str) -> dict:
    message = "" if pd.isna(customer_message) else str(customer_message).lower()
    notes = "" if pd.isna(agent_notes) else str(agent_notes).lower()
    combined = f"{message} {notes}"
    evidence = [name for name, pattern in REASON_PATTERNS.items() if re.search(pattern, combined)]
    code = "" if pd.isna(reason_code) else str(reason_code).strip().upper()
    expected = REASON_CODE_PATTERNS.get(code)

    if not combined.strip() or not code:
        assessment, confidence = "ambiguous", 0.0
        likely_reason = evidence[0] if len(evidence) == 1 else "Unclear"
    elif len(evidence) > 1:
        message_evidence = any(re.search(REASON_PATTERNS[name], message) for name in evidence)
        note_evidence = any(re.search(REASON_PATTERNS[name], notes) for name in evidence)
        assessment, confidence = ("unsupported", 0.8) if code == "GW-OTHER" and message_evidence and note_evidence else ("ambiguous", 0.4)
        likely_reason = "; ".join(evidence)
    elif len(evidence) == 1:
        likely_reason = evidence[0]
        if expected and likely_reason in expected:
            found_in_message = bool(re.search(REASON_PATTERNS[likely_reason], message))
            found_in_notes = bool(re.search(REASON_PATTERNS[likely_reason], notes))
            assessment = "supported" if found_in_message and found_in_notes else "probably_supported"
            if code == "DUP-PAYMENT" and not found_in_notes:
                assessment = "ambiguous"
            weak_transit_terms = ("delivery delayed", "delivery delay", "out for delivery", "stuck on shipped")
            strong_transit_terms = ("lost in transit", "undelivered", "never arrived", "not received", "haven't received", "courier lost", "empty box", "empty envelope")
            if (
                likely_reason == "Transit"
                and code == "LOST-TRANSIT"
                and any(term in combined for term in weak_transit_terms)
                and not any(term in combined for term in strong_transit_terms)
            ):
                assessment = "probably_supported"
            confidence = 0.9 if assessment == "supported" else 0.72
        elif code == "GW-OTHER" and likely_reason == "Goodwill":
            assessment, confidence = "supported", 0.8
        elif code == "GW-OTHER":
            found_in_message = bool(re.search(REASON_PATTERNS[likely_reason], message))
            found_in_notes = bool(re.search(REASON_PATTERNS[likely_reason], notes))
            assessment = "unsupported" if found_in_notes else "ambiguous"
            confidence = 0.85 if assessment == "unsupported" else 0.4
        elif expected:
            assessment, confidence = "unsupported", 0.85
        else:
            assessment, confidence = "probably_supported", 0.6
    else:
        assessment, confidence, likely_reason = "ambiguous", 0.3, "Unclear"

    return {
        "assessment": assessment,
        "likely_reason": likely_reason,
        "confidence": confidence,
        "review_status": "Needs human review" if assessment in {"unsupported", "ambiguous"} else "Text supports code",
        "evidence_summary": f"Detected {', '.join(evidence)} in message/notes." if evidence else "No clear reason evidence found in the available text.",
        "reviewer": "local_rules",
    }


def _load_prompt(prompt_version: str) -> str:
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / f"refund_reason_{prompt_version}.txt"
    return prompt_path.read_text(encoding="utf-8")


def _gemini_assessment(customer_message: str, agent_notes: str, reason_code: str, api_key: str, prompt_version: str) -> dict:
    prompt = _load_prompt(prompt_version).format(
        reason_code=reason_code or "MISSING",
        reason_meaning=CODE_TO_REASON.get(str(reason_code or "").upper(), "unknown or missing"),
        customer_message=customer_message or "[blank]",
        agent_notes=agent_notes or "[blank]",
    )
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    parsed = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    if parsed.get("assessment") not in ASSESSMENTS:
        raise ValueError("Model returned an unsupported assessment label")
    confidence = float(parsed.get("confidence", 0))
    if not 0 <= confidence <= 1:
        raise ValueError("Model confidence must be between 0 and 1")
    return {
        "assessment": parsed["assessment"],
        "likely_reason": str(parsed.get("likely_reason", "Unclear")),
        "confidence": confidence,
        "review_status": "Needs human review" if parsed["assessment"] in {"unsupported", "ambiguous"} else "Text supports code",
        "evidence_summary": str(parsed.get("evidence_summary", "")),
        "reviewer": model,
    }


def review_refund_ticket(
    customer_message: str,
    agent_notes: str,
    reason_code: str,
    use_llm: bool = False,
    prompt_version: str = "v2",
) -> dict:
    """Assess whether ticket text supports a structured refund reason; never calculate money."""
    if use_llm and os.getenv("GEMINI_API_KEY"):
        try:
            return _gemini_assessment(
                customer_message,
                agent_notes,
                reason_code,
                os.environ["GEMINI_API_KEY"],
                prompt_version,
            )
        except Exception as exc:
            fallback = _local_assessment(customer_message, agent_notes, reason_code)
            fallback["reviewer"] = "local_rules (LLM unavailable)"
            fallback["llm_error"] = type(exc).__name__
            return fallback
    return _local_assessment(customer_message, agent_notes, reason_code)


def review_refund_frame(df, use_llm: bool = False, prompt_version: str = "v2"):
    """Attach text assessments to refund rows, keeping the source data unchanged."""
    refunds = df[df["is_refund"]].copy()
    assessments = [
        review_refund_ticket(row.customer_message, row.agent_notes, row.refund_reason_code, use_llm, prompt_version)
        for row in refunds.itertuples()
    ]
    return refunds.join(pd.DataFrame(assessments, index=refunds.index))
