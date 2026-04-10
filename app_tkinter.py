# dice_auto_apply/app_tkinter.py
"""
Dice Auto Apply Bot - Main GUI Application
==========================================

This module contains the primary Tkinter graphical user interface and the core orchestration 
logic for the Dice Auto Apply Bot.

Key Integrated Features & Architectural Overview:
-------------------------------------------------
1. Automated Job Search & Application:
   - Polls Dice for job URLs and manages automated Selenium interactions to apply to jobs.
   - Includes early-exit mechanisms to prevent 60-second timeouts on empty pages.

2. Advanced Resume Matching Engine (Semantic & Hierarchical):
   - Uses `SemanticResumeMatcher` (TF-IDF inspired) to find the best resume for the job description.
   - Boost modes (exact, high, low, off) let users prioritize specific resumes for distinct job roles.
   
3. Native OS Resume Uploads (Safe PyAutoGUI Integration):
   - Directly bypasses rigid Dice file-upload blocking screens by invoking native OS file dialogs via PyAutoGUI.
   - Fallback mechanisms handle edge case UI changes reliably.

4. Comprehensive Logging & Skip Reasoning:
   - Maintains robust records in `applied_jobs.xlsx`, `not_applied_jobs.xlsx`, and `excluded_jobs.xlsx`.
   - "Skip Reason" is captured intelligently on application failure (e.g., Timeout, Missing fields, Auth Issue).
   
5. Robust Exception Handling & Thread-Safe UI:
   - GUI runs on the main thread, while the Selenium application logic (`job_thread`) runs concurrently.
   - Frequent checks ensure pause and stop responsiveness (Cascading Resume Deletion fixes).
   - Real-time AI learning tracking mechanisms distinguish manual UI events from automatic model runs safely.

6. Profile ID Type-Safety & Path Normalization:
   - Resume profiles have unique IDs that avoid bugs where similarly named profiles clash. 
   - OS file paths are normalized seamlessly between Windows/Mac paths.
"""


import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import pandas as pd
from datetime import datetime
import time
import logging
import pyautogui
import subprocess

# Try both absolute and relative imports for compatibility
try:
    from core.browser_detector import get_browser_path
    from core.dice_login import login_to_dice, update_dice_credentials, validate_dice_credentials
    from core.main_script import get_web_driver, fetch_jobs_with_requests, apply_to_job_url
    from core.semantic_matcher import SemanticResumeMatcher
except ImportError:
    # Attempt parent-directory relative imports if normal ones fail
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from core.browser_detector import get_browser_path
    from core.dice_login import login_to_dice, update_dice_credentials, validate_dice_credentials
    from core.main_script import get_web_driver, fetch_jobs_with_requests, apply_to_job_url
    from core.semantic_matcher import SemanticResumeMatcher



def fix_imports():
    """Fix imports for both development and packaged environments"""
    import os
    import sys
    
    # Add the parent directory to the path if not already there
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

# Call this at the beginning of your script
fix_imports()

class DiceAutoBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dice Auto Apply Bot")
        
        # Prevent the window from silently shrinking if monitor resolution is 1366x768 or scaled
        self.root.geometry("1100x820")
        
        # Override rigid native OS themes with 'clam' so custom padding and fonts reliably work
        style = ttk.Style()
        style.theme_use('clam')

        # ── Rich global styles ───────────────────────────────────────────────
        BASE_FONT  = ("Segoe UI", 10)
        BOLD_FONT  = ("Segoe UI", 10, "bold")
        SMALL_FONT = ("Segoe UI", 8)

        style.configure(".",            font=BASE_FONT)
        style.configure("TLabel",       font=BASE_FONT, padding=2)
        style.configure("TEntry",       padding=4)
        style.configure("TButton",      padding=(8, 4), font=BASE_FONT)
        style.configure("TLabelframe",  padding=6)
        style.configure("TLabelframe.Label", font=BOLD_FONT)
        style.configure("TNotebook.Tab", padding=[18, 7], font=BOLD_FONT, background="#e8e8e8")
        style.map("TNotebook.Tab",      background=[("selected", "#d0e8ff")])
        style.configure("Treeview",     rowheight=28, font=BASE_FONT)
        style.configure("Treeview.Heading", font=BOLD_FONT, background="#d0d0d0")
        style.configure("Horizontal.TProgressbar", background="#28a745", troughcolor="#e9ecef")
        
        # Set app icon if available
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "resources", "app_icon.png")
            if os.path.exists(icon_path):
                # For Windows
                if sys.platform == 'win32':
                    self.root.iconbitmap(icon_path)
                # For macOS and others that support .png icons
                else:
                    img = tk.PhotoImage(file=icon_path)
                    self.root.iconphoto(True, img)
        except Exception as e:
            pass
        
        # Disable PyAutoGUI failsafe
        pyautogui.FAILSAFE = False
        
        # Configure logging
        self.setup_logging()
        
        # Initialize variables
        self.driver = None
        self.job_thread = None
        self.running = False
        self.is_paused = False
        
        # Load configuration if exists
        self.next_id = 1
        
        # Initialize AI components early
        from core.learning_engine import LearningEngine
        self.learning_engine = LearningEngine()
        self.semantic_matcher = None # Delayed init until config is loaded
        self.ai_loading = False
        
        self.load_config()
        
        # Create the tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tab frames
        self.main_tab = ttk.Frame(self.notebook)
        self.resumes_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)
        self.ai_trainer_tab = ttk.Frame(self.notebook)
        self.logs_tab = ttk.Frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.main_tab, text="Run Bot")
        self.notebook.add(self.resumes_tab, text="Resumes")
        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.ai_trainer_tab, text="AI Training")
        self.notebook.add(self.logs_tab, text="Logs")
        
        # Set up UI for each tab
        self.setup_main_tab()
        self.setup_resumes_tab()
        self.setup_settings_tab()
        self.setup_ai_trainer_tab()
        self.setup_logs_tab()
        
        # Log that app is started
        self.logger.info("Application started")
        
    def setup_logging(self):
        """Set up logging for the application"""
        # Create logs directory if needed
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        # Create log filename with timestamp
        log_file = os.path.join(logs_dir, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        # Configure logging
        # Use UTF-8 on the stream handler so emoji/unicode in log messages
        # don't crash on Windows terminals that default to cp1252.
        import io
        utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(utf8_stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_config(self):
        """Load configuration from config file"""
        self.config_dir = os.path.join(os.path.dirname(__file__), "config")
        self.config_file = os.path.join(self.config_dir, "settings.json")
        
        # Default values
        self.search_queries = ["AI ML", "Gen AI", "Agentic AI", "Data Engineer", "Data Analyst", "Machine Learning"]
        self.exclude_keywords = ["Manager", "Director",".net", "SAP","java","w2 only","only w2","no c2c",
        "only on w2","w2 profiles only","tester","f2f"]
        self.include_keywords = ["AI", "Artificial","Inteligence","Machine","Learning", "ML", "Data", "NLP", "ETL",
        "Natural Language Processing","analyst","scientist","senior","cloud", 
        "aws","gcp","Azure","agentic","python","rag","llm"]
        self.headless_mode = False
        self.job_limit = 1500
        self.resume_profiles = []
        self.editing_idx = None  # Track index of profile being edited
        self.profile_name_boost_mode = 'off'  # Default: disabled until user enables per-profile
        self.semantic_enabled = True # New feature enabled by default
        
        # Try to load from file if it exists
        import json
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.search_queries = config.get('search_queries', self.search_queries)
                    self.exclude_keywords = config.get('exclude_keywords', self.exclude_keywords)
                    self.include_keywords = config.get('include_keywords', self.include_keywords)
                    self.headless_mode = config.get('headless_mode', self.headless_mode)
                    self.job_limit = config.get('job_application_limit', self.job_limit)
                    self.resume_profiles = config.get('resume_profiles', self.resume_profiles)
                    # Assign unique IDs to profiles for reliable GUI management
                    for p in self.resume_profiles:
                        if 'id' not in p:
                            p['id'] = self.next_id
                        self.next_id = max(self.next_id, p.get('id', 0) + 1)
                    
                    self.profile_name_boost_mode = config.get('profile_name_boost_mode', 'high')
                    self.semantic_enabled = config.get('semantic_enabled', True)
                    
                    # Initialize Semantic Matcher in BACKGROUND if enabled
                    if self.semantic_enabled and self.resume_profiles:
                        self.ai_loading = True
                        threading.Thread(target=self._init_ai_async, daemon=True).start()
                    
                    self.logger.info("Configuration loaded successfully")
            except Exception as e:
                self.logger.error(f"Error loading configuration: {e}")
        
    def _init_ai_async(self):
        """Initializes the AI Semantic Matcher in the background to avoid GUI freeze"""
        try:
            self.root.after(0, lambda: self.update_status("[AI] Matcher is initializing in background..."))
            
            # This triggers the 80MB download if not present.
            # We already imported SemanticResumeMatcher at the top level to avoid thread-init issues.
            matcher = SemanticResumeMatcher(self.resume_profiles)
            
            def _on_complete():
                self.semantic_matcher = matcher
                self.ai_loading = False
                # Log directly — avoids nesting another root.after() inside an
                # already-scheduled callback, which causes 'main thread is not
                # in main loop' on some Python/Tk builds.
                msg = "[AI] Semantic Matcher initialized and ready."
                self.logger.info(msg)
                try:
                    self.status_label.config(text=msg)
                except Exception:
                    pass
                try:
                    self.refresh_ai_stats()
                except Exception:
                    pass
            
            self.root.after(0, _on_complete)
            
        except Exception as e:
            err_str = str(e)
            def _on_error(err_msg=err_str):
                self.ai_loading = False
                # Strip emoji from the console-bound log message to guarantee
                # encoding safety, then update the Tkinter label directly.
                safe_msg = f"Background AI Init failed: {err_msg}"
                self.logger.error(safe_msg)
                try:
                    short = err_msg[:50]
                    self.status_label.config(text=f"AI Matcher failed to load: {short}...")
                except Exception:
                    pass
            
            self.root.after(0, _on_error)

    def _persist_config(self):
        """
        Low-level disk write — uses ONLY the in-memory instance attributes,
        NOT widget .get() calls.  Safe to call from any tab at any time.
        """
        import json
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
            
        # Pull current widget values where they exist, fall back to stored attrs
        def _safe_get(attr, widget_attr=None, default=None):
            if widget_attr and hasattr(self, widget_attr):
                try:
                    val = getattr(self, widget_attr).get()
                    if val is not None:
                        return val
                except Exception:
                    pass
            return getattr(self, attr, default)

        profiles = getattr(self, 'resume_profiles', [])
        config = {
            'search_queries':    [q.strip() for q in _safe_get('search_queries', 'search_query_entry', '') .replace('', '').split(',') if q.strip()] if isinstance(_safe_get('search_queries', 'search_query_entry', ''), str) else getattr(self, 'search_queries', []),
            'exclude_keywords':  [k.strip() for k in _safe_get('exclude_keywords', 'exclude_keywords_entry', '').split(',') if k.strip()] if isinstance(_safe_get('exclude_keywords', 'exclude_keywords_entry', ''), str) else getattr(self, 'exclude_keywords', []),
            'include_keywords':  [k.strip() for k in _safe_get('include_keywords', 'include_keywords_entry', '').split(',') if k.strip()] if isinstance(_safe_get('include_keywords', 'include_keywords_entry', ''), str) else getattr(self, 'include_keywords', []),
            'headless_mode':     _safe_get('headless_mode', 'headless_var', False),
            'job_application_limit': _safe_get('job_limit', 'job_limit_var', 1500),
            'resume_profiles':   profiles,
            'profile_name_boost_mode': (
                getattr(self, 'name_boost_var', None) and
                self.name_boost_var.get().split('|')[0].strip().lower()
            ) or getattr(self, 'profile_name_boost_mode', 'off'),
            'semantic_enabled': _safe_get('semantic_enabled', 'semantic_var', True),
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            self.logger.info(f"Configuration persisted to disk. Profiles count: {len(profiles)}")
        except Exception as e:
            self.logger.error(f"Failed to persist configuration: {e}")

    def save_config(self, silent: bool = False):
        """Save configuration to config file (reads widgets + writes disk)."""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        import json
        try:
            # Read from all widgets (only call this when all tabs are initialised)
            config = {
                'search_queries':    [q.strip() for q in self.search_query_entry.get().split(',') if q.strip()],
                'exclude_keywords':  [k.strip() for k in self.exclude_keywords_entry.get().split(',') if k.strip()],
                'include_keywords':  [k.strip() for k in self.include_keywords_entry.get().split(',') if k.strip()],
                'headless_mode':     self.headless_var.get(),
                'job_application_limit': self.job_limit_var.get(),
                'resume_profiles':   self.resume_profiles,
                'profile_name_boost_mode': self.name_boost_var.get().split('|')[0].strip().lower(),
                'semantic_enabled': self.semantic_var.get(),
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)

            # Persist .env credentials
            username = self.username_entry.get()
            password = self.password_entry.get()
            if username and password:
                update_dice_credentials(username, password)

            if not silent:
                messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")
            self.logger.info("Settings saved successfully")

        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            # Fallback: write what we can from in-memory state
            try:
                self._persist_config()
                self.logger.info("Settings saved via fallback persist")
            except Exception as e2:
                self.logger.error(f"Fallback persist also failed: {e2}")
                if not silent:
                    messagebox.showerror("Error", f"Could not save settings: {str(e)}")

            self.logger.error(f"Error saving configuration: {e}")
            messagebox.showerror("Error", f"Could not save settings: {str(e)}")
        
    def calculate_time_estimate(self, jobs_count):
        """Calculate and display estimated completion time based on job count"""
        # Calculate based on historical data or defaults
        # Average time per job is around 10 seconds, but can vary
        avg_job_time = 10  # seconds
        total_seconds = jobs_count * avg_job_time
        
        # Add overhead time for initialization, etc.
        overhead_seconds = 60  # 1 minute overhead
        
        total_seconds += overhead_seconds
        
        # Calculate hours, minutes, seconds
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Create time string
        time_str = ""
        if hours > 0:
            time_str += f"{int(hours)} hours "
        if minutes > 0 or hours > 0:
            time_str += f"{int(minutes)} minutes "
        time_str += f"{int(seconds)} seconds"
        
        # Update UI with estimate
        self.update_status(f"Estimated completion time: {time_str}")
        return time_str

    def setup_main_tab(self):
        """Set up the main tab UI — compact, responsive layout."""
        style = ttk.Style()

        # ── Inputs ───────────────────────────────────────────────────────────
        input_frame = ttk.LabelFrame(self.main_tab, text="Search & Filter")
        input_frame.pack(fill="x", padx=10, pady=(8, 4))
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(3, weight=1)

        ttk.Label(input_frame, text="Job Titles:").grid(row=0, column=0, sticky="w", padx=(8,4), pady=4)
        self.search_query_entry = ttk.Entry(input_frame)
        self.search_query_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=4)
        self.search_query_entry.insert(0, ", ".join(self.search_queries))

        ttk.Label(input_frame, text="Exclude:").grid(row=1, column=0, sticky="w", padx=(8,4), pady=4)
        self.exclude_keywords_entry = ttk.Entry(input_frame)
        self.exclude_keywords_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        self.exclude_keywords_entry.insert(0, ", ".join(self.exclude_keywords))

        ttk.Label(input_frame, text="Include:").grid(row=1, column=2, sticky="w", padx=(12,4), pady=4)
        self.include_keywords_entry = ttk.Entry(input_frame)
        self.include_keywords_entry.grid(row=1, column=3, sticky="ew", padx=4, pady=4)
        self.include_keywords_entry.insert(0, ", ".join(self.include_keywords))

        # ── Action buttons ───────────────────────────────────────────────────
        btn_frame = ttk.Frame(self.main_tab)
        btn_frame.pack(fill="x", padx=10, pady=4)
        btn_frame.columnconfigure(0, weight=3)
        btn_frame.columnconfigure(1, weight=1)

        style.configure("Start.TButton",
            background="#28a745", foreground="white",
            font=("Segoe UI", 12, "bold"), padding=(10, 6)
        )
        style.map("Start.TButton", background=[("active", "#218838"), ("disabled", "#94d3a2")])
        style.configure("Stop.TButton",
            background="#dc3545", foreground="white",
            font=("Segoe UI", 10, "bold"), padding=(6, 6)
        )
        style.map("Stop.TButton", background=[("active", "#c82333"), ("disabled", "#e8a0a7")])

        self.start_button = ttk.Button(
            btn_frame, text="▶  Start Applying", command=self.start_applying, style="Start.TButton"
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=2)

        self.stop_button = ttk.Button(
            btn_frame, text="■  Stop", command=self.stop_applying, style="Stop.TButton", state="disabled"
        )
        self.stop_button.grid(row=0, column=2, sticky="ew", pady=2)
        
        self.pause_button = ttk.Button(
            btn_frame, text="⏸  Pause", command=self.toggle_pause, state="disabled"
        )
        self.pause_button.grid(row=0, column=1, sticky="ew", padx=6, pady=2)

        # ── Progress ─────────────────────────────────────────────────────────
        progress_frame = ttk.LabelFrame(self.main_tab, text="Progress")
        progress_frame.pack(fill="x", padx=10, pady=4)

        self.status_label = ttk.Label(progress_frame, text="Ready to start.", font=("Segoe UI", 9))
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=8, pady=(2, 4))

        # ── Stats row (colored badge-style labels) ────────────────────────────
        stats_frame = ttk.Frame(self.main_tab)
        stats_frame.pack(fill="x", padx=10, pady=2)
        for col in range(4):
            stats_frame.columnconfigure(col, weight=1)

        def _stat_badge(parent, col, label_text, initial="0", bg="#e9ecef", fg="#212529"):
            f = tk.Frame(parent, bg=bg, bd=0, highlightthickness=1, highlightbackground="#ced4da")
            f.grid(row=0, column=col, sticky="ew", padx=4, pady=2)
            tk.Label(f, text=label_text, bg=bg, fg="#555", font=("Segoe UI", 8)).pack(pady=(4,0))
            val = tk.Label(f, text=initial, bg=bg, fg=fg, font=("Segoe UI", 16, "bold"))
            val.pack(pady=(0,4))
            return val

        self.jobs_found_label   = _stat_badge(stats_frame, 0, "Total Jobs",    bg="#e8f4fd", fg="#0d6efd")
        self.jobs_applied_label = _stat_badge(stats_frame, 1, "Applied",       bg="#d4edda", fg="#155724")
        self.jobs_failed_label  = _stat_badge(stats_frame, 2, "Failed",        bg="#f8d7da", fg="#721c24")
        self.estimated_time_label = _stat_badge(stats_frame, 3, "Est. Time", initial="--", bg="#fff3cd", fg="#856404")

        # ── Excel quick-open buttons ──────────────────────────────────────────
        excel_frame = ttk.LabelFrame(self.main_tab, text="Quick Open")
        excel_frame.pack(fill="x", padx=10, pady=4)
        ef = ttk.Frame(excel_frame)
        ef.pack(fill="x", padx=5, pady=4)
        ttk.Button(ef, text="✔ Applied Jobs",     command=lambda: self.open_excel_file("applied_jobs.xlsx")).pack(side="left", padx=5)
        ttk.Button(ef, text="✘ Not Applied",      command=lambda: self.open_excel_file("not_applied_jobs.xlsx")).pack(side="left", padx=5)
        ttk.Button(ef, text="⊘ Excluded Jobs",    command=lambda: self.open_excel_file("excluded_jobs.xlsx")).pack(side="left", padx=5)

        # ── Live log ─────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self.main_tab, text="Live Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(4, 8))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=8, wrap=tk.WORD, font=("Consolas", 8),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text.config(state="disabled")

        self.log_handler = LogTextHandler(self.log_text)
        self.log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.log_handler.setFormatter(formatter)
        self.logger.addHandler(self.log_handler)

    def open_excel_file(self, filename):
        """Open an Excel file using the system default application"""
        try:
            if not os.path.exists(filename):
                if filename == "excluded_jobs.xlsx":
                    # Create the file if it doesn't exist
                    df = pd.DataFrame(columns=["Job Title", "Job URL", "Company", "Location", "Employment Type", "Posted Date", "Exclusion Reason"])
                    df.to_excel(filename, index=False)
                    self.logger.info(f"Created new {filename} file")
                else:
                    messagebox.showinfo("File Not Found", f"The file {filename} does not exist yet.")
                    return
                    
            # Open the file with the default system application
            if sys.platform == "win32":
                os.startfile(filename)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", filename])
            else:  # Linux
                subprocess.run(["xdg-open", filename])
                
            self.logger.info(f"Opened {filename}")
        except Exception as e:
            self.logger.error(f"Error opening {filename}: {e}")
            messagebox.showerror("Error", f"Could not open {filename}: {str(e)}")

    def setup_resumes_tab(self):
        """Set up the resumes tab UI with flexible paned layout"""
        style = ttk.Style()
        style.configure("Treeview", rowheight=30)

        # Main Paned window (Vertical split)
        self.resume_paned = ttk.Panedwindow(self.resumes_tab, orient="vertical")
        self.resume_paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Top Pane: Treeview Container
        tree_container = ttk.LabelFrame(self.resume_paned, text="Resume Profiles")
        self.resume_paned.add(tree_container, weight=3)

        tree_frame = ttk.Frame(tree_container)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # --- Search Bar Implementation ---
        search_frame = ttk.Frame(tree_frame)
        search_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(search_frame, text="🔍 Search:").pack(side="left", padx=(0, 5))
        self.resume_search_var = tk.StringVar()
        self.resume_search_entry = ttk.Entry(search_frame, textvariable=self.resume_search_var)
        self.resume_search_entry.pack(side="left", fill="x", expand=True)
        
        def _on_search_key(event):
            self.refresh_resume_list(self.resume_search_var.get())
        self.resume_search_entry.bind("<KeyRelease>", _on_search_key)

        tree_scroll_y = ttk.Scrollbar(tree_frame)
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree_scroll_x.pack(side="bottom", fill="x")

        columns = ("#", "ID", "Name", "Boost", "Unique Keywords", "General Keywords", "File Path")
        self.resume_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set
        )

        self.resume_tree.heading("#",               text="#")
        self.resume_tree.heading("Name",             text="Profile Name")
        self.resume_tree.heading("Boost",            text="Boost Mode")
        self.resume_tree.heading("Unique Keywords",  text="Unique/Priority")
        self.resume_tree.heading("General Keywords", text="General Skills")
        self.resume_tree.heading("File Path",        text="Local Path")

        self.resume_tree.column("#",               width=35,  minwidth=35,  stretch=tk.NO,  anchor="center")
        self.resume_tree.column("ID",              width=0,   minwidth=0,   stretch=tk.NO) # Hidden ID
        self.resume_tree.column("Name",             width=160, minwidth=120, stretch=tk.YES, anchor="w")
        self.resume_tree.column("Boost",            width=80,  minwidth=70,  stretch=tk.NO,  anchor="center")
        self.resume_tree.column("Unique Keywords",  width=300, minwidth=200, stretch=tk.YES, anchor="w")
        self.resume_tree.column("General Keywords", width=300, minwidth=200, stretch=tk.YES, anchor="w")
        self.resume_tree.column("File Path",        width=300, minwidth=200, stretch=tk.YES, anchor="w")

        self.resume_tree.tag_configure("boost_exact", background="#fff3cd", foreground="#7d5a00")
        self.resume_tree.tag_configure("boost_high",  background="#d4edda", foreground="#155724")
        self.resume_tree.tag_configure("boost_low",   background="#d1ecf1", foreground="#0c5460")
        self.resume_tree.tag_configure("boost_off",   background="#f8f9fa", foreground="#6c757d")

        self.resume_tree.pack(side="left", fill="both", expand=True)
        tree_scroll_y.config(command=self.resume_tree.yview)
        tree_scroll_x.config(command=self.resume_tree.xview)
        self.resume_tree.bind("<<TreeviewSelect>>", self.on_resume_select)

        self.profile_count_label = ttk.Label(tree_container, text="Total Profiles: 0")
        self.profile_count_label.pack(anchor="e", padx=10, pady=(0, 2))

        # Bottom Pane: Form Container
        self.form_container = ttk.LabelFrame(self.resume_paned, text="Edit Profile Details")
        self.resume_paned.add(self.form_container, weight=1)

        form_frame = ttk.Frame(self.form_container)
        form_frame.pack(fill="x", padx=10, pady=5)
        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(3, weight=1)

        # Row 0: Name and Boost
        ttk.Label(form_frame, text="Profile Name:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.resume_name_entry = ttk.Entry(form_frame)
        self.resume_name_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        ttk.Label(form_frame, text="Boost Level:").grid(row=0, column=2, sticky="w", padx=(20, 2), pady=2)
        self.profile_boost_var = tk.StringVar(value="off")
        PROFILE_BOOST_OPTIONS  = ["exact", "high", "low", "off"]
        self.profile_boost_combo = ttk.Combobox(
            form_frame, textvariable=self.profile_boost_var,
            values=PROFILE_BOOST_OPTIONS, state="readonly", width=10
        )
        self.profile_boost_combo.grid(row=0, column=3, sticky="w", padx=2, pady=2)

        self.boost_color_label = tk.Label(
            form_frame, text="  OFF  ", bg="#f8f9fa", fg="#6c757d",
            font=("Segoe UI", 8, "bold"), relief="solid", bd=1
        )
        self.boost_color_label.grid(row=0, column=4, padx=8, pady=2)

        def _on_boost_change(e=None):
            m = self.profile_boost_var.get()
            bg={"exact":"#fff3cd", "high":"#d4edda", "low":"#d1ecf1", "off":"#f8f9fa"}
            fg={"exact":"#7d5a00", "high":"#155724", "low":"#0c5460", "off":"#6c757d"}
            self.boost_color_label.config(text=f"  {m.upper()}  ", bg=bg.get(m,"#f8f9fa"), fg=fg.get(m,"#333"))
        self.profile_boost_combo.bind("<<ComboboxSelected>>", _on_boost_change)

        # Row 1: Unique Keywords
        ttk.Label(form_frame, text="Priority Skills:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.resume_unique_keywords_entry = ttk.Entry(form_frame)
        self.resume_unique_keywords_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=2, pady=2)

        # Row 2: General Keywords
        ttk.Label(form_frame, text="General Skills:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.resume_keywords_entry = ttk.Entry(form_frame)
        self.resume_keywords_entry.grid(row=2, column=1, columnspan=4, sticky="ew", padx=2, pady=2)

        # Row 3: File Path
        ttk.Label(form_frame, text="Resume File:").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.resume_path_entry = ttk.Entry(form_frame)
        self.resume_path_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=2, pady=2)
        ttk.Button(form_frame, text="📁 Browse", command=self.browse_resume_file).grid(row=3, column=4, padx=5, pady=2)

        # Actions
        action_outer = ttk.Frame(self.form_container)
        action_outer.pack(fill="x", padx=10, pady=(5, 10))
        
        self.add_update_btn = ttk.Button(action_outer, text="✚ Add New Profile", command=self.add_resume_profile, style="Start.TButton")
        self.add_update_btn.pack(side="left", padx=5)
        
        ttk.Button(action_outer, text="↺ Clear / New", command=self.clear_resume_form).pack(side="left", padx=5)
        ttk.Button(action_outer, text="🗑 Delete Selected", command=self.delete_resume_profile).pack(side="left", padx=5)
        
        ttk.Button(action_outer, text="⚙ Test Matcher", command=self.open_test_simulator).pack(side="right", padx=5)

        self.refresh_resume_list()

    def refresh_resume_list(self, search_query=""):
        for item in self.resume_tree.get_children():
            self.resume_tree.delete(item)

        TAG_MAP = {"exact": "boost_exact", "high": "boost_high", "low": "boost_low", "off": "boost_off"}

        profiles = getattr(self, "resume_profiles", [])
        
        # Always sort alphabetically by name (in-place)
        profiles.sort(key=lambda x: str(x.get("name", "")).lower())
        
        query = str(search_query).strip().lower()
        
        display_count = 0
        for i, profile in enumerate(profiles, start=1):
            name            = str(profile.get("name", ""))
            uni_kws         = ", ".join(profile.get("unique_keywords", []))
            gen_kws         = ", ".join(profile.get("keywords", []))
            file_path       = str(profile.get("file_path", ""))
            
            # Filtering logic
            if query:
                match_found = (
                    query in name.lower() or
                    query in uni_kws.lower() or
                    query in gen_kws.lower() or
                    query in file_path.lower()
                )
                if not match_found:
                    continue

            display_count += 1
            mode = profile.get("boost_mode", "high")
            tag  = TAG_MAP.get(mode, "boost_high")
            self.resume_tree.insert("", "end", tags=(tag,), values=(
                str(display_count),
                str(profile.get("id", "")),
                name,
                mode.upper(),
                uni_kws,
                gen_kws,
                file_path
            ))

        if hasattr(self, 'profile_count_label'):
            if query:
                self.profile_count_label.config(text=f"Showing: {display_count} / {len(profiles)}")
            else:
                self.profile_count_label.config(text=f"Total Profiles: {len(profiles)}")

    def clear_resume_form(self):
        """Reset the profile form and selection state"""
        self.resume_tree.selection_remove(self.resume_tree.selection())
        self.editing_idx = None
        self.editing_id  = None
        self.resume_name_entry.delete(0, tk.END)
        self.resume_unique_keywords_entry.delete(0, tk.END)
        self.resume_keywords_entry.delete(0, tk.END)
        self.resume_path_entry.delete(0, tk.END)
        self.profile_boost_var.set("off")
        self.boost_color_label.config(text="  OFF  ", bg="#f8f9fa", fg="#6c757d")
        if hasattr(self, 'add_update_btn'):
            self.add_update_btn.config(text="✚ Add New Profile")

        self.sync_trainer_profiles()

    def on_resume_select(self, event):
        selected = self.resume_tree.selection()
        if not selected:
            return

        item_id = selected[0]
        item    = self.resume_tree.item(item_id)
        values  = item.get("values", [])
        
        # Use the hidden ID to find the correct profile in the internal list
        try:
            profile_id = int(values[1])
        except (ValueError, IndexError):
            self.logger.error("Could not determine ID of selected profile")
            return
            
        profiles = getattr(self, "resume_profiles", [])
        self.editing_idx = None
        self.editing_id  = profile_id
        
        for idx, p in enumerate(profiles):
            if int(p.get("id", -1)) == profile_id:
                self.editing_idx = idx
                break
        
        if self.editing_idx is None:
            self.logger.warning(f"UI: Could not find original profile for ID: {profile_id}")
            return
            
        p = profiles[self.editing_idx]

        if len(values) >= 6:
            self.resume_name_entry.delete(0, tk.END)
            # Use columns indices correctly (ID was inserted at [1], so Name is at [2])
            self.resume_name_entry.insert(0, str(values[2]))
            
            if hasattr(self, 'add_update_btn'):
                self.add_update_btn.config(text="💾 Update Selected Profile")

            # Restore boost mode dropdown
            mode = str(values[3]).strip().lower()
            if mode in ("exact", "high", "low", "off"):
                self.profile_boost_var.set(mode)
                bg={"exact":"#fff3cd", "high":"#d4edda", "low":"#d1ecf1", "off":"#f8f9fa"}
                fg={"exact":"#7d5a00", "high":"#155724", "low":"#0c5460", "off":"#6c757d"}
                self.boost_color_label.config(text=f"  {mode.upper()}  ", bg=bg.get(mode,"#f8f9fa"), fg=fg.get(mode,"#333"))

            self.resume_unique_keywords_entry.delete(0, tk.END)
            val_uni = str(values[4]) if values[4] != "None" else ""
            self.resume_unique_keywords_entry.insert(0, val_uni)

            self.resume_keywords_entry.delete(0, tk.END)
            val_gen = str(values[5]) if values[5] != "None" else ""
            self.resume_keywords_entry.insert(0, val_gen)

            self.resume_path_entry.delete(0, tk.END)
            self.resume_path_entry.insert(0, str(values[6]))

    def browse_resume_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF/Word Documents", "*.pdf *.docx *.doc")])
        if file_path:
            # Normalize to OS-native separators (important for Windows path pasting)
            normalized_path = os.path.normpath(file_path)
            self.resume_path_entry.delete(0, tk.END)
            self.resume_path_entry.insert(0, normalized_path)
            # Scroll to the end of the entry so users can see the filename
            self.resume_path_entry.xview_moveto(1)

    def add_resume_profile(self):
        name          = self.resume_name_entry.get().strip()
        unique_kws_str= self.resume_unique_keywords_entry.get().strip()
        keywords_str  = self.resume_keywords_entry.get().strip()
        file_path     = self.resume_path_entry.get().strip()
        boost_mode    = self.profile_boost_var.get().strip().lower()

        if not name or not file_path:
            messagebox.showwarning("Missing Fields", "Please provide a Name and a File Path.")
            return
        if not os.path.exists(file_path):
            messagebox.showwarning("File Not Found", f"The file could not be found: {file_path}")
            return

        unique_keywords = [k.strip() for k in unique_kws_str.split(",") if k.strip()]
        keywords        = [k.strip() for k in keywords_str.split(",")  if k.strip()]

        if not hasattr(self, "resume_profiles"):
            self.resume_profiles = []

        # If we are editing, update the profile at that index
        target_profile = None
        if hasattr(self, 'editing_id') and self.editing_id is not None:
            for idx, p in enumerate(self.resume_profiles):
                # Use strict integer comparison to avoid type mismatches
                if int(p.get('id', -1)) == int(self.editing_id):
                    target_profile = p
                    self.editing_idx = idx # Keep sync
                    break
        
        if target_profile:
            # Check if updated name conflicts with ANOTHER profile
            for p in self.resume_profiles:
                if p.get("name") == name and p.get("id") != self.editing_id:
                    messagebox.showwarning("Duplicate Name", f"A DIFFERENT profile named '{name}' already exists. Select it to update.")
                    return

            target_profile["name"]            = name
            target_profile["unique_keywords"] = unique_keywords
            target_profile["keywords"]        = keywords
            target_profile["file_path"]       = file_path
            target_profile["boost_mode"]      = boost_mode
            self.logger.info(f"Updated profile ID {self.editing_id}: {name}")
        else:
            # Check for duplicate names if adding new
            for p in self.resume_profiles:
                if p.get("name") == name:
                    messagebox.showwarning("Duplicate Name", f"A profile named '{name}' already exists. Select it to update.")
                    return

            self.resume_profiles.append({
                "id":              self.next_id,
                "name":            name,
                "unique_keywords": unique_keywords,
                "keywords":        keywords,
                "file_path":       file_path,
                "boost_mode":      boost_mode,
            })
            self.logger.info(f"Added new profile (ID {self.next_id}): {name}")
            self.next_id += 1

        self._persist_config()
        # Keep current search filter after update
        self.refresh_resume_list(self.resume_search_var.get() if hasattr(self, 'resume_search_var') else "")
        self.clear_resume_form()

    def delete_resume_profile(self):
        selected = self.resume_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a resume profile to delete.")
            return
            
        item = self.resume_tree.item(selected[0])
        try:
            # We identify the profile by ID for deletion
            profile_id = int(item.get("values", [])[1])
            profile_name = str(item.get("values", [])[2])
        except (ValueError, IndexError):
            self.logger.error("Could not determine ID/name of profile to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete profile '{profile_name}'?"):
            profiles = getattr(self, "resume_profiles", [])
            target_idx = None
            for idx, p in enumerate(profiles):
                if p.get("id") == profile_id:
                    target_idx = idx
                    break
                if str(p.get("name", "")) == profile_name:
                    target_idx = idx
                    break
            
            if target_idx is not None:
                deleted_profile = profiles.pop(target_idx)
                self.logger.info(f"Deleted resume profile: {deleted_profile.get('name', 'Unknown')}")
                
                # Delete from AI Training data
                try:
                    if hasattr(self, 'learning_engine') and self.learning_engine:
                        self.learning_engine.delete_profile_history(profile_id)
                except Exception as e:
                    self.logger.error(f"Error removing AI training data: {e}")
                    
                # Delete from Semantic Matcher
                if getattr(self, 'semantic_enabled', False) and getattr(self, 'semantic_matcher', None):
                    try:
                        self.semantic_matcher.delete_profile(profile_id)
                    except Exception as e:
                        self.logger.error(f"Error removing semantic profile: {e}")
                
                self._persist_config()
                self.refresh_resume_list(self.resume_search_var.get())
                self.clear_resume_form()
                
                if hasattr(self, 'refresh_ai_stats'):
                    self.refresh_ai_stats()
            else:
                self.logger.error(f"Delete failed: Profile '{profile_name}' not found in internal list.")
                messagebox.showerror("Error", "Could not delete profile: it was not found in the master list.")

    def open_test_simulator(self):
        """Open a window to test which profile matches a given job description text based on configured keywords."""
        test_window = tk.Toplevel(self.root)
        test_window.title("Test Profile Matching Simulator")
        test_window.geometry("600x600")
        
        # Add instructional label
        ttk.Label(test_window, text="Paste a sample job description below to completely simulate which profile uniquely matches:").pack(padx=10, pady=10, anchor="w")

        # Display the result - MUST PACK IT TOP LEVEL SO IT DOESN'T GET PUSHED OFF-SCREEN!
        result_label = ttk.Label(test_window, text="[ Awaiting Test... ]", font=("Helvetica", 11, "bold"), foreground="blue", justify="center")
        result_label.pack(pady=10)
        
        def run_test():
            import re
            try:
                # Configure highlight tags and clear previous highlights
                job_desc_text.tag_remove("match_unique", "1.0", tk.END)
                job_desc_text.tag_remove("match_general", "1.0", tk.END)
                job_desc_text.tag_config("match_unique", background="#aaffaa", foreground="black", font=("Helvetica", 10, "bold")) # Light green
                job_desc_text.tag_config("match_general", background="#ffffaa", foreground="black") # Yellow

                text = job_desc_text.get("1.0", tk.END).lower()
                if not text.strip():
                    result_label.config(text="Please paste some job description text.", foreground="red")
                    return
                    
                profiles = getattr(self, "resume_profiles", [])
                if not profiles:
                    result_label.config(text="No profiles are configured in settings.", foreground="red")
                    return

                from core.matcher import ResumeMatcher
                matcher = ResumeMatcher(
                    profiles, 
                    semantic_matcher=self.semantic_matcher if self.semantic_enabled else None,
                    learning_engine=self.learning_engine
                )
                ranked_results = matcher.score_profiles(text)
                
                if not ranked_results:
                    result_label.config(text="No keywords matched any configured profile.", foreground="black")
                    return
                    
                best_match = ranked_results[0]
                selected_profile_name = best_match['name']
                tot     = best_match['score']
                u_sc    = best_match.get('uni_score', 0)
                g_sc    = best_match.get('gen_score', 0)
                sem_sc  = best_match.get('semantic_score', 0)
                learn_sc= best_match.get('learning_boost', 0)
                
                matched_reason = (
                    f"Hybrid Score: {tot}\n"
                    f"(Unique: {u_sc} | Gen: {g_sc} | Semantic: {sem_sc}% | AI Learning: +{learn_sc})"
                )
                
                best_used_uni = best_match['matched_uni']
                best_used_gen = best_match['matched_gen']

                # Highlight matched keywords in the text area using the strict regex matcher
                for word in best_used_uni:
                    pattern = matcher.build_keyword_pattern(word)
                    if pattern:
                        for match in re.finditer(pattern, text):
                            start_idx = f"1.0+{match.start()}c"
                            end_idx = f"1.0+{match.end()}c"
                            job_desc_text.tag_add("match_unique", start_idx, end_idx)
                        
                for word in best_used_gen:
                    pattern = matcher.build_keyword_pattern(word)
                    if pattern:
                        for match in re.finditer(pattern, text):
                            start_idx = f"1.0+{match.start()}c"
                            end_idx = f"1.0+{match.end()}c"
                            job_desc_text.tag_add("match_general", start_idx, end_idx)

                result_string = f"WINNING PROFILE: {selected_profile_name}\nREASON: {matched_reason}\n(Unique: Green Bold | General: Yellow)"
                result_label.config(text=result_string, foreground="green")
            except Exception as e:
                result_label.config(text=f"Error occurred during calculation: {str(e)}", foreground="red")
                print(f"Test Simulator Error: {e}")
                
            # Force UI update
            test_window.update_idletasks()

        ttk.Button(test_window, text="Test Match ->", command=run_test).pack(pady=5)
        
        # Add Input text area LAST so it expands but doesn't push elements out of the window
        ttk.Label(test_window, text="Job Description Data:").pack(padx=10, pady=2, anchor="w")
        job_desc_text = scrolledtext.ScrolledText(test_window, height=15, wrap=tk.WORD)
        job_desc_text.pack(fill="both", expand=True, padx=10, pady=5)
        
    def setup_settings_tab(self):
        """Set up the settings tab UI — wrapped in a scrollable canvas so nothing gets clipped."""
        # ── Scrollable container ─────────────────────────────────────────────
        canvas = tk.Canvas(self.settings_tab, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.settings_tab, orient="vertical", command=canvas.yview)
        self.settings_scroll_frame = ttk.Frame(canvas)

        self.settings_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.settings_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Allow mouse-wheel scrolling on Windows
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        parent = self.settings_scroll_frame

        # ── Group 1: Dice.com Login ──────────────────────────────────────────
        login_frame = ttk.LabelFrame(parent, text="Dice Account Credentials")
        login_frame.pack(fill="x", padx=15, pady=10)
        login_frame.columnconfigure(1, weight=1)

        ttk.Label(login_frame, text="Username:").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        self.username_entry = ttk.Entry(login_frame)
        self.username_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=8)

        ttk.Label(login_frame, text="Password:").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        self.password_entry = ttk.Entry(login_frame, show="*")
        self.password_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=8)

        self.test_login_button = ttk.Button(login_frame, text="✔ Test Login Connection", command=self.test_login)
        self.test_login_button.grid(row=2, column=0, columnspan=2, pady=15)

        # ── Group 2: Automation Controls ─────────────────────────────────────
        settings_frame = ttk.LabelFrame(parent, text="Automation Behavior")
        settings_frame.pack(fill="x", padx=15, pady=10)
        settings_frame.columnconfigure(1, weight=1)

        # Headless mode
        self.headless_var = tk.BooleanVar(value=self.headless_mode)
        ttk.Checkbutton(
            settings_frame,
            text="Headless Mode (Hide Chrome while applying)",
            variable=self.headless_var
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=8)

        # Job limit
        ttk.Label(settings_frame, text="Stop at Job Limit:").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        self.job_limit_var = tk.IntVar(value=self.job_limit)
        ttk.Spinbox(
            settings_frame, from_=1, to=10000, width=8, textvariable=self.job_limit_var
        ).grid(row=1, column=1, sticky="w", padx=10, pady=8)
        
        # Semantic AI Toggle
        self.semantic_var = tk.BooleanVar(value=self.semantic_enabled)
        ttk.Checkbutton(
            settings_frame,
            text="Enable AI Semantic Matching (Understanding meanings/concepts)",
            variable=self.semantic_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=8)

        # AI Memory Reset
        def _reset_ai():
            if messagebox.askyesno("Reset AI Memory", "This will delete all learned context from your past applications. Proceed?"):
                self.learning_engine.reset_memory()
                messagebox.showinfo("Success", "AI Memory has been wiped.")
                
        ttk.Button(settings_frame, text="🗑 Reset AI Memory", command=_reset_ai).grid(row=3, column=0, sticky="w", padx=10, pady=8)

        # Global Profile Name Boost (Used as a fallback/multiplier)
        ttk.Label(settings_frame, text="Global Name Boost:").grid(row=3, column=0, columnspan=2, sticky="e", padx=(0, 150), pady=8)
        self.name_boost_var = tk.StringVar(value=f"{self.profile_name_boost_mode.upper()} | Default")
        ttk.Combobox(
            settings_frame, 
            textvariable=self.name_boost_var,
            values=["OFF | Keywords Only", "LOW | Nudge Match", "HIGH | Aggressive", "EXACT | Strict Title Match"],
            state="readonly",
            width=20
        ).grid(row=3, column=1, sticky="e", padx=10, pady=8)

        # Help text for Boost (now in Resumes)
        ttk.Label(
            settings_frame,
            text="💡 Tip: Semantic matching is 'Smart'. It knows that 'Data Engineer' is 80% similar\nto 'ETL Engineer' even if keywords don't match exactly.",
            foreground="#666", font=("Segoe UI", 8, "italic")
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 10))

        # Save button
        self.save_settings_button = ttk.Button(
            parent, text="💾 Save All Settings", command=self.save_config, style="Start.TButton"
        )
        self.save_settings_button.pack(pady=20)

        # ── Group 3: User Guide ──────────────────────────────────────────────
        guide_frame = ttk.LabelFrame(parent, text="Getting Started & Best Practices")
        guide_frame.pack(fill="x", padx=15, pady=10)

        self.guide_text = scrolledtext.ScrolledText(guide_frame, wrap=tk.WORD, height=14, font=("Segoe UI", 9))
        self.guide_text.pack(fill="x", padx=10, pady=10)

        guide_content = """\
Dice Auto-Apply Bot Guide
--------------------------
1. DICE LOGIN: 
   Enter your credentials in this tab and click 'Test Login'. 
   This verifies the bot can access your account correctly.

2. PROFILE SETUP (Resumes Tab):
   Add multiple resume profiles. 
   Set 'Boost Mode' for each profile:
   - EXACT: If name matches job title >= 60%, auto-select this resume.
   - HIGH/LOW: Tie-breaker nudges for similar keyword scores.
   - OFF: Use keyword scoring only.

3. JOB SEARCH (Run Bot Tab):
   - 'Job Titles': Enter what you are looking for (e.g. Data Engineer).
   - 'Exclude': Hard exclude (e.g. 'Senior' if you want Junior roles).
   - 'Include': Must-have keywords (e.g. 'Python, AWS').

4. FILTERS:
   The bot automatically skips roles containing W2 or Full-Time patterns 
   unless a C2C override is found.

5. MONITORING:
   Watch the 'Live Log' on the main tab. Completed applications appear 
   in 'applied_jobs.xlsx' automatically.
"""
        self.guide_text.insert("1.0", guide_content)
        self.guide_text.config(state="disabled")

        # ── Pre-fill login from .env ─────────────────────────────────────────
        from dotenv import load_dotenv
        load_dotenv()
        import os
        username = os.getenv("DICE_USERNAME", "")
        password = os.getenv("DICE_PASSWORD", "")
        if username:
            self.username_entry.insert(0, username)
        if password:
            self.password_entry.insert(0, password)


    def setup_logs_tab(self):
        """Set up the logs tab UI with a professional dark theme."""
        # Top toolbar
        toolbar = ttk.Frame(self.logs_tab)
        toolbar.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Button(toolbar, text="🔄 Refresh Latest Log", command=self.load_log_file).pack(side="left", padx=5)
        ttk.Button(toolbar, text="🗑 Clear View", command=self.clear_logs_view).pack(side="left", padx=5)
        ttk.Button(toolbar, text="📁 Open Log Folder", command=self.open_log_folder).pack(side="right", padx=5)

        # Full log view
        log_frame = ttk.LabelFrame(self.logs_tab, text="Complete Session Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.full_log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.full_log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.full_log_text.config(state="disabled")

        # Auto-load on setup
        self.root.after(500, self.load_log_file)
        
    def load_log_file(self):
        """Load and display the latest log file"""
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        if not os.path.exists(logs_dir):
            return

        # Find all log files
        log_files = [os.path.join(logs_dir, f) for f in os.listdir(logs_dir) if f.startswith("app_")]
        if not log_files:
            return

        # Get the most recent log file
        latest_log = max(log_files, key=os.path.getmtime)
        try:
            with open(latest_log, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            self.full_log_text.config(state="normal")
            self.full_log_text.delete("1.0", tk.END)
            self.full_log_text.insert("1.0", content)
            self.full_log_text.see(tk.END) # Scroll to bottom
            self.full_log_text.config(state="disabled")
            self.logger.info(f"UI: Loaded log file: {os.path.basename(latest_log)}")
        except Exception as e:
            self.logger.error(f"UI Error loading log file: {e}")

    def clear_logs_view(self):
        """Clears the displayed log text"""
        self.full_log_text.config(state="normal")
        self.full_log_text.delete("1.0", tk.END)
        self.full_log_text.config(state="disabled")

    def open_log_folder(self):
        """Open the logs directory in explorer"""
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        
        if sys.platform == "win32":
            os.startfile(logs_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", logs_dir])
        else:
            subprocess.run(["xdg-open", logs_dir])
            
    def test_login(self):
        """Test Dice login credentials"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showwarning("Missing Credentials", "Please enter both username and password.")
            return
            
        # Disable button during testing
        self.test_login_button.config(state="disabled", text="Testing...")
        self.root.update_idletasks()
        
        def test_login_thread():
            try:
                # Import the validation function
                
                success = validate_dice_credentials(username, password)
                
                # Update UI from the main thread
                self.root.after(0, lambda: self.test_login_complete(success))
                
            except Exception as e:
                self.logger.error(f"Login test error: {str(e)}")
                # Update UI from the main thread
                self.root.after(0, lambda: self.test_login_complete(False, str(e)))
                
        # Run the test in a separate thread
        threading.Thread(target=test_login_thread, daemon=True).start()
        
    def test_login_complete(self, success, error_msg=None):
        """Handle login test completion"""
        # Re-enable the button
        self.test_login_button.config(state="normal", text="Test Login")
        
        if success:
            self.logger.info("Login test successful")
            messagebox.showinfo("Login Test", "Login successful!")
        else:
            error = error_msg if error_msg else "Login failed. Please check your credentials."
            self.logger.error(f"Login test failed: {error}")
            messagebox.showerror("Login Test", error)
            
    def start_applying(self):
        """Start the job application process"""
        # Validate inputs
        search_queries = [q.strip() for q in self.search_query_entry.get().split(",") if q.strip()]
        if not search_queries:
            messagebox.showwarning("Missing Input", "Please enter at least one job title to search for.")
            return
            
        # Check for login credentials
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Missing Credentials", "Please enter Dice login credentials in the Settings tab.")
            self.notebook.select(1)  # Switch to settings tab
            return
            
        # Get keywords
        exclude_keywords = [k.strip() for k in self.exclude_keywords_entry.get().split(",") if k.strip()]
        include_keywords = [k.strip() for k in self.include_keywords_entry.get().split(",") if k.strip()]
        job_limit = self.job_limit_var.get()
        profile_boost_mode = self.name_boost_var.get().split('|')[0].strip().lower()

        # Update UI
        self.running = True
        self.is_paused = False
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.pause_button.config(state="normal", text="⏸  Pause")
        self.progress_bar["value"] = 0
        self.status_label.config(text="Starting...")
        
        # Reset counters
        self.jobs_found_label.config(text="0")
        self.jobs_applied_label.config(text="0")
        self.jobs_failed_label.config(text="0")
        
        # Clear log text
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        
        # Run job application process in a separate thread
        self.job_thread = threading.Thread(
            target=self.run_job_application,
            args=(search_queries, include_keywords, exclude_keywords, username, password, job_limit, profile_boost_mode),
            daemon=True
        )
        self.job_thread.start()
        
    def toggle_pause(self):
        """Toggles the pause state of the application loop"""
        if not self.running:
            return
            
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.config(text="▶  Resume")
            self.update_status("⏸  Application PAUSED. Bot is waiting...")
        else:
            self.pause_button.config(text="⏸  Pause")
            self.update_status("▶  Application RESUMED.")

    def check_pause(self):
        """Returns True if the bot has been stopped. Will block if paused."""
        while self.is_paused and self.running:
            time.sleep(0.5)
        return not self.running

    def run_job_application(self, search_queries, include_keywords, exclude_keywords, username, password, job_limit, profile_boost_mode):
        """Run the job application process in a background thread"""
        try:
            # Record start time
            start_time = time.time()
            self.logger.info(f"Starting job applications with queries: {search_queries}")
            
            # Initialize web driver
            self.update_status("Initializing web driver...")
            headless = self.headless_var.get()
            driver = get_web_driver()
            
            # Login to Dice
            self.update_status("Logging in to Dice...")
            login_success = login_to_dice(driver, (username, password))
            if not login_success:
                self.update_status("Login failed. Please check your credentials.")
                self.root.after(0, lambda: messagebox.showerror(
                    "Login Failed", 
                    "Could not log in to Dice. Please check your credentials."
                ))
                driver.quit()
                self.reset_ui()
                return
                    
            self.update_status("Login successful. Fetching jobs...")
            
            # Find jobs matching the search queries
            all_jobs = {}
            excluded_jobs = []  # Track excluded jobs
            total_queries = len(search_queries)
            
            for i, query in enumerate(search_queries):
                # Check if bot is paused
                while self.is_paused and self.running:
                    time.sleep(1)
                if not self.running:
                    self.update_status("Stopped by user.")
                    driver.quit()
                    self.reset_ui()
                    return
                    
                self.update_status(f"Searching for '{query}' ({i+1}/{total_queries})...")
                
                # Use the fetch_jobs_with_requests function
                jobs, excluded = fetch_jobs_with_requests(driver, query, include_keywords, exclude_keywords, pause_check=self.check_pause)
                
                # Track counts before adding new jobs
                jobs_before = len(all_jobs)
                
                # Add unique jobs to dictionary
                for job in jobs:
                    if job["Job URL"] not in all_jobs:
                        all_jobs[job["Job URL"]] = job
                
                # Add excluded jobs
                excluded_jobs.extend(excluded)
                
                # Calculate current count
                current_count = len(all_jobs)
                
                # Update the counter after each query, capturing the current count
                count_to_display = current_count
                self.root.after(0, lambda c=count_to_display: self.jobs_found_label.config(text=str(c)))
                
                # Print debug info
                print(f"Query '{query}': Found {len(jobs)} total jobs, added {current_count - jobs_before} unique jobs")
                
                # Move mouse to prevent sleeping
                pyautogui.moveRel(1, 1, duration=0.1)
                pyautogui.moveRel(-1, -1, duration=0.1)
                        
            # Make sure the final count is displayed
            final_count = len(all_jobs)
            self.update_status(f"Found {final_count} unique jobs matching criteria")
            self.root.after(0, lambda c=final_count: self.jobs_found_label.config(text=str(c)))
            
            # Save excluded jobs to Excel
            if excluded_jobs:
                try:
                    excluded_file = "excluded_jobs.xlsx"
                    df_excluded = pd.DataFrame(excluded_jobs)
                    df_excluded.to_excel(excluded_file, index=False)
                    self.logger.info(f"Saved {len(excluded_jobs)} excluded jobs to {excluded_file}")
                except Exception as e:
                    self.logger.error(f"Error saving excluded jobs: {e}")
            
            # Check for already applied jobs
            self.update_status("Checking for already applied jobs...")
            applied_jobs_file = "applied_jobs.xlsx"
            already_applied = set()
            
            if os.path.exists(applied_jobs_file):
                try:
                    df_applied = pd.read_excel(applied_jobs_file)
                    already_applied = set(df_applied["Job URL"].dropna())
                    self.update_status(f"Found {len(already_applied)} previously applied jobs to skip")
                except Exception as e:
                    self.logger.error(f"Error reading applied jobs file: {e}")
            
            # Filter out already applied jobs
            jobs_to_apply = [job for job in all_jobs.values() if job["Job URL"] not in already_applied]
            self.update_status(f"Applying to {len(jobs_to_apply)} jobs...")

            # Update the Total Jobs count to show the jobs that will be processed
            jobs_to_process_count = len(jobs_to_apply)
            self.root.after(0, lambda c=jobs_to_process_count: self.jobs_found_label.config(text=str(c)))

            # Apply job limit if set
            job_limit = self.job_limit_var.get()
            if job_limit > 0 and len(jobs_to_apply) > job_limit:
                limited_count = job_limit
                self.update_status(f"Limiting to {job_limit} jobs as per settings")
                jobs_to_apply = jobs_to_apply[:job_limit]
                self.root.after(0, lambda c=limited_count: self.jobs_found_label.config(text=str(c)))

            # Calculate initial estimated time (assuming 10 jobs per minute)
            jobs_per_minute = 10.0
            total_jobs = len(jobs_to_apply)
            
            if total_jobs > 0:
                estimated_minutes = total_jobs / jobs_per_minute
                hours = int(estimated_minutes // 60)
                minutes = int(estimated_minutes % 60)

                # Format time string
                initial_estimate = ""
                if hours > 0:
                    initial_estimate += f"{hours} hours "
                if minutes > 0 or hours > 0:
                    initial_estimate += f"{minutes} minutes"
                else:
                    initial_estimate += "less than 1 minute"

                # Update both status and dedicated time label
                self.update_status(f"Estimated completion time: {initial_estimate}")
                self.root.after(0, lambda t=initial_estimate: self.estimated_time_label.config(text=t))
            
            # Start applying to jobs
            applied_count = 0
            failed_count = 0
            
            # Variables for dynamic time estimation
            job_start_times = []
            job_processing_times = []
            
            for i, job in enumerate(jobs_to_apply):
                # Check if bot is paused
                while self.is_paused and self.running:
                    time.sleep(1)
                if not self.running:
                    self.update_status("Stopped by user.")
                    driver.quit()
                    self.reset_ui()
                    return
                
                # Record job start time for this specific job
                job_start_time = time.time()
                
                # Update progress
                progress = int((i / len(jobs_to_apply)) * 100) if jobs_to_apply else 0
                self.root.after(0, lambda p=progress: self.progress_bar.config(value=p))
                
                # Show job details in status
                job_title = job.get("Job Title", "Unknown")
                self.update_status(f"Applying to: {job_title} ({i+1}/{len(jobs_to_apply)})")

                # Apply to job using your existing function
                try:
                    job_result = apply_to_job_url(
                        driver, 
                        job["Job URL"], 
                        getattr(self, "resume_profiles", []), 
                        job_title=job_title,
                        semantic_matcher=self.semantic_matcher if self.semantic_enabled else None,
                        learning_engine=self.learning_engine,
                        pause_check=self.check_pause
                    )
                    applied_status, profile_name, match_reason, skip_reason, job_desc_text, profile_id = job_result
                    
                    job["Resume Profile"] = profile_name
                    job["Match Reason"] = match_reason
                    
                    if profile_name and profile_name != "Default/None":
                        self.logger.info(f"Using Resume: {profile_name} | {match_reason}")
                    
                    # Record job completion time and calculate processing time for this job
                    job_end_time = time.time()
                    processing_time = job_end_time - job_start_time
                    
                    # Keep track of job times for estimation
                    job_start_times.append(job_start_time)
                    job_processing_times.append(processing_time)
                    
                    # Calculate dynamic time estimate after a few jobs
                    if i >= 2 and len(jobs_to_apply) > i+1:
                        # Calculate average time per job based on the last few jobs
                        recent_times = job_processing_times[-min(10, len(job_processing_times)):]
                        avg_time_per_job = sum(recent_times) / len(recent_times)
                        
                        # Calculate remaining time
                        remaining_jobs = len(jobs_to_apply) - (i + 1)
                        remaining_seconds = avg_time_per_job * remaining_jobs
                        
                        # Format remaining time string
                        remaining_hours = int(remaining_seconds // 3600)
                        remaining_minutes = int((remaining_seconds % 3600) // 60)
                        remaining_seconds = int(remaining_seconds % 60)
                        
                        time_remaining = ""
                        if remaining_hours > 0:
                            time_remaining += f"{remaining_hours} hours "
                        if remaining_minutes > 0 or remaining_hours > 0:
                            time_remaining += f"{remaining_minutes} minutes "
                        time_remaining += f"{remaining_seconds} seconds"
                        
                        # Update the estimated time label
                        self.root.after(0, lambda t=time_remaining: self.estimated_time_label.config(text=t))
                    
                    if applied_status:
                        applied_count += 1
                        # Update applied count
                        count_to_display = applied_count
                        self.root.after(0, lambda c=count_to_display: 
                            self.jobs_applied_label.config(text=str(c)))
                        
                        # Record success for AI Learning
                        if profile_id and self.learning_engine:
                            try:
                                # Use source='auto' for bot applications
                                self.learning_engine.record_success(profile_id, job_title, job_desc_text, source='auto')
                                # Real-time AI Stats Refresh
                                self.root.after(0, self.refresh_ai_stats)
                            except Exception as e:
                                self.logger.error(f"Failed to record AI learning: {e}")
                        
                        # Save to applied jobs Excel file
                        try:
                            job["Applied"] = True
                            # If Submit was clicked but confirmation wasn't detected, note it for auditing
                            if skip_reason:
                                job["Application Note"] = skip_reason
                            if os.path.exists(applied_jobs_file):
                                df_existing = pd.read_excel(applied_jobs_file)
                            else:
                                df_existing = pd.DataFrame(columns=[
                                    "Job Title", "Job URL", "Company", "Location", 
                                    "Employment Type", "Posted Date", "Applied",
                                    "Resume Profile", "Match Reason", "Application Note"
                                ])
                            
                            df_new = pd.DataFrame([job])
                            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                            df_combined.to_excel(applied_jobs_file, index=False)
                        except Exception as e:
                            self.logger.error(f"Error updating Excel file: {e}")
                    else:
                        failed_count += 1
                        # Update failed count
                        count_to_display = failed_count
                        self.root.after(0, lambda c=count_to_display: 
                            self.jobs_failed_label.config(text=str(c)))
                        
                        # Save to not applied jobs Excel file
                        not_applied_file = "not_applied_jobs.xlsx"
                        try:
                            EXPECTED_COLS = [
                                "Job Title", "Job URL", "Company", "Location",
                                "Employment Type", "Posted Date", "Applied",
                                "Resume Profile", "Match Reason", "Skip Reason"
                            ]
                            if os.path.exists(not_applied_file):
                                df_existing = pd.read_excel(not_applied_file)
                                # Ensure all expected columns exist in old files
                                for col in EXPECTED_COLS:
                                    if col not in df_existing.columns:
                                        df_existing[col] = ""
                            else:
                                df_existing = pd.DataFrame(columns=EXPECTED_COLS)

                            job["Applied"] = False
                            # Truncate very long reasons so Excel cells stay readable
                            raw_reason = skip_reason or "Unknown failure"
                            job["Skip Reason"] = raw_reason[:500] if len(raw_reason) > 500 else raw_reason
                            df_new = pd.DataFrame([job])
                            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                            # Reorder so Skip Reason column is always present and last
                            for col in EXPECTED_COLS:
                                if col not in df_combined.columns:
                                    df_combined[col] = ""
                            df_combined = df_combined[EXPECTED_COLS + [c for c in df_combined.columns if c not in EXPECTED_COLS]]
                            df_combined.to_excel(not_applied_file, index=False)
                        except Exception as e:
                            self.logger.error(f"Error updating not_applied Excel file: {e}")
                    
                except Exception as e:
                    self.logger.error(f"Error applying to {job_title}: {e}")
                    failed_count += 1
                    # Update failed count
                    count_to_display = failed_count
                    self.root.after(0, lambda c=count_to_display: 
                        self.jobs_failed_label.config(text=str(c)))
                
                # Move mouse to prevent sleeping
                pyautogui.moveRel(1, 1, duration=0.1)
                pyautogui.moveRel(-1, -1, duration=0.1)
            
            # ── Retry pass ────────────────────────────────────────────────────
            # Re-attempt jobs that failed due to transient issues (button timeout,
            # wizard timing out, click failures). Only ONE retry per job.
            RETRYABLE_REASONS = [
                "Apply button not found or timed out",
                "Wizard completed max steps but Submit button was never found",
                "Wizard finished all steps but Submit button was never clicked",
                "Failed to click the Apply button",
                "Wizard error",
                "Exception during application",
            ]
            retry_candidates = [
                job for job in jobs_to_apply
                if not job.get("Applied", False)
                and any(r in job.get("Skip Reason", "") for r in RETRYABLE_REASONS)
            ]

            retry_success_count = 0
            retry_fail_count    = 0

            if retry_candidates and self.running:
                not_applied_file = "not_applied_jobs.xlsx"
                self.update_status(f"Retrying {len(retry_candidates)} failed job(s)...")
                self.logger.info(f"Starting retry pass for {len(retry_candidates)} job(s).")

                for job in retry_candidates:
                    # Check if bot is paused
                    while self.is_paused and self.running:
                        time.sleep(1)
                    
                    if not self.running:
                        break
                        
                    try:
                        job_result = apply_to_job_url(
                            driver, 
                            job["Job URL"], 
                            getattr(self, "resume_profiles", []),
                            job_title=job_title,
                            semantic_matcher=self.semantic_matcher if self.semantic_enabled else None,
                            learning_engine=self.learning_engine
                        )
                        applied_status, profile_name, match_reason, skip_reason, job_desc_text, profile_id = job_result
                        job["Applied"]        = applied_status
                        job["Resume Profile"] = profile_name
                        job["Match Reason"]   = match_reason

                        if applied_status:
                            retry_success_count += 1
                            applied_count       += 1
                            failed_count        -= 1
                            self.root.after(0, lambda c=applied_count: self.jobs_applied_label.config(text=str(c)))
                            self.root.after(0, lambda c=max(failed_count, 0): self.jobs_failed_label.config(text=str(c)))
                            self.logger.info(f"  ✓ Retry succeeded: {job_title}")
                            # Write to applied_jobs
                            if skip_reason:
                                job["Application Note"] = skip_reason
                            try:
                                if os.path.exists(applied_jobs_file):
                                    df_existing = pd.read_excel(applied_jobs_file)
                                else:
                                    df_existing = pd.DataFrame(columns=[
                                        "Job Title", "Job URL", "Company", "Location",
                                        "Employment Type", "Posted Date", "Applied",
                                        "Resume Profile", "Match Reason", "Application Note"
                                    ])
                                df_combined = pd.concat([df_existing, pd.DataFrame([job])], ignore_index=True)
                                df_combined.to_excel(applied_jobs_file, index=False)
                            except Exception as xe:
                                self.logger.error(f"Error updating applied_jobs on retry: {xe}")
                            # Remove from not_applied_jobs
                            try:
                                df_not = pd.read_excel(not_applied_file)
                                df_not = df_not[df_not["Job URL"] != job["Job URL"]]
                                df_not.to_excel(not_applied_file, index=False)
                            except Exception:
                                pass
                        else:
                            retry_fail_count += 1
                            self.logger.info(f"  ✗ Retry failed: {job_title} | {skip_reason}")
                            job["Skip Reason"] = f"[Retry] {skip_reason[:460]}" if skip_reason else "[Retry] Unknown"
                            # Update the not_applied row in place
                            try:
                                EXPECTED_COLS = [
                                    "Job Title", "Job URL", "Company", "Location",
                                    "Employment Type", "Posted Date", "Applied",
                                    "Resume Profile", "Match Reason", "Skip Reason"
                                ]
                                if os.path.exists(not_applied_file):
                                    df_not = pd.read_excel(not_applied_file)
                                    for col in EXPECTED_COLS:
                                        if col not in df_not.columns:
                                            df_not[col] = ""
                                else:
                                    df_not = pd.DataFrame(columns=EXPECTED_COLS)
                                if job["Job URL"] in df_not["Job URL"].values:
                                    df_not.loc[df_not["Job URL"] == job["Job URL"], "Skip Reason"] = job["Skip Reason"]
                                else:
                                    df_not = pd.concat([df_not, pd.DataFrame([job])], ignore_index=True)
                                df_not.to_excel(not_applied_file, index=False)
                            except Exception as xe:
                                self.logger.error(f"Error updating not_applied_jobs on retry: {xe}")
                    except Exception as e:
                        self.logger.error(f"Exception during retry of {job_title}: {e}")
                        retry_fail_count += 1

                self.logger.info(f"Retry pass done: {retry_success_count} succeeded, {retry_fail_count} still failed.")

            # Compute execution time
            end_time = time.time()
            execution_time = end_time - start_time
            hours, remainder = divmod(execution_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_str = f"{int(hours)}h {int(minutes)}m {seconds:.2f}s"
            retry_summary = f"\nRetried {len(retry_candidates)} failed job(s): {retry_success_count} succeeded, {retry_fail_count} still failed." if retry_candidates else ""
            self.update_status(f"Completed! Applied: {applied_count}, Failed: {failed_count}, Time: {time_str}")
            
            # Final progress update
            self.root.after(0, lambda: self.progress_bar.config(value=100))
            # Clear estimated time as we're done
            self.root.after(0, lambda: self.estimated_time_label.config(text="Completed"))
            
            # Save job data to JSON file
            import json
            try:
                job_data = {
                    "Total Jobs Found": len(all_jobs),
                    "Jobs Applied": applied_count,
                    "Jobs Failed": failed_count,
                    "Execution Time": time_str,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                with open("job_application_summary.json", "w") as f:
                    json.dump(job_data, f, indent=4)
            except Exception as e:
                self.logger.error(f"Error saving job data: {e}")
                
            # Show completion message
            self.root.after(0, lambda rs=retry_summary: messagebox.showinfo(
                "Process Complete", 
                f"Application process completed!\n\n"
                f"Applied to {applied_count} jobs\n"
                f"Failed for {failed_count} jobs\n"
                f"{rs}\n\n"
                f"Total execution time: {time_str}"
            ))
            
            # Clean up
            driver.quit()
                
        except Exception as e:
            self.logger.error(f"Error in job application process: {e}")
            self.update_status(f"Error: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror(
                "Error", 
                f"An error occurred: {str(e)}"
            ))
        finally:
            # Reset UI
            self.reset_ui()


            
    def stop_applying(self):
        """Stop the job application process"""
        if not self.running:
            return
            
        self.running = False
        self.stop_button.config(state="disabled")
        self.pause_button.config(state="disabled", text="⏸  Pause")
        self.is_paused = False
        self.update_status("Application cycle complete.")
        self.status_label.config(text="Stopping... Please wait.")
        self.logger.info("User requested to stop the application process")
        
    def reset_ui(self):
        """Reset UI after job completion or stop"""
        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="normal", text="Stop")
        
    def setup_ai_trainer_tab(self):
        """Set up the UI for the AI Training tab"""
        container = ttk.Frame(self.ai_trainer_tab, padding="20")
        container.pack(fill="both", expand=True)
        
        # Header
        header_lbl = ttk.Label(
            container, 
            text="🧠 AI Training Center", 
            font=("Segoe UI", 16, "bold"),
            foreground="#2c3e50"
        )
        header_lbl.pack(anchor="w", pady=(0, 10))
        
        desc_lbl = ttk.Label(
            container,
            text="Paste a 'Dream Job' description below to teach the AI what you're looking for.\nThis will boost matching accuracy for your selected profile.",
            font=("Segoe UI", 10),
            foreground="#666"
        )
        desc_lbl.pack(anchor="w", pady=(0, 20))
        
        # Split into Left (Input) and Right (Stats)
        panes = ttk.Frame(container)
        panes.pack(fill="both", expand=True)
        
        left_pane = ttk.Frame(panes)
        left_pane.pack(side="left", fill="both", expand=True, padx=(0, 20))
        
        # Job Description Input
        ttk.Label(left_pane, text="Paste Job Description / Requirements:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.trainer_text = tk.Text(left_pane, height=15, font=("Consolas", 10), wrap="word", borderwidth=1, relief="solid")
        self.trainer_text.pack(fill="both", expand=True)
        
        # Controls (Profile select + Train button)
        controls = ttk.Frame(left_pane, padding="10 10 0 0")
        controls.pack(fill="x")
        
        ttk.Label(controls, text="Target Profile:").pack(side="left", padx=(0, 5))
        self.trainer_profile_var = tk.StringVar()
        self.trainer_profile_combo = ttk.Combobox(controls, textvariable=self.trainer_profile_var, state="readonly", width=30)
        self.trainer_profile_combo.pack(side="left", padx=(0, 20))
        
        # Populating profile combo
        self.sync_trainer_profiles()
        def _on_train():
            jd = self.trainer_text.get("1.0", "end-1c").strip()
            p_name = self.trainer_profile_var.get()
            
            if not jd or not p_name:
                messagebox.showwarning("Incomplete", "Please paste a job description and select a profile.")
                return
            
            # Find profile ID
            p_id = next((p.get('id') for p in self.resume_profiles if p.get('name') == p_name), None)
            
            if p_id is None:
                messagebox.showerror("Error", "Could not find profile ID.")
                return
                
            try:
                # Use source='manual' for samples pasted in this tab
                self.learning_engine.record_success(p_id, f"Manual: {p_name}", jd, source='manual')
                self.trainer_text.delete("1.0", tk.END)
                self.refresh_ai_stats()
                messagebox.showinfo("Success", f"AI has successfully learned this manual sample for '{p_name}'!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to train: {e}")
                
        self.train_btn = ttk.Button(controls, text="🚀 Train AI on this Sample", command=_on_train)
        self.train_btn.pack(side="left")

        # --- Self Training Analysis Section ---
        analysis_frame = ttk.LabelFrame(left_pane, text=" Self Training Tools ", padding="10")
        analysis_frame.pack(fill="x", pady=(20, 0))
        
        ttk.Label(analysis_frame, text="Let the AI propose a match for your pasted JD:").pack(anchor="w")
        
        suggest_row = ttk.Frame(analysis_frame)
        suggest_row.pack(fill="x", pady=5)
        
        self.analyze_btn = ttk.Button(suggest_row, text="🔍 Analyze JD", command=self.analyze_jd_for_training)
        self.analyze_btn.pack(side="left", padx=(0, 10))
        
        self.suggestion_var = tk.StringVar(value="✨ Paste a JD and click Analyze...")
        self.suggestion_label = ttk.Label(suggest_row, textvariable=self.suggestion_var, font=("Segoe UI", 10, "italic"), foreground="#0056b3")
        self.suggestion_label.pack(side="left")
        
        self.confirm_frame = ttk.Frame(analysis_frame)
        # Hidden initially
        
        self.approve_btn = ttk.Button(self.confirm_frame, text="✅ Approve match", style="Start.TButton", command=self.approve_suggestion)
        self.approve_btn.pack(side="left", padx=5)
        
        self.reject_btn = ttk.Button(self.confirm_frame, text="❌ Not a fit", command=self.reject_suggestion)
        self.reject_btn.pack(side="left", padx=5)
        
        self.suggested_id = None
        
        # Right Pane: Stats & Memory
        right_pane = ttk.LabelFrame(panes, text=" AI Memory Status ", padding="15")
        right_pane.pack(side="right", fill="both")
        
        self.stats_label = ttk.Label(right_pane, text="Lessons Learned by Profile:", font=("Segoe UI", 10, "bold"))
        self.stats_label.pack(anchor="w", pady=(0, 10))
        
        self.stats_text = tk.Text(right_pane, height=12, width=35, font=("Segoe UI", 9), state="disabled", bg="#f8f9fa", borderwidth=0)
        self.stats_text.pack(fill="both", expand=True)
        
        self.refresh_ai_stats()
        
    def analyze_jd_for_training(self):
        """Analyze the JD in the trainer text box and suggest a profile"""
        jd = self.trainer_text.get("1.0", "end-1c").strip()
        if not jd:
            messagebox.showwarning("Empty", "Please paste a job description first.")
            return
            
        if not self.resume_profiles:
            messagebox.showwarning("No Profiles", "Please add at least one resume profile first.")
            return

        self.suggestion_var.set("✨ AI is thinking...")
        self.confirm_frame.pack_forget()
        
        # We'll use a temporary matcher to score the JD
        from core.matcher import ResumeMatcher
        # If semantic matcher isn't ready, we'll just use keyword matching
        matcher = ResumeMatcher(self.resume_profiles, semantic_matcher=self.semantic_matcher)
        
        # Scoring logic (simplified titles for training focus)
        results = []
        try:
            # We try to find the best match using the matcher's logic
            # For training purposes, we care about the holistic score
            for p in self.resume_profiles:
                # We'll do a quick score. In a real scenario we'd use semantic or keyword density.
                # Here we'll just use the semantic matcher if available, or keyword overlap.
                p_id = p.get('id')
                score = 0
                if self.semantic_matcher:
                    # Holistic semantic check
                    score_res = self.semantic_matcher.score_job("Training Sample", jd)
                    for r in score_res:
                        if r['profile_id'] == p_id:
                            score = r['semantic_score']
                            break
                else:
                    # Fallback to simple keyword density check
                    text = jd.lower()
                    kws = p.get('unique_keywords', []) + p.get('keywords', [])
                    matches = sum(1 for kw in kws if kw.lower() in text)
                    score = (matches / len(kws) * 100) if kws else 0
                
                results.append({'id': p_id, 'name': p.get('name'), 'score': score})
            
            results.sort(key=lambda x: x['score'], reverse=True)
            best = results[0]
            
            if best['score'] > 20: # Reasonable threshold
                self.suggestion_var.set(f"✨ Match found: {best['name']} ({best['score']}%)")
                self.suggested_id = best['id']
                self.confirm_frame.pack(fill="x", pady=5)
                # Auto-select in combo for convenience
                self.trainer_profile_var.set(best['name'])
            else:
                self.suggestion_var.set("✨ AI is unsure. Low confidence match.")
                self.suggested_id = None
                self.confirm_frame.pack_forget()
                
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            self.suggestion_var.set("✨ AI Analysis failed.")

    def approve_suggestion(self):
        if not self.suggested_id: return
        
        jd = self.trainer_text.get("1.0", "end-1c").strip()
        p_name = next((p.get('name') for p in self.resume_profiles if p.get('id') == self.suggested_id), "Unknown")
        
        try:
            self.learning_engine.record_success(self.suggested_id, f"Approved Match: {p_name}", jd, source='manual')
            self.trainer_text.delete("1.0", tk.END)
            self.confirm_frame.pack_forget()
            self.suggestion_var.set("✨ Paste a JD and click Analyze...")
            self.refresh_ai_stats()
            messagebox.showinfo("Success", f"AI learned from your approval for '{p_name}'!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to record approval: {e}")

    def reject_suggestion(self):
        self.suggestion_var.set("✨ Suggestion rejected. Please pick manually.")
        self.confirm_frame.pack_forget()
        self.suggested_id = None

    def sync_trainer_profiles(self):
        """Updates the dropdown in the AI trainer tab with the current resume profiles"""
        if not hasattr(self, 'trainer_profile_combo'): return
        
        names = [p.get('name', 'Unknown') for p in self.resume_profiles]
        self.trainer_profile_combo['values'] = names
        if names and not self.trainer_profile_var.get():
             self.trainer_profile_combo.current(0)
             
    def refresh_ai_stats(self):
        """Update the statistics box in the AI trainer tab"""
        if not hasattr(self, 'stats_text'): return
        
        stats = self.learning_engine.get_stats()
        
        self.stats_text.config(state="normal")
        self.stats_text.delete("1.0", tk.END)
        
        if not stats:
            self.stats_text.insert("end", "AI is currently a blank slate.\nStart training to see progress!")
        else:
            for p in self.resume_profiles:
                p_id = p.get('id')
                p_name = p.get('name', 'Unknown')
                
                # Get the breakdown from the dict structure returned by LearningEngine
                p_stats = stats.get(p_id, {'manual': 0, 'auto': 0})
                m_count = p_stats['manual']
                a_count = p_stats['auto']
                total   = m_count + a_count
                
                icon = "⭐" if total >= 5 else "🌱"
                # Show breakdown: Profile Name ... Total (M manual, A auto)
                display_str = f"{icon} {p_name:.<20} {total} ({m_count}m, {a_count}a)\n"
                self.stats_text.insert("end", display_str)
        
        self.stats_text.config(state="disabled")

    def update_status(self, message):
        """Update status message and log it"""
        self.logger.info(message)
        self.root.after(0, lambda msg=message: self.status_label.config(text=msg))
        

class LogTextHandler(logging.Handler):
    """Custom log handler that redirects logs to a tk Text widget"""
    
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget
        
    def emit(self, record):
        msg = self.format(record)
        
        def append_log():
            self.text_widget.config(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")  # Scroll to the bottom
            self.text_widget.config(state="disabled")
            
        # Schedule the update in the main thread
        self.text_widget.after(0, append_log)


def main():
    root = tk.Tk()
    app = DiceAutoBotApp(root)
    root.protocol("WM_DELETE_WINDOW", root.quit)
    root.mainloop()

if __name__ == "__main__":
    main()
