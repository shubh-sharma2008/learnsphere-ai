import os
import sqlite3
import random
import json
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from openai import OpenAI
except ImportError:  # The local tutor remains available without an API package/key.
    OpenAI = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "learnsphere.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_NOTE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("LEARN_SPHERE_SECRET_KEY", "learnsphere-dev-secret-change-in-production")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT,
            difficulty TEXT DEFAULT 'Beginner',
            study_note TEXT,
            UNIQUE(subject_id, slug)
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL REFERENCES topics(id),
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            explanation TEXT
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            topic_id INTEGER NOT NULL REFERENCES topics(id),
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attempt_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL REFERENCES attempts(id),
            question_id INTEGER NOT NULL REFERENCES questions(id),
            selected_option TEXT,
            is_correct INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS flashcard_reviews (
            user_id INTEGER NOT NULL REFERENCES users(id),
            question_id INTEGER NOT NULL REFERENCES questions(id),
            interval_days INTEGER NOT NULL DEFAULT 1,
            ease REAL NOT NULL DEFAULT 2.5,
            due_date TEXT NOT NULL,
            last_reviewed TEXT,
            PRIMARY KEY (user_id, question_id)
        );

        CREATE TABLE IF NOT EXISTS user_badges (
            user_id INTEGER NOT NULL REFERENCES users(id),
            badge_key TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            PRIMARY KEY (user_id, badge_key)
        );

        CREATE TABLE IF NOT EXISTS uploaded_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            filename TEXT NOT NULL,
            extracted_text TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Seed data — sample curriculum so the platform is usable out of the box
# ---------------------------------------------------------------------------

SEED_SUBJECTS = [
    {
        "name": "Python Programming",
        "slug": "python",
        "description": "Core programming fundamentals every learner starts with.",
        "icon": "code",
        "topics": [
            {
                "name": "Variables & Data Types",
                "slug": "variables",
                "description": "Storing and typing data in Python.",
                "difficulty": "Beginner",
                "study_note": "A variable is a named label for a value stored in memory. Python is "
                               "dynamically typed, so a variable's type is inferred from the value "
                               "assigned to it (int, float, str, bool, list, dict, etc.).",
                "questions": [
                    ("Which keyword is used to define a variable in Python?", "var", "let", "No keyword needed", "dim", "C",
                     "Python has no declaration keyword — you just assign a value, e.g. x = 5."),
                    ("What is the data type of x = 3.14?", "int", "float", "str", "bool", "B",
                     "Numbers with a decimal point are floats in Python."),
                    ("Which of these is a valid variable name?", "2value", "my-value", "my_value", "my value", "C",
                     "Variable names can use letters, digits and underscores, but can't start with a digit or contain spaces/hyphens."),
                    ("What does type(10) return?", "<class 'int'>", "<class 'float'>", "<class 'str'>", "<class 'bool'>", "A",
                     "10 has no decimal point, so Python treats it as an integer."),
                    ("Which type is used for True/False values?", "int", "bool", "str", "float", "B",
                     "bool is Python's Boolean type, holding True or False."),
                ],
            },
            {
                "name": "Loops & Conditionals",
                "slug": "loops",
                "description": "Controlling flow with if/else, for and while.",
                "difficulty": "Beginner",
                "study_note": "Conditionals (if/elif/else) branch based on a condition. Loops (for, while) "
                               "repeat a block of code — 'for' iterates over a sequence, 'while' repeats "
                               "until a condition becomes False.",
                "questions": [
                    ("Which loop is best for iterating over a list?", "while", "for", "do-while", "repeat", "B",
                     "A for loop naturally iterates over each item in a sequence like a list."),
                    ("What does 'range(5)' produce?", "1 to 5", "0 to 4", "0 to 5", "1 to 4", "B",
                     "range(5) generates 0, 1, 2, 3, 4 — five values starting at 0."),
                    ("Which keyword exits a loop early?", "exit", "stop", "break", "return", "C",
                     "'break' immediately terminates the nearest enclosing loop."),
                    ("What does 'continue' do inside a loop?", "Ends the loop", "Skips to the next iteration", "Restarts the program", "Pauses execution", "B",
                     "'continue' skips the rest of the current iteration and moves to the next one."),
                    ("Which is the correct if-statement syntax?", "if x == 5:", "if (x = 5)", "if x = 5 then", "if x == 5 then:", "A",
                     "Python uses '==' for comparison and a colon to start the block."),
                ],
            },
            {
                "name": "Functions",
                "slug": "functions",
                "description": "Writing reusable blocks of code.",
                "difficulty": "Intermediate",
                "study_note": "A function is defined with 'def', can accept parameters, and optionally "
                               "returns a value with 'return'. Functions make code reusable and easier to test.",
                "questions": [
                    ("Which keyword defines a function?", "func", "def", "function", "lambda", "B",
                     "Functions in Python are defined using the 'def' keyword."),
                    ("What does a function return if there is no 'return' statement?", "0", "None", "Error", "Empty string", "B",
                     "A function without an explicit return returns None by default."),
                    ("What is a lambda function?", "A named multi-line function", "An anonymous single-expression function", "A loop", "A class method only", "B",
                     "lambda creates small, anonymous, single-expression functions."),
                    ("How do you call a function named greet?", "call greet", "greet()", "greet", "run greet()", "B",
                     "Functions are invoked using parentheses: greet()."),
                    ("What are default parameter values used for?", "Making a parameter optional", "Declaring constants", "Looping", "Importing modules", "A",
                     "A default value lets the caller omit that argument."),
                ],
            },
        ],
    },
    {
        "name": "Mathematics",
        "slug": "mathematics",
        "description": "Foundational math concepts for problem solving.",
        "icon": "calculator",
        "topics": [
            {
                "name": "Algebra Basics",
                "slug": "algebra-basics",
                "description": "Working with variables and equations.",
                "difficulty": "Beginner",
                "study_note": "Algebra uses symbols (like x, y) to represent unknown values in equations. "
                               "Solving an equation means finding the value that makes both sides equal.",
                "questions": [
                    ("Solve for x: x + 5 = 12", "5", "6", "7", "17", "C", "x = 12 - 5 = 7."),
                    ("Solve for x: 3x = 15", "3", "5", "12", "45", "B", "x = 15 / 3 = 5."),
                    ("What is the value of x in 2x - 4 = 10?", "3", "5", "7", "14", "C", "2x = 14, so x = 7."),
                    ("Simplify: 2(x + 3)", "2x + 3", "2x + 6", "x + 6", "2x + 5", "B", "Distribute: 2*x + 2*3 = 2x + 6."),
                    ("What is a variable in algebra?", "A fixed number", "A symbol representing an unknown value", "An operator", "An equation", "B",
                     "A variable stands in for a value that can change or is unknown."),
                ],
            },
            {
                "name": "Geometry Essentials",
                "slug": "geometry",
                "description": "Shapes, angles, and area calculations.",
                "difficulty": "Beginner",
                "study_note": "Geometry studies shapes, sizes, and the properties of space — including "
                               "perimeter, area, and angle relationships in common figures.",
                "questions": [
                    ("How many degrees are in a triangle's angles combined?", "90", "180", "270", "360", "B",
                     "The interior angles of any triangle always sum to 180 degrees."),
                    ("What is the formula for the area of a rectangle?", "length + width", "length x width", "2(length + width)", "length / width", "B",
                     "Area of a rectangle = length multiplied by width."),
                    ("How many sides does a hexagon have?", "5", "6", "7", "8", "B", "Hexagon comes from the Greek for 'six'."),
                    ("What is the area of a circle with radius r?", "2*pi*r", "pi*r", "pi*r^2", "2*r^2", "C", "Area of a circle = pi times radius squared."),
                    ("What do you call a triangle with all equal sides?", "Scalene", "Isosceles", "Equilateral", "Right-angled", "C",
                     "An equilateral triangle has three equal sides and three equal 60-degree angles."),
                ],
            },
        ],
    },
    {
        "name": "General Science",
        "slug": "science",
        "description": "Core scientific concepts across physics, chemistry and biology.",
        "icon": "flask",
        "topics": [
            {
                "name": "Forces & Motion",
                "slug": "forces-motion",
                "description": "Newton's laws and everyday motion.",
                "difficulty": "Beginner",
                "study_note": "Newton's three laws describe how objects move: they resist changes in "
                               "motion (inertia), accelerate proportionally to force, and every action "
                               "has an equal and opposite reaction.",
                "questions": [
                    ("Which law states 'an object at rest stays at rest unless acted on by a force'?", "Newton's 1st law", "Newton's 2nd law", "Newton's 3rd law", "Law of gravity", "A",
                     "This is the law of inertia — Newton's first law."),
                    ("What is the unit of force?", "Joule", "Newton", "Watt", "Pascal", "B", "Force is measured in Newtons (N)."),
                    ("F = m x a is which law?", "1st law", "2nd law", "3rd law", "Law of conservation", "B",
                     "Newton's second law relates force, mass, and acceleration."),
                    ("Every action has an equal and opposite what?", "Force", "Reaction", "Mass", "Velocity", "B",
                     "Newton's third law: for every action, there is an equal and opposite reaction."),
                    ("What quantity measures how fast velocity changes?", "Speed", "Acceleration", "Distance", "Momentum", "B",
                     "Acceleration is the rate of change of velocity over time."),
                ],
            },
            {
                "name": "Cells & Life",
                "slug": "cells-life",
                "description": "The basic unit of life and its structures.",
                "difficulty": "Beginner",
                "study_note": "The cell is the basic structural and functional unit of all living "
                               "organisms. Cells contain organelles such as the nucleus, mitochondria, "
                               "and cell membrane, each with a specific role.",
                "questions": [
                    ("What is the basic unit of life?", "Tissue", "Cell", "Organ", "Atom", "B", "The cell is the smallest unit that can be considered alive."),
                    ("Which organelle is the 'powerhouse of the cell'?", "Nucleus", "Ribosome", "Mitochondria", "Vacuole", "C",
                     "Mitochondria generate the energy (ATP) a cell needs."),
                    ("Which part controls the cell's activities?", "Cell wall", "Nucleus", "Cytoplasm", "Membrane", "B",
                     "The nucleus houses DNA and directs the cell's activities."),
                    ("Which cells have a cell wall — plant or animal?", "Animal", "Plant", "Both", "Neither", "B",
                     "Plant cells have a rigid cell wall made of cellulose; animal cells do not."),
                    ("What process do plants use to make food from sunlight?", "Respiration", "Digestion", "Photosynthesis", "Fermentation", "C",
                     "Photosynthesis converts light energy into chemical energy (glucose)."),
                ],
            },
        ],
    },
]

# Rule-based study tips per subject, used by the AI Study Assistant when a
# learner is weak on a topic. This runs fully offline / locally — no external
# API calls — in line with the "AI processing" step of the platform.
SUBJECT_TIPS = {
    "python": [
        "Re-read the topic note, then rewrite each missed question in your own words before answering again.",
        "Open a Python shell and type out the exact example from the note — running code beats reading it.",
        "Trace through the code line by line on paper, noting what each variable holds at each step.",
    ],
    "mathematics": [
        "Redo each missed problem step-by-step on paper instead of jumping to the formula.",
        "Substitute your answer back into the original equation to check it actually balances.",
        "Draw a quick diagram or number line — geometry and algebra both get easier when visualised.",
    ],
    "science": [
        "Connect the concept to something you see daily — motion, cooking, or plants — to make it stick.",
        "Say the definition out loud in your own words before checking the textbook version.",
        "Make a simple flashcard for every term you got wrong and review it tomorrow.",
    ],
}


def seed_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    existing = db.execute("SELECT COUNT(*) AS c FROM subjects").fetchone()["c"]
    if existing:
        db.close()
        return

    for subject in SEED_SUBJECTS:
        cur = db.execute(
            "INSERT INTO subjects (name, slug, description, icon) VALUES (?, ?, ?, ?)",
            (subject["name"], subject["slug"], subject["description"], subject["icon"]),
        )
        subject_id = cur.lastrowid
        for topic in subject["topics"]:
            cur = db.execute(
                "INSERT INTO topics (subject_id, name, slug, description, difficulty, study_note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (subject_id, topic["name"], topic["slug"], topic["description"],
                 topic["difficulty"], topic["study_note"]),
            )
            topic_id = cur.lastrowid
            for q in topic["questions"]:
                db.execute(
                    "INSERT INTO questions (topic_id, question_text, option_a, option_b, option_c, "
                    "option_d, correct_option, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (topic_id, *q),
                )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return {"current_user": user}


# ---------------------------------------------------------------------------
# Personalization / recommendation engine
# ---------------------------------------------------------------------------

def get_topic_performance(user_id):
    """Return per-topic stats (attempts, best %, last %) for a user."""
    db = get_db()
    rows = db.execute(
        """
        SELECT t.id AS topic_id, t.name AS topic_name, t.slug AS topic_slug,
               s.name AS subject_name, s.slug AS subject_slug,
               COUNT(a.id) AS attempts,
               MAX(ROUND(100.0 * a.score / a.total)) AS best_pct,
               (SELECT ROUND(100.0 * a2.score / a2.total)
                  FROM attempts a2 WHERE a2.topic_id = t.id AND a2.user_id = ?
                  ORDER BY a2.created_at DESC LIMIT 1) AS last_pct
        FROM topics t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN attempts a ON a.topic_id = t.id AND a.user_id = ?
        GROUP BY t.id
        ORDER BY s.name, t.name
        """,
        (user_id, user_id),
    ).fetchall()
    return rows


def get_recommendation(user_id):
    """Pick the next best topic: unattempted topics first, then weakest score."""
    performance = get_topic_performance(user_id)
    if not performance:
        return None
    unattempted = [t for t in performance if t["attempts"] == 0]
    if unattempted:
        return unattempted[0]
    weakest = min(performance, key=lambda t: t["best_pct"] if t["best_pct"] is not None else 0)
    return weakest


def get_study_tips(user_id, subject_slug, wrong_questions):
    tips = SUBJECT_TIPS.get(subject_slug, SUBJECT_TIPS["python"])
    picks = random.sample(tips, k=min(2, len(tips)))
    focus = [q["question_text"] for q in wrong_questions[:3]]
    return {"tips": picks, "focus_questions": focus}


def learning_report(topic_name, pct, wrong_count):
    """Create the learner-facing, score-band report shown after every quiz."""
    if pct < 50:
        status = "Weak topic detected"
        message = "Your current result shows this topic needs focused revision before moving on."
        steps = [
            "Revise the study note slowly and write down the key ideas in your own words.",
            f"Review the {wrong_count} incorrect question{'s' if wrong_count != 1 else ''} and read each explanation.",
            "Reattempt this quiz after your revision to check that the ideas have stuck.",
        ]
    elif pct < 70:
        status = "Needs more practice"
        message = "You understand part of this topic; targeted practice will strengthen it."
        steps = [
            "Revisit the parts of the study note connected to your missed answers.",
            "Work through the incorrect-question explanations and try to explain them aloud.",
            "Take the quiz again and aim to improve one answer at a time.",
        ]
    else:
        status = "Strong topic"
        message = "You have a strong grasp of this topic. Keep it active with a short review."
        steps = [
            "Summarize the main idea from the study note without looking.",
            "Review any incorrect questions so small gaps do not become habits.",
            "Try a challenge quiz or help a study buddy with this topic.",
        ]
    return {"topic_name": topic_name, "status": status, "message": message, "steps": steps}


def _extract_note_text(file_path, extension):
    """Extract PDF text locally; images can be interpreted by the configured AI parser."""
    if extension == "pdf":
        try:
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(file_path).pages).strip()
        except Exception:
            return ""
    return ""


def _local_quiz_from_text(text):
    """Safe offline fallback when no AI key is configured."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 30]
    if not sentences:
        sentences = ["Review the uploaded note and identify its most important concepts before trying again."]
    questions = []
    for sentence in sentences[:5]:
        questions.append({
            "question": "Which statement is supported by your uploaded note?",
            "options": [sentence, "It says the topic has no important details.", "It says revision is unnecessary.", "It describes an unrelated subject."],
            "correct": "A",
            "explanation": "This answer restates information from your uploaded note.",
        })
    return questions


def _ai_quiz_from_note(text, image_path=None):
    """Use OpenAI when available, otherwise produce a local note-based quiz."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key and OpenAI:
        try:
            content = [{"type": "input_text", "text": "Create 5 multiple-choice study questions from these notes. Return ONLY JSON: a list with question, options (exactly 4 strings), correct (A-D), explanation. Notes: " + text[:12000]}]
            if image_path:
                import base64
                with open(image_path, "rb") as image_file:
                    encoded = base64.b64encode(image_file.read()).decode("ascii")
                content.append({"type": "input_image", "image_url": f"data:image/*;base64,{encoded}"})
            response = OpenAI(api_key=api_key).responses.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                input=[{"role": "user", "content": content}],
            )
            raw = response.output_text.strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            generated = json.loads(raw)
            valid = [q for q in generated if isinstance(q, dict) and len(q.get("options", [])) == 4 and q.get("correct") in "ABCD"]
            if valid:
                return valid[:5]
        except Exception:
            pass
    return _local_quiz_from_text(text)


def get_study_buddies(user_id):
    """Rank learners whose demonstrated strengths fill this learner's weak areas."""
    db = get_db()
    my_scores = {row["topic_id"]: row["last_pct"] for row in get_topic_performance(user_id) if row["last_pct"] is not None}
    candidates = db.execute("SELECT id, name FROM users WHERE id != ?", (user_id,)).fetchall()
    matches = []
    for candidate in candidates:
        scores = {row["topic_id"]: row["last_pct"] for row in get_topic_performance(candidate["id"]) if row["last_pct"] is not None}
        complementary = [topic_id for topic_id, score in my_scores.items() if score < 70 and scores.get(topic_id, 0) >= 70]
        reciprocal = [topic_id for topic_id, score in scores.items() if score < 70 and my_scores.get(topic_id, 0) >= 70]
        if complementary or reciprocal:
            names = db.execute("SELECT name FROM topics WHERE id IN ({})".format(",".join("?" * len(complementary + reciprocal))), complementary + reciprocal).fetchall()
            matches.append({"name": candidate["name"], "score": len(complementary) + len(reciprocal), "topics": [r["name"] for r in names]})
    return sorted(matches, key=lambda item: (-item["score"], item["name"]))


BADGES = {
    "first_step": ("First Step", "Complete your first quiz", "🌱"),
    "perfect_score": ("Perfect Score", "Score 100% on a quiz", "🏆"),
    "quiz_master": ("Quiz Master", "Complete 10 quizzes", "🧠"),
    "streak_5": ("5-Day Streak", "Learn on five consecutive days", "🔥"),
}


def utc_now():
    return datetime.now(timezone.utc)


def get_streak(user_id):
    """Return the current consecutive-day learning streak and last activity date."""
    db = get_db()
    dates = db.execute(
        "SELECT DISTINCT substr(created_at, 1, 10) AS day FROM attempts WHERE user_id = ? ORDER BY day DESC",
        (user_id,),
    ).fetchall()
    if not dates:
        return 0, None
    days = [datetime.fromisoformat(row["day"]).date() for row in dates]
    today = utc_now().date()
    if days[0] not in (today, today - timedelta(days=1)):
        return 0, days[0]
    streak, expected = 0, days[0]
    for day in days:
        if day != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    return streak, days[0]


def award_badges(user_id, pct):
    db = get_db()
    quiz_count = db.execute("SELECT COUNT(*) AS c FROM attempts WHERE user_id = ?", (user_id,)).fetchone()["c"]
    streak, _ = get_streak(user_id)
    eligible = ["first_step"]
    if pct == 100:
        eligible.append("perfect_score")
    if quiz_count >= 10:
        eligible.append("quiz_master")
    if streak >= 5:
        eligible.append("streak_5")
    new_badges = []
    for key in eligible:
        existing = db.execute("SELECT 1 FROM user_badges WHERE user_id = ? AND badge_key = ?", (user_id, key)).fetchone()
        if not existing:
            db.execute("INSERT INTO user_badges (user_id, badge_key, earned_at) VALUES (?, ?, ?)",
                       (user_id, key, utc_now().isoformat()))
            new_badges.append(BADGES[key])
    db.commit()
    return new_badges


def get_leaderboard(limit=5):
    """Weekly ranked score; at least two quiz attempts avoids a one-quiz leaderboard."""
    week_start = (utc_now() - timedelta(days=7)).isoformat()
    return get_db().execute(
        """
        SELECT u.name, ROUND(AVG(100.0 * a.score / a.total)) AS average_score,
               COUNT(a.id) AS quiz_count
        FROM attempts a JOIN users u ON u.id = a.user_id
        WHERE a.created_at >= ?
        GROUP BY u.id
        ORDER BY average_score DESC, quiz_count DESC, u.name ASC
        LIMIT ?
        """, (week_start, limit)
    ).fetchall()


def get_local_tutor_reply(question, topic):
    note = topic["study_note"] or topic["description"]
    return (f"Start with this idea: {note}\n\nFor your question — {question} — "
            "break it into one small step, use the study note above, and then try one example. "
            "Ask a more specific question if you want a targeted explanation.")


# ---------------------------------------------------------------------------
# Routes — marketing / auth
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "LearnSphere AI"})


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    db = get_db()
    subjects = db.execute("SELECT * FROM subjects").fetchall()
    return render_template("index.html", subjects=subjects)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("An account with that email already exists.", "error")
            return render_template("register.html")

        db.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            next_url = request.args.get("next")
            # Only allow local paths to prevent open-redirects.
            if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("dashboard")
            return redirect(next_url)
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes — learner dashboard / subjects / topics
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user_id = session["user_id"]
    subjects = db.execute("SELECT * FROM subjects").fetchall()
    performance = get_topic_performance(user_id)

    attempted = [t for t in performance if t["attempts"] > 0]
    avg_pct = round(sum(t["best_pct"] for t in attempted) / len(attempted)) if attempted else 0
    topics_started = len(attempted)
    topics_total = len(performance)

    recommendation = get_recommendation(user_id)
    streak, _ = get_streak(user_id)
    quiz_count = db.execute("SELECT COUNT(*) AS c FROM attempts WHERE user_id = ?", (user_id,)).fetchone()["c"]
    badge_rows = db.execute("SELECT badge_key FROM user_badges WHERE user_id = ? ORDER BY earned_at DESC", (user_id,)).fetchall()
    badges = [BADGES[row["badge_key"]] for row in badge_rows if row["badge_key"] in BADGES]

    recent = db.execute(
        """
        SELECT a.*, t.name AS topic_name, t.slug AS topic_slug, s.name AS subject_name, s.slug AS subject_slug
        FROM attempts a
        JOIN topics t ON t.id = a.topic_id
        JOIN subjects s ON s.id = t.subject_id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
        LIMIT 5
        """,
        (user_id,),
    ).fetchall()

    return render_template(
        "dashboard.html",
        subjects=subjects,
        performance=performance,
        avg_pct=avg_pct,
        topics_started=topics_started,
        topics_total=topics_total,
        recommendation=recommendation,
        recent=recent,
        quiz_count=quiz_count,
        streak=streak,
        badges=badges,
        leaderboard=get_leaderboard(),
    )


@app.route("/subject/<slug>")
@login_required
def subject_detail(slug):
    db = get_db()
    subject = db.execute("SELECT * FROM subjects WHERE slug = ?", (slug,)).fetchone()
    if not subject:
        flash("Subject not found.", "error")
        return redirect(url_for("dashboard"))

    topics = db.execute("SELECT * FROM topics WHERE subject_id = ?", (subject["id"],)).fetchall()
    user_id = session["user_id"]

    topic_stats = {}
    for t in topics:
        row = db.execute(
            "SELECT MAX(ROUND(100.0 * score / total)) AS best_pct, COUNT(*) AS attempts "
            "FROM attempts WHERE topic_id = ? AND user_id = ?",
            (t["id"], user_id),
        ).fetchone()
        topic_stats[t["id"]] = row

    return render_template("subject.html", subject=subject, topics=topics, topic_stats=topic_stats)


# ---------------------------------------------------------------------------
# Routes — quizzes
# ---------------------------------------------------------------------------

@app.route("/quiz/<topic_slug>")
@login_required
def quiz_start(topic_slug):
    db = get_db()
    topic = db.execute("SELECT * FROM topics WHERE slug = ?", (topic_slug,)).fetchone()
    if not topic:
        flash("Topic not found.", "error")
        return redirect(url_for("dashboard"))
    subject = db.execute("SELECT * FROM subjects WHERE id = ?", (topic["subject_id"],)).fetchone()
    questions = db.execute("SELECT * FROM questions WHERE topic_id = ?", (topic["id"],)).fetchall()
    timed = request.args.get("mode") == "challenge"
    return render_template("quiz.html", topic=topic, subject=subject, questions=questions,
                           timed=timed, time_limit=90 if timed else None)


@app.route("/challenge")
@login_required
def challenge_pick():
    topics = get_db().execute("SELECT t.*, s.name AS subject_name FROM topics t JOIN subjects s ON s.id = t.subject_id").fetchall()
    return render_template("challenge.html", topics=topics)


@app.route("/study-buddies")
@login_required
def study_buddies():
    return render_template("study_buddies.html", matches=get_study_buddies(session["user_id"]))


@app.route("/generate-quiz", methods=["GET", "POST"])
@login_required
def generate_quiz():
    if request.method == "POST":
        note = request.files.get("note")
        title = request.form.get("title", "My uploaded notes").strip()[:80] or "My uploaded notes"
        if not note or not note.filename:
            flash("Choose a PDF or image of your notes first.", "error")
            return redirect(url_for("generate_quiz"))
        extension = note.filename.rsplit(".", 1)[-1].lower() if "." in note.filename else ""
        if extension not in ALLOWED_NOTE_EXTENSIONS:
            flash("Please upload a PDF, PNG, JPG, JPEG, or WEBP note.", "error")
            return redirect(url_for("generate_quiz"))
        stored_name = f"{session['user_id']}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(note.filename)}"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
        note.save(file_path)
        extracted_text = _extract_note_text(file_path, extension)
        if extension != "pdf" and not os.environ.get("OPENAI_API_KEY"):
            flash("Image uploads need OPENAI_API_KEY for visual AI parsing. Try a text-based PDF or configure the key.", "warning")
            return redirect(url_for("generate_quiz"))
        if extension == "pdf" and not extracted_text:
            flash("We could not read text from that PDF. Try a selectable-text PDF or an image with AI parsing enabled.", "error")
            return redirect(url_for("generate_quiz"))
        generated = _ai_quiz_from_note(extracted_text, file_path if extension != "pdf" else None)
        if not generated:
            flash("Quiz generation did not return questions. Please try another note.", "error")
            return redirect(url_for("generate_quiz"))

        db = get_db()
        db.execute("INSERT INTO uploaded_notes (user_id, filename, extracted_text, created_at) VALUES (?, ?, ?, ?)",
                   (session["user_id"], secure_filename(note.filename), extracted_text, utc_now().isoformat()))
        uploads_subject = db.execute("SELECT id FROM subjects WHERE slug = 'uploaded-notes'").fetchone()
        if not uploads_subject:
            cur = db.execute("INSERT INTO subjects (name, slug, description, icon) VALUES (?, ?, ?, ?)",
                             ("My Uploaded Notes", "uploaded-notes", "AI-generated quizzes from your notes.", "file-text"))
            subject_id = cur.lastrowid
        else:
            subject_id = uploads_subject["id"]
        slug = f"uploaded-{session['user_id']}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        cur = db.execute("INSERT INTO topics (subject_id, name, slug, description, difficulty, study_note) VALUES (?, ?, ?, ?, ?, ?)",
                         (subject_id, title, slug, "Quiz generated from an uploaded note.", "Custom", extracted_text or "AI parsed an uploaded image note."))
        topic_id = cur.lastrowid
        for question in generated:
            options = question["options"]
            db.execute("""INSERT INTO questions (topic_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                       (topic_id, question["question"], options[0], options[1], options[2], options[3], question["correct"], question.get("explanation", "Review the uploaded note for the supporting detail.")))
        db.commit()
        flash("Your custom quiz is ready.", "success")
        return redirect(url_for("quiz_start", topic_slug=slug))
    return render_template("generate_quiz.html")


@app.route("/quiz/<topic_slug>/submit", methods=["POST"])
@login_required
def quiz_submit(topic_slug):
    db = get_db()
    topic = db.execute("SELECT * FROM topics WHERE slug = ?", (topic_slug,)).fetchone()
    if not topic:
        flash("Topic not found.", "error")
        return redirect(url_for("dashboard"))
    subject = db.execute("SELECT * FROM subjects WHERE id = ?", (topic["subject_id"],)).fetchone()
    questions = db.execute("SELECT * FROM questions WHERE topic_id = ?", (topic["id"],)).fetchall()

    score = 0
    results = []
    wrong_questions = []
    for q in questions:
        selected = request.form.get(f"q{q['id']}")
        is_correct = 1 if selected == q["correct_option"] else 0
        score += is_correct
        results.append({"question": q, "selected": selected, "is_correct": is_correct})
        if not is_correct:
            wrong_questions.append(q)

    total = len(questions)
    user_id = session["user_id"]
    cur = db.execute(
        "INSERT INTO attempts (user_id, topic_id, score, total, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, topic["id"], score, total, datetime.utcnow().isoformat()),
    )
    attempt_id = cur.lastrowid
    for r in results:
        db.execute(
            "INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct) "
            "VALUES (?, ?, ?, ?)",
            (attempt_id, r["question"]["id"], r["selected"], r["is_correct"]),
        )
    db.commit()

    pct = round(100 * score / total) if total else 0
    assistant = None
    if pct < 70:
        assistant = get_study_tips(user_id, subject["slug"], wrong_questions)

    new_badges = award_badges(user_id, pct)
    return render_template(
        "quiz_result.html",
        topic=topic,
        subject=subject,
        results=results,
        score=score,
        total=total,
        pct=pct,
        learning_report=learning_report(topic["name"], pct, len(wrong_questions)),
        assistant=assistant,
        new_badges=new_badges,
    )


# ---------------------------------------------------------------------------
# Routes — AI tutor and spaced-repetition flashcards
# ---------------------------------------------------------------------------

@app.route("/tutor/<topic_slug>", methods=["POST"])
@login_required
def tutor(topic_slug):
    db = get_db()
    topic = db.execute("SELECT * FROM topics WHERE slug = ?", (topic_slug,)).fetchone()
    question = request.form.get("question", "").strip()
    if not topic or not question:
        return jsonify({"error": "Please enter a question."}), 400
    if len(question) > 800:
        return jsonify({"error": "Keep your question under 800 characters."}), 400

    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key and OpenAI:
        try:
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=("You are LearnSphere's encouraging study tutor. Explain accurately at a "
                              "student-friendly level. Do not provide answers to an active test; teach "
                              "the concept, use one short example, and end with a check-for-understanding question."),
                input=f"Topic: {topic['name']}\nStudy note: {topic['study_note']}\nStudent question: {question}",
            )
            return jsonify({"answer": response.output_text, "mode": "AI"})
        except Exception:
            # Never expose provider failures or credentials to learners.
            pass
    return jsonify({"answer": get_local_tutor_reply(question, topic), "mode": "Study coach"})


@app.route("/flashcards")
@login_required
def flashcards():
    user_id = session["user_id"]
    now = utc_now().isoformat()
    cards = get_db().execute(
        """
        SELECT q.*, t.name AS topic_name, s.name AS subject_name,
               COALESCE(r.interval_days, 1) AS interval_days
        FROM questions q JOIN topics t ON t.id = q.topic_id JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN flashcard_reviews r ON r.question_id = q.id AND r.user_id = ?
        WHERE r.due_date IS NULL OR r.due_date <= ?
        ORDER BY COALESCE(r.due_date, '') ASC LIMIT 20
        """, (user_id, now)
    ).fetchall()
    return render_template("flashcards.html", cards=cards)


@app.route("/flashcards/<int:question_id>/review", methods=["POST"])
@login_required
def review_flashcard(question_id):
    quality = request.form.get("quality", "again")
    if quality not in {"again", "good", "easy"}:
        return jsonify({"error": "Invalid review."}), 400
    db, user_id = get_db(), session["user_id"]
    old = db.execute("SELECT interval_days, ease FROM flashcard_reviews WHERE user_id = ? AND question_id = ?",
                     (user_id, question_id)).fetchone()
    interval = old["interval_days"] if old else 1
    ease = old["ease"] if old else 2.5
    if quality == "again":
        interval, ease = 1, max(1.3, ease - 0.2)
    elif quality == "good":
        interval, ease = max(2, round(interval * ease)), ease
    else:
        ease = min(3.0, ease + 0.15)
        interval = max(3, round(interval * ease * 1.25))
    due = (utc_now() + timedelta(days=interval)).isoformat()
    db.execute("""INSERT INTO flashcard_reviews (user_id, question_id, interval_days, ease, due_date, last_reviewed)
                  VALUES (?, ?, ?, ?, ?, ?)
                  ON CONFLICT(user_id, question_id) DO UPDATE SET interval_days=excluded.interval_days,
                  ease=excluded.ease, due_date=excluded.due_date, last_reviewed=excluded.last_reviewed""",
               (user_id, question_id, interval, ease, due, utc_now().isoformat()))
    db.commit()
    return jsonify({"ok": True, "next_review": f"Review again in {interval} day{'s' if interval != 1 else ''}."})


# ---------------------------------------------------------------------------
# Routes — progress
# ---------------------------------------------------------------------------

@app.route("/progress")
@login_required
def progress():
    db = get_db()
    user_id = session["user_id"]
    performance = get_topic_performance(user_id)
    history = db.execute(
        """
        SELECT a.created_at, a.score, a.total, t.name AS topic_name, s.name AS subject_name
        FROM attempts a
        JOIN topics t ON t.id = a.topic_id
        JOIN subjects s ON s.id = t.subject_id
        WHERE a.user_id = ?
        ORDER BY a.created_at ASC
        """,
        (user_id,),
    ).fetchall()

    chart_labels = [h["created_at"][:10] for h in history]
    chart_data = [round(100 * h["score"] / h["total"]) for h in history]

    return render_template(
        "progress.html",
        performance=performance,
        history=history,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )


# Initialize the local SQLite database whenever the app module is loaded.
# This makes both `python app.py` and `flask --app app run` work.
with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
