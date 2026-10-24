# Gymiboost

**An AI tutoring platform for the Zurich Gymiprüfung, built as my Maturarbeit (graded 5.5 / 6).**

📄 **Paper (German):** [Luka_Simonovic_Maturitaetsarbeit_RAG.pdf](Luka_Simonovic_Maturitaetsarbeit_RAG.pdf)

## In English

**Title:** *Knowledge Integration in AI Tutoring Systems: The Influence of Retrieval-Augmented Generation on the Answer Quality of AI Models* (Kantonsschule Zürcher Unterland, 2025/2026)

**Research question:** Can a single developer design and build a RAG-based web app that gives hallucination-free, exam-specific help for the ZAP, the central entrance exam for the Langgymnasium (academic high school) in the canton of Zurich, and can the technical and architectural hurdles be overcome with limited resources?

**Answer:** Yes, with clear limits. Retrieval over a database of past ZAP exams let the tutor correctly walk through specific old exam problems (e.g. "solution for task 3, ZAP 2022") that a standard chatbot couldn't answer, and it greatly reduced hallucinations. Handwriting recognition with open-source OCR was the main goal that wasn't reached.

**What I built** (solo, March–August 2025, roughly 400 hours):

- A streaming AI tutor chat with retrieval-augmented generation over past exams (ChromaDB)
- Document upload with OCR (Tesseract) so students can ask about their own material
- An AI task generator that creates practice sheets by topic and difficulty, with separate solution sheets
- Timed exam simulations with AI grading and feedback
- Auto-generated interactive courses with quizzes, polls and spaced-repetition flashcards
- Progress tracking, streaks and XP
- User accounts and Stripe subscriptions

**Stack:** Python, Flask, SQLAlchemy, ChromaDB, Tesseract OCR, OpenAI API, Jinja templates, vanilla JS, MathJax, Stripe.

The paper covers the development process, the RAG architecture, and the technical problems along the way (database migration from SQLite to MySQL, emoji encoding, rendering math notation, context management).
