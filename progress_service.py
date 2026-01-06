from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import re

from openai import OpenAI
from flask import current_app
from config import Config
from extensions import db
from models import UserTopicMastery, ExamAttempt, ChatAnalysis, CoursePlan, ProgressAISummary

# Canonical subjects and default topic taxonomy
SUBJECTS = ["Deutsch", "Mathematik"]

DEFAULT_TOPICS = {
    "Deutsch": [
        # Textproduktion
        "Erzählung", "Bericht", "Beschreibung", "Brief",
        "Themenumsetzung", "Beobachtungen/Gefühle beschreiben", "Erlebnisse erzählen",
        "Ideenfindung", "Planung", "Formulierung", "Überarbeitung",
        # Textverständnis
        "Literarische Texte erfassen", "Sachtexte erfassen",
        "Fragen zu Inhalt", "Fragen zu Form und Absicht", "Realität vs. Fiktion",
        # Sprachbetrachtung
        "Sprachwirkung analysieren", "Wortschatz anwenden",
        "Wortbildung", "Wortarten", "Syntax", "Rechtschreibung"
    ],
    "Mathematik": [
        # Zahl und Variable
        "Natürliche Zahlen", "Brüche", "Dezimalzahlen",
        "Rechenoperationen", "Teilbarkeitsregeln", "Terme und Variablen", "Arithmetische Muster",
        # Form und Raum
        "Geometrische Grundbegriffe", "Konstruktionen", "Figuren und Körper",
        "Umfang", "Fläche", "Volumen", "Winkel und Dreiecke", "Koordinatensysteme", "Netze",
        # Grössen/Funktionen/Daten
        "Masseinheiten umrechnen", "Proportionalität",
        "Funktionen und Zuordnungen", "Kombinatorik",
        "Daten und Diagramme", "Mittelwerte und Streuung"
    ],
}

# Simple keyword hints to map free text to topics when LLM is unavailable
TOPIC_KEYWORDS = {
    "Deutsch": {
        "Erzählung": ["erzählung", "geschichte", "erzählen", "narrativ"],
        "Bericht": ["bericht", "berichten", "report", "sachlich"],
        "Beschreibung": ["beschreibung", "beschreiben", "merkmale"],
        "Brief": ["brief", "anschreiben", "leserbrief"],
        "Themenumsetzung": ["thema", "themenumsetzung"],
        "Beobachtungen/Gefühle beschreiben": ["beobachtung", "gefühl", "emotion", "wahrnehmung"],
        "Erlebnisse erzählen": ["erlebnis", "eigene erfahrung", "tagebucheintrag"],
        "Ideenfindung": ["ideenfindung", "brainstorming", "ideen", "thema finden"],
        "Planung": ["planung", "struktur", "gliederung", "aufbau"],
        "Formulierung": ["formulierung", "satzbau", "ausdruck", "stil"],
        "Überarbeitung": ["überarbeitung", "korrigieren", "revision", "verbessern"],
        "Literarische Texte erfassen": ["literarisch", "erzähler", "figur", "motiv", "stilmittel"],
        "Sachtexte erfassen": ["sachtext", "artikel", "bericht", "argumentation"],
        "Fragen zu Inhalt": ["inhalt", "kernaussage", "zusammenfassung"],
        "Fragen zu Form und Absicht": ["form", "absicht", "intention", "ziel", "textsorte"],
        "Realität vs. Fiktion": ["realität", "fiktion", "realistisch", "fiktiv"],
        "Sprachwirkung analysieren": ["sprachwirkung", "wirkung", "stilmittel", "metapher"],
        "Wortschatz anwenden": ["wortschatz", "wortfeld", "wortfamilie", "synonym", "antonym"],
        "Wortbildung": ["wortbildung", "präfix", "suffix", "stamm"],
        "Wortarten": ["wortarten", "nomen", "verb", "adjektiv", "pronomen", "adverb", "präposition", "konjunktion", "artikel"],
        "Syntax": ["syntax", "satzbau", "hauptsatz", "nebensatz", "satzglied", "subjekt", "prädikat", "objekt"],
        "Rechtschreibung": ["rechtschreibung", "komma", "gross", "klein", "orthografie", "s-ss-ß"],
    },
    "Mathematik": {
        "Natürliche Zahlen": ["natürliche zahlen", "ganze zahlen", "zahlenbereich"],
        "Brüche": ["bruch", "brüche", "bruchteile", "kürzen", "erweitern"],
        "Dezimalzahlen": ["dezimal", "kommazahl", "stellenwert"],
        "Rechenoperationen": ["addition", "subtraktion", "multiplikation", "division", "rechnen", "rechenregeln"],
        "Teilbarkeitsregeln": ["teilbarkeit", "teilbarkeitsregeln", "primzahlen", "ggt", "kgv"],
        "Terme und Variablen": ["term", "variablen", "ausklammern", "vereinfachen", "gleichung"],
        "Arithmetische Muster": ["muster", "folgen", "zahlenmuster"],
        "Geometrische Grundbegriffe": ["punkt", "strecke", "winkel", "kreis", "dreieck", "viereck", "grundbegriffe"],
        "Konstruktionen": ["konstruktion", "zirkel", "lineal", "konstruiere"],
        "Figuren und Körper": ["figur", "körper", "quader", "würfel", "prisma", "pyramide", "kegel", "kugel"],
        "Umfang": ["umfang", "perimeter", "randlänge"],
        "Fläche": ["fläche", "quadratzentimeter", "quadratmeter", "flächeninhalt"],
        "Volumen": ["volumen", "kubik", "inhalt", "räumlich"],
        "Winkel und Dreiecke": ["winkel", "dreieck", "pythagoras", "spitzer winkel", "rechter winkel", "stumpfer winkel"],
        "Koordinatensysteme": ["koordinatensystem", "koordinaten", "achsen"],
        "Netze": ["netz", "flächennetz"],
        "Masseinheiten umrechnen": ["masseinheiten", "umrechnen", "meter", "gramm", "liter", "zeit", "sekunden", "stunden"],
        "Proportionalität": ["proportional", "direkt proportional", "dreisatz", "verhältnis"],
        "Funktionen und Zuordnungen": ["funktion", "zuordnung", "x", "y", "tabelle", "graph"],
        "Kombinatorik": ["kombinatorik", "anzahl", "varianten", "möglichkeiten"],
        "Daten und Diagramme": ["daten", "diagramm", "säulendiagramm", "liniendiagramm", "kreisdiagramm"],
        "Mittelwerte und Streuung": ["mittelwert", "durchschnitt", "median", "modus", "spannweite", "streuung"],
    },
}


def _get_openai_client() -> OpenAI:
    api_key = getattr(Config, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


def _normalize_subject(s: str) -> Optional[str]:
    if not s:
        return None
    s_clean = s.strip().lower()
    for subj in SUBJECTS:
        if subj.lower().startswith(s_clean) or s_clean.startswith(subj.lower()):
            return subj
    # Basic guesses
    if "deu" in s_clean:
        return "Deutsch"
    if "mat" in s_clean:
        return "Mathematik"
    return None


def _fallback_topics_for_text(subject: str, text: str) -> List[str]:
    subject = subject if subject in DEFAULT_TOPICS else "Deutsch"
    found = set()
    lower = (text or "").lower()
    for topic, kws in TOPIC_KEYWORDS.get(subject, {}).items():
        for kw in kws:
            if kw in lower:
                found.add(topic)
                break
    return list(found) or DEFAULT_TOPICS[subject][:1]


def _bounded_int(n: float, lo: int = 0, hi: int = 100) -> int:
    try:
        return max(lo, min(hi, int(round(n))))
    except Exception:
        return 0


def _clean_json(s: str) -> str:
    # remove code fences if present
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s.strip(), flags=re.IGNORECASE).strip()
        if s.endswith("```"):
            s = s[: -3].strip()
    return s


def analyze_and_update_from_chat(
    user_id: int,
    session_id: int,
    message_id: int,
    message_text: str,
    conversation_history: Optional[str] = None,
) -> None:
    """
    Analyze a user chat message for subject/topic relevance and learning signal.
    Persists a ChatAnalysis row and updates per-topic mastery in UserTopicMastery.
    """
    subject: Optional[str] = None
    topics: List[str] = []
    relevance_score: float = 0.0
    learning_signal: str = "neutral"
    deltas: Dict[str, float] = {}
    summary: Optional[str] = None

    # Try OpenAI analysis
    try:
        client = _get_openai_client()
        sys = (
            "Du bist ein KI-Analyst für Lernfortschritt. "
            "Aufgabe: Analysiere die folgende Chat-Nachricht eines Schülers in Bezug auf die Gymiprüfung "
            "und gib eine JSON-Antwort mit Schlüsseln: subject ('Deutsch'|'Mathematik'|null), "
            "topics (Liste von bekannten Themen), relevance (0..1), learning_signal ('positive'|'neutral'|'negative'), "
            "deltas (Objekt: topic -> delta zwischen -25 und 25), summary (kurzer Satz). "
            "Wähle konservative, graduelle Anpassungen (typisch 2–8). "
            "Verwende grosse Sprünge (15–25) nur bei klarer, eindeutiger Evidenz für totale Kompetenz/Inkompetenz."
            "Wenn Themen unklar sind, ordne sie der besten Näherung zu."
        )
        usr = {
            "message": message_text,
            "history": (conversation_history or "")[:4000],
            "subjects": SUBJECTS,
            "topic_taxonomy": DEFAULT_TOPICS,
            "instructions": "Antworte ausschliesslich als gültiges JSON.",
        }
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(usr, ensure_ascii=False)},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(_clean_json(raw))

        subject = _normalize_subject(data.get("subject") or "")
        if not subject:
            # Guess subject via keywords
            lower = (message_text or "").lower()
            if any(k in lower for k in ["satz", "text", "aufsatz", "lesen", "grammatik"]):
                subject = "Deutsch"
            elif any(k in lower for k in ["rechnung", "winkel", "bruch", "funktion", "geometrie", "proportional"]):
                subject = "Mathematik"

        if not subject:
            # If still unclear, skip updating progress
            subject = "Deutsch"  # default

        topics = [t for t in (data.get("topics") or []) if isinstance(t, str)]
        if not topics:
            topics = _fallback_topics_for_text(subject, message_text)

        try:
            relevance_score = float(data.get("relevance", 0.0))
        except Exception:
            relevance_score = 0.0

        ls = str(data.get("learning_signal", "neutral")).lower()
        learning_signal = ls if ls in ("positive", "neutral", "negative") else "neutral"

        deltas_in = data.get("deltas") or {}
        if isinstance(deltas_in, dict):
            for k, v in deltas_in.items():
                try:
                    deltas[str(k)] = max(-25.0, min(25.0, float(v)))
                except Exception:
                    continue

        summary = data.get("summary", None)
    except Exception:
        # Heuristic fallback
        subject = subject or "Deutsch"
        topics = topics or _fallback_topics_for_text(subject, message_text)
        learning_signal = "positive" if any(w in (message_text or "").lower() for w in ["verstanden", "jetzt klar", "ah", "danke"]) else "neutral"
        relevance_score = 0.6 if topics else 0.2
        base_delta = 6.0 if learning_signal == "positive" else (3.0 if learning_signal == "neutral" else -5.0)
        deltas = {t: base_delta for t in topics}
        summary = "Relevante Lernaktivität erkannt." if relevance_score >= 0.5 else "Geringe Relevanz."

    # Persist ChatAnalysis
    try:
        analysis = ChatAnalysis(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            subject=subject or "Deutsch",
            topics_json=json.dumps(topics, ensure_ascii=False),
            relevance_score=relevance_score,
            learning_signal=learning_signal,
            delta_json=json.dumps(deltas, ensure_ascii=False),
            summary=summary or "",
        )
        db.session.add(analysis)
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Update mastery
    apply_mastery_deltas(user_id, subject or "Deutsch", deltas)
    # Auto-refresh AI summary (best-effort)
    try:
        refresh_ai_summary(user_id, subject or "Deutsch")
    except Exception:
        pass


def apply_mastery_deltas(user_id: int, subject: str, deltas: Dict[str, float]) -> None:
    if not deltas:
        return
    for topic, delta in deltas.items():
        try:
            row = UserTopicMastery.query.filter_by(user_id=user_id, subject=subject, topic=topic).first()
            if not row:
                row = UserTopicMastery(user_id=user_id, subject=subject, topic=topic, mastery=0, signals_count=0)
                db.session.add(row)
            d = max(-25.0, min(25.0, float(delta)))
            new_val = _bounded_int((row.mastery or 0) + d)
            row.mastery = new_val
            row.signals_count = (row.signals_count or 0) + 1
            row.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()


def get_progress_for_user(user_id: int, subject: str) -> Dict:
    subject = _normalize_subject(subject) or "Deutsch"
    # Topics: return rows; if none exist, return defaults with 0 mastery
    rows = UserTopicMastery.query.filter_by(user_id=user_id, subject=subject).all()
    if not rows:
        topics = [{"name": t, "mastery": 0} for t in DEFAULT_TOPICS[subject]]
    else:
        topics = [{"name": r.topic, "mastery": int(r.mastery or 0)} for r in rows]

    # Exams
    attempts = ExamAttempt.query.filter_by(user_id=user_id, subject=subject).order_by(ExamAttempt.created_at.asc()).all()
    exams = []
    for a in attempts:
        if a.grade is None:
            continue  # Skip ungraded attempts to avoid NaN in frontend metrics
        exams.append({
            "grade": float(a.grade),
            "timestamp": int(a.created_at.timestamp() * 1000),
            "exam_filename": a.exam_filename or "",
        })

    return {"topics": topics, "exams": exams}


def set_topics_for_user(user_id: int, subject: str, topics: List[Dict]) -> None:
    """
    Upsert topic masteries for a user/subject.
    topics: [{name: str, mastery: int}]
    """
    subject = _normalize_subject(subject) or "Deutsch"
    for t in topics:
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        mastery = _bounded_int(t.get("mastery") if isinstance(t.get("mastery"), (int, float)) else 0)
        try:
            row = UserTopicMastery.query.filter_by(user_id=user_id, subject=subject, topic=name).first()
            if not row:
                row = UserTopicMastery(user_id=user_id, subject=subject, topic=name, mastery=mastery, signals_count=0)
                db.session.add(row)
            else:
                row.mastery = mastery
                row.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()


    # After bulk upsert, refresh AI summary (best-effort)
    try:
        refresh_ai_summary(user_id, subject)
    except Exception:
        pass


def seed_user_topics(user_id: int) -> None:
    """
    Create missing topic rows at 0% mastery for all default topics across both subjects.
    Safe to call multiple times (idempotent).
    """
    try:
        for subject in SUBJECTS:
            existing = UserTopicMastery.query.filter_by(user_id=user_id, subject=subject).all()
            existing_names = {r.topic for r in existing}
            missing = [t for t in DEFAULT_TOPICS.get(subject, []) if t not in existing_names]
            if not missing:
                continue
            for t in missing:
                db.session.add(UserTopicMastery(
                    user_id=user_id,
                    subject=subject,
                    topic=t,
                    mastery=0,
                    signals_count=0,
                    updated_at=datetime.utcnow()
                ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def ai_progress_summary(user_id: int, subject: str, topics: List[Dict], exams: List[Dict]) -> Dict[str, List[str]]:
    subject = _normalize_subject(subject) or "Deutsch"
    # Try OpenAI
    try:
        client = _get_openai_client()
        sys = (
            "Du bist ein KI-Tutor-Analyst. Erzeuge eine kurze, umsetzbare Analyse des Lernstands "
            "als JSON mit Schlüsseln: strengths (string[]), weaknesses (string[]), tips (string[]). "
            "Sprache: Deutsch. Beziehe dich auf das Fach und die Themen."
        )
        usr = {
            "subject": subject,
            "topics": topics,
            "exams": exams,
            "note": "Antworte ausschliesslich als gültiges JSON ohne Erklärtext.",
        }
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(usr, ensure_ascii=False)},
            ],
            max_tokens=400,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(_clean_json(raw))
        strengths = data.get("strengths") or []
        weaknesses = data.get("weaknesses") or []
        tips = data.get("tips") or []
        return {
            "strengths": [str(s) for s in strengths],
            "weaknesses": [str(w) for w in weaknesses],
            "tips": [str(t) for t in tips],
        }
    except Exception:
        # Fallback heuristic
        strong = [t["name"] for t in topics if (t.get("mastery") or 0) >= 75]
        weak = [t["name"] for t in topics if (t.get("mastery") or 0) < 50]
        tips = []
        if weak:
            tips.append(f"Konzentriere dich auf: {', '.join(weak[:3])}.")
        if strong:
            tips.append(f"Vertiefe deine Stärken: {', '.join(strong[:3])}.")
        # Grade hint
        grades = [e["grade"] for e in exams if e.get("grade") is not None]
        if grades:
            avg = sum(grades) / len(grades)
            tips.append(f"Aktueller Ø aus Simulationen: {avg:.1f}. Starte regelmässig neue Simulationen.")
        return {"strengths": strong, "weaknesses": weak, "tips": tips}


def parse_grade_from_feedback(feedback_html: str) -> Optional[float]:
    if not feedback_html:
        return None
    text = re.sub(r"<[^>]+>", " ", feedback_html)  # strip html tags
    # Look for explicit "Gesamtbewertung" or "Note"
    m = re.search(r"(Gesamtbewertung|Note)\D{0,10}([1-6](?:[.,]\d)?)", text, flags=re.IGNORECASE)
    if m:
        val = m.group(2).replace(",", ".")
        try:
            g = float(val)
            if 1.0 <= g <= 6.0:
                return g
        except Exception:
            pass
    # Fallback: find any 1-6 float-ish number; choose last one
    nums = re.findall(r"\b([1-6](?:[.,]\d)?)\b", text)
    for n in reversed(nums):
        try:
            g = float(n.replace(",", "."))
            if 1.0 <= g <= 6.0:
                return g
        except Exception:
            continue
    return None


def _infer_topics_from_feedback(subject: str, feedback_html: str) -> List[str]:
    text = (re.sub(r"<[^>]+>", " ", feedback_html) or "").lower()
    subject = subject if subject in DEFAULT_TOPICS else "Deutsch"
    found = set()
    for topic, kws in TOPIC_KEYWORDS.get(subject, {}).items():
        for kw in kws:
            if kw in text:
                found.add(topic)
                break
    return list(found) or DEFAULT_TOPICS[subject]


def handle_exam_feedback_and_update(
    user_id: int,
    subject: str,
    exam_filename: Optional[str],
    feedback_html: str,
) -> None:
    subject = _normalize_subject(subject) or "Deutsch"
    grade = parse_grade_from_feedback(feedback_html)

    # Persist attempt
    try:
        attempt = ExamAttempt(
            user_id=user_id,
            subject=subject,
            exam_filename=exam_filename or "",
            grade=grade,
            feedback=feedback_html or "",
            created_at=datetime.utcnow(),
        )
        db.session.add(attempt)
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Adjust mastery based on grade and topic hints in feedback
    topics = _infer_topics_from_feedback(subject, feedback_html)
    deltas: Dict[str, float] = {}
    if grade is not None:
        # Map grade 1..6 to overall delta with stronger scaling; clamp safely
        if grade >= 5.5:
            delta_base = 18.0
        elif grade <= 2.0:
            delta_base = -18.0
        else:
            delta_base = (grade - 3.5) * 5.0  # roughly -12.5 .. +12.5
    else:
        delta_base = 3.0  # small positive for completion

    # Distribute across inferred topics
    if topics:
        per = max(-18.0, min(18.0, delta_base))
        share = per / max(1, len(topics))
        for t in topics:
            deltas[t] = share
    else:
        # Apply to a generic default topic
        deltas[DEFAULT_TOPICS[subject][0]] = max(-12.0, min(12.0, delta_base))

    apply_mastery_deltas(user_id, subject, deltas)
    # Auto-refresh AI summary (best-effort)
    try:
        refresh_ai_summary(user_id, subject)
    except Exception:
        pass


def get_compact_progress_snapshot(user_id: int) -> Dict:
    """
    Compact snapshot of progress for prompt context. Keep small.
    Structure:
    {
      "Deutsch": {"topics": [{"n":"...", "m": 0..100}, ...], "exams": {"cnt": n, "avg": 4.2, "last": 4.5, "trend": [..]}},
      "Mathematik": {...}
    }
    """
    snapshot: Dict[str, Dict] = {}
    for subject in SUBJECTS:
        # Topics
        rows = UserTopicMastery.query.filter_by(user_id=user_id, subject=subject).all()
        if rows:
            topics = sorted(
                [{"n": r.topic, "m": int(r.mastery or 0)} for r in rows],
                key=lambda x: x["n"].lower()
            )[:12]  # cap to 12 topics
        else:
            topics = [{"n": t, "m": 0} for t in DEFAULT_TOPICS[subject]]

        # Exams
        attempts = ExamAttempt.query.filter_by(user_id=user_id, subject=subject).order_by(ExamAttempt.created_at.asc()).all()
        grades = [float(a.grade) for a in attempts if a.grade is not None]
        cnt = len(grades)
        avg = round(sum(grades) / cnt, 2) if cnt else None
        last = grades[-1] if cnt else None
        trend = grades[-5:] if cnt else []
        snapshot[subject] = {
            "topics": topics,
            "exams": {"cnt": cnt, "avg": avg, "last": last, "trend": trend}
        }
    return snapshot


def ai_suggest_progress_updates(
    user_id: int,
    user_text: str,
    bot_text: str,
    conversation_history: Optional[str] = None,
) -> None:
    """
    Ask the AI to propose small topic mastery updates based on interaction quality.
    Expected JSON:
    {
      "updates": [
        {"subject": "Mathematik", "topic": "Form und Raum", "op": "delta", "value": 2, "reason": "..."},
        {"subject": "Deutsch", "topic": "Textverständnis", "op": "set", "value": 60, "reason": "..."}
      ]
    }
    """
    try:
        snapshot = get_compact_progress_snapshot(user_id)
        client = _get_openai_client()
        sys = (
            "Rolle: Tutor-Analyst. Aufgabe: Schlage vorsichtige Aktualisierungen für den Themen-Fortschritt vor. "
            "Gib AUSSCHLIESSLICH JSON mit Schlüssel 'updates' zurück. Jede Aktualisierung: "
            "{subject: 'Deutsch'|'Mathematik', topic: string, op: 'delta'|'set', value: number, reason: string}. "
            "Regeln: "
            "- delta: -25..+25 (in Prozentpunkten). Bevorzuge kleine Schritte (typisch 2–8). "
            "- Verwende grosse Sprünge (15–25) nur bei klarer, eindeutiger Evidenz für totale Kompetenz/Inkompetenz. "
            "- set: 0..100 NUR wenn du dir sicher bist (selten); ansonsten 'delta' bevorzugen. "
            "- Maximal 5 Updates. "
            "- Wenn unklar, gib leere Liste zurück."
        )
        usr = {
            "snapshot": snapshot,
            "conversation_history": (conversation_history or "")[:4000],
            "user_message": (user_text or "")[:2000],
            "assistant_reply": (bot_text or "")[:2000],
            "taxonomy": DEFAULT_TOPICS,
        }
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(usr, ensure_ascii=False)},
            ],
            max_tokens=400,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(_clean_json(raw))
        updates = data.get("updates") or []
        if not isinstance(updates, list):
            return
    except Exception:
        return

    # Apply updates
    by_subject: Dict[str, Dict[str, float]] = {}
    sets_by_subject: Dict[str, List[Dict]] = {}
    for up in updates:
        try:
            subj = _normalize_subject(up.get("subject") or "")
            if not subj:
                continue
            topic = str(up.get("topic") or "").strip()
            if not topic:
                continue
            op = (up.get("op") or "delta").lower()
            val = float(up.get("value"))
            if op == "delta":
                if subj not in by_subject:
                    by_subject[subj] = {}
                # clamp delta -25..+25
                d = max(-25.0, min(25.0, val))
                by_subject[subj][topic] = d
            elif op == "set":
                if subj not in sets_by_subject:
                    sets_by_subject[subj] = []
                sets_by_subject[subj].append({"name": topic, "mastery": _bounded_int(val, 0, 100)})
        except Exception:
            continue

    # Apply deltas
    for subj, deltas in by_subject.items():
        apply_mastery_deltas(user_id, subj, deltas)

    # Apply sets
    for subj, topics in sets_by_subject.items():
        set_topics_for_user(user_id, subj, topics)


# --- Course planning and analyses helpers ---

def _compute_weeks_until(target_date: Optional[str]) -> int:
    """
    Compute number of weeks until target_date (YYYY-MM-DD). Default to 4 if invalid.
    """
    try:
        if not target_date:
            return 4
        from datetime import datetime as _dt
        d = _dt.strptime(target_date, "%Y-%m-%d").date()
        today = _dt.utcnow().date()
        days = (d - today).days
        if days <= 7:
            return 1
        return min(16, max(4, days // 7))
    except Exception:
        return 4


def generate_course_plan(user_id: int, subject: str, goals: Optional[str], target_date: Optional[str]) -> Dict:
    """
    Generate a course plan (JSON) prioritizing weak topics based on mastery and goals.
    Returns a dict plan with keys: title, weeks, modules: [{week, focus_topics, objectives, activities, resources}...]
    """
    subject = _normalize_subject(subject) or "Deutsch"
    progress = get_progress_for_user(user_id, subject)
    topics = progress.get("topics", [])
    exams = progress.get("exams", [])
    weeks = _compute_weeks_until(target_date)
    weak = [t["name"] for t in sorted(topics, key=lambda x: x.get("mastery", 0)) if (t.get("mastery") or 0) < 50][:6]
    medium = [t["name"] for t in topics if 50 <= (t.get("mastery") or 0) < 75][:6]
    strong = [t["name"] for t in topics if (t.get("mastery") or 0) >= 75][:6]

    # Try OpenAI
    try:
        client = _get_openai_client()
        sys = (
            "Rolle: Kursplaner für Gymiprüfung. "
            "Erzeuge einen kompakten Kursplan als JSON: "
            "{title: string, weeks: number, modules: [{week: number, focus_topics: string[], objectives: string[], activities: string[], resources: string[]}]} "
            "Regeln: "
            f"Weeks = {weeks}. Priorisiere schwache Themen zuerst, dann mittlere, dann starke. "
            "Realistisch und umsetzbar. Sprache: Deutsch. Keine Erklärtexte ausser JSON."
        )
        usr = {
            "subject": subject,
            "goals": goals or "",
            "weeks": weeks,
            "weak_topics": weak,
            "medium_topics": medium,
            "strong_topics": strong,
            "exams": exams[-5:],
            "taxonomy": DEFAULT_TOPICS[subject],
        }
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(usr, ensure_ascii=False)},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        plan = json.loads(_clean_json(raw))
        if not isinstance(plan, dict) or "modules" not in plan:
            raise ValueError("Invalid plan JSON")
        return plan
    except Exception:
        # Fallback heuristic plan
        modules = []
        pool = weak + medium + strong
        pool = pool[:max(weeks * 2, 4)]
        for w in range(1, weeks + 1):
            focus = pool[(w - 1) * 2: (w - 1) * 2 + 2] or pool[:2] or DEFAULT_TOPICS[subject][:2]
            modules.append({
                "week": w,
                "focus_topics": focus,
                "objectives": [
                    f"Sichere Grundlagen in: {focus[0]}" if focus else "Grundlagen sichern",
                    f"Anwendungsaufgaben zu: {', '.join(focus)}" if focus else "Anwendungen üben",
                ],
                "activities": [
                    "Tägliche 30–45 Min. Übungssession",
                    "1 Prüfungsaufgabe am Stück (Simulation light)",
                    "Fehleranalyse und Wiederholung",
                ],
                "resources": [
                    "Eigene Notizen/Fehlerliste",
                    "Aufgaben aus alten ZAPs",
                    "Kurze Theoriezusammenfassung",
                ],
            })
        title = f"Kursplan {subject}: {'Schwerpunkte' if weak else 'Wiederholung'}"
        return {"title": title, "weeks": weeks, "modules": modules}


def create_course_plan(user_id: int, subject: str, title: str, plan_dict: Dict) -> Dict:
    subject = _normalize_subject(subject) or "Deutsch"
    try:
        cp = CoursePlan(
            user_id=user_id,
            subject=subject,
            title=title or plan_dict.get("title") or f"Kursplan {subject}",
            plan_json=json.dumps(plan_dict, ensure_ascii=False),
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(cp)
        db.session.commit()
        return {"id": cp.id, "subject": cp.subject, "title": cp.title, "status": cp.status, "plan": plan_dict}
    except Exception:
        db.session.rollback()
        raise


def list_course_plans(user_id: int) -> List[Dict]:
    items = CoursePlan.query.filter_by(user_id=user_id).order_by(CoursePlan.created_at.desc()).all()
    out: List[Dict] = []
    for i in items:
        try:
            plan = json.loads(i.plan_json or "{}")
        except Exception:
            plan = {}
        out.append({
            "id": i.id,
            "subject": i.subject,
            "title": i.title,
            "status": i.status,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "updated_at": i.updated_at.isoformat() if i.updated_at else None,
            "plan": plan,
        })
    return out


def refresh_ai_summary(user_id: int, subject: str) -> Dict[str, List[str]]:
    """
    Compute AI progress analysis for the given user/subject from current topics and exams,
    persist it in ProgressAISummary, and return it.
    """
    subject_norm = _normalize_subject(subject) or "Deutsch"
    prog = get_progress_for_user(user_id, subject_norm)
    topics = prog.get("topics") or []
    exams = prog.get("exams") or []
    data = ai_progress_summary(user_id, subject_norm, topics, exams)
    try:
        row = ProgressAISummary.query.filter_by(user_id=user_id, subject=subject_norm).first()
        if not row:
            row = ProgressAISummary(
                user_id=user_id,
                subject=subject_norm,
                strengths_json=json.dumps(data.get("strengths") or [], ensure_ascii=False),
                weaknesses_json=json.dumps(data.get("weaknesses") or [], ensure_ascii=False),
                tips_json=json.dumps(data.get("tips") or [], ensure_ascii=False),
                updated_at=datetime.utcnow(),
            )
            db.session.add(row)
        else:
            row.strengths_json = json.dumps(data.get("strengths") or [], ensure_ascii=False)
            row.weaknesses_json = json.dumps(data.get("weaknesses") or [], ensure_ascii=False)
            row.tips_json = json.dumps(data.get("tips") or [], ensure_ascii=False)
            row.updated_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return {
        "strengths": data.get("strengths") or [],
        "weaknesses": data.get("weaknesses") or [],
        "tips": data.get("tips") or [],
    }


def get_ai_summary(user_id: int, subject: str) -> Dict[str, List[str]]:
    """
    Return the latest stored AI summary; if none exists, compute and persist it.
    """
    subject_norm = _normalize_subject(subject) or "Deutsch"
    try:
        row = ProgressAISummary.query.filter_by(user_id=user_id, subject=subject_norm).first()
        if row:
            try:
                strengths = json.loads(row.strengths_json or "[]")
            except Exception:
                strengths = []
            try:
                weaknesses = json.loads(row.weaknesses_json or "[]")
            except Exception:
                weaknesses = []
            try:
                tips = json.loads(row.tips_json or "[]")
            except Exception:
                tips = []
            return {"strengths": strengths, "weaknesses": weaknesses, "tips": tips}
    except Exception:
        pass
    # If missing or failed, compute fresh and persist
    return refresh_ai_summary(user_id, subject_norm)


def get_course_plan(user_id: int, plan_id: int) -> Optional[Dict]:
    item = CoursePlan.query.filter_by(user_id=user_id, id=plan_id).first()
    if not item:
        return None
    try:
        plan = json.loads(item.plan_json or "{}")
    except Exception:
        plan = {}
    return {
        "id": item.id,
        "subject": item.subject,
        "title": item.title,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "plan": plan,
    }


def update_course_plan(user_id: int, plan_id: int, patch: Dict) -> Optional[Dict]:
    item = CoursePlan.query.filter_by(user_id=user_id, id=plan_id).first()
    if not item:
        return None
    try:
        status = patch.get("status")
        if status:
            item.status = str(status)
        plan_patch = patch.get("plan")
        if isinstance(plan_patch, dict):
            try:
                current = json.loads(item.plan_json or "{}")
            except Exception:
                current = {}
            # shallow merge for simplicity
            current.update(plan_patch)
            item.plan_json = json.dumps(current, ensure_ascii=False)
        item.updated_at = datetime.utcnow()
        db.session.commit()
        return get_course_plan(user_id, plan_id)
    except Exception:
        db.session.rollback()
        raise


def get_recent_chat_analyses(user_id: int, subject: Optional[str] = None, limit: int = 50) -> List[Dict]:
    q = ChatAnalysis.query.filter_by(user_id=user_id)
    if subject:
        subj = _normalize_subject(subject)
        if subj:
            q = q.filter(ChatAnalysis.subject == subj)
    rows = q.order_by(ChatAnalysis.created_at.desc()).limit(max(1, min(200, int(limit)))).all()
    out = []
    for r in rows:
        try:
            topics = json.loads(r.topics_json or "[]")
            deltas = json.loads(r.delta_json or "{}")
        except Exception:
            topics = []
            deltas = {}
        out.append({
            "id": r.id,
            "session_id": r.session_id,
            "message_id": r.message_id,
            "subject": r.subject,
            "topics": topics,
            "relevance": r.relevance_score,
            "learning_signal": r.learning_signal,
            "deltas": deltas,
            "summary": r.summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out