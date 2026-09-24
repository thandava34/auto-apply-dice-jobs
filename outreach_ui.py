"""
OutreachUI

All heavy imports (selenium, pipeline, scraper) are deferred to the
functions that actually need them so the GUI window opens instantly.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from utils.ui_components import LabeledToggleSwitch
import json
import os
import re
import threading
import traceback
import tempfile
from datetime import datetime

# Heavy imports (selenium, torch, pipeline) are intentionally deferred
# inside the methods that use them so the GUI opens instantly.
from utils.config_manager import ConfigManager
from core.groq_config import get_groq_key, save_groq_key


class OutreachUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        from utils.ui_events import install_ui_events
        install_ui_events(root)
        self.root.title("Career-Ops  ·  Cold Outreach Pipeline")
        self.root.resizable(True, True)

        # ── Unified dark color palette ─────────────────────────────────
        from utils.desktop_theme import legacy_palette
        palette = legacy_palette()
        BG, PANEL, ENTRY_BG = palette['BG'], palette['PANEL'], palette['ENTRY_BG']
        BORDER, FG, FG2 = palette['BORDER'], palette['FG'], palette['FG2']
        CARD_B = CARD_G = CARD_Y = PANEL
        self._theme = dict(BG=BG, PANEL=PANEL, BORDER=BORDER, FG=FG, FG2=FG2,
                           ENTRY_BG=ENTRY_BG, CARD_B=CARD_B, CARD_G=CARD_G, CARD_Y=CARD_Y)

        self.root.configure(bg=BG)

        style = ttk.Style()
        style.theme_use('clam')

        BF  = ("Segoe UI", 10)
        BBF = ("Segoe UI", 10, "bold")

        style.configure(".",              font=BF, background=PANEL, foreground=FG)
        style.configure("TFrame",         background=PANEL)
        style.configure("TLabel",         font=BF,  background=PANEL, foreground=FG, padding=2)
        style.configure("TCheckbutton",   background=PANEL, foreground=FG, font=BF)
        style.configure("TEntry",         fieldbackground=ENTRY_BG, foreground=FG,
                        insertcolor=FG, padding=5)
        style.configure("TCombobox",      fieldbackground=ENTRY_BG, foreground=FG,
                        background=PANEL, padding=4)
        style.map("TCombobox",            fieldbackground=[("readonly", ENTRY_BG)],
                  foreground=[("readonly", FG)])
        style.configure("TLabelframe",    background=PANEL, relief="groove")
        style.configure("TLabelframe.Label", font=BBF, background=PANEL, foreground="#7dd3fc")
        style.configure("TNotebook",      background=BG, tabmargins=[2, 4, 2, 0])
        style.configure("TNotebook.Tab",  padding=[10, 6], font=BBF,
                        background="#252b3b", foreground=FG2)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL)],
                  foreground=[("selected", FG)])
        style.configure("TScrollbar",     background=BORDER, troughcolor=PANEL)
        style.configure("TCheckbutton",   background=PANEL, foreground=FG, font=("Segoe UI", 10),
                        indicatorsize=18, indicatormargin=5)
        style.map("TCheckbutton",         background=[("active", PANEL)])

        # Named button styles
        for name, bg, abg in [
            ("Start",   "#16a34a", "#15803d"),
            ("Stop",    "#dc2626", "#b91c1c"),
            ("Blue",    "#2563eb", "#1d4ed8"),
            ("Amber",   "#d97706", "#b45309"),
            ("Skip",    "#7c3aed", "#6d28d9"),
        ]:
            style.configure(f"{name}.TButton",
                background=bg, foreground="white",
                font=("Segoe UI", 10, "bold"), padding=(10, 6), relief="flat")
            style.map(f"{name}.TButton",
                background=[("active", abg), ("disabled", "#374151")])

        from utils.outreach_styles import configure_action_styles
        configure_action_styles(style)

        # Treeview styling for dark theme with spacious 28px row height
        style.configure("Treeview",
                        background="#1e2430",
                        foreground="#ffffff",
                        fieldbackground="#1e2430",
                        rowheight=28,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background="#272f40",
                        foreground="#38bdf8",
                        relief="flat",
                        font=("Segoe UI", 9, "bold"),
                        padding=6)
        style.map("Treeview.Heading",
                  background=[("active", "#313b50")],
                  foreground=[("active", "#38bdf8")])
        style.map("Treeview",
                  background=[("selected", "#2563eb")],
                  foreground=[("selected", "#ffffff")])

        self.settings_file = "config/outreach_settings.json"
        self.cm      = ConfigManager()
        self.profiles = self.cm.get("resume_profiles", [])

        self.settings = self._load_settings()

        # Pipeline cache — rebuilt only when key settings change
        self._pipeline = None
        self._pipeline_key = None

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        win_w = min(int(sw * 0.88), 1280)
        win_h = min(int(sh * 0.88), 900)
        win_w = max(win_w, 900)
        win_h = max(win_h, 640)
        x_pos = max(0, (sw - win_w) // 2)
        y_pos = max(0, (sh - win_h) // 2)

        saved_geometry = self.settings.get("window_geometry", "")
        if saved_geometry:
            try:
                import re
                m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", saved_geometry)
                if m:
                    w, h = int(m.group(1)), int(m.group(2))
                    x, y = int(m.group(3)), int(m.group(4))
                    w = min(max(w, 900), sw)
                    h = min(max(h, 640), sh)
                    if x < -w // 2 or x > sw - 40 or y < -20 or y > sh - 40:
                        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2)
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                else:
                    self.root.geometry(f"{win_w}x{win_h}+{x_pos}+{y_pos}")
            except Exception:
                self.root.geometry(f"{win_w}x{win_h}+{x_pos}+{y_pos}")
        else:
            self.root.geometry(f"{win_w}x{win_h}+{x_pos}+{y_pos}")
        self.root.minsize(900, 640)
            
        self._build_widgets()
        from utils.desktop_theme import install_theme
        install_theme(self.root, 'nvoids')
        self._refresh_phone_queue_from_excel()
        
        self.on_provider_change()
        
        # ── Auto-Save Bindings ──
        for var in [
            self.provider_var, self.mode_var, self.target_resume_var,
            self.cc_var, self.bcc_var, self.groq_key_var,
            self.use_ai_email_var, self.subject_template_var,
            self.nvoids_queries_var, self.nvoids_limit_var, self.nvoids_max_age_var,
            self.continuous_var, self.my_core_skills_var, self.min_match_score_var,
            self.rest_time_var, self.exclude_keywords_var, self.headless_var,
            self.cooldown_hours_var, self.always_accept_titles_var,
            self.excluded_vendor_domains_var,
            self.excluded_email_addresses_var,
            self.daily_cap_var, self.cycle_cap_var,
            self.gmail_client_secret_var, self.gmail_token_path_var,
        ]:
            var.trace_add("write", self._queue_save)
            
        self.template_text.bind("<<Modified>>", lambda e: self._on_template_modified(e))

    def _on_template_modified(self, event):
        if self.template_text.edit_modified():
            self._queue_save()
            self.template_text.edit_modified(False)



    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> dict:
        defaults = {
            "email_provider":    "outlook",
            "send_mode":         "draft",
            "target_resume":     "Auto-Match (AI)",
            "headless":          False,
            "gmail_user":        "",
            "gmail_app_password":"",
            "gmail_client_secret_path": "config/gmail_client_secret.json",
            "gmail_token_path": "config/gmail_token.json",
            "cc_email":          "",
            "bcc_email":         "",
            "groq_api_key":      "",
            "nvoids_queries":    "Data Engineer, AI Engineer",
            "nvoids_limit":      10,
            "nvoids_max_age_hours": 24,
            "subject_template":  "Application for {job_title}",
            "my_core_skills":    "Python, AWS, PyTorch, SQL, Spark",
            "always_accept_titles": "",
            "min_match_score":   30,
            "cooldown_hours":    48,
            "daily_cap":         50,
            "cycle_cap":         15,
            "require_resume_attachment": True,
            "allow_ai_email_auto_send": False,
            "excluded_vendor_domains": "googlegroups.com, jobs.nvoids.com",
            "excluded_email_addresses": "",
            "template_selection_mode": "random",
            "selected_template_id": "1",
            "templates_list": [
                {
                    "id": "1",
                    "name": "Template 1 - Professional Standard",
                    "body": (
                        "Hi {recruiter_name},\n\n"
                        "I came across your listing for the {job_title} role at "
                        "{company_name} and believe my background aligns well with "
                        "what you are looking for. Please find my resume attached "
                        "for your consideration.\n\n"
                        "Best regards,\n[Your Name]"
                    )
                },
                {
                    "id": "2",
                    "name": "Template 2 - Direct & Impactful",
                    "body": (
                        "Hi {recruiter_name},\n\n"
                        "I am writing to express my strong interest in the {job_title} position at {company_name}. "
                        "With extensive experience in {keywords}, I can make an immediate contribution to your engineering team. "
                        "My resume is attached for your review.\n\n"
                        "Best,\n[Your Name]"
                    )
                }
            ],
            "template": (
                "Hi {recruiter_name},\n\n"
                "I came across your listing for the {job_title} role at "
                "{company_name} and believe my background aligns well with "
                "what you are looking for. Please find my resume attached "
                "for your consideration.\n\n"
                "Best regards,\n[Your Name]"
            ),
        }
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Merge: saved values win, but preserve all defaults if key missing
            for k, v in defaults.items():
                saved.setdefault(k, v)
            return saved
        except Exception:
            return defaults

    
    def _queue_save(self, *args):
        if hasattr(self, "_save_timer"):
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(800, self._save_settings)

    def _save_settings(self):
        """Read all widget values into self.settings and write to disk."""
        self.settings["email_provider"]     = self.provider_var.get()
        self.settings["send_mode"]          = self.mode_var.get()
        self.settings["target_resume"]      = self.target_resume_var.get()
        self.settings["zoho_domain"]        = getattr(self, "zoho_domain_var", tk.StringVar()).get().strip()
        self.settings["gmail_client_secret_path"] = self.gmail_client_secret_var.get().strip()
        self.settings["gmail_token_path"] = self.gmail_token_path_var.get().strip()
        self.settings["cc_email"]           = self.cc_var.get()
        self.settings["bcc_email"]          = self.bcc_var.get()
        shared_key = self.groq_key_var.get().strip()
        # Other settings autosave too. Do not overwrite a newer Dice-side key
        # merely because this window still displays an older value.
        if (shared_key != getattr(self, "_groq_key_last_seen", shared_key)
                or (shared_key and not get_groq_key(legacy=False))):
            save_groq_key(shared_key)
            self._groq_key_last_seen = shared_key
        self.settings.pop("groq_api_key", None)
        self.settings["use_ai_email"]       = getattr(self, "use_ai_email_var", tk.BooleanVar()).get()
        self.settings["subject_template"]   = self.subject_template_var.get()
        self.settings["nvoids_queries"]     = self.nvoids_queries_var.get()
        try:
            self.settings["nvoids_limit"]   = int(self.nvoids_limit_var.get() or 10)
        except ValueError:
            self.settings["nvoids_limit"]   = 10
            
        try:
            self.settings["nvoids_max_age_hours"] = int(self.nvoids_max_age_var.get() or 24)
        except ValueError:
            self.settings["nvoids_max_age_hours"] = 24
        
        self.settings["continuous_mode"] = self.continuous_var.get()
        self.settings["my_core_skills"] = self.my_core_skills_var.get()
        
        try:
            self.settings["min_match_score"] = int(self.min_match_score_var.get() or 0)
        except ValueError:
            self.settings["min_match_score"] = 0
        
        try:
            self.settings["rest_time_mins"] = int(self.rest_time_var.get() or 5)
        except ValueError:
            self.settings["rest_time_mins"] = 5

        self.settings["exclude_keywords"] = self.exclude_keywords_var.get()
        self.settings["always_accept_titles"] = self.always_accept_titles_var.get()
        self.settings["headless"] = self.headless_var.get()
        self.settings["excluded_vendor_domains"] = getattr(self, "excluded_vendor_domains_var", tk.StringVar()).get().strip()
        self.settings["excluded_email_addresses"] = getattr(self, "excluded_email_addresses_var", tk.StringVar()).get().strip()

        try:
            self.settings["cooldown_hours"] = int(self.cooldown_hours_var.get() or 48)
        except ValueError:
            self.settings["cooldown_hours"] = 48
        try:
            self.settings["daily_cap"] = max(0, int(self.daily_cap_var.get() or 50))
        except ValueError:
            self.settings["daily_cap"] = 50
        try:
            self.settings["cycle_cap"] = max(0, int(self.cycle_cap_var.get() or 15))
        except ValueError:
            self.settings["cycle_cap"] = 15

        raw_template = self.template_text.get("1.0", tk.END).strip()
        # Strip accidental "Subject: …\n\n" prefix that crept into older configs
        if raw_template.lower().startswith("subject:"):
            blank = raw_template.find("\n\n")
            if blank != -1:
                raw_template = raw_template[blank + 2:].strip()
        self.settings["template"] = raw_template
        
        try:
            self.settings["window_geometry"] = self.root.geometry()
        except Exception:
            pass

        
        os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(self.settings_file),
                prefix="outreach_settings.", suffix=".tmp", delete=False
            ) as f:
                temp_path = f.name
                json.dump(self.settings, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.settings_file)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        # ── Real-time Push to live bot instances ──────────────────────────
        if hasattr(self, 'scraper') and self.scraper:
            self.scraper.exclude_keywords = [k.strip().lower() for k in self.settings["exclude_keywords"].split(",") if k.strip()]
            self.scraper._parse_always_accept(self.settings.get("always_accept_titles", ""))
            self.scraper.my_core_skills = [s.strip().lower() for s in self.settings["my_core_skills"].split(",") if s.strip()]
            self.scraper.min_match_score = self.settings["min_match_score"]
            self.scraper.rest_time_mins = self.settings["rest_time_mins"]
            self.scraper.continuous_loop = self.settings["continuous_mode"]
            self.scraper.headless = self.settings["headless"]
            self.scraper.max_hours = self.settings["nvoids_max_age_hours"]
            # Push updated vendor domain exclusion list to live scraper
            self.scraper.excluded_vendor_domains = [
                d.strip().lower().lstrip('@')
                for d in self.settings.get("excluded_vendor_domains", "").split(",")
                if d.strip()
            ]
            # Push updated exact blocked email addresses to live scraper
            self.scraper.excluded_email_addresses = [
                e.strip().lower()
                for e in self.settings.get("excluded_email_addresses", "").replace("\n", ",").split(",")
                if e.strip()
            ]
            # Push new queries
            raw_queries = [q.strip() for q in self.settings["nvoids_queries"].split(",") if q.strip()]
            parsed_queries = []
            for q in raw_queries:
                if ":" in q:
                    parts = q.split(":")
                    try:
                        q_limit = int(parts[-1].strip())
                        q_str = ":".join(parts[:-1]).strip()
                        parsed_queries.append((q_str, q_limit))
                    except ValueError:
                        parsed_queries.append((q, self.settings.get("nvoids_limit", 10)))
                else:
                    parsed_queries.append((q, self.settings.get("nvoids_limit", 10)))
            self.scraper.parsed_queries = parsed_queries

        if hasattr(self, 'pipeline') and self.pipeline:
            self.pipeline.config = dict(self.settings, groq_api_key=get_groq_key())

    def _get_pipeline(self):
        """Return a cached OutreachPipeline; rebuild only when key settings change."""
        from core.outreach.outreach_pipeline import OutreachPipeline
        key_settings = {k: v for k, v in self.settings.items() if k != "window_geometry"}
        key_settings['groq_api_key'] = get_groq_key()
        key = (json.dumps(key_settings, sort_keys=True, default=str), json.dumps(self.profiles, sort_keys=True, default=str))
        if self._pipeline is None or self._pipeline_key != key:
            self.log_ui("⚙ Initializing pipeline…")
            if self._pipeline is not None and hasattr(self._pipeline, "shutdown"):
                self._pipeline.shutdown()
            self._pipeline = OutreachPipeline(dict(self.settings, groq_api_key=get_groq_key()), self.profiles)
            self._pipeline_key = key
        else:
            self.log_ui("♻ Reusing existing pipeline (no settings changed)…")
            if hasattr(self._pipeline, 'reset_runtime_state'):
                self._pipeline.reset_runtime_state()
        self._pipeline.email_engine.log = self.log_ui
        return self._pipeline

    def save_settings_ui(self):
        """Save settings explicitly and show confirmation to the user."""
        self._save_settings()
        messagebox.showinfo("Settings Saved", "Your outreach settings have been saved successfully.")
        self.log_ui("✅ Settings saved successfully.")


    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_widgets(self):

        t = self._theme
        BG, PANEL = t["BG"], t["PANEL"]
        FG, FG2   = t["FG"], t["FG2"]
        BORDER    = t["BORDER"]
        ENTRY_BG  = t["ENTRY_BG"]

        # ── Dark Header Banner ────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG, height=58)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="Career-Ops · Nvoids | Recruiter outreach",
                 bg=BG, fg="#76d4c8",
                 font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT, padx=12, pady=8)
        self.status_var = tk.StringVar(value="◉  Idle")
        self.status_lbl = tk.Label(header, textvariable=self.status_var,
                                   bg=BG, fg="#4ade80",
                                   font=("Segoe UI", 11, "bold"))
        self.status_lbl.pack(side=tk.RIGHT, padx=18)

        # ── Live Date & Time Clock Widget ─────────────────────────────
        self.clock_var = tk.StringVar()
        self.clock_lbl = tk.Label(header, textvariable=self.clock_var,
                                  bg=BG, fg="#fde047",
                                  font=("Segoe UI", 11, "bold"))
        self.clock_lbl.pack(side=tk.RIGHT, padx=(0, 20))

        def _update_clock():
            try:
                now = datetime.now()
                self.clock_var.set(now.strftime("📅 %a, %b %d, %Y  |  🕒 %I:%M:%S %p"))
                self.root.after(1000, _update_clock)
            except Exception:
                pass
        _update_clock()

        # ── Main notebook ─────────────────────────────────────────────
        main = ttk.Frame(self.root, padding=(10, 6))
        main.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_dashboard     = ttk.Frame(self.notebook, padding=10)
        self.tab_add_jd        = ttk.Frame(self.notebook, padding=10)
        self.tab_templates     = ttk.Frame(self.notebook, padding=10)
        self.tab_config        = ttk.Frame(self.notebook, padding=10)
        self.tab_dedup         = ttk.Frame(self.notebook, padding=10)
        self.tab_custom_filters = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_dashboard,      text="Dashboard")
        self.notebook.add(self.tab_add_jd,         text="Jobs & Contacts")
        self.notebook.add(self.tab_templates,      text="Templates & AI")
        self.notebook.add(self.tab_config,         text="Email Config")
        self.notebook.add(self.tab_dedup,          text="Dedup")
        self.notebook.add(self.tab_custom_filters, text="Custom Filters")

        self._build_dashboard_tab(t, BG, PANEL, FG, FG2, BORDER, ENTRY_BG)
        self._build_add_jd_tab(t, PANEL, FG, FG2, ENTRY_BG)
        self._build_templates_tab(t, PANEL, FG, ENTRY_BG)
        self._build_config_tab(t, PANEL, FG, FG2)
        self._build_dedup_tab(t, PANEL, FG, FG2)
        self._build_custom_filters_tab(t, PANEL, FG, FG2, ENTRY_BG)

    def _build_dashboard_tab(self, t, BG, PANEL, FG, FG2, BORDER, ENTRY_BG):
        db = self.tab_dashboard

        # ── Action Buttons ────────────────────────────────────────────
        btn_frame = ttk.Frame(db)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        for c in range(3):
            btn_frame.columnconfigure(c, weight=1)

        self.scrape_btn = ttk.Button(btn_frame, text="▶  Scrape & Queue",
                                     command=self.run_nvoids_scraper, style="Start.TButton")
        self.scrape_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=2)

        self.email_btn = ttk.Button(btn_frame, text="✉  Draft Emails",
                                    command=self.run_email_sender, style="Blue.TButton")
        self.email_btn.grid(row=0, column=1, sticky="ew", padx=3, pady=2)

        self.auto_btn = ttk.Button(btn_frame, text="🚀  Auto-Pilot",
                                   command=self.run_auto_pilot, style="Secondary.TButton")
        self.auto_btn.grid(row=0, column=2, sticky="ew", padx=3, pady=2)

        self.stop_btn = ttk.Button(btn_frame, text="⏹  Stop",
                                   command=self.stop_scraper, state=tk.DISABLED, style="Stop.TButton")
        self.stop_btn.grid(row=1, column=2, sticky="ew", padx=3, pady=4)

        self.pause_btn = ttk.Button(btn_frame, text="⏸  Pause",
                                    command=self.pause_scraper, state=tk.DISABLED, style="Amber.TButton")
        self.pause_btn.grid(row=1, column=0, sticky="ew", padx=3, pady=4)

        self.skip_btn = ttk.Button(btn_frame, text="⏭  Skip Job",
                                   command=self.skip_current_job, state=tk.DISABLED, style="Skip.TButton")
        self.skip_btn.grid(row=1, column=1, sticky="ew", padx=3, pady=4)

        # ── Stat Cards ────────────────────────────────────────────────
        cards_frame = ttk.Frame(db)
        cards_frame.pack(fill=tk.X, pady=(0, 6))
        for c in range(4):
            cards_frame.columnconfigure(c, weight=1)

        def _card(col, title, init="0", bg="#1a3a5c", fg="#60a5fa", fg2="#93c5fd"):
            f = tk.Frame(cards_frame, bg=bg, bd=0, highlightthickness=1, highlightbackground=BORDER)
            f.grid(row=0, column=col, sticky="ew", padx=5, pady=2)
            tk.Label(f, text=title, bg=bg, fg=fg2, font=("Segoe UI", 8, "bold")).pack(pady=(8, 0))
            lbl = tk.Label(f, text=init, bg=bg, fg=fg, font=("Segoe UI", 22, "bold"))
            lbl.pack(pady=(2, 8))
            return lbl

        self.jobs_scraped_label  = _card(0, "JOBS SCRAPED",  bg=t["CARD_B"], fg="#60a5fa", fg2="#93c5fd")
        self.jobs_pipeline_label = _card(1, "IN PIPELINE",   bg=t["CARD_G"], fg="#4ade80", fg2="#86efac")
        self.jobs_remaining_label= _card(2, "REMAINING",     bg=t["CARD_Y"], fg="#fbbf24", fg2="#fcd34d")
        self.groq_calls_label    = _card(3, "GROQ CALLS",    bg="#1a1a3a",   fg="#a78bfa", fg2="#c4b5fd")

        def _refresh_groq_counter():
            try:
                from core.outreach.ai_extractor import AIExtractor
                count = AIExtractor.get_call_count()
                self.groq_calls_label.config(text=str(count))
                color = "#f87171" if count >= 12960 else ("#fbbf24" if count >= 10000 else "#a78bfa")
                self.groq_calls_label.config(fg=color)
            except Exception:
                pass
            self.root.after(5000, _refresh_groq_counter)
        _refresh_groq_counter()

        # ── Card 1: Search & Skill Match Targets ─────────────────────────
        card1 = ttk.LabelFrame(db, text="🎯  Search & Skill Match Targets")
        card1.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Search Queries, Max Jobs, Max Age
        c1_row1 = ttk.Frame(card1)
        c1_row1.pack(fill=tk.X, padx=10, pady=(6, 4))
        ttk.Label(c1_row1, text="Queries:").pack(side=tk.LEFT, padx=(0, 6))
        self.nvoids_queries_var = tk.StringVar(value=self.settings.get("nvoids_queries", "Data Engineer, AI Engineer"))
        ttk.Entry(c1_row1, textvariable=self.nvoids_queries_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

        ttk.Label(c1_row1, text="Max Jobs:").pack(side=tk.LEFT, padx=(0, 4))
        self.nvoids_limit_var = tk.StringVar(value=str(self.settings.get("nvoids_limit", 10)))
        ttk.Entry(c1_row1, textvariable=self.nvoids_limit_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(c1_row1, text="Max Age (h):").pack(side=tk.LEFT, padx=(0, 4))
        self.nvoids_max_age_var = tk.StringVar(value=str(self.settings.get("nvoids_max_age_hours", 24)))
        ttk.Combobox(c1_row1, textvariable=self.nvoids_max_age_var, values=["12", "24", "48", "72", "168"], width=5).pack(side=tk.LEFT)

        limits_row = ttk.Frame(card1)
        limits_row.pack(fill=tk.X, padx=10, pady=6)
        ttk.Label(limits_row, text="Daily draft/send limit:").pack(side=tk.LEFT, padx=(0, 4))
        self.daily_cap_var = tk.StringVar(value=str(self.settings.get("daily_cap", 50)))
        ttk.Entry(limits_row, textvariable=self.daily_cap_var, width=5).pack(side=tk.LEFT)
        ttk.Label(limits_row, text="Per batch/cycle:").pack(side=tk.LEFT, padx=(12, 4))
        self.cycle_cap_var = tk.StringVar(value=str(self.settings.get("cycle_cap", 15)))
        ttk.Entry(limits_row, textvariable=self.cycle_cap_var, width=5).pack(side=tk.LEFT)
        ttk.Label(limits_row, text="  0 = unlimited; counts successful drafts/sends").pack(side=tk.LEFT)

        # Row 2: Core Skills, Scan Resume, Min Match %
        c1_row2 = ttk.Frame(card1)
        c1_row2.pack(fill=tk.X, padx=10, pady=(0, 6))
        ttk.Label(c1_row2, text="Core Skills:").pack(side=tk.LEFT, padx=(0, 6))
        self.my_core_skills_var = tk.StringVar(value=self.settings.get("my_core_skills", "Python, AWS, PyTorch, SQL, Spark"))
        ttk.Entry(c1_row2, textvariable=self.my_core_skills_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(c1_row2, text="📄 Scan Resume", command=self._auto_scan_resume, style="Blue.TButton").pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(c1_row2, text="Min Match %:").pack(side=tk.LEFT, padx=(0, 4))
        self.min_match_score_var = tk.StringVar(value=str(self.settings.get("min_match_score", 30)))
        ttk.Combobox(c1_row2, textvariable=self.min_match_score_var, values=["0","10","20","30","40","50","60","80"], state="readonly", width=5).pack(side=tk.LEFT)

        # ── Card 2: Rules, Automation & Toolbar ──────────────────────────
        card2 = ttk.LabelFrame(db, text="⚙️  Rules, Automation & Actions")
        card2.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Exclude Words
        c2_row1 = ttk.Frame(card2)
        c2_row1.pack(fill=tk.X, padx=10, pady=(6, 4))
        ttk.Label(c2_row1, text="Exclude Words:").pack(side=tk.LEFT, padx=(0, 6))
        self.exclude_keywords_var = tk.StringVar(value=self.settings.get("exclude_keywords", "No C2C, W2 Only, US Citizen Only, Clearance"))
        ttk.Entry(c2_row1, textvariable=self.exclude_keywords_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 2: Always Accept Titles
        c2_row2 = ttk.Frame(card2)
        c2_row2.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(c2_row2, text="Always Accept:").pack(side=tk.LEFT, padx=(0, 6))
        self.always_accept_titles_var = tk.StringVar(value=self.settings.get("always_accept_titles", ""))
        ttk.Entry(c2_row2, textvariable=self.always_accept_titles_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        def _load_accept_titles():
            titles = [p.get("name", "").strip() for p in getattr(self, "profiles", []) if p.get("name", "").strip()]
            if titles:
                current = self.always_accept_titles_var.get().strip()
                if current:
                    existing = {t.strip().lower() for t in current.split(",")}
                    new_ones = [t for t in titles if t.lower() not in existing]
                    self.always_accept_titles_var.set(current + (", " + ", ".join(new_ones) if new_ones else ""))
                else:
                    self.always_accept_titles_var.set(", ".join(titles))
                self.log_ui(f"✅ Imported {len(titles)} title(s) into Always Accept.")
            else:
                messagebox.showinfo("No Profiles", "No resume profiles found.")
        ttk.Button(c2_row2, text="📂 Load Profiles", command=_load_accept_titles).pack(side=tk.RIGHT)

        # Row 3: Toggles & Rest Time
        c2_row3 = ttk.Frame(card2)
        c2_row3.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.continuous_var = tk.BooleanVar(value=self.settings.get("continuous_mode", False))
        ck_cont = LabeledToggleSwitch(c2_row3, text="Continuous (24/7)", variable=self.continuous_var, bg=PANEL, fg=FG)
        ck_cont.pack(side=tk.LEFT, padx=(0, 12))

        self.headless_var = tk.BooleanVar(value=self.settings.get("headless", False))
        ck_head = LabeledToggleSwitch(c2_row3, text="👁 Headless", variable=self.headless_var, bg=PANEL, fg=FG)
        ck_head.pack(side=tk.LEFT, padx=(0, 12))

        self.transparent_var = tk.BooleanVar(value=False)
        ck_trans = LabeledToggleSwitch(c2_row3, text="👁 Top", variable=self.transparent_var, command=self._toggle_transparent, bg=PANEL, fg=FG)
        ck_trans.pack(side=tk.LEFT, padx=(0, 4))

        self.transparency_level = tk.DoubleVar(value=0.85)
        ttk.Scale(c2_row3, from_=0.1, to_=1.0, variable=self.transparency_level, orient=tk.HORIZONTAL, command=lambda _: self._toggle_transparent(), length=70).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(c2_row3, text="Rest Window (mins):").pack(side=tk.LEFT, padx=(0, 4))
        self.rest_time_var = tk.StringVar(value=str(self.settings.get("rest_time_mins", 5)))
        ttk.Combobox(c2_row3, textvariable=self.rest_time_var, values=["1","3","5","10","15","30","60"], state="readonly", width=6).pack(side=tk.LEFT)

        # Row 4: Action Toolbar (Separated dedicated button row)
        c2_row4 = ttk.Frame(card2)
        c2_row4.pack(fill=tk.X, padx=10, pady=(4, 6))

        ttk.Button(c2_row4, text="📂 Open Excel",    command=self._open_excel,      style="Blue.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(c2_row4, text="🗑 Clear Logs",    command=self._clear_logs,      style="Amber.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(c2_row4, text="☠ Erase DB",       command=self._clear_excel,     style="Stop.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(c2_row4, text="💾 Save Settings", command=self.save_settings_ui, style="Start.TButton").pack(side=tk.RIGHT)

        c2_row5 = ttk.Frame(card2)
        c2_row5.pack(fill=tk.X, padx=10, pady=(0, 6))
        ttk.Label(
            c2_row5,
            text="Verified mailbox bookkeeping (does not create or send email):",
            foreground=FG2,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            c2_row5, text="Mark All Drafted",
            command=lambda: self._mark_all_email_status("draft"),
            style="Blue.TButton",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            c2_row5, text="Mark All Sent",
            command=lambda: self._mark_all_email_status("sent"),
            style="Amber.TButton",
        ).pack(side=tk.LEFT)

        # ── Live Log ──────────────────────────────────────────────────
        lf = ttk.LabelFrame(db, text="📋  Live Log")
        lf.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        self.log_text = tk.Text(lf, state=tk.DISABLED,
                                bg="#0d1117", fg="#c9d1d9",
                                font=("Consolas", 9), wrap=tk.WORD,
                                insertbackground="white", relief="flat")
        sb = ttk.Scrollbar(lf, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.configure(yscrollcommand=sb.set)

    # ------------------------------------------------------------------
    def _build_add_jd_tab(self, t, PANEL, FG, FG2, ENTRY_BG):
        from utils.jobs_contacts_view import JobsContactsView
        self.add_job_window = tk.Toplevel(self.root)
        self.add_job_window.withdraw()
        self.add_job_window.title("Add Job — paste and save")
        self.add_job_window.geometry("1040x640")
        self.add_job_window.minsize(760, 480)
        self.add_job_window.configure(bg=PANEL)
        self.add_job_window.protocol("WM_DELETE_WINDOW", self.add_job_window.withdraw)
        tb = ttk.Frame(self.add_job_window, padding=12)
        tb.pack(fill=tk.BOTH, expand=True)
        # Top Header Frame
        hdr = ttk.LabelFrame(tb, text="📥  Quick Add Job Description to Excel & Auto-Match Resume")
        hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            hdr,
            text="Paste raw Job Description below. The system extracts recruiter emails/phones, recruiter name, company,\n"
            "auto-matches a resume and saves the job. Close this window to return; unsaved text is retained.",
            font=("Segoe UI", 9, "italic"),
            bg=PANEL, fg="#94a3b8", justify=tk.LEFT, wraplength=900
        ).pack(anchor="w", padx=10, pady=6)

        # Extracted Contact Details Panel
        fields = ttk.LabelFrame(tb, text="📞  Extracted Contact & Application Details")
        fields.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Title, Company, Recruiter Name
        r1 = ttk.Frame(fields)
        r1.pack(fill=tk.X, padx=8, pady=4)
        r1.columnconfigure((0, 1), weight=1, uniform='manual')

        f_title = ttk.Frame(r1)
        f_title.grid(row=0, column=0, sticky='ew', padx=4, pady=3)
        ttk.Label(f_title, text="Job Title / Position:").pack(anchor="w")
        self.manual_title_var = tk.StringVar()
        ttk.Entry(f_title, textvariable=self.manual_title_var).pack(fill=tk.X)

        f_comp = ttk.Frame(r1)
        f_comp.grid(row=0, column=1, sticky='ew', padx=4, pady=3)
        ttk.Label(f_comp, text="Company:").pack(anchor="w")
        self.manual_company_var = tk.StringVar()
        ttk.Entry(f_comp, textvariable=self.manual_company_var).pack(fill=tk.X)

        f_name = ttk.Frame(r1)
        f_name.grid(row=1, column=0, sticky='ew', padx=4, pady=3)
        ttk.Label(f_name, text="Recruiter Name:").pack(anchor="w")
        self.manual_name_var = tk.StringVar()
        ttk.Entry(f_name, textvariable=self.manual_name_var).pack(fill=tk.X)

        f_date = ttk.Frame(r1)
        f_date.grid(row=1, column=1, sticky='ew', padx=4, pady=3)
        ttk.Label(f_date, text="Scraped / Added Date:").pack(anchor="w")
        self.manual_date_var = tk.StringVar()
        ttk.Entry(f_date, textvariable=self.manual_date_var, state="readonly").pack(fill=tk.X)

        # Row 2: Email, Phone Selector, Matched Resume, Email Drafted Status
        r2 = ttk.Frame(fields)
        r2.pack(fill=tk.X, padx=8, pady=(0, 6))
        r2.columnconfigure((0, 1), weight=1, uniform='manual')

        f_email = ttk.Frame(r2)
        f_email.grid(row=0, column=0, sticky='ew', padx=4, pady=3)
        ttk.Label(f_email, text="Recruiter Email:").pack(anchor="w")
        self.manual_email_var = tk.StringVar()
        ttk.Entry(f_email, textvariable=self.manual_email_var).pack(fill=tk.X)

        f_phone = ttk.Frame(r2)
        f_phone.grid(row=0, column=1, sticky='ew', padx=4, pady=3)
        ttk.Label(f_phone, text="Found Phone Number(s):").pack(anchor="w")
        self.manual_phone_var = tk.StringVar()
        self.manual_phone_cb = ttk.Combobox(f_phone, textvariable=self.manual_phone_var, values=[])
        self.manual_phone_cb.pack(fill=tk.X)

        f_resume = ttk.Frame(r2)
        f_resume.grid(row=1, column=0, sticky='ew', padx=4, pady=3)
        ttk.Label(f_resume, text="Matched Resume:").pack(anchor="w")
        self.manual_resume_var = tk.StringVar()
        ttk.Entry(f_resume, textvariable=self.manual_resume_var, state="readonly").pack(fill=tk.X)

        f_status = ttk.Frame(r2)
        f_status.grid(row=1, column=1, sticky='ew', padx=4, pady=3)
        ttk.Label(f_status, text="Email Draft Status:").pack(anchor="w")
        self.manual_draft_status_var = tk.StringVar(value="Not Drafted")
        ttk.Entry(f_status, textvariable=self.manual_draft_status_var, state="readonly").pack(fill=tk.X)

        # Raw JD Text Box Frame
        jd_frame = ttk.LabelFrame(tb, text="📝  Raw Job Description (Paste Text Here)")
        jd_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.manual_jd_text = tk.Text(
            jd_frame, wrap=tk.WORD, font=("Segoe UI", 10), height=5,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, padx=8, pady=6
        )
        jd_scroll = ttk.Scrollbar(jd_frame, command=self.manual_jd_text.yview)
        jd_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.manual_jd_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.manual_jd_text.configure(yscrollcommand=jd_scroll.set)

        # Record Index Tracking for Navigation
        self._manual_record_idx = -1
        self._manual_records_cache = []

        # Action Buttons & Navigation Bar
        btm_frame = ttk.Frame(tb)
        btm_frame.pack(fill=tk.X, pady=(4, 0))

        ttk.Button(
            btm_frame,
            text="⚡ Add / Save to Excel",
            command=self.process_manual_jd,
            style="Start.TButton"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            btm_frame,
            text="⏮ Prev",
            command=self._prev_manual_record,
            style="Blue.TButton"
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            btm_frame,
            text="⏭ Next / Skip",
            command=self._next_manual_record,
            style="Skip.TButton"
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btm_frame,
            text="🧹 Clear",
            command=self._clear_manual_jd_form,
            style="Amber.TButton"
        ).pack(side=tk.LEFT)

        self.manual_jd_status_var = tk.StringVar(value="Ready. Paste a job description and click 'Add / Save to Excel'.")
        self.manual_jd_status_lbl = tk.Label(
            tb,
            textvariable=self.manual_jd_status_var,
            font=("Segoe UI", 9, "bold"),
            bg=PANEL, fg="#38bdf8", anchor="w", wraplength=900
        )
        self.manual_jd_status_lbl.pack(fill=tk.X, pady=(6, 0))


        self._manual_saved_snapshot = self._manual_snapshot()
        self.jobs_view = JobsContactsView(
            self.tab_add_jd,
            path=lambda: self.settings.get("outreach_excel_path", "data/outreach_jobs.xlsx"),
            add_job=self._show_add_job,
            phone_update=self._update_contact_records,
            theme=t,
        )
        self.jobs_view.pack(fill=tk.BOTH, expand=True)

    def _show_add_job(self):
        self.add_job_window.deiconify()
        self.add_job_window.lift()
        self.manual_jd_text.focus_set()

    def _manual_snapshot(self):
        return (self.manual_jd_text.get("1.0", "end-1c"),
                *(getattr(self, name).get() for name in (
                    "manual_title_var", "manual_company_var", "manual_name_var",
                    "manual_email_var", "manual_phone_var")))

    def _confirm_manual_discard(self):
        if self._manual_snapshot() == self._manual_saved_snapshot:
            return True
        return messagebox.askyesno("Unsaved Add Job",
                                   "Discard the unsaved Add Job text and edits?",
                                   parent=self.root)

    def _update_contact_records(self, records, action):
        from core.outreach.excel_store import OutreachExcelStore
        path = self.settings.get("outreach_excel_path", "data/outreach_jobs.xlsx")
        pipeline = getattr(self, "_pipeline", None)
        store = pipeline.excel if pipeline and os.path.abspath(pipeline.excel.filepath) == os.path.abspath(path) else OutreachExcelStore(path)
        status = f"Called ({datetime.now().strftime('%Y-%m-%d %H:%M')})" if action == "called" else "Skipped to Contact"
        return store.update_phone_records(records, status)

    def process_manual_jd(self):
        """Processes pasted JD text, runs AI/keyword resume matcher, and appends to Excel."""
        raw_text = self.manual_jd_text.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Empty JD", "Please paste a Job Description before adding.")
            return

        self.log_ui("📥 Processing manual JD entry...")
        self.manual_jd_status_var.set("⏳ Processing JD and matching resume profile...")
        self.root.update_idletasks()

        try:
            # 1. Extract Recruiter Email & Phone Numbers
            manual_email = self.manual_email_var.get().strip()
            if manual_email:
                recruiter_email = manual_email
            else:
                emails = [
                    e for e in re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', raw_text)
                    if not any(e.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg'))
                ]
                recruiter_email = emails[0] if emails else ""
                self.manual_email_var.set(recruiter_email)

            phones = list(dict.fromkeys(re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', raw_text)))
            self.manual_phone_cb["values"] = phones
            selected_phone = self.manual_phone_var.get().strip()
            if not selected_phone and phones:
                selected_phone = phones[0]
                self.manual_phone_var.set(selected_phone)
            phone = selected_phone

            # Extract Recruiter Name if present
            name_match = re.findall(r'(?:Recruiter|Contact|Hiring Manager|Name)\s*[:\-]\s*([^\n\r]+)', raw_text, re.IGNORECASE)
            recruiter_name = self.manual_name_var.get().strip() or (name_match[0].strip() if name_match else "Recruiter")
            self.manual_name_var.set(recruiter_name)

            # 2. Determine Title, Company & Location
            pipeline = self._get_pipeline()
            manual_title = self.manual_title_var.get().strip()
            if manual_title:
                job_title = manual_title
            else:
                job_title = ""
                role_matches = re.findall(r'(?:Role|Position|Job Title|Title)\s*[:\-]\s*([^\n\r]+)', raw_text, re.IGNORECASE)
                if role_matches:
                    candidate = role_matches[0].strip()
                    candidate = re.sub(r'^(?:is|for|a|an)\s+', '', candidate, flags=re.IGNORECASE).strip()
                    if len(candidate) > 2:
                        job_title = candidate

                if not job_title:
                    junk_words = {"home", "menu", "search", "login", "dashboard", "back", "jobs", "apply", "your email title", "hi", "hello", "dear", "http", "https"}
                    role_keywords = ["engineer", "developer", "architect", "scientist", "analyst", "lead", "manager", "consultant", "specialist", "ai/ml", "genai", "data", "ml", "software", "backend", "fullstack", "frontend"]
                    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

                    for line in lines:
                        l_lower = line.lower()
                        if any(w in l_lower for w in junk_words) and not any(rk in l_lower for rk in ["engineer", "developer", "ai/ml", "genai"]):
                            continue
                        if "@" in line or "http://" in line or "https://" in line:
                            continue
                        if any(rk in l_lower for rk in role_keywords):
                            job_title = line.split("||")[0].split(" at ")[0].strip()
                            break

                    if not job_title:
                        for line in lines:
                            l_lower = line.lower()
                            if line in junk_words or l_lower in junk_words or "@" in line or "http" in line:
                                continue
                            job_title = line[:60].strip()
                            break

                if not job_title:
                    job_title = "AI / Data Engineer"

                if job_title.lower() in ("ai/ml", "genai", "data"):
                    job_title = f"{job_title} Engineer"
                job_title = pipeline._clean_job_title(job_title) or job_title
            self.manual_title_var.set(job_title)

            # Company Extraction
            manual_company = self.manual_company_var.get().strip()
            if manual_company:
                company = manual_company
            else:
                company = ""
                comp_matches = re.findall(r'(?:Company|Client|Vendor)\s*[:\-]\s*([^\n\r]+)', raw_text, re.IGNORECASE)
                if comp_matches:
                    company = comp_matches[0].strip()
                elif recruiter_email and "@" in recruiter_email:
                    domain = recruiter_email.split("@")[-1].split(".")[0].capitalize()
                    if domain.lower() not in ("gmail", "outlook", "yahoo", "hotmail", "icloud"):
                        company = domain
                if not company:
                    company = "Direct Reach out"
            self.manual_company_var.set(company)

            loc_matches = re.findall(r'(?:Location|Loc)\s*[:\-]\s*([^\n\r]+)', raw_text, re.IGNORECASE)
            location = loc_matches[0].strip() if loc_matches else "Remote / Direct"

            # 3. Resume Selection / Matching
            raw_job = {
                "Job Title": job_title,
                "Company": company,
                "Description": raw_text,
                "Recruiter Email": recruiter_email,
                "Phone": phone
            }

            best_profile = pipeline._pick_profile(job_title, raw_text, raw_job=raw_job)
            resume_name = best_profile.get("name", "Default") if best_profile else "Default"
            resume_path = best_profile.get("file_path", "") if best_profile else ""
            self.manual_resume_var.set(resume_name)
            
            from core.outreach.email_engine import EmailEngine
            valid_resume_path = EmailEngine.resolve_valid_resume_path(resume_path, self.profiles)

            # 4. Check draft status & filter excluded emails (domain + exact address) from To/CC/BCC
            from core.outreach.nvoids_scraper import is_email_blocked
            excluded_domains   = self.settings.get("excluded_vendor_domains", "")
            excluded_addresses = self.settings.get("excluded_email_addresses", "")
            if recruiter_email and is_email_blocked(recruiter_email, excluded_domains, excluded_addresses):
                self.log_ui(f"🛡️ [EMAIL FILTER] Recruiter email '{recruiter_email}' is blocked (domain or exact match) — removed from To/CC/BCC.")
                self._append_domain_skip_log(f"Manual JD Email Filtered: '{recruiter_email}' for '{job_title}'")
                recruiter_email = ""
                self.manual_email_var.set("")

            # Build the identity only after recipient filtering, then apply the
            # same SQLite/legacy/Excel dedup gates as scraped jobs.
            dedup_hash = pipeline.dedup._generate_hash(recruiter_email, company, job_title, location, "")
            if (pipeline.state.is_duplicate("outreach", dedup_hash)
                    or pipeline.dedup.is_duplicate(recruiter_email, company, job_title, location, "")
                    or pipeline.excel.is_in_excel(dedup_hash)):
                self.manual_draft_status_var.set("Skipped (Duplicate)")
                self.log_ui(f"⏭ Manual JD skipped as duplicate: {job_title} ({company})")
                return

            draft_status = "Pending Sending" if recruiter_email else ("Call Pending" if phone else "No Email Found")
            self.manual_draft_status_var.set(draft_status)

            added_date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.manual_date_var.set(added_date_str)

            record = {
                "Posted Date": added_date_str,
                "Job Title": job_title,
                "Company": company,
                "Location": location,
                "Keywords": self.settings.get("my_core_skills", ""),
                "Recruiter Name": recruiter_name,
                "Recruiter Email": recruiter_email,
                "Phone": phone,
                "Status": draft_status,
                "Resume Used": resume_name,
                "Email Sent?": "No",
                "Draft/Sent": self.settings.get("send_mode", "draft"),
                "CC": self.settings.get("cc_email", ""),
                "BCC": self.settings.get("bcc_email", ""),
                "Source": "Manual Paste",
                "Dedup Hash": dedup_hash,
                "Job URL": "",
                "Description": raw_text[:800]
            }

            pipeline.excel.append_record(record, auto_flush=True)
            pipeline.excel.flush()

            self._add_phone_pending({
                "Job Title": job_title,
                "Company": company,
                "Phone": phone if phone else "Manual Contact",
                "Resume Used": resume_name,
                "Source": "Manual Paste",
                "URL": "",
                "Dedup Hash": dedup_hash,
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Email Sent?": "No",  # Just added — not yet drafted/sent
            })

            matched_file_basename = os.path.basename(valid_resume_path) if valid_resume_path else "Default"
            msg = (
                f"✅ Added to Excel! | Title: {job_title} | Company: {company} | "
                f"Matched Resume: {resume_name} ({matched_file_basename})"
            )
            if recruiter_email:
                msg += f" | Email: {recruiter_email}"
            if phone:
                msg += f" | Phone: {phone}"

            self.log_ui(f"[Manual Add] {msg}")
            self._manual_saved_snapshot = self._manual_snapshot()
            self.manual_jd_status_var.set(f"✅ Saved to Excel! Matched: {resume_name} | Draft Status: {draft_status}")

            messagebox.showinfo(
                "Job Saved to Excel",
                f"Successfully added to Excel!\n\n"
                f"• Job Title: {job_title}\n"
                f"• Company: {company}\n"
                f"• Recruiter Name: {recruiter_name}\n"
                f"• Recruiter Email: {recruiter_email or 'None'}\n"
                f"• Phone Number(s): {', '.join(phones) if phones else 'None'}\n"
                f"• Matched Resume: {resume_name}\n"
                f"• Email Draft Status: {draft_status}\n\n"
                f"Click 'Draft Emails' to send/draft."
            )

        except Exception as e:
            err_msg = f"Error processing JD: {e}"
            self.log_ui(f"[Manual Add] ❌ {err_msg}")
            self.manual_jd_status_var.set(f"❌ Error: {e}")
            messagebox.showerror("Error", err_msg)

    def _next_manual_record(self):
        """Skip to next record or clear form for next JD."""
        if self._clear_manual_jd_form():
            self.manual_jd_status_var.set("⏭ Ready for the next job description.")

    def _prev_manual_record(self):
        """Move back to previous entry state."""
        self.manual_jd_status_var.set("⏮ Reset to previous record state.")

    def _clear_manual_jd_form(self):
        if not self._confirm_manual_discard():
            return False
        self.manual_title_var.set("")
        self.manual_company_var.set("")
        self.manual_name_var.set("")
        self.manual_date_var.set("")
        self.manual_email_var.set("")
        self.manual_phone_var.set("")
        self.manual_phone_cb["values"] = []
        self.manual_resume_var.set("")
        self.manual_draft_status_var.set("Not Drafted")
        self.manual_jd_text.delete("1.0", tk.END)
        self.manual_jd_status_var.set("Form cleared. Ready for next Job Description.")
        self._manual_saved_snapshot = self._manual_snapshot()
        return True

    # ------------------------------------------------------------------
    # Phone Call Queue Methods
    # ------------------------------------------------------------------

    def _add_phone_pending(self, raw_job: dict):
        """Pipeline notification; all record reads remain in the paged browser."""
        self.root.after(0, self._refresh_phone_queue_from_excel)

    def _refresh_phone_queue_from_excel(self):
        # A single mail emits several progress messages. Coalesce their reads
        # without continually postponing refresh during a busy scraper run.
        if getattr(self, '_jobs_refresh_pending', False):
            return
        self._jobs_refresh_pending = True
        def refresh():
            self._jobs_refresh_pending = False
            if hasattr(self, 'jobs_view'):
                self.jobs_view.refresh()
        self.root.after(350, refresh)

    # ------------------------------------------------------------------
    def _build_templates_tab(self, t, PANEL, FG, ENTRY_BG):
        tb = self.tab_templates

        # Action buttons
        top_row = ttk.Frame(tb)
        top_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(top_row, text="💾 Save Settings", command=self.save_settings_ui, style="Start.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(top_row, text="🧪 Test Email", command=self._test_email, style="Blue.TButton").pack(side=tk.RIGHT)

        # Target Resume
        res_f = ttk.LabelFrame(tb, text="📄  Target Resume")
        res_f.pack(fill=tk.X, pady=(0, 6))
        res_inner = ttk.Frame(res_f)
        res_inner.pack(fill=tk.X, padx=10, pady=8)
        self.target_resume_var = tk.StringVar(value=self.settings.get("target_resume", "Auto-Match (AI)"))
        profile_names = ["Auto-Match (AI)"] + [p.get("name", "") for p in self.profiles]
        ttk.Combobox(res_inner, textvariable=self.target_resume_var,
                     values=profile_names, state="readonly", width=40).pack(side=tk.LEFT)
        ttk.Label(res_inner, text="  ←  Auto-Match uses AI to select the best resume per job",
                  font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)

        # AI Email toggle
        ai_f = ttk.LabelFrame(tb, text="🤖  AI Email Generation")
        ai_f.pack(fill=tk.X, pady=(0, 6))
        ai_inner = ttk.Frame(ai_f)
        ai_inner.pack(fill=tk.X, padx=10, pady=8)
        self.use_ai_email_var = tk.BooleanVar(value=self.settings.get("use_ai_email", False))
        LabeledToggleSwitch(ai_inner, text="Generate Dynamic Email Body via Groq AI",
                            variable=self.use_ai_email_var, bg=PANEL, fg=FG).pack(side=tk.LEFT)
        ttk.Label(ai_inner, text="  (requires Groq API key in System Config)",
                  font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)

        # Multi-Template Selection & Management Panel
        tmpl_mg_f = ttk.LabelFrame(tb, text="📑  Custom Email Templates & Random Rotation")
        tmpl_mg_f.pack(fill=tk.X, pady=(0, 6))
        tmpl_inner = ttk.Frame(tmpl_mg_f)
        tmpl_inner.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(tmpl_inner, text="Selection Mode:").pack(side=tk.LEFT, padx=(0, 6))
        self.template_mode_var = tk.StringVar(value=self.settings.get("template_selection_mode", "random"))
        ttk.Combobox(
            tmpl_inner, textvariable=self.template_mode_var,
            values=["random", "preferred"], state="readonly", width=12
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(tmpl_inner, text="Active Template:").pack(side=tk.LEFT, padx=(0, 6))
        self.active_template_var = tk.StringVar()
        self.template_cb = ttk.Combobox(
            tmpl_inner, textvariable=self.active_template_var,
            state="readonly", width=32
        )
        self.template_cb.pack(side=tk.LEFT, padx=(0, 10))
        self.template_cb.bind("<<ComboboxSelected>>", lambda _: self._on_template_selected())

        ttk.Button(tmpl_inner, text="➕ Add New", command=self._add_new_template).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(tmpl_inner, text="💾 Save Changes", command=self._save_active_template).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(tmpl_inner, text="🗑 Delete", command=self._delete_active_template).pack(side=tk.LEFT)

        # Subject template
        subj_f = ttk.LabelFrame(tb, text="✏️  Email Subject Template")
        subj_f.pack(fill=tk.X, pady=(0, 6))
        subj_inner = ttk.Frame(subj_f)
        subj_inner.pack(fill=tk.X, padx=10, pady=8)
        self.subject_template_var = tk.StringVar(
            value=self.settings.get("subject_template", "Application for {job_title}"))
        ttk.Entry(subj_inner, textvariable=self.subject_template_var).pack(fill=tk.X, expand=True)

        # Template body
        tf = ttk.LabelFrame(tb, text="📝  Email Body  ·  {job_title}  {company_name}  {recruiter_name}  {keywords}  {location}")
        tf.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        self.template_text = tk.Text(tf, wrap=tk.WORD, font=("Segoe UI", 10),
                                     relief="flat", bg=ENTRY_BG, fg=FG,
                                     insertbackground=FG, padx=8, pady=6)
        ts = ttk.Scrollbar(tf, command=self.template_text.yview)
        ts.pack(side=tk.RIGHT, fill=tk.Y)
        self.template_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.template_text.configure(yscrollcommand=ts.set)

        self._refresh_templates_dropdown()

    def _refresh_templates_dropdown(self):
        """Load templates list into dropdown and select active template."""
        templates_list = self.settings.get("templates_list", [])
        if not templates_list:
            templates_list = [{
                "id": "1",
                "name": "Template 1 - Professional Standard",
                "body": self.settings.get("template", "Hi {recruiter_name},\n\nPlease find my resume attached.\n\nBest regards,\n[Your Name]")
            }]
            self.settings["templates_list"] = templates_list

        names = [t.get("name", f"Template {i+1}") for i, t in enumerate(templates_list)]
        self.template_cb["values"] = names
        sel_id = str(self.settings.get("selected_template_id", "1"))
        matched_name = names[0]
        for t in templates_list:
            if str(t.get("id")) == sel_id:
                matched_name = t.get("name", names[0])
                break
        self.active_template_var.set(matched_name)
        self._on_template_selected()

    def _on_template_selected(self):
        """Display the body of the currently selected template."""
        sel_name = self.active_template_var.get()
        templates_list = self.settings.get("templates_list", [])
        for t in templates_list:
            if t.get("name") == sel_name:
                self.template_text.delete("1.0", tk.END)
                self.template_text.insert(tk.END, t.get("body", ""))
                self.settings["selected_template_id"] = str(t.get("id"))
                break

    def _add_new_template(self):
        """Add a new custom email template to the list."""
        templates_list = self.settings.get("templates_list", [])
        new_id = str(len(templates_list) + 1)
        new_name = f"Template {new_id} - Custom"
        new_template = {
            "id": new_id,
            "name": new_name,
            "body": "Hi {recruiter_name},\n\nI am writing regarding the {job_title} position at {company_name}.\n\nBest regards,\n[Your Name]"
        }
        templates_list.append(new_template)
        self.settings["templates_list"] = templates_list
        self.settings["selected_template_id"] = new_id
        self._refresh_templates_dropdown()
        self.log_ui(f"➕ Added new template: {new_name}")

    def _save_active_template(self):
        """Save modifications to the active template body."""
        sel_name = self.active_template_var.get()
        new_body = self.template_text.get("1.0", tk.END).strip()
        templates_list = self.settings.get("templates_list", [])
        for t in templates_list:
            if t.get("name") == sel_name:
                t["body"] = new_body
                break
        self.settings["templates_list"] = templates_list
        self.settings["template"] = new_body
        self._save_settings()
        self.log_ui(f"💾 Saved template changes for '{sel_name}'")

    def _delete_active_template(self):
        """Delete the currently selected template if more than 1 exists."""
        templates_list = self.settings.get("templates_list", [])
        if len(templates_list) <= 1:
            messagebox.showwarning("Cannot Delete", "You must keep at least one template.")
            return
        sel_name = self.active_template_var.get()
        self.settings["templates_list"] = [t for t in templates_list if t.get("name") != sel_name]
        self._refresh_templates_dropdown()
        self.log_ui(f"🗑 Deleted template '{sel_name}'")

    # ------------------------------------------------------------------
    def _build_config_tab(self, t, PANEL, FG, FG2):
        cb = self.tab_config

        # ── Email Provider & Mode ────────────────────────────────────
        ep_f = ttk.LabelFrame(cb, text="📧  Email Provider & Mode")
        ep_f.pack(fill=tk.X, pady=(0, 6))
        ep_inner = ttk.Frame(ep_f)
        ep_inner.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(ep_inner, text="Provider:").pack(side=tk.LEFT, padx=(0, 6))
        self.provider_var = tk.StringVar(value=self.settings.get("email_provider", "outlook_web"))
        self.provider_var.trace_add("write", lambda *_: self.on_provider_change())
        ttk.Combobox(ep_inner, textvariable=self.provider_var,
                     values=["outlook", "outlook_web", "gmail_web", "gmail_api", "zoho_web"],
                     state="readonly", width=14).pack(side=tk.LEFT)

        ttk.Label(ep_inner, text="   Send Mode:").pack(side=tk.LEFT, padx=(0, 6))
        self.mode_var = tk.StringVar(value=self.settings.get("send_mode", "draft"))
        ttk.Combobox(ep_inner, textvariable=self.mode_var,
                     values=["draft", "send"], state="readonly", width=10).pack(side=tk.LEFT)

        # ── Provider info/credential frames (shown/hidden by on_provider_change) ─

        # Outlook Desktop
        self.outlook_frame = ttk.Frame(cb)
        tk.Label(self.outlook_frame,
                 text="✅  Native Outlook Desktop — no credentials needed.",
                 fg="#4ade80", bg="#14532d",
                 font=("Segoe UI", 9, "bold"), padx=12, pady=8).pack(fill=tk.X, padx=10, pady=4)

        # Outlook Web
        self.outlook_web_frame = ttk.Frame(cb)
        tk.Label(self.outlook_web_frame,
                 text="✅  Chrome / Outlook Web — browser opens once for login. Shared chrome_profile/.",
                 fg="#93c5fd", bg="#1e3a5f",
                 font=("Segoe UI", 9, "bold"), padx=12, pady=8).pack(fill=tk.X, padx=10, pady=4)

        # Gmail Web
        self.gmail_web_frame = ttk.Frame(cb)
        tk.Label(self.gmail_web_frame,
                 text="✅  Gmail Web (mail.google.com) — Chrome browser opens once for login.\n"
                      "    Supports both Draft and Send modes. Shared chrome_profile/.",
                 fg="#34d399", bg="#064e3b",
                 font=("Segoe UI", 9, "bold"), padx=12, pady=8,
                 justify=tk.LEFT).pack(fill=tk.X, padx=10, pady=4)

        # Gmail API (OAuth2)
        self.gmail_api_frame = ttk.Frame(cb)
        tk.Label(self.gmail_api_frame,
                 text="Gmail API uses OAuth2, not a mailbox API key. Select a Google OAuth Desktop Client JSON.\n"
                      "Connect / Re-authorize opens Google login and creates or safely replaces the local token.",
                 fg="#86efac", bg="#14532d",
                 font=("Segoe UI", 9, "bold"), padx=12, pady=8,
                 justify=tk.LEFT).pack(fill=tk.X, padx=10, pady=4)

        gmail_secret_row = ttk.Frame(self.gmail_api_frame)
        gmail_secret_row.pack(fill=tk.X, padx=10, pady=(2, 3))
        ttk.Label(gmail_secret_row, text="OAuth Client JSON:", width=18).pack(side=tk.LEFT)
        self.gmail_client_secret_var = tk.StringVar(
            value=self.settings.get("gmail_client_secret_path", "config/gmail_client_secret.json")
        )
        ttk.Entry(gmail_secret_row, textvariable=self.gmail_client_secret_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )
        ttk.Button(
            gmail_secret_row, text="Browse…", command=self._choose_gmail_client_secret,
            style="Blue.TButton",
        ).pack(side=tk.LEFT)

        gmail_token_row = ttk.Frame(self.gmail_api_frame)
        gmail_token_row.pack(fill=tk.X, padx=10, pady=3)
        ttk.Label(gmail_token_row, text="Generated Token File:", width=18).pack(side=tk.LEFT)
        self.gmail_token_path_var = tk.StringVar(
            value=self.settings.get("gmail_token_path", "config/gmail_token.json")
        )
        ttk.Entry(gmail_token_row, textvariable=self.gmail_token_path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )
        ttk.Button(
            gmail_token_row, text="Choose Save Location…", command=self._choose_gmail_token_path,
            style="Blue.TButton",
        ).pack(side=tk.LEFT)

        gmail_action_row = ttk.Frame(self.gmail_api_frame)
        gmail_action_row.pack(fill=tk.X, padx=10, pady=(3, 7))
        ttk.Button(
            gmail_action_row, text="Connect / Re-authorize Gmail API",
            command=self._authorize_gmail_api, style="Start.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            gmail_action_row, text="Check Configuration",
            command=self._refresh_gmail_api_status, style="Blue.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.gmail_api_status_var = tk.StringVar(value="Not checked")
        self.gmail_api_status_label = ttk.Label(
            gmail_action_row, textvariable=self.gmail_api_status_var
        )
        self.gmail_api_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.root.after(0, self._refresh_gmail_api_status)

        # Zoho Mail Web
        self.zoho_web_frame = ttk.Frame(cb)
        zoho_info = tk.Label(self.zoho_web_frame,
                 text="✅  Zoho Mail Web (mail.zoho.com) — Chrome browser opens once for login.\n"
                      "    Works with both Personal and Business/Workplace accounts. Shared chrome_profile/.",
                 fg="#fb923c", bg="#431407",
                 font=("Segoe UI", 9, "bold"), padx=12, pady=8,
                 justify=tk.LEFT)
        zoho_info.pack(fill=tk.X, padx=10, pady=(4, 2))
        # Optional: Zoho custom domain field
        zoho_domain_row = ttk.Frame(self.zoho_web_frame)
        zoho_domain_row.pack(fill=tk.X, padx=10, pady=(0, 6))
        ttk.Label(zoho_domain_row,
                  text="Zoho Domain (optional — leave blank for zoho.com):").pack(side=tk.LEFT, padx=(0, 6))
        self.zoho_domain_var = tk.StringVar(value=self.settings.get("zoho_domain", ""))
        ttk.Entry(zoho_domain_row, textvariable=self.zoho_domain_var, width=30).pack(side=tk.LEFT)
        ttk.Label(zoho_domain_row,
                  text="  e.g. yourcompany.zoho.com",
                  font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)

        # ── CC / BCC ─────────────────────────────────────────────────
        cc_f = ttk.LabelFrame(cb, text="📨  CC / BCC")
        cc_f.pack(fill=tk.X, pady=(0, 6))
        cc_inner = ttk.Frame(cc_f)
        cc_inner.pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(cc_inner, text="CC:").pack(side=tk.LEFT, padx=(0, 6))
        self.cc_var = tk.StringVar(value=self.settings.get("cc_email", ""))
        ttk.Entry(cc_inner, textvariable=self.cc_var, width=30).pack(side=tk.LEFT)
        ttk.Label(cc_inner, text="   BCC:").pack(side=tk.LEFT, padx=(0, 6))
        self.bcc_var = tk.StringVar(value=self.settings.get("bcc_email", ""))
        ttk.Entry(cc_inner, textvariable=self.bcc_var, width=30).pack(side=tk.LEFT)

        # ── Groq API Key ──────────────────────────────────────────────
        gk_f = ttk.LabelFrame(cb, text="🔑  Shared Groq API Key  (Dice + Nvoids)")
        gk_f.pack(fill=tk.X, pady=(0, 6))
        gk_inner = ttk.Frame(gk_f)
        gk_inner.pack(fill=tk.X, padx=10, pady=8)
        self.groq_key_var = tk.StringVar(value=get_groq_key())
        self._groq_key_last_seen = self.groq_key_var.get().strip()
        ttk.Entry(gk_inner, textvariable=self.groq_key_var, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(gk_inner, text="  Saved for both bots",
                  font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        groq_check = ttk.Frame(gk_f)
        groq_check.pack(fill=tk.X, padx=10, pady=(0, 8))
        self.groq_status_var = tk.StringVar(value="Connection not checked")
        ttk.Button(groq_check, text="Check Groq connection",
                   command=self._check_groq_connection).pack(side=tk.LEFT)
        ttk.Label(groq_check, textvariable=self.groq_status_var).pack(side=tk.LEFT, padx=10)

        # Save button
        ttk.Button(cb, text="💾 Save Settings", command=self.save_settings_ui,
                   style="Start.TButton").pack(fill=tk.X, pady=(8, 0))

        # row1 alias needed by on_provider_change
        self.row1 = ep_inner

    def _check_groq_connection(self):
        """Read-only account and model check; never starts email processing."""
        key = self.groq_key_var.get().strip()
        if not key:
            self.groq_status_var.set("Enter a Groq key first")
            return
        self.groq_status_var.set("Checking connection…")

        def check():
            try:
                from groq import Groq
                from core.outreach.ai_extractor import AIExtractor
                available = {item.id for item in Groq(api_key=key, timeout=8, max_retries=0).models.list().data}
                if AIExtractor.MODEL in available:
                    result = "Connected; Nvoids model available"
                else:
                    result = "Connected, but Nvoids model is unavailable. Update the model before using AI."
            except Exception as exc:
                name = type(exc).__name__
                result = ("Groq rejected the key. Check the key in Dice or Nvoids."
                          if name in {'AuthenticationError', 'PermissionDeniedError'} else
                          "Groq check failed. Check the connection and try again.")
            try:
                self.root.after(0, lambda: self.groq_status_var.set(result) if self.root.winfo_exists() else None)
            except tk.TclError:
                pass

        threading.Thread(target=check, daemon=True).start()

    def _choose_gmail_client_secret(self):
        path = filedialog.askopenfilename(
            title="Select Google OAuth Client JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.gmail_client_secret_var.set(os.path.abspath(path))
            self._refresh_gmail_api_status()

    def _choose_gmail_token_path(self):
        current = self.gmail_token_path_var.get().strip() or "config/gmail_token.json"
        path = filedialog.asksaveasfilename(
            title="Choose Local Gmail OAuth Token File",
            initialdir=os.path.dirname(os.path.abspath(current)),
            initialfile=os.path.basename(current),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.gmail_token_path_var.set(os.path.abspath(path))
            self._refresh_gmail_api_status()

    def _gmail_engine_from_ui(self):
        from core.outreach.email_engine import EmailEngine

        config = dict(self.settings)
        config["gmail_client_secret_path"] = self.gmail_client_secret_var.get().strip()
        config["gmail_token_path"] = self.gmail_token_path_var.get().strip()
        return EmailEngine(config)

    def _refresh_gmail_api_status(self):
        try:
            engine = self._gmail_engine_from_ui()
            valid, message = engine.gmail_api_configuration_status()
            prefix = "Ready: " if valid else "Not ready: "
            self.gmail_api_status_var.set(prefix + message)
        except Exception as exc:
            self.gmail_api_status_var.set(f"Not ready: {exc}")

    def _authorize_gmail_api(self):
        """Authorize Gmail OAuth in a worker because browser consent may take time."""
        self._save_settings()
        engine = self._gmail_engine_from_ui()
        valid, message = engine.gmail_api_configuration_status()
        if not valid:
            self.gmail_api_status_var.set(f"Not ready: {message}")
            messagebox.showerror("Gmail API Configuration", message)
            return

        self.gmail_api_status_var.set(
            "Connecting: expired tokens are backed up; complete Google authorization in the browser…"
        )

        def _run():
            try:
                engine.authorize_gmail_api()

                def _connected():
                    self._pipeline_key = None
                    self._refresh_gmail_api_status()
                    messagebox.showinfo(
                        "Gmail API Connected",
                        "OAuth authorization completed. Use Test Email in draft mode with an address you control "
                        "to verify mailbox access and attachment handling.",
                    )

                self.root.after(0, _connected)
            except Exception as exc:
                def _failed(error=str(exc)):
                    self.gmail_api_status_var.set(f"Connection failed: {error}")
                    messagebox.showerror("Gmail API Connection Failed", error)

                self.root.after(0, _failed)

        threading.Thread(target=_run, daemon=True).start()


    # ------------------------------------------------------------------
    # Provider frame switcher
    # ------------------------------------------------------------------

    def on_provider_change(self, *_):
        """Show the correct info/credential panel for the selected email provider."""
        all_frames = (
            self.outlook_frame,
            self.outlook_web_frame,
            self.gmail_web_frame,
            getattr(self, 'gmail_api_frame', None),
            self.zoho_web_frame,
        )
        for f in all_frames:
            if f:
                f.pack_forget()

        provider = self.provider_var.get()
        if provider == "outlook_web":
            self.outlook_web_frame.pack(fill=tk.X, pady=(0, 6))
        elif provider == "gmail_web":
            self.gmail_web_frame.pack(fill=tk.X, pady=(0, 6))
        elif provider == "gmail_api":
            if hasattr(self, 'gmail_api_frame'):
                self.gmail_api_frame.pack(fill=tk.X, pady=(0, 6))
        elif provider == "zoho_web":
            self.zoho_web_frame.pack(fill=tk.X, pady=(0, 6))
        else:  # "outlook"
            self.outlook_frame.pack(fill=tk.X, pady=(0, 6))


    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _open_excel(self):
        path = os.path.abspath("data/outreach_jobs.xlsx")
        if os.path.exists(path):
            os.startfile(path)
        else:
            data_dir = os.path.abspath("data")
            backups = [f for f in os.listdir(data_dir) if f.startswith("outreach_jobs_backup") and f.endswith(".xlsx")] if os.path.exists(data_dir) else []
            if backups:
                latest = sorted(backups)[-1]
                os.startfile(os.path.join(data_dir, latest))
                self.log_ui(f"📂 Opened latest backup file: {latest}")
            else:
                self.log_ui("⚠ Excel file not found — run 'Scrape & Queue' first.")

    def _close_all_db_connections(self):
        """Close any active SQLite database handles in pipeline or scraper so files can be deleted cleanly."""
        import gc
        try:
            if hasattr(self, '_pipeline') and self._pipeline:
                if hasattr(self._pipeline, 'stop_worker'):
                    self._pipeline.stop_worker()
                if hasattr(self._pipeline, 'dedup') and self._pipeline.dedup:
                    self._pipeline.dedup.close()
                self._pipeline = None
                self._pipeline_key = None

            if hasattr(self, 'pipeline') and self.pipeline:
                if hasattr(self.pipeline, 'dedup') and self.pipeline.dedup:
                    self.pipeline.dedup.close()
                self.pipeline = None

            if hasattr(self, 'scraper') and self.scraper:
                if hasattr(self.scraper, '_dedup_db') and self.scraper._dedup_db:
                    self.scraper._dedup_db.close()
                self.scraper = None

            gc.collect()
        except Exception as e:
            print(f"[OutreachUI] Error closing DB connections: {e}")

    def _clear_excel(self):
        excel_path = os.path.abspath("data/outreach_jobs.xlsx")
        db_path = os.path.abspath("data/outreach_dedup.db")
        
        if not os.path.exists(excel_path) and not os.path.exists(db_path):
            messagebox.showinfo("Clear Data", "No tracking data exists yet. Nothing to clear.")
            return
            
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to completely delete the outreach_jobs.xlsx file AND the Dedup Tracking Database? This will permanently erase the bot's memory of previously processed jobs."):
            self._close_all_db_connections()
            errs = []
            if os.path.exists(excel_path):
                try:
                    os.remove(excel_path)
                except Exception as e:
                    errs.append(f"Excel ({e})")
            if os.path.exists(db_path):
                try:
                    for p in (db_path, db_path + "-wal", db_path + "-shm"):
                        if os.path.exists(p):
                            os.remove(p)
                except Exception:
                    # Fallback SQL wipe if Windows process lock prevents os.remove
                    try:
                        from core.outreach.dedup_engine import DedupEngine
                        d = DedupEngine()
                        d.wipe_database()
                        d.close()
                    except Exception as e2:
                        errs.append(f"Dedup DB ({e2})")

            if not errs:
                self.log_ui("🗑 Deleted outreach_jobs.xlsx and outreach_dedup.db. Bot memory cleared.")
                messagebox.showinfo("Success", "Data cleared successfully! The bot will now treat all jobs as brand new.")
            else:
                self.log_ui(f"⚠ Memory cleared (with notes: {', '.join(errs)})")
                messagebox.showinfo("Success", "Data cleared successfully!")

    def _mark_all_email_status(self, target: str):
        """Bulk-correct verified mailbox status without contacting providers."""
        normalized = str(target or "").strip().lower()
        if normalized not in {"draft", "sent"}:
            return
        display = "Drafted" if normalized == "draft" else "Sent"
        if not messagebox.askyesno(
            f"Confirm Mark All {display}",
            f"Mark every eligible email row as {display}?\n\n"
            "This is a bookkeeping action only. It will NOT create a draft or send an email. "
            "Use it only after you have verified those messages in your mailbox.\n\n"
            "Skipped, call-only, missing-email, and already matching rows will not be changed.",
        ):
            return

        self._save_settings()
        self._set_buttons_state(tk.DISABLED)
        self.log_ui(f"Updating all eligible records to {display}…")

        def _run():
            try:
                pipeline = self._get_pipeline()
                changed, failures = pipeline.mark_all_email_status(normalized)

                def _done():
                    self._set_buttons_state(tk.NORMAL)
                    self._refresh_phone_queue_from_excel()
                    if failures:
                        messagebox.showwarning(
                            f"Mark All {display}",
                            f"Excel changed {changed} row(s), but {failures} state/dedup update(s) failed. "
                            "Review the live log before continuing.",
                        )
                    else:
                        messagebox.showinfo(
                            f"Mark All {display}",
                            f"Updated {changed} eligible row(s). No email was created or sent.",
                        )
                    self.log_ui(
                        f"Bulk status complete: {changed} row(s) marked {display}; "
                        f"state-sync failures: {failures}."
                    )

                self.root.after(0, _done)
            except Exception as exc:
                def _failed(error=str(exc)):
                    self._set_buttons_state(tk.NORMAL)
                    self.log_ui(f"Bulk status update failed: {error}")
                    messagebox.showerror("Bulk Status Failed", error)

                self.root.after(0, _failed)

        threading.Thread(target=_run, daemon=True).start()

    def run_email_sender(self):
        """Run a checked batch and display authoritative outcome counts."""
        self._save_settings()
        self._set_buttons_state(tk.DISABLED)
        self.status_var.set("Checking email batch…")

        def _run():
            from core.outreach.batch_result import BatchResult
            result = BatchResult(stop_reason="Batch did not start")
            try:
                self.pipeline = self._get_pipeline()
                result = self.pipeline.process_pending_emails(
                    log_ui=self.log_ui
                )
            except Exception as exc:
                result.stop_reason = f"Batch interrupted: {exc}"
                self.log_ui(result.stop_reason)
            finally:
                def _done():
                    self._set_buttons_state(tk.NORMAL)
                    self.status_var.set(f"Drafted {result.drafted} | Sent {result.sent} | Needs review {result.unconfirmed} | Deferred {result.deferred}")
                    self.status_lbl.config(fg="#4ade80" if result.stop_reason == "Complete" else "#fbbf24")
                    messagebox.showinfo("Email batch result", result.summary())
                    self._refresh_phone_queue_from_excel()
                self.root.after(0, _done)
        self._active_worker = threading.Thread(target=_run, daemon=True)
        self._active_worker.start()


    def _test_email(self):
        from tkinter import simpledialog
        test_email = simpledialog.askstring("Test Email", "Enter a recipient email address to send a test message to:")
        if not test_email:
            return
            
        self._save_settings()
        configured_mode = str(self.settings.get("send_mode", "draft")).strip().lower()
        if configured_mode == "send" and not messagebox.askyesno(
            "Confirm Live Test Send",
            "Email Config is currently in SEND mode. This test will send a real message "
            "to the address you entered. Continue?",
        ):
            return
        self.log_ui(f"▶ Testing email integration to {test_email}...")
        self._set_buttons_state(tk.DISABLED)

        def _run():
            try:
                self.pipeline = self._get_pipeline()

                mock_job = {
                    "Job Title": "Test Software Engineer",
                    "Company": "TestCorp Inc.",
                    "Recruiter Name": "Alex Testing",
                    "Recruiter Email": test_email,
                    "Keywords": "Python, React, SQL",
                    "Location": "Remote"
                }
                
                resume_path = self.pipeline._resolve_resume_path(self.settings.get("target_resume", ""))
                    
                body, subject = self.pipeline._build_email(mock_job, mock_job["Job Title"], mock_job["Company"])
                
                status = self.pipeline.email_engine.send_email(mock_job, resume_path, body, subject)
                self.log_ui(f"✅ Test Email Result: {status}")
                success = status in {"Draft", "Sent"}

                def _show_result():
                    if success:
                        messagebox.showinfo(
                            "Test Success",
                            f"Provider confirmed the test operation.\nResult: {status}",
                        )
                    else:
                        messagebox.showwarning(
                            "Test Failed",
                            f"Email attempt failed or was not confirmed.\nResult: {status}\n\n"
                            "Check Live Log for details.",
                        )

                self.root.after(0, _show_result)
            except Exception as e:
                self.log_ui(f"❌ Test Failed: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.root.after(0, lambda: self._set_buttons_state(tk.NORMAL))

        threading.Thread(target=_run, daemon=True).start()

    def run_nvoids_scraper(self):
        """
        Start the Nvoids scraper in ONE background thread.
        The scraper itself is now synchronous inside that thread.
        Heavy imports (selenium, pipeline) happen inside the thread
        so the UI never blocks.
        """
        self._save_settings()
        self.log_ui("▶ Starting Nvoids scraper…")
        self._set_buttons_state(tk.DISABLED)

        def _run():
            try:
                self.pipeline = self._get_pipeline()

                from core.outreach.nvoids_scraper import NvoidsScraper
                self.scraper  = NvoidsScraper(
                    queries      = self.settings["nvoids_queries"],
                    limit        = self.settings["nvoids_limit"],
                    pipeline     = self.pipeline,
                    skip_email   = True,
                    log_callback = self.log_ui,
                    stats_callback = self.update_scraper_stats,
                    max_age_hours = self.settings.get("nvoids_max_age_hours", 24),
                    continuous_loop = self.settings.get("continuous_mode", False),
                    rest_time_mins = self.settings.get("rest_time_mins", 5),
                    groq_api_key = get_groq_key(),
                    my_core_skills = self.settings.get("my_core_skills", ""),
                    always_accept_titles = self.settings.get("always_accept_titles", ""),
                    min_match_score = self.settings.get("min_match_score", 30),
                    exclude_keywords = self.settings.get("exclude_keywords", ""),
                    excluded_vendor_domains = self.settings.get("excluded_vendor_domains", ""),
                    excluded_email_addresses = self.settings.get("excluded_email_addresses", ""),
                    headless     = self.settings.get("headless", False),
                    email_recontact_days = self.settings.get("cooldown_hours", 48) / 24,
                    phone_callback = self._add_phone_pending,
                )
                self.scraper.start()   # Synchronous in this thread
            except Exception as e:
                self.log_ui(f"❌ SCRAPER ERROR: {e}\n{traceback.format_exc()}")
            finally:
                self.root.after(0, lambda: self._set_buttons_state(tk.NORMAL))

        self._active_worker = threading.Thread(target=_run, daemon=True)
        self._active_worker.start()

    def run_auto_pilot(self):
        """
        Runs the scraper but executes emails immediately (skip_email=False).
        """
        self._save_settings()
        self.log_ui("🚀 Starting Auto-Pilot (Scrape + Email)...")
        self._set_buttons_state(tk.DISABLED)

        def _run():
            try:
                from core.outreach.nvoids_scraper import NvoidsScraper
                self.pipeline = self._get_pipeline()
                problems = self.pipeline.preflight()
                if problems:
                    message = '\n'.join(problems)
                    self.log_ui('Preflight blocked: ' + message)
                    self.root.after(0, lambda: messagebox.showerror('Fix configuration before Auto-Pilot', message))
                    return
                
                self.scraper = NvoidsScraper(
                    queries      = self.settings["nvoids_queries"],
                    limit        = self.settings["nvoids_limit"],
                    pipeline     = self.pipeline,
                    skip_email   = False,
                    log_callback = self.log_ui,
                    stats_callback = self.update_scraper_stats,
                    max_age_hours = self.settings.get("nvoids_max_age_hours", 24),
                    continuous_loop = self.settings.get("continuous_mode", False),
                    rest_time_mins = self.settings.get("rest_time_mins", 5),
                    groq_api_key = get_groq_key(),
                    my_core_skills = self.settings.get("my_core_skills", ""),
                    always_accept_titles = self.settings.get("always_accept_titles", ""),
                    min_match_score = self.settings.get("min_match_score", 30),
                    exclude_keywords = self.settings.get("exclude_keywords", ""),
                    excluded_vendor_domains = self.settings.get("excluded_vendor_domains", ""),
                    excluded_email_addresses = self.settings.get("excluded_email_addresses", ""),
                    headless     = self.settings.get("headless", False),
                    email_recontact_days = self.settings.get("cooldown_hours", 48) / 24,
                    phone_callback = self._add_phone_pending,
                )
                self.scraper.start()
            except Exception as e:
                self.log_ui(f"❌ AUTO-PILOT ERROR: {e}\n{traceback.format_exc()}")
            finally:
                self.root.after(0, lambda: self._set_buttons_state(tk.NORMAL))

        self._active_worker = threading.Thread(target=_run, daemon=True)
        self._active_worker.start()

    def pause_scraper(self):
        is_paused = False
        
        if hasattr(self, 'scraper') and self.scraper:
            self.scraper.pause_flag = not getattr(self.scraper, 'pause_flag', False)
            is_paused = self.scraper.pause_flag
            
        if hasattr(self, 'pipeline') and self.pipeline:
            self.pipeline.pause_flag = not getattr(self.pipeline, 'pause_flag', False)
            is_paused = self.pipeline.pause_flag or is_paused

        if not is_paused:
            self.pause_btn.config(text="⏸  Pause")
            self.log_ui("▶ Resumed pipeline...")
            self.status_var.set("⬤  Running")
            self.status_lbl.config(fg="#6ee7b7")
        else:
            self.pause_btn.config(text="▶  Resume")
            self.log_ui("⏸ Paused pipeline. Will halt after current action.")
            self.status_var.set("⏸  Paused")
            self.status_lbl.config(fg="#fbbf24")

    def stop_scraper(self):
        self.log_ui("⏹ Stop requested! Will halt after current job finishes...")
        if hasattr(self, 'scraper') and self.scraper:
            self.scraper.stop_flag = True
            self.scraper.pause_flag = False
        if hasattr(self, 'pipeline') and self.pipeline:
            self.pipeline.stop_flag = True
        self.stop_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.status_var.set("⏹  Stopping...")
        self.status_lbl.config(fg="#f87171")
        # Close the shared Selenium web browser (Outlook/Gmail/Zoho) cleanly
        try:
            from core.outreach.email_engine import EmailEngine
            EmailEngine.close_web_drivers()
        except Exception:
            pass

    def skip_current_job(self):
        """Tell the scraper to abandon the current job and move to the next one."""
        skipped = False
        if hasattr(self, 'scraper') and self.scraper:
            self.scraper.skip_flag = True
            skipped = True
        if hasattr(self, 'pipeline') and self.pipeline:
            self.pipeline.skip_flag = True
            skipped = True
            
        if skipped:
            self.log_ui("⏭ Skip requested — will jump to next job after current action.")
            self.status_var.set("⏭  Skipping...")
            self.status_lbl.config(fg="#a78bfa")
        else:
            self.log_ui("⚠ No active process to skip.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _toggle_transparent(self):
        if self.transparent_var.get():
            self.root.attributes("-alpha", self.transparency_level.get())
            self.root.attributes("-topmost", True)
        else:
            self.root.attributes("-alpha", 1.0)
            self.root.attributes("-topmost", False)

    def _blink_ui(self):
        original_bg = self._theme["BG"]
        blink_bg = "#b45309"
        
        def step1(): self.root.configure(bg=blink_bg)
        def step2(): self.root.configure(bg=original_bg)
        def step3(): self.root.configure(bg=blink_bg)
        def step4(): self.root.configure(bg=original_bg)
        
        self.root.after(0, step1)
        self.root.after(300, step2)
        self.root.after(600, step3)
        self.root.after(900, step4)

    def _auto_scan_resume(self):
        """Auto-parse selected PDF/DOCX resume using PyMuPDF / python-docx and extract core tech skills."""
        file_path = filedialog.askopenfilename(
            title="Select Resume File",
            filetypes=[
                ("Resume Files", "*.pdf *.docx *.doc *.txt"),
                ("PDF Documents", "*.pdf"),
                ("Word Documents", "*.docx *.doc"),
                ("All Files", "*.*")
            ]
        )
        if not file_path:
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()
            text = ""
            if ext == ".pdf":
                import fitz
                doc = fitz.open(file_path)
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
            elif ext in (".docx", ".doc"):
                import docx
                doc = docx.Document(file_path)
                text = "\n".join(p.text for p in doc.paragraphs)
            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()

            if not text.strip():
                messagebox.showwarning("Empty File", "Could not extract text from the selected file.")
                return

            # Comprehensive tech skill terms catalog (100+ skills across Data, AI, Cloud, Dev)
            TECH_CATALOG = [
                "Python", "AWS", "SQL", "Spark", "PySpark", "Databricks", "Snowflake", "ETL", "ELT",
                "Data Engineering", "Data Pipeline", "Big Data", "Hadoop", "Hive", "Redshift", "Glue",
                "Athena", "EMR", "S3", "Lambda", "Azure", "ADF", "Synapse", "GCP", "BigQuery",
                "PostgreSQL", "MySQL", "MongoDB", "NoSQL", "Redis", "Kafka", "Airflow", "dbt",
                "Docker", "Kubernetes", "K8s", "Terraform", "CI/CD", "Git", "GitHub", "Linux", "Bash",
                "Java", "Scala", "C++", "C#", ".NET", "Go", "Rust", "JavaScript", "TypeScript",
                "React", "Node.js", "FastAPI", "Flask", "Django", "REST API", "GraphQL",
                "PyTorch", "TensorFlow", "Scikit-Learn", "Pandas", "NumPy", "MLOps",
                "GenAI", "Generative AI", "LLM", "RAG", "LangChain", "LlamaIndex", "Vector DB",
                "Pinecone", "Chroma", "Weaviate", "NLP", "Computer Vision", "Machine Learning",
                "Deep Learning", "AI", "Power BI", "Tableau", "Looker", "Excel"
            ]

            # Also harvest candidate skills from loaded profiles if present
            profile_kws = []
            for p in getattr(self, "profiles", []):
                for k in p.get("unique_keywords", []) + p.get("keywords", []):
                    if k.strip() and k.strip().title() not in TECH_CATALOG:
                        profile_kws.append(k.strip().title())

            ALL_SKILLS = TECH_CATALOG + profile_kws
            text_lower = text.lower()
            found_skills = []

            for term in ALL_SKILLS:
                pattern = r'\b' + re.escape(term.lower()).replace(r'\ ', r'\s+') + r'\b'
                if re.search(pattern, text_lower):
                    if term not in found_skills:
                        found_skills.append(term)

            if found_skills:
                skills_str = ", ".join(found_skills[:30])
                self.my_core_skills_var.set(skills_str)
                self.save_settings_ui()
                self.log_ui(f"📄 Auto-scanned '{os.path.basename(file_path)}': extracted {len(found_skills)} skills -> {skills_str}")
                messagebox.showinfo(
                    "Resume Scanned Successfully",
                    f"Successfully extracted {len(found_skills)} tech skills from '{os.path.basename(file_path)}':\n\n{skills_str}"
                )
            else:
                messagebox.showinfo("Resume Scanned", f"Scanned '{os.path.basename(file_path)}', but no standard tech keywords were found.")
        except Exception as e:
            messagebox.showerror("Error Scanning Resume", f"Could not parse resume file:\n{e}")

    def log_ui(self, message: str):
        """Thread-safe append to the log box with timestamp."""
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        print(line, end="")

        def _update():
            if message.startswith('Export pending:'):
                self.status_var.set(message)
            if "BLINK_UI_PHONE_DETECTED" in message:
                self._blink_ui()
                return

            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, line)
            from utils.log_view import trim_log_widget
            trim_log_widget(self.log_text)
            
            if "(Phone:" in message or "Call Pending" in message:
                self.log_text.tag_add("phone_hi", "end-1l linestart", "end-1l lineend")
                self.log_text.tag_config("phone_hi", background="#eab308", foreground="black", font=("Consolas", 9, "bold"))

            if "Drafting [" in message or "📅 Scraped:" in message:
                self.log_text.tag_add("draft_hi", "end-1l linestart", "end-1l lineend")
                self.log_text.tag_config("draft_hi", background="#1e3a8a", foreground="#93c5fd", font=("Consolas", 9, "bold"))

            if "🎯 Skill Match:" in message or "✅ Skill Match:" in message:
                self.log_text.tag_add("match_hi", "end-1l linestart", "end-1l lineend")
                self.log_text.tag_config("match_hi", background="#065f46", foreground="#a7f3d0", font=("Consolas", 9, "bold"))

            # 🚫 Domain-skip lines — highlight bright red + also mirror to Custom Filters tab
            if "[DOMAIN SKIP]" in message or "Skipped (Excluded Vendor Domain" in message:
                self.log_text.tag_add("domain_skip_hi", "end-1l linestart", "end-1l lineend")
                self.log_text.tag_config("domain_skip_hi", background="#7f1d1d", foreground="#fca5a5", font=("Consolas", 9, "bold"))
                if hasattr(self, '_append_domain_skip_log'):
                    self._append_domain_skip_log(message)

            # ✅ C2C Override lines — highlight green so they're easy to spot
            if "[C2C OVERRIDE]" in message or "[C2C CARD OVERRIDE]" in message:
                self.log_text.tag_add("c2c_override_hi", "end-1l linestart", "end-1l lineend")
                self.log_text.tag_config("c2c_override_hi", background="#14532d", foreground="#86efac", font=("Consolas", 9, "bold"))

            # ⚡ Instant JD tab auto-update whenever email draft or send occurs
            if "[Pipeline] ✅" in message or "EMAIL DRAFT COMPLETE" in message or "Drafting [" in message:
                self._on_email_event_instant_update(message)

            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.root.after(0, _update)

    def _on_email_event_instant_update(self, message: str):
        """Instantly updates JD tab status & treeview when an email draft/send event occurs."""
        try:
            # 1. Trigger instant refresh of Phone Call Queue treeview in JD tab
            self._refresh_phone_queue_from_excel()

            # 2. Check if current manual form title matches the emailed job title
            cur_manual_title = self.manual_title_var.get().strip().lower()
            if cur_manual_title:
                msg_lower = message.lower()
                if cur_manual_title in msg_lower or any(w in msg_lower for w in cur_manual_title.split() if len(w) > 3):
                    if "draft" in msg_lower:
                        self.manual_draft_status_var.set("Drafted")
                    elif "sent" in msg_lower:
                        self.manual_draft_status_var.set("Sent")
                    self.manual_jd_status_var.set(f"✅ Updated instantly! Email status: {self.manual_draft_status_var.get()}")
        except Exception as e:
            print(f"[OutreachUI] Instant update error: {e}")

    def update_scraper_stats(self, scraped: int, pipeline: int, remaining: int):
        def _update():
            self.jobs_scraped_label.config(text=str(scraped))
            self.jobs_pipeline_label.config(text=str(pipeline))
            self.jobs_remaining_label.config(text=str(remaining))
        self.root.after(0, _update)

    def _set_buttons_state(self, state):
        self.scrape_btn.config(state=state)
        self.email_btn.config(state=state)
        self.auto_btn.config(state=state)
        if state == tk.NORMAL:
            self.status_var.set("⬤  Idle")
            self.status_lbl.config(fg="#6ee7b7")
            self.stop_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED)
            self.skip_btn.config(state=tk.DISABLED)
            self.pause_btn.config(text="⏸  Pause")
        else:
            self.status_var.set("⬤  Running")
            self.status_lbl.config(fg="#34d399")
            self.stop_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL)
            self.skip_btn.config(state=tk.NORMAL)

    # ------------------------------------------------------------------
    # Custom Filters tab
    # ------------------------------------------------------------------

    def _build_custom_filters_tab(self, t, PANEL, FG, FG2, ENTRY_BG):
        """Build the 🚫 Custom Filters tab for domain-level vendor exclusions."""
        tb = self.tab_custom_filters
        BORDER = t["BORDER"]

        # ── Section 1: Excluded Vendor Email Domains ───────────────────────
        domain_lf = ttk.LabelFrame(tb, text="🚫  Excluded Vendor Email Domains")
        domain_lf.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            domain_lf,
            text=(
                "Enter email domains to SKIP (one per line or comma-separated).\n"
                "Example: @xyz.com  or  xyz.com  — any recruiter whose email matches\n"
                "a listed domain will be skipped with the reason shown in the Live Log."
            ),
            font=("Segoe UI", 9, "italic"),
            bg=PANEL, fg="#94a3b8", justify=tk.LEFT,
        ).pack(anchor="w", padx=10, pady=(6, 4))

        # Single-line entry for quick paste
        row1 = ttk.Frame(domain_lf)
        row1.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(row1, text="Domains (comma-separated):").pack(side=tk.LEFT, padx=(0, 6))
        self.excluded_vendor_domains_var = tk.StringVar(
            value=self.settings.get("excluded_vendor_domains", "googlegroups.com, jobs.nvoids.com")
        )
        ttk.Entry(row1, textvariable=self.excluded_vendor_domains_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # Quick Add Presets Row
        preset_frame = ttk.Frame(domain_lf)
        preset_frame.pack(fill=tk.X, padx=10, pady=(2, 6))
        ttk.Label(preset_frame, text="Quick Add Common Exclusions:", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        def _add_preset_domain(d_str):
            current = self.excluded_vendor_domains_var.get().strip()
            existing = [d.strip().lower().lstrip('@') for d in current.replace("\n", ",").split(",") if d.strip()]
            clean = d_str.strip().lower().lstrip('@')
            if clean not in existing:
                new_val = (current + f", @{clean}") if current else f"@{clean}"
                self.excluded_vendor_domains_var.set(new_val)
                self.save_settings_ui()

        ttk.Button(preset_frame, text="+ @googlegroups.com", command=lambda: _add_preset_domain("googlegroups.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(preset_frame, text="+ @jobs.nvoids.com", command=lambda: _add_preset_domain("jobs.nvoids.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(preset_frame, text="+ @nvoids.com", command=lambda: _add_preset_domain("nvoids.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))

        # Helper label showing parsed domains live
        self._domain_preview_var = tk.StringVar(value="")
        preview_lbl = tk.Label(
            domain_lf,
            textvariable=self._domain_preview_var,
            font=("Consolas", 8), bg=PANEL, fg="#fbbf24", anchor="w", wraplength=900,
        )
        preview_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        def _update_preview(*_):
            raw = self.excluded_vendor_domains_var.get().strip()
            if not raw:
                self._domain_preview_var.set("No domains configured — all vendors will be processed.")
                return
            domains = [
                d.strip().lower().lstrip('@')
                for d in raw.replace("\n", ",").split(",")
                if d.strip()
            ]
            self._domain_preview_var.set(
                f"🚫 Will skip vendors from: {', '.join('@' + d for d in domains)}"
            )

        self.excluded_vendor_domains_var.trace_add("write", _update_preview)
        _update_preview()  # Initial render

        # ── Section 2: Blocked Specific Email Addresses ─────────────────────
        email_block_lf = ttk.LabelFrame(tb, text="🚫  Blocked Specific Email Addresses (To / CC / BCC)")
        email_block_lf.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            email_block_lf,
            text=(
                "Enter EXACT email addresses to BLOCK — they will NEVER be inserted into To, CC, or BCC.\n"
                "One per line  OR  comma-separated. Example:  jobs@nvoids.com, noreply@googlegroups.com\n"
                "The job listing & phone number are still kept — only the email address is removed."
            ),
            font=("Segoe UI", 9, "italic"),
            bg=PANEL, fg="#94a3b8", justify=tk.LEFT,
        ).pack(anchor="w", padx=10, pady=(6, 4))

        email_block_row = ttk.Frame(email_block_lf)
        email_block_row.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(email_block_row, text="Blocked Emails:").pack(side=tk.LEFT, padx=(0, 6))
        self.excluded_email_addresses_var = tk.StringVar(
            value=self.settings.get("excluded_email_addresses", "")
        )
        ttk.Entry(email_block_row, textvariable=self.excluded_email_addresses_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # Quick add presets for common system/noreply addresses
        email_preset_frame = ttk.Frame(email_block_lf)
        email_preset_frame.pack(fill=tk.X, padx=10, pady=(2, 4))
        ttk.Label(email_preset_frame, text="Quick Add:", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        def _add_preset_email(email_str):
            current = self.excluded_email_addresses_var.get().strip()
            existing_lower = [e.strip().lower() for e in current.replace("\n", ",").split(",") if e.strip()]
            clean = email_str.strip().lower()
            if clean not in existing_lower:
                new_val = (current + f", {clean}") if current else clean
                self.excluded_email_addresses_var.set(new_val)
                self.save_settings_ui()

        ttk.Button(email_preset_frame, text="+ jobs@nvoids.com",
                   command=lambda: _add_preset_email("jobs@nvoids.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(email_preset_frame, text="+ noreply@googlegroups.com",
                   command=lambda: _add_preset_email("noreply@googlegroups.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(email_preset_frame, text="+ postmaster@nvoids.com",
                   command=lambda: _add_preset_email("postmaster@nvoids.com"), style="Skip.TButton").pack(side=tk.LEFT, padx=(0, 4))

        # Live preview of blocked addresses
        self._email_block_preview_var = tk.StringVar(value="")
        tk.Label(
            email_block_lf,
            textvariable=self._email_block_preview_var,
            font=("Consolas", 8), bg=PANEL, fg="#fbbf24", anchor="w", wraplength=900,
        ).pack(anchor="w", padx=10, pady=(0, 6))

        def _update_email_block_preview(*_):
            raw = self.excluded_email_addresses_var.get().strip()
            if not raw:
                self._email_block_preview_var.set("No specific emails blocked.")
                return
            emails_list = [e.strip() for e in raw.replace("\n", ",").split(",") if e.strip()]
            self._email_block_preview_var.set(
                f"🚫 Will strip from To/CC/BCC: {', '.join(emails_list)}"
            )

        self.excluded_email_addresses_var.trace_add("write", _update_email_block_preview)
        _update_email_block_preview()  # initial render

        # ── Section 3: Current Skip Log (filtered) ────────────────────────
        skip_lf = ttk.LabelFrame(tb, text="📋  Filter Activity Log (live — updates as bot runs)")
        skip_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        tk.Label(
            skip_lf,
            text="Lines below are auto-populated when the bot skips a vendor due to a domain match.",
            font=("Segoe UI", 8, "italic"), bg=PANEL, fg="#64748b",
        ).pack(anchor="w", padx=8, pady=(4, 0))

        self.domain_skip_log = tk.Text(
            skip_lf, state=tk.DISABLED,
            bg="#0d1117", fg="#f87171",
            font=("Consolas", 9), wrap=tk.WORD, relief="flat", height=12,
        )
        sb2 = ttk.Scrollbar(skip_lf, command=self.domain_skip_log.yview)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.domain_skip_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.domain_skip_log.configure(yscrollcommand=sb2.set)

        def _clear_skip_log():
            self.domain_skip_log.config(state=tk.NORMAL)
            self.domain_skip_log.delete("1.0", tk.END)
            self.domain_skip_log.config(state=tk.DISABLED)

        btn_row = ttk.Frame(tb)
        btn_row.pack(fill=tk.X, pady=(0, 0))
        ttk.Button(btn_row, text="🗑 Clear Skip Log", command=_clear_skip_log,
                   style="Amber.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="💾 Save Settings", command=self.save_settings_ui,
                   style="Start.TButton").pack(side=tk.RIGHT)

    def _append_domain_skip_log(self, message: str):
        """Thread-safe append to the domain skip log panel on the Custom Filters tab."""
        def _update():
            try:
                self.domain_skip_log.config(state=tk.NORMAL)
                ts = datetime.now().strftime("%H:%M:%S")
                self.domain_skip_log.insert(tk.END, f"[{ts}] {message}\n")
                self.domain_skip_log.see(tk.END)
                self.domain_skip_log.config(state=tk.DISABLED)
            except Exception:
                pass

    def on_close(self):
        """Keep resources alive until producers and provider work have stopped."""
        if getattr(self, '_closing', False) or not self._confirm_manual_discard():
            return
        self._closing = True
        self.status_var.set('Stopping; waiting for current work to finish…')
        for target in (getattr(self, 'scraper', None), getattr(self, '_pipeline', None)):
            if target:
                target.stop_flag = True
                target.pause_flag = False
        def wait_for_producer():
            if getattr(self, '_active_worker', None) and self._active_worker.is_alive():
                self.root.after(250, wait_for_producer)
                return
            def close_resources():
                try:
                    pipeline = getattr(self, '_pipeline', None)
                    if pipeline:
                        pipeline.shutdown(timeout=10)
                    from core.outreach.email_engine import EmailEngine
                    EmailEngine.close_web_drivers()
                    self.root.after(0, self.root.destroy)
                except Exception as exc:
                    def blocked(error=str(exc)):
                        self._closing = False
                        self.status_var.set(error)
                    self.root.after(0, blocked)
            threading.Thread(target=close_resources, daemon=True).start()
        wait_for_producer()

    # ------------------------------------------------------------------
    # Dedup tab
    # ------------------------------------------------------------------

    def _build_dedup_tab(self, t, PANEL, FG, FG2):
        """Build the Dedup Controls tab."""
        BORDER = t["BORDER"]
        cb = self.tab_dedup

        dd = ttk.LabelFrame(cb, text="🛡️  Duplicate Suppression Controls")
        dd.pack(fill=tk.X, pady=(0, 8))

        # Row 1 – cooldown hours + refresh button
        row1 = ttk.Frame(dd)
        row1.pack(fill=tk.X, padx=6, pady=(6, 2))

        ttk.Label(row1, text="Cooldown Window (hours):").pack(side=tk.LEFT, padx=(0, 6))
        self.cooldown_hours_var = tk.StringVar(
            value=str(self.settings.get("cooldown_hours", 48))
        )
        ttk.Combobox(
            row1, textvariable=self.cooldown_hours_var,
            values=["12", "24", "48", "72", "168"],
            state="readonly", width=8
        ).pack(side=tk.LEFT)
        ttk.Label(
            row1,
            text="  ← same vendor re-posting same role is blocked for this many hours",
            font=("Segoe UI", 8, "italic"), foreground=FG2
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            row1, text="🔄 Refresh Status",
            command=self._refresh_cooldown_status,
            style="Blue.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))

        # Row 2 – clear cooldown for a specific email
        row2 = ttk.Frame(dd)
        row2.pack(fill=tk.X, padx=6, pady=(2, 4))

        ttk.Label(row2, text="Clear Cooldown for Email:").pack(side=tk.LEFT, padx=(0, 6))
        self.clear_cooldown_email_var = tk.StringVar()
        ttk.Entry(
            row2, textvariable=self.clear_cooldown_email_var, width=36
        ).pack(side=tk.LEFT)
        ttk.Button(
            row2, text="🧹 Clear (All Roles)",
            command=lambda: self._clear_cooldown_for_email(all_roles=True),
            style="Amber.TButton"
        ).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(
            row2, text="🗑 Erase Dedup DB",
            command=self._erase_dedup_db,
            style="Stop.TButton"
        ).pack(side=tk.RIGHT, padx=(0, 0))

        # Row 2b – clear ALL cooldowns at once
        row2b = ttk.Frame(dd)
        row2b.pack(fill=tk.X, padx=6, pady=(0, 4))
        ttk.Button(
            row2b, text="⚡ Clear ALL Cooldowns (Layers 1 & 2)",
            command=self._clear_all_cooldowns,
            style="Stop.TButton"
        ).pack(side=tk.LEFT)

        # Row 3 – status display
        status_frame = ttk.LabelFrame(dd, text="Active Cooldowns (last 50)")
        status_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

        self.cooldown_status_text = tk.Text(
            status_frame,
            height=8,
            state=tk.DISABLED,
            bg="#0d1117", fg="#94a3b8",
            font=("Consolas", 8),
            relief="flat",
            wrap=tk.NONE,
        )
        sb = ttk.Scrollbar(status_frame, orient=tk.HORIZONTAL, command=self.cooldown_status_text.xview)
        sb.pack(side=tk.BOTTOM, fill=tk.X, padx=4)
        self.cooldown_status_text.configure(xscrollcommand=sb.set)
        self.cooldown_status_text.pack(fill=tk.X, padx=4, pady=(4, 0))

        # Save button
        ttk.Button(cb, text="💾 Save Settings", command=self.save_settings_ui,
                   style="Start.TButton").pack(fill=tk.X, pady=(8, 0))

        # Auto-refresh every 30 s
        self._schedule_cooldown_refresh()

    def _schedule_cooldown_refresh(self):
        """Auto-refresh cooldown status every 30 seconds."""
        self._refresh_cooldown_status()
        self.root.after(30_000, self._schedule_cooldown_refresh)

    def _refresh_cooldown_status(self):
        """Read active cooldowns from DedupEngine and display them."""
        try:
            from core.outreach.dedup_engine import DedupEngine
            cooldown_hours = int(self.cooldown_hours_var.get() or 48)
            dedup = DedupEngine(cooldown_hours=cooldown_hours)
            records = dedup.get_cooldown_status()

            self.cooldown_status_text.config(state=tk.NORMAL)
            self.cooldown_status_text.delete("1.0", tk.END)

            if not records:
                self.cooldown_status_text.insert(
                    tk.END, "✅  No active cooldowns — all vendors are contactable.\n"
                )
            else:
                header = f"{'EMAIL':<35} {'ROLE':<30} {'SENT':<20} {'HRS LEFT'}\n"
                self.cooldown_status_text.insert(tk.END, header)
                self.cooldown_status_text.insert(tk.END, "-" * 95 + "\n")
                for r in records:
                    line = (
                        f"{r['recruiter_email']:<35} "
                        f"{r['norm_title'][:28]:<30} "
                        f"{r['sent_at'][:16]:<20} "
                        f"{r['hours_remaining']:.1f}h remaining\n"
                    )
                    self.cooldown_status_text.insert(tk.END, line)

            self.cooldown_status_text.config(state=tk.DISABLED)
        except Exception as e:
            pass  # Non-critical UI widget — don't crash

    def _clear_cooldown_for_email(self, all_roles: bool = True):
        """Clear cooldown records for the entered email address."""
        email = self.clear_cooldown_email_var.get().strip()
        if not email:
            messagebox.showwarning(
                "Input Required",
                "Please enter a recruiter email address to clear cooldown for."
            )
            return
        try:
            from core.outreach.dedup_engine import DedupEngine
            cooldown_hours = int(self.cooldown_hours_var.get() or 48)
            dedup = DedupEngine(cooldown_hours=cooldown_hours)
            dedup.clear_cooldown(email, norm_title=None)  # clears all roles for this email
            self.log_ui(f"🧹 Cooldown cleared for: {email} (all roles)")
            messagebox.showinfo(
                "Cooldown Cleared",
                f"Cooldown cleared for {email}.\n"
                f"This vendor will be treated as contactable on the next scrape run."
            )
            self._refresh_cooldown_status()
        except Exception as e:
            messagebox.showerror("Error", f"Could not clear cooldown: {e}")

    def _clear_all_cooldowns(self):
        """Delete every cooldown and content-fingerprint record (Layers 1 & 2)."""
        if not messagebox.askyesno(
            "Clear All Cooldowns",
            "This will remove ALL active cooldowns (Layers 1 & 2) so every vendor\n"
            "becomes immediately re-contactable.\n\n"
            "The sent_jobs history (Layer 0) is NOT affected.\n\nContinue?"
        ):
            return
        try:
            from core.outreach.dedup_engine import DedupEngine
            cooldown_hours = int(self.cooldown_hours_var.get() or 48)
            dedup = DedupEngine(cooldown_hours=cooldown_hours)
            deleted = dedup.clear_all_cooldowns()
            self.log_ui(f"⚡ Cleared {deleted} cooldown record(s) — all vendors are now re-contactable.")
            messagebox.showinfo("Done", f"Cleared {deleted} cooldown record(s).\nAll vendors are now immediately contactable.")
            self._refresh_cooldown_status()
        except Exception as e:
            messagebox.showerror("Error", f"Could not clear cooldowns: {e}")

    def _erase_dedup_db(self):
        """Nuclear option — wipe the entire dedup DB."""
        db_path = os.path.abspath("data/outreach_dedup.db")
        if not os.path.exists(db_path):
            messagebox.showinfo("Erase Dedup DB", "No dedup database found.")
            return
        if messagebox.askyesno(
            "Confirm Erase",
            "This will delete ALL dedup records (sent_jobs, content fingerprints, cooldowns).\n"
            "The bot will treat every vendor as brand-new. Continue?"
        ):
            try:
                self._close_all_db_connections()
                wiped = False
                try:
                    for p in (db_path, db_path + "-wal", db_path + "-shm"):
                        if os.path.exists(p):
                            os.remove(p)
                    wiped = True
                except Exception:
                    from core.outreach.dedup_engine import DedupEngine
                    d = DedupEngine()
                    wiped = d.wipe_database()
                    d.close()

                if wiped:
                    self.log_ui("🗑 Dedup database erased. All vendor history cleared.")
                    self._refresh_cooldown_status()
                    messagebox.showinfo("Done", "Dedup DB erased. The bot starts fresh on next run.")
                else:
                    messagebox.showerror("Error", "Could not erase DB file.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to erase DB: {e}")



if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    from utils.process_lock import instance_lock
    try:
        with instance_lock('nvoids', os.path.join(os.path.dirname(__file__), 'data')):
            root = tk.Tk()
            app = OutreachUI(root)
            root.protocol("WM_DELETE_WINDOW", app.on_close)
            root.mainloop()
    except TimeoutError:
        messagebox.showerror('Nvoids already running', 'Close the existing Nvoids window before launching another copy.')

