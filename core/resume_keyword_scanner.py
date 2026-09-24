import hashlib
import json
import os
import re
import datetime
from core.file_utils import extract_text_from_file

CACHE_DIR = "data/keyword_cache"

class ResumeKeywordScanner:
    """
    Extracts tech keywords from resumes and job descriptions using Groq LLM.
    Caches resume scans by file hash to avoid redundant API calls.
    """
    def __init__(self, groq_scorer):
        self.groq_scorer = groq_scorer
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
            
    def scan_resume(self, file_path: str) -> dict:
        """
        Reads a resume file, sends to Groq to extract tech keywords, 
        and classifies them into unique (specialized) vs general.
        Caches the result using the file's MD5 hash.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Resume not found at {file_path}")
            
        # Get file hash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
            
        cache_path = os.path.join(CACHE_DIR, f"resume_{file_hash}.json")
        if os.path.exists(cache_path):
            from core.groq_resume_scorer import GroqResumeScorer
            if isinstance(self.groq_scorer, GroqResumeScorer):
                GroqResumeScorer._CACHED_CALLS += 1
            with open(cache_path, 'r') as f:
                return json.load(f)
                
        # Not cached, read text
        text = extract_text_from_file(file_path)
        if not text:
            raise ValueError(f"Could not extract text from {file_path}")
            
        return self._extract_keywords_from_text(text, cache_path, is_resume=True)

    def extract_jd_keywords(self, jd_text: str, job_id: str = None) -> dict:
        """
        Extracts tech keywords from a job description.
        Caches by job_id if provided.
        """
        if job_id:
            cache_path = os.path.join(CACHE_DIR, f"jd_{job_id}.json")
            if os.path.exists(cache_path):
                from core.groq_resume_scorer import GroqResumeScorer
                if isinstance(self.groq_scorer, GroqResumeScorer):
                    GroqResumeScorer._CACHED_CALLS += 1
                with open(cache_path, 'r') as f:
                    return json.load(f)
        else:
            cache_path = None
            
        return self._extract_keywords_from_text(jd_text, cache_path, is_resume=False)

    def _extract_keywords_from_text(self, text: str, cache_path: str, is_resume: bool) -> dict:
        """Helper to call LLM (Groq or Gemini) for keyword extraction and caching."""
        api_keys = getattr(self.groq_scorer, '_api_keys', []) if self.groq_scorer else []
        if not api_keys:
            return {"unique": [], "general": []}
            
        # Limit text length to avoid token limit
        text = text[:8000]
        
        prompt = (
            "You are an expert IT recruiter and tech keyword extractor.\n"
            "Extract ALL technical skills, tools, frameworks, languages, and specific domain concepts "
            f"from the following {'resume' if is_resume else 'job description'}.\n\n"
            "RULES:\n"
            "1. ONLY extract hard skills and technologies (e.g. 'React', 'Neo4j', 'Kubernetes', 'AWS IAM', 'Graph RAG').\n"
            "2. DO NOT extract soft skills (e.g. 'communication', 'leadership', 'agile', 'mentoring', 'teamwork').\n"
            "3. Classify each keyword as either 'unique' (specialized/advanced frameworks, niche tools like LangGraph, Neo4j, CrewAI, Databricks, Snowflake) "
            "or 'general' (common skills like Python, SQL, Docker, Git, AWS, Azure).\n"
            "4. CRITICAL: You MUST extract an exhaustive list. Aim to extract 40 to 80+ keywords for a standard resume. Read sentence-by-sentence and extract every single technology, framework, database, or tool mentioned.\n"
            "5. DO NOT REPEAT ANY KEYWORDS.\n"
            "6. Return strictly valid JSON with this exact structure:\n"
            "{\n"
            '  "unique": ["LangGraph", "Neo4j", ...],\n'
            '  "general": ["Python", "SQL", ...]\n'
            "}\n"
            "Do not output markdown blocks or any other text.\n\n"
            f"TEXT TO ANALYZE:\n{text}"
        )
        
        import time
        start_idx = getattr(self.groq_scorer, '_select_key_index', lambda: 0)() if self.groq_scorer else 0
        keys_tried = 0
        raw_result = None
        t0 = time.time()

        while keys_tried < max(len(api_keys), 1):
            key_idx = (start_idx + keys_tried) % len(api_keys)
            active_key = api_keys[key_idx]
            provider_name = "Groq" if active_key.startswith("gsk_") else "Gemini"
            masked_key = f"{active_key[:8]}...****" if len(active_key) > 8 else "****"
            
            if hasattr(self.groq_scorer, '_log') and callable(self.groq_scorer._log):
                self.groq_scorer._log(f"[Groq AI] 🚀 Hitting {provider_name} API (Key #{key_idx+1}: {masked_key}) for {'resume' if is_resume else 'JD'} keyword discovery...")

            try:
                raw_result = self.groq_scorer._call_llm(prompt, active_key)
                break
            except Exception as e:
                keys_tried += 1
                if hasattr(self.groq_scorer, '_log') and callable(self.groq_scorer._log):
                    self.groq_scorer._log(f"[Groq AI] ⚠️ Key #{key_idx+1} ({masked_key}) failed: {e}. Trying next key...")

        if not raw_result:
            return {"unique": [], "general": []}

        elapsed = round(time.time() - t0, 2)

        from core.groq_resume_scorer import GroqResumeScorer
        if isinstance(self.groq_scorer, GroqResumeScorer):
            GroqResumeScorer._TOTAL_CALLS += 1
            GroqResumeScorer._LAST_CALL_TIME = datetime.datetime.now().strftime("%H:%M:%S")

        from utils.json_utils import safe_json_parse
        parsed = safe_json_parse(raw_result, default={})
        
        from core.matcher import _ENGLISH_STOP_WORDS
        def _clean_kws(kw_list):
            cleaned = []
            for k in kw_list:
                s_val = str(k).strip()
                if s_val and s_val.lower() not in _ENGLISH_STOP_WORDS and not s_val.isdigit():
                    cleaned.append(s_val)
            return cleaned

        result = {
            "unique": _clean_kws(parsed.get("unique", [])),
            "general": _clean_kws(parsed.get("general", []))
        }
        
        if hasattr(self.groq_scorer, '_log') and callable(self.groq_scorer._log):
            self.groq_scorer._log(f"[Groq AI] ✅ Keyword discovery finished in {elapsed}s: Extracted {len(result['unique'])} priority & {len(result['general'])} general keywords.")

        if cache_path:
            with open(cache_path, 'w') as f:
                json.dump(result, f)
                
        return result

    def find_gaps(self, resume_kws: dict, jd_kws: dict, profile_dict: dict) -> dict:
        """
        Skill Gap Analysis & ATS Fit Scoring:
        Identifies tech keywords required in the Job Description (jd_kws) that are
        MISSING from the candidate's resume or profile keywords, and computes ATS fit %.
        """
        def _norm(lst): return {k.lower(): k for k in lst}

        res_unique = _norm(resume_kws.get("unique", []))
        res_general = _norm(resume_kws.get("general", []))
        res_all = {**res_general, **res_unique}

        jd_unique = _norm(jd_kws.get("unique", []))
        jd_general = _norm(jd_kws.get("general", []))

        prof_unique_list = profile_dict.get("unique_keywords", [])
        prof_general_list = profile_dict.get("keywords", [])
        prof_all = _norm(prof_unique_list + prof_general_list)

        candidate_all = {**res_all, **prof_all}

        from core.matcher import ResumeMatcher
        cand_regex_list = []
        for kw in candidate_all.values():
            pat = ResumeMatcher.build_keyword_pattern(kw)
            if pat:
                cand_regex_list.append(re.compile(pat, re.IGNORECASE))

        # Build synonym regex list from profile keywords so e.g. "Neo 4j" in the
        # profile doesn't let "Neo4j" get flagged as a gap.
        prof_all_regex = []
        for kw in prof_unique_list + prof_general_list:
            pat = ResumeMatcher.build_keyword_pattern(kw) if 'ResumeMatcher' in dir() else None
            if pat:
                prof_all_regex.append(re.compile(pat, re.IGNORECASE))

        def _is_in_candidate(kw):
            if kw.lower() in candidate_all:
                return True
            for pat in cand_regex_list:
                if pat.search(kw):
                    return True
            # Also check profile synonyms
            for pat in prof_all_regex:
                if pat.search(kw):
                    return True
            return False

        gaps = {"unique": [], "general": []}

        for key, original_case in jd_unique.items():
            if not _is_in_candidate(key):
                gaps["unique"].append(original_case)

        for key, original_case in jd_general.items():
            if not _is_in_candidate(key):
                gaps["general"].append(original_case)

        all_missing = gaps["unique"] + gaps["general"]
        total_jd_skills = len(jd_unique) + len(jd_general)
        missing_skills = len(all_missing)
        matched_skills = max(0, total_jd_skills - missing_skills)
        ats_score = round((matched_skills / max(total_jd_skills, 1)) * 100, 1)

        return {
            "unique": gaps["unique"],
            "general": gaps["general"],
            "all_missing": all_missing,
            "total_jd_skills": total_jd_skills,
            "matched_skills": matched_skills,
            "ats_score": ats_score
        }
