# FragmentFusion Studio — VS Code Project

A screenshot-inspired professional Streamlit academic workspace with a navy sidebar, welcome banner, KPI cards, recent activity, login/register, document matching, AI-writing signal review, Crossref Research Paper Finder, contextual academic chatbot, SQLite history, and downloadable PDF reports.

## Windows / VS Code setup (Python 3.11 recommended)

1. Extract ZIP, then open the **FragmentFusion_Pro** folder (the folder containing `app.py` and `requirements.txt`) in VS Code.
2. Open VS Code terminal. Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

3. Visit http://localhost:8501 manually if VS Code does not open the browser.
4. Register a local user, log in, and use each module.
5. Use `data/sample_submission.txt` for a demo and enable **Include 2 clearly labeled demo reference documents** in Plagiarism Detector. When pasting text, switch **Choose input to analyze** to **Pasted text**.
6. If you need PDF uploads, optionally run: `.\.venv\Scripts\python.exe -m pip install pymupdf`. DOCX and TXT do not need PyMuPDF.

**Windows Smart App Control:** if your system blocks Python compiled packages, avoid disabling Windows security. This project intentionally avoids scikit-learn and uses mostly pure-Python comparisons; Streamlit's own dependencies may still be subject to local policy. Consider VS Code connected to Linux/WSL or Codespaces if required.

## Features

- **Accounts:** local SQLite registration/login, salted PBKDF2 password hashes. Not production-ready multi-user auth; no password resets/email verification.
- **Dashboard:** saved analysis counts, recent activity, basic trend chart. No fabricated sample counts.
- **Plagiarism Detector:** upload DOCX/TXT, optional PDF, or paste text; reference library upload; per-sentence token cosine + sequence similarity; text highlighting; matched reference passages; coverage percentage; PDF report.
- **AI Detection:** rule-based writing-signal screening, per-sentence explanations, highlighted passages and coverage percentage. **This is not a validated AI-authorship classifier.** It cannot certify human or AI-written text.
- **Research Paper Finder:** real Crossref metadata, DOI links, saved research papers. Requires internet; papers can be paywalled.
- **Academic Chatbot:** project-specific structured answers and last-analysis context; not a generative model. Can explain report percentages, sentence source matches, citation styles and features.
- **Reports:** SQLite persistence and downloadable PDF output.

## Accuracy and important limitations

A **similarity percentage** here means the share of document words in submitted sentences that match supplied reference sentences above a configurable threshold. It is **not a plagiarism verdict** and does not search the full web or publications database.

An **AI-writing signal percentage** means the share of words within sentences flagged by a small set of stylistic heuristics. It is **not the probability of AI authorship**. Unflagged sentences must not be called verified human-written. Both modules may yield false positives/negatives.

For school submissions, show these limits on the methodology slide and evaluate results against a labeled dataset rather than making unsupported accuracy claims.

## Structure

```
FragmentFusion_Pro/
  app.py               # all Streamlit pages, chatbot and research API
  engine.py            # similarity matching, signal review and HTML highlights
  db.py                # local user/history/paper SQLite
  styles.css           # screenshot-inspired frontend styles
  requirements.txt
  data/                # clearly labeled sample references and submission
  tests/test_engine.py
```

## Useful commands

```powershell
# Run tests
.\.venv\Scripts\python.exe -m pytest -q
# Launch app
.\.venv\Scripts\python.exe -m streamlit run app.py
# Stop server
# Press Ctrl+C in terminal
```

Do not make the developer Streamlit service publicly accessible without production authentication, rate limiting, security review and deployment hardening.
