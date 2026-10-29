# Student Assistant AI

> **Learn Smarter. Study Better. Achieve More.**

A professional, full-stack AI study companion built with Flask and the Groq API. Students can ask questions across any subject, get step-by-step solutions, generate quizzes, create study plans, debug code, and more — all in a clean, responsive interface.

---

## Features

- **8 Quick-Action Tools** — Explain a Topic, Study Notes, Solve a Problem, Generate a Quiz, Study Plan, Explain Code, Improve Assignment, Interview Prep
- **Full Markdown Rendering** — headings, bold, italic, lists, code blocks, blockquotes
- **Conversation Context** — last 10 messages sent for contextual follow-ups
- **Copy Response** — one-click copy any AI message
- **Retry on Error** — retry failed requests without reloading
- **New Chat** — reset without a page refresh
- **Responsive Layout** — desktop sidebar + mobile-friendly with hamburger menu
- **Secure** — API key stays server-side, never exposed to the browser

---

## Prerequisites

- Python 3.9 or newer
- A free [Groq API key](https://console.groq.com/keys)
- Internet connection

---

## Installation (Windows)

### 1. Open PowerShell and navigate to the project folder

```powershell
cd "C:\Users\Admin\OneDrive\New folder\student-chatbot"
```

### 2. Create a virtual environment

```powershell
python -m venv venv
```

### 3. Activate the virtual environment

```powershell
.\venv\Scripts\Activate.ps1
```

If you see a script execution error, run this first:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

---

## Configuration

### 5. Set your Groq API key

Copy `.env.example` to `.env` and add your key:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace the placeholder:

```
GROQ_API_KEY=your_groq_api_key_here
```

Get a free key at: https://console.groq.com/keys

---

## Running the App

### 6. Start Flask

```powershell
python app.py
```

### 7. Open your browser

```
http://127.0.0.1:5000
```

---

## Model Configuration

The default model is `llama-3.3-70b-versatile` (free tier on Groq).

To change the model, edit `MODEL_NAME` at the top of `app.py`:

```python
MODEL_NAME = "llama-3.3-70b-versatile"
```

Other available Groq models: https://console.groq.com/docs/models

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GROQ_API_KEY is not set` | Create `.env` with your key (see step 5) |
| `API key is invalid` | Check your key at console.groq.com/keys — keys start with `gsk_` |
| `Rate limit reached` | Wait 60 seconds. Free tier has per-minute limits |
| `Model not available` | Change `MODEL_NAME` in `app.py` to a valid Groq model |
| `ModuleNotFoundError: groq` | Run `pip install -r requirements.txt` with venv active |
| `Could not reach the AI service` | Check your internet connection |
| Script execution policy error | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

---

## Project Structure

```
student-chatbot/
├── app.py                 # Flask backend + Groq integration
├── requirements.txt       # Python dependencies
├── .env                   # Your API key (never commit this)
├── .env.example           # Placeholder for version control
├── .gitignore
├── README.md
├── templates/
│   └── index.html         # App shell and chat UI
└── static/
    ├── css/
    │   └── style.css      # All styles (design tokens, layout, responsive)
    └── js/
        └── app.js         # Chat logic, markdown renderer, UI state
```

---

## Security Notes

- `.env` is in `.gitignore` — never commit it
- The API key is only used server-side in `app.py`
- No API keys appear in frontend code, HTML, or logs

---

## Usage Limits

Groq's free tier has rate limits and model availability that change over time. Check the current limits at [console.groq.com](https://console.groq.com). This app has no paid dependencies.
