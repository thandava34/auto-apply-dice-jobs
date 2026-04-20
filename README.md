# Dice Auto Apply Bot

Dice Auto Apply Bot is a Python-based application that automates your job application process on Dice.com. It leverages Selenium for web automation, BeautifulSoup for HTML parsing, and Tkinter for a user-friendly GUI.

## Features
- **🧠 AI Semantic Resume Matching:** Employs advanced NLP models (`sentence-transformers` / `all-MiniLM-L6-v2`) to deeply "understand" job descriptions and your resumes. Moves beyond basic keyword searches into proper semantic meaning (e.g. recognizing that "Data Engineer" concepts overlap heavily with "ETL Pipelines").
- **🤖 Continual AI Learning Engine:** A built-in local SQLite memory tracks your application history and incorporates manual teaching. The more you apply or submit mock JDs in the "AI Training" tab, the smarter the matching engine becomes.
- **🚀 Automated Job Search & Application:** Automatically searches for and safely applies to job listings using precise queries, handling captchas/timeouts gracefully, and accelerating through empty pages via early-exit mechanisms.
- **📁 Native OS Resume Uploads:** Effectively bypasses rigid Dice UI elements utilizing Python's PyAutoGUI to interact dynamically with your system's native file dialogs for fault-proof resume uploads.
- **📊 Detailed Logging & Auditing:** Comprehensive logs and complete Excel outputs for applied, failed, and excluded jobs. Features a dedicated "Skip Reason" column for extensive error auditing.
- **🛡️ Robust Synchronization:** Smart implicit wait times, background polling, and dynamic timeout handling designed for sluggish or unresponsive website pages without skipping jobs accidentally.
- **🖥️ Thread-Safe Responsive UI:** An expansive Tkinter application interface equipped with real-time logging, live AI learning metrics, embedded progress dashboards, and zero visual freezing.
- **🌍 Cross-Platform Compatibility:** Performs natively on Windows, macOS, and Linux, with smart automated browser profile detection.

## Demo Video

Watch a complete demonstration of how to set up and use the Dice Auto Apply Bot:

[![Watch the Demo Video](https://img.shields.io/badge/Watch-Demo_Video-red?style=for-the-badge&logo=google-drive&logoColor=white)](https://drive.google.com/file/d/1c0Y69PZ5UlFb3dZg0_-_wn7UibRQQwlW/view?usp=sharing)

The video shows step-by-step instructions for installation, configuration, and running the application on both Windows and Mac.

## Prerequisites
- Python 3.8+ installed.
- A web browser (preferably Brave Browser, but Chrome, Firefox, Edge or Safari will also work).
- Git (optional) if you wish to clone the repository.

---

## Project Structure

```
auto-apply-dice-jobs/
│
├── run.py                     # ← START HERE: Main entry point
├── app_tkinter.py             # Tkinter GUI application
├── fix_chromedriver.py        # Fixes webdriver permissions on Mac/Linux
├── test_ai_integration.py     # AI integration test script
├── requirements.txt           # Python dependencies
│
├── core/
│   ├── main_script.py         # Selenium automation & job application logic
│   ├── matcher.py             # TF-IDF + Jaccard resume scoring engine
│   ├── semantic_matcher.py    # AI semantic matching (sentence-transformers)
│   ├── learning_engine.py     # SQLite AI memory & training database
│   ├── browser_detector.py    # Auto-detects installed browsers
│   ├── dice_login.py          # Dice.com login automation
│   └── file_utils.py          # PDF/DOCX resume text extractor
│
├── config/
│   └── settings.json          # Your job search settings & resume profiles
│
├── utils/
│   ├── config_manager.py      # Settings read/write helper
│   └── log_manager.py         # Log file management
│
├── resources/
│   └── app_icon.png           # Application window icon
│
├── models/                    # ← Auto-created: AI model cache (~80MB, downloaded on first run)
├── data/                      # ← Auto-created: AI learning database (your private history)
├── logs/                      # ← Auto-created: Session log files
│
├── applied_jobs.xlsx          # ← Auto-created: Successfully applied jobs
├── not_applied_jobs.xlsx      # ← Auto-created: Skipped jobs with reasons
└── excluded_jobs.xlsx         # ← Auto-created: Keyword-excluded jobs
```

> **Note:** Files and folders marked **"Auto-created"** do not exist in the repo — the bot creates them automatically on first run. You do not need to create them manually.

---

## Installation

### Clone the Repository
Copy and run these commands:( Download Zip File)

```bash
git clone https://github.com/thandava34/auto-apply-dice-jobs.git
cd auto-apply-dice-jobs
```

### Create and Activate a Virtual Environment

#### For Windows
```bash
python -m venv venv
venv\Scripts\activate
```

#### For macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies
After activating your virtual environment, install the required packages. 

**📢 Note on AI Requirements:** This project now incorporates state-of-the-art AI semantic modeling using PyTorch and SentenceTransformers. The installation may take a few moments as these models are quite comprehensive.

```bash
pip install -r requirements.txt
```

*(Optional)* **For Mac users on Apple Silicon (M1/M2/M3):**
To ensure PyTorch utilizes hardware acceleration correctly, you may optionally install it manually *before* running `requirements.txt`:
```bash
pip install torch torchvision torchaudio
```

If your Python installation doesn't include Tkinter, install it using:

```bash
# For macOS
brew install python-tk

# For Ubuntu/Debian
sudo apt-get install python3-tk
```

## Running the Application

### For Windows
```bash
# Using the run script
python run.py

# Or directly
python app_tkinter.py
```

### For macOS / Linux
```bash
# Using the run script (recommended)
python3 run.py

# Or directly
python3 app_tkinter.py

# If you encounter permission issues with chromedriver
chmod +x run.py
./run.py
```

The run.py script automatically handles chromedriver permissions, which is particularly helpful for macOS users.

## Browser Configuration

The application will automatically detect your installed browsers in this preference order:
1. Brave Browser (recommended)
2. Google Chrome
3. Safari (macOS only)
4. Microsoft Edge
5. Firefox

If Brave Browser is installed, it will be used by default. If not, the application will fall back to the next available browser in the preference list.

## Using the Application

Once started, the GUI has 5 tabs: **Run Bot**, **Resumes**, **Settings**, **AI Training**, and **Logs**.

### Step 1 — Configure Settings
1. Navigate to the **Settings** tab.
2. Enter your **Dice.com email and password**, then click **Test Login** to verify your credentials.
3. Set your **Job Search Queries** (e.g. `Data Engineer`, `ETL Developer`).
4. Set **Include Keywords** (must appear in the job) and **Exclude Keywords** (instantly skip this job type).
5. Set the **Max Applications** limit for each run.
6. Click **Save Settings** to persist your configuration to `config/settings.json`.

---

### Step 2 — Creating & Managing Resume Profiles

The bot supports **multiple resume profiles**. Each profile maps a specific resume file to a set of targeted keywords. The AI uses these to pick the best resume for every job automatically.

#### ➕ Adding a New Profile
1. Navigate to the **Resumes** tab.
2. Click **Add Profile**.
3. Fill in the following fields:
   - **Profile Name** — A descriptive label (e.g. `Data Engineer`, `ML Engineer`). This name is compared against job titles for smart auto-selection.
   - **Resume File** — Click **Browse** to select your `.pdf` or `.docx` resume file.
   - **Unique Keywords** — Skills that are *specific* to this role and carry **3× weight** (e.g. `Airflow`, `dbt`, `Spark`). These are your strongest signals.
   - **General Keywords** — Broader skills at **1× weight** (e.g. `Python`, `SQL`, `AWS`).
   - **Boost Mode** — Controls how strongly the profile name influences resume selection:
     | Mode | Behaviour |
     |------|-----------|
     | `EXACT` | If the profile name matches the job title ≥ 60%, this resume is **auto-selected**, skipping all others. |
     | `HIGH` | Strong tiebreaker — name match adds up to 80% of the median keyword score as a bonus. |
     | `LOW` | Soft tiebreaker — name match adds up to 20% bonus. Keyword scoring still dominates. |
     | `OFF` | Pure keyword math only. Name is ignored entirely. |
4. Click **Save Profile**.

#### ✏️ Editing a Profile
- Select an existing profile from the list and click **Edit Profile** to update any field.

#### 🗑️ Deleting a Profile
- Select a profile and click **Delete Profile**. This also removes its associated AI training history from memory.

---

### Step 3 — Testing Resume Matching (Before Running the Bot)

You can dry-run the matching engine to verify the correct resume is being selected *before* starting the bot.

1. Navigate to the **AI Training** tab.
2. Paste any **real job description** from Dice into the large text area.
3. Click **🔍 Analyze JD**.
4. The AI will immediately propose the **best-matching resume profile** for that job, showing you:
   - Which profile was selected and why.
   - The keyword score breakdown (Unique vs. General keywords matched).
   - The Semantic Similarity percentage (AI conceptual match score).
5. You can then:
   - Click **✅ Approve match** — Confirms this was a good match and feeds it into AI memory as a training sample.
   - Click **❌ Not a fit** — Dismisses the suggestion without saving.

> **Tip:** This is the best way to verify your Unique Keywords are working correctly before sending the bot live.

---

### Step 4 — Training the AI

The AI Learning Engine improves over time by remembering which resumes worked for which types of jobs. There are two ways it learns:

#### 🤖 Automatic Learning (Passive)
Every time the bot **successfully submits an application**, it automatically records the job title and description into the local SQLite memory database (`data/learning_v3.db`). Future similar jobs will automatically receive a **+5 point learning boost** for that profile.

#### 🧑‍🏫 Manual Training (Active — Recommended for New Users)
You can teach the AI yourself using real job descriptions *before* even running the bot:

1. Navigate to the **AI Training** tab.
2. Find a job description on Dice that closely represents your ideal role.
3. **Paste the full job description** into the text area.
4. Select the **Target Profile** (which resume should be linked to this kind of job).
5. Click **🚀 Train AI on this Sample**.
6. The AI stores this as a `manual` training record and immediately confirms with a success message.

Repeat this with 5–10 ideal job descriptions per profile for best results. The **AI Memory Status** panel on the right shows a live count of how many lessons each profile has learned, split by `Manual` (your direct training) and `Auto` (bot-applied successes).

---

### Running the Bot
1. Go to the **Run Bot** tab.
2. Click **▶ Start** to begin the automated job search and application process.
3. Watch the **Live Log** panel for real-time status updates.
4. Use **⏸ Pause** or **⏹ Stop** at any time — the bot responds within a few seconds.

Results are saved automatically to:
| File | Contents |
|------|----------|
| `applied_jobs.xlsx` | Successfully submitted applications |
| `not_applied_jobs.xlsx` | Skipped jobs with the reason why |
| `excluded_jobs.xlsx` | Jobs filtered out by your exclude keywords |



---

## 🧠 How the Bot Picks a Resume (The Scoring Pipeline)

For every job it finds, the bot scores all of your resume profiles through **5 layers** and picks whichever has the **highest final score**. This all happens in under a second per job.

```
Final Score = Keyword Score + Name Boost + Semantic AI Score + Learning Boost
```

---

### Layer 1 — Keyword Scoring (the Foundation)

The bot scans the job description for every keyword defined in your profiles. Each match is scored using a **log-scale formula** that prevents keyword stuffing from unfairly dominating:

```
Unique keyword hit  →  3.0 × log₂(1 + times_found_in_JD)
General keyword hit →  1.0 × log₂(1 + times_found_in_JD)
```

**Example:**
- `Airflow` (Unique) appears 3 times → `3.0 × log₂(4) = 6.0 pts`
- `Python` (General) appears 5 times → `1.0 × log₂(6) = 2.58 pts`

> **Why log scale?** A word appearing 10 times shouldn't score 10× more than one appearing once. The logarithm dampens wild repetition so keyword-stuffed job descriptions don't skew results.

---

### Layer 2 — Name Affinity Boost (Boost Mode)

After keyword scoring, the bot compares your **profile name** against the **job title** to check for concept overlap. The effect depends on the **Boost Mode** you configure per profile:

| Mode | What Happens |
|------|---|
| `EXACT` | Name matches title ≥ 55% → **+9,999 points** instantly. That profile wins regardless of keyword scores. |
| `HIGH` | Adds up to **80% of the median keyword score** as a bonus. A strong nudge toward the name-matched profile. |
| `LOW` | Adds up to **20% of the median keyword score**. Keywords still dominate; name is a soft hint. |
| `OFF` | Profile name is completely ignored. Pure keyword math decides. |

> **Example:** Job title is *"Senior Azure Data Engineer"* and profile name is *"Data Engineer"* → they share "Data" + "Engineer" → high affinity → `HIGH` mode gives a meaningful bonus.

---

### Layer 3 — Semantic AI Score (Conceptual Match)

If the AI model (`all-MiniLM-L6-v2`) loaded successfully, it converts the **full job description** and each **resume file's text** into dense mathematical vectors (embeddings) and computes their cosine similarity (0–100%).

```
Semantic bonus = semantic_similarity% × 0.30
```

So if your resume is 70% conceptually similar to the JD → **+21 points** added to that profile's score.

> **Why only 30%?** The semantic score acts as a *booster*, not a decision maker. If your keywords are strong, they still lead. The AI fills the gap when two profiles have similar keyword counts but very different resume content.

> **Note:** If the model hasn't finished downloading or fails to load, the bot gracefully falls back to keyword-only scoring — no crash, no skipped jobs.

---

### Layer 4 — Learning Boost (AI Memory)

If a profile has **any past successful applications** recorded in AI memory (from the bot running automatically, or from your manual training in the AI Training tab), it receives a flat **+5 point reliability bonus**.

This nudges proven, battle-tested profiles ahead when scores are otherwise very close.

---

### Layer 5 — Final Ranking & Resume Selection

All profiles are sorted by total score (descending). The bot picks **#1** and uploads that resume file to Dice.

#### Real-World Example

Two profiles — *"Data Engineer"* and *"ML Engineer"* — evaluated for job *"Data Engineer - Spark/Airflow"*:

| | Data Engineer Profile | ML Engineer Profile |
|---|---|---|
| **Keyword Score** | 28.5 (Airflow ✓, Spark ✓, Python ✓) | 12.1 (Python ✓ only) |
| **Name Boost** (`HIGH`) | +18.0 (strong title match) | +2.0 (weak match) |
| **Semantic AI Score** | +19.5 (resume text conceptually close) | +8.4 |
| **Learning Boost** | +5.0 (has past AI-memory successes) | +0.0 |
| **Total Score** | **71.0 ✅ Winner** | **22.5** |

**→ The "Data Engineer" resume is uploaded for this job.**

The breakdown for every job is printed live in the **Logs** tab so you can verify the AI's reasoning in real time.

---

## Troubleshooting

- **Slow Login Issues:**  
  The application has been updated to handle slower login processes. If you still experience issues, try increasing timeouts in the settings.

- **WebDriver Issues:**  
  The application uses `webdriver_manager` to handle drivers automatically. If you encounter issues, try running `run.py` which fixes common permission issues.

- **Browser Detection Problems:**  
  If your browser isn't being detected correctly, you can manually specify the browser path in the .env file.

## Contributing
Feel free to fork this repository and submit pull requests for improvements, additional features, or bug fixes.

## Support
If you find this project useful, please consider supporting its development:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/yuvarajareddy)
