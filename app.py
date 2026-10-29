"""
Student Assistant AI — Flask backend
Authentication: SQLite + Werkzeug password hashing + Flask sessions + CSRF.
Groq AI integration — API key server-side only.
"""
import os, sys, logging, sqlite3, secrets, re, time
from functools import wraps
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, g, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# ── Environment ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# ── Logging (no secrets logged) ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Groq setup ────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY not set. Add it to .env")
    sys.exit(1)

try:
    from groq import Groq, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
except ImportError:
    logger.error("groq package missing. Run: pip install groq")
    sys.exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME        = "openai/gpt-oss-120b"
MAX_CONTEXT       = 10
MAX_INPUT_CHARS   = 4000
MAX_OUTPUT_TOKENS = 1024
TEMPERATURE       = 0.7
GROQ_TIMEOUT      = 30

SYSTEM_PROMPT = (
    "You are Student Assistant AI - a friendly, knowledgeable academic companion for students.\n\n"
    "You help with:\n"
    "- Explaining concepts (beginner to advanced) across all subjects\n"
    "- Step-by-step problem solving with clear explanations\n"
    "- Assignment guidance, writing improvement, outlines and examples\n"
    "- Exam prep, revision plans, summaries and practice quizzes\n"
    "- Programming help, debugging, algorithms and code explanations\n"
    "- Flashcards, definitions, interview prep and study notes\n"
    "- Project ideas, documentation outlines, presentation planning\n"
    "- Study schedules, productivity tips and learning strategies\n\n"
    "Guidelines:\n"
    "- Give accurate, well-structured answers. Use headings, numbered steps, bullets and code blocks.\n"
    "- Adapt to the student level. Admit uncertainty honestly. Never invent facts or citations.\n"
    "- Encourage understanding, not blind copying."
)

# ── Flask app ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not SECRET_KEY or len(SECRET_KEY) < 16:
    logger.error("FLASK_SECRET_KEY not set or too short. Add a long random value to .env")
    sys.exit(1)

app = Flask(__name__, instance_relative_config=True)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,   # set True in production over HTTPS
    PERMANENT_SESSION_LIFETIME=86400 * 7,  # 7 days
    JSON_SORT_KEYS=False,
)

# Ensure instance folder exists (holds the SQLite DB)
os.makedirs(app.instance_path, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, "users.db")

# ── Simple in-process rate limiter ────────────────────────────────────────────
_rate_store: dict = {}   # key -> [timestamps]

def _rate_check(key: str, limit: int, window: int) -> bool:
    """Return True if allowed, False if rate limit exceeded."""
    now = time.time()
    hits = [t for t in _rate_store.get(key, []) if now - t < window]
    if len(hits) >= limit:
        return False
    hits.append(now)
    _rate_store[key] = hits
    return True

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            email     TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            pw_hash   TEXT    NOT NULL,
            created   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    db.commit()
    db.close()
    logger.info("Database ready: %s", DB_PATH)

# ── CSRF helpers ──────────────────────────────────────────────────────────────
def generate_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]

def validate_csrf(token: str) -> bool:
    return secrets.compare_digest(session.get("_csrf", ""), token or "")

# ── Auth helpers ──────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PW_MIN   = 8

def _validate_password(pw: str) -> list[str]:
    errs = []
    if len(pw) < PW_MIN:
        errs.append(f"At least {PW_MIN} characters.")
    if not re.search(r"[A-Za-z]", pw):
        errs.append("Include at least one letter.")
    if not re.search(r"\d", pw):
        errs.append("Include at least one number.")
    return errs

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json:
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db  = get_db()
    row = db.execute("SELECT id, name, email FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None

# ── Template context helpers ──────────────────────────────────────────────────
@app.context_processor
def inject_csrf():
    """Make csrf_token available in all templates."""
    return {"csrf_token": generate_csrf()}


# ── Routes: public ────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    email_val = ""

    if request.method == "POST":
        ip  = request.remote_addr or "unknown"
        key = f"login:{ip}"
        if not _rate_check(key, limit=10, window=60):
            error = "Too many attempts. Please wait a minute."
        else:
            csrf  = request.form.get("csrf_token", "")
            if not validate_csrf(csrf):
                abort(400)

            email    = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            remember = bool(request.form.get("remember"))
            email_val = email

            if not email or not password:
                error = "Please enter your email and password."
            elif not EMAIL_RE.match(email):
                error = "Please enter a valid email address."
            else:
                db  = get_db()
                row = db.execute(
                    "SELECT id, name, pw_hash FROM users WHERE email=?", (email,)
                ).fetchone()
                # Always run hash check to prevent timing attacks
                dummy = generate_password_hash("dummy")
                pw_ok = check_password_hash(
                    row["pw_hash"] if row else dummy, password
                )
                if not row or not pw_ok:
                    error = "Incorrect email or password."
                else:
                    # Regenerate session to prevent fixation
                    session.clear()
                    generate_csrf()
                    session["user_id"]   = row["id"]
                    session["user_name"] = row["name"]
                    if remember:
                        session.permanent = True
                    logger.info("Login: user_id=%s", row["id"])
                    next_url = request.args.get("next", "")
                    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                        return redirect(next_url)
                    return redirect(url_for("index"))

    return render_template("login.html",
                           csrf_token=generate_csrf(),
                           error=error,
                           email_val=email_val)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("index"))

    errors = {}
    vals   = {}

    if request.method == "POST":
        ip  = request.remote_addr or "unknown"
        key = f"signup:{ip}"
        if not _rate_check(key, limit=5, window=60):
            errors["general"] = "Too many attempts. Please wait a minute."
        else:
            csrf = request.form.get("csrf_token", "")
            if not validate_csrf(csrf):
                abort(400)

            name     = request.form.get("name", "").strip()
            email    = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm  = request.form.get("confirm", "")
            terms    = bool(request.form.get("terms"))
            vals     = {"name": name, "email": email}

            if not name or len(name) < 2:
                errors["name"] = "Full name must be at least 2 characters."
            if not email:
                errors["email"] = "Email is required."
            elif not EMAIL_RE.match(email):
                errors["email"] = "Enter a valid email address."
            pw_errs = _validate_password(password)
            if pw_errs:
                errors["password"] = pw_errs[0]
            if password and confirm and password != confirm:
                errors["confirm"] = "Passwords do not match."
            if not terms:
                errors["terms"] = "You must accept the terms to continue."

            if not errors:
                db = get_db()
                existing = db.execute(
                    "SELECT id FROM users WHERE email=?", (email,)
                ).fetchone()
                if existing:
                    # Generic: don't reveal whether email exists
                    errors["email"] = "An account with that email already exists."
                else:
                    pw_hash = generate_password_hash(password)
                    try:
                        db.execute(
                            "INSERT INTO users (name, email, pw_hash) VALUES (?,?,?)",
                            (name, email, pw_hash)
                        )
                        db.commit()
                        uid = db.execute(
                            "SELECT id FROM users WHERE email=?", (email,)
                        ).fetchone()["id"]
                        session.clear()
                        generate_csrf()
                        session["user_id"]   = uid
                        session["user_name"] = name
                        logger.info("Signup: user_id=%s", uid)
                        return redirect(url_for("index"))
                    except sqlite3.IntegrityError:
                        errors["email"] = "An account with that email already exists."

    return render_template("signup.html",
                           csrf_token=generate_csrf(),
                           errors=errors,
                           vals=vals)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    submitted = False
    error     = None

    if request.method == "POST":
        csrf = request.form.get("csrf_token", "")
        if not validate_csrf(csrf):
            abort(400)
        email = request.form.get("email", "").strip().lower()
        if not email or not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        else:
            # Do NOT reveal if account exists.
            # Real reset requires email delivery which is not configured.
            submitted = True

    return render_template("forgot_password.html",
                           csrf_token=generate_csrf(),
                           submitted=submitted,
                           error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Routes: protected ─────────────────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    user = get_current_user()
    return render_template("index.html", user=user)
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    # CSRF for AJAX — check header or form token
    csrf = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
    if not validate_csrf(csrf):
        return jsonify({"error": "Invalid request."}), 403

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid request body."}), 400
    messages = data.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list."}), 400

    recent    = messages[-MAX_CONTEXT:]
    validated = []
    for msg in recent:
        if not isinstance(msg, dict):
            return jsonify({"error": "Each message must be an object."}), 400
        role    = msg.get("role")
        content = msg.get("content")
        if role not in ("user", "assistant"):
            return jsonify({"error": "Role must be user or assistant."}), 400
        if not isinstance(content, str) or not content.strip():
            return jsonify({"error": "Content must be a non-empty string."}), 400
        if len(content) > MAX_INPUT_CHARS:
            return jsonify({"error": f"Message exceeds {MAX_INPUT_CHARS} characters."}), 400
        validated.append({"role": role, "content": content.strip()})

    groq_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + validated
    try:
        completion = groq_client.chat.completions.create(
            model=MODEL_NAME, messages=groq_messages,
            max_tokens=MAX_OUTPUT_TOKENS, temperature=TEMPERATURE, timeout=GROQ_TIMEOUT,
        )
        reply = completion.choices[0].message.content
        if not reply or not reply.strip():
            return jsonify({"error": "Empty response from AI. Please try again."}), 502
        logger.info("Chat OK model=%s tokens=%s user=%s",
                    MODEL_NAME,
                    getattr(completion.usage, "total_tokens", "?"),
                    session.get("user_id"))
        return jsonify({"reply": reply.strip()})
    except AuthenticationError:
        logger.error("Groq auth failed")
        return jsonify({"error": "API key invalid or revoked."}), 500
    except RateLimitError:
        return jsonify({"error": "Rate limit reached. Please wait and retry."}), 429
    except APIConnectionError:
        return jsonify({"error": "Could not reach AI service. Check internet connection."}), 503
    except APIStatusError as e:
        logger.error("Groq status %s", e.status_code)
        if e.status_code == 404:
            return jsonify({"error": f"Model '{MODEL_NAME}' not available."}), 500
        return jsonify({"error": "AI service error. Please try again."}), 502
    except Exception as e:
        logger.exception("Unexpected: %s", type(e).__name__)
        return jsonify({"error": "Unexpected error. Please try again."}), 500


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(400)
def bad_request(_e):
    if request.is_json:
        return jsonify({"error": "Bad request."}), 400
    return render_template("login.html",
                           csrf_token=generate_csrf(),
                           error="Invalid request. Please try again.",
                           email_val=""), 400

@app.errorhandler(404)
def not_found(_e):
    if request.is_json:
        return jsonify({"error": "Not found."}), 404
    return redirect(url_for("index"))

@app.errorhandler(401)
def unauthorized(_e):
    return redirect(url_for("login"))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    logger.info("Starting Student Assistant AI on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
