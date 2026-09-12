# LearnSphere AI

Smart Learning Software for the Digital Age — built for **Smart India Hackathon 2026**
(Problem Statement 26207, Theme: Smart Education, Team: **Code_Crafters**, Team ID: SIH-S-B1-102).

A working prototype of the platform described in the team's pitch deck: personalized
learning paths, interactive quizzes, an AI study assistant, and progress tracking.

## Features

- **Personalized learning** — the dashboard recommends the next topic to study:
  unattempted topics first, then whichever topic you're weakest in.
- **Interactive quizzes** — multiple-choice quizzes per topic with a live progress bar,
  instant right/wrong feedback, and worked explanations for every question.
- **AI study assistant** — when a quiz score is below 70%, a rule-based assistant
  surfaces targeted study tips and flags exactly which questions to revisit. It runs
  entirely offline (no external API calls), matching the "AI Processing" step in the
  team's methodology diagram.
- **Progress tracking** — a per-topic performance table plus a score-over-time chart
  across every quiz attempt.
- **Accounts** — simple email/password registration and login, with hashed passwords.
- **AI tutor** — an optional OpenAI-powered explanation assistant on quiz results; without a key, the safe local study coach remains available.
- **Smart review loop** — weakest-topic recommendations, daily streaks, achievement badges, weekly leaderboard, skill-galaxy progression, flashcards with adaptive spaced repetition, and 90-second quiz challenges.

## Optional AI tutor setup

The app works without any external key. To enable the OpenAI tutor, install the requirements and set a server-side key before starting it:

```powershell
$env:OPENAI_API_KEY="your_key_here"
# Optional: choose the model configured for your account
$env:OPENAI_MODEL="gpt-4.1-mini"
python app.py
```

Never add the API key to source code, templates, the APK, or GitHub. The tutor is called only by the Flask server and falls back to a local study coach if the key or service is unavailable.

## Tech stack

Matches the pitch deck exactly: **Python**, **Flask**, **SQLite**, **HTML/CSS/JavaScript**.
(OpenCV was listed in the deck for a future image-based module; this prototype focuses
on the core learning loop — see "Extending this prototype" below for where it plugs in.)

## Project structure

```
learnsphere/
├── app.py                  # Flask app: routes, DB helpers, seed data, recommendation engine
├── requirements.txt
├── learnsphere.db           # created automatically on first run
├── templates/
│   ├── base.html            # shared layout, nav, flash messages
│   ├── index.html           # landing page
│   ├── register.html / login.html
│   ├── dashboard.html       # stats, AI recommendation, subject grid, performance table
│   ├── subject.html         # topic list for a subject
│   ├── quiz.html            # quiz-taking screen
│   ├── quiz_result.html     # score, answer review, AI study assistant
│   └── progress.html        # score-over-time chart + per-topic table
└── static/
    ├── css/style.css
    └── js/main.js            # quiz progress bar + answer selection UI
```

## Setup

```bash
cd learnsphere
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Then open **http://localhost:5000** in your browser. The SQLite database and sample
curriculum (Python Programming, Mathematics, General Science — 7 topics, 35 questions)
are created automatically the first time you run the app.

## How the personalization works

`get_topic_performance()` computes each topic's attempt count and best score for the
logged-in user. `get_recommendation()` then picks, in order:

1. The first topic the user hasn't attempted yet, or
2. If everything has been attempted, the topic with the lowest best score.

That topic is surfaced on the dashboard as the "AI recommendation." After a quiz,
if the score is under 70%, `get_study_tips()` pulls subject-specific tips and lists
the exact questions that were missed, so review time is targeted rather than generic.

## Extending this prototype

- **OpenCV image recognition**: add a `/scan` route that accepts an uploaded photo
  (e.g. of a textbook page or diagram), runs OpenCV to identify it, and routes the
  learner to the matching topic — following the Capture → AI Processing → Fetch Info →
  Display → Learn workflow from the pitch deck.
- **Smarter recommendations**: swap the rule-based assistant for a lightweight
  ML model (e.g. scikit-learn) trained on attempt history once more usage data exists.
- **Deployment**: the app is a standard Flask app — deployable to any host that
  supports Python/WSGI (Render, PythonAnywhere, Railway, etc.) with SQLite swapped
  for PostgreSQL for multi-user scale.
# LearnSphere AI

## Added learning tools

- **Quiz Result Learning Analysis** classifies every result as *Weak topic detected* (below 50%), *Needs more practice* (50–69%), or *Strong topic* (70%+), with a targeted revision plan.
- **Study Buddy Matching** compares quiz strengths and weaknesses across learners to surface complementary partners.
- **AI Quiz Generator** accepts PDF notes and image notes. PDF text is extracted locally; image notes use the OpenAI vision parser when `OPENAI_API_KEY` is configured. Generated questions use the existing quiz and result flows.
- **Offline-first PWA** caches visited pages, notes, quizzes, and app assets. A completed cached quiz is queued locally if submitted offline and is sent when the learner reconnects.

Install dependencies with `pip install -r requirements.txt`. For AI image parsing, set `OPENAI_API_KEY` before starting the app.
