"""
Dice Auto Apply Bot - Resume Matching Engine
============================================

This module contains the `ResumeMatcher`, which evaluates a job description 
against multiple candidate resumes and ranks them mathematically. 

Key Algorithms & Features:
--------------------------
1. TF-IDF Inspired Keyword Scoring:
   - Evaluates Term Frequency (TF) using logarithmic scaling: `math.log2(1 + count)`.
   - Distinguishes between "Unique/Priority" keywords (3.0x multiplier) and 
     "General" keywords (1.0x multiplier), mitigating keyword stuffing.
   - Robust NLP regex building enables tolerance for plurals, and safely jumps 
     HTML newlines/spaces.

2. Job Title Affinity Score (Jaccard + Subset Overlap):
   - Compares the `Job Title` against the `Resume Profile Name` by tokenizing 
     and stripping generic stop words (e.g., 'senior', 'lead', 'the').
   - Handles role aliasing/stemming (e.g., 'developer' -> 'engineer', 'dev' -> 'engineer').
   - Calculates overlapping terms via mathematical Jaccard logic and Subset percentages
     to handle cases where the Job Title is very long.

3. Name-Boost Tiebreaker System:
   - EXACT: If Jaccard overlap >= 0.55, the profile gets a massive boost (9999.0 points),
     guaranteeing it wins over general keyword matching.
   - HIGH: Tiebreaker bonus up to 80% of median keyword score.
   - LOW: Tiebreaker bonus up to 20% of median keyword score.
   - OFF: Pure mathematical keyword frequencies.

4. Advanced Vector RAG Integrations:
   - Semantic Matching (via PyTorch/SentenceTransformers) adds up to a 30% conceptual bonus.
   - A Learning Engine checks for previously applied and accepted job descriptions.
"""
import re
import math


class ResumeMatcher:
    # Valid boost mode strings
    BOOST_MODES = ("exact", "high", "low", "off")

    def __init__(self, profiles, semantic_matcher=None, learning_engine=None):
        """
        profiles: list of dictionaries configuring the user's resumes
        semantic_matcher: (optional) SemanticResumeMatcher instance
        learning_engine: (optional) LearningEngine instance
        """
        self.profiles = profiles
        self.semantic_matcher = semantic_matcher
        self.learning_engine = learning_engine

    @staticmethod
    def build_keyword_pattern(kw):
        """
        Builds a robust NLP regex pattern for a given keyword.
        - Escapes special characters
        - Converts spaces to \\s+ to cleanly jump HTML newlines and extra spaces
        - Adds an optional 's?' for grammatical plural tolerance if it terminates in an alphabetic character
        """
        kw_clean = str(kw).strip().lower()
        if not kw_clean:
            return None

        escaped = re.escape(kw_clean)

        # Python 3.3+ re.escape escapes spaces as '\ '. Replace both literal and escaped spaces with \s+
        escaped = escaped.replace(r'\ ', r'\s+').replace(' ', r'\s+')

        # Intelligent pluralization tolerance without mutating non-alphabetic skills (like C++)
        if kw_clean[-1].isalpha() and not kw_clean.endswith('s'):
            escaped += r's?'

        return r'(?<![a-z0-9])' + escaped + r'(?![a-z0-9])'

    @staticmethod
    def _name_affinity_score(profile_name: str, job_title: str) -> float:
        """
        Computes a 0.0-1.0 affinity score. Improved to handle role variants 
        (Stemming) and subset matching (e.g. 'Azure Data Engineer' matches 
        'Senior Principal Azure Data Engineering Lead').
        """
        def tokenize(s):
            # Comprehensive role-related stopwords to ignore for name matching
            stop = {
                'a', 'an', 'the', 'and', 'or', 'of', 'in', 'for', 'to', 'with', 
                'sr', 'jr', 'senior', 'junior', 'lead', 'leader', 'principal', 
                'staff', 'contract', 'contractor', 'remote', 'hybrid', 'onsite',
                'expert', 'specialist', 'professional', 'associate', 'hiring',
                'global', 'international', 'location', 'preferred', 'part', 'time', 'full'
            }
            # Preserving symbols like +, #, . (for C++, C#, .NET)
            raw_tokens = re.split(r'[^a-z0-9\+\#\.]+', s.lower())
            
            # Simple stemming/aliasing for common roles
            variants = {
                'engineering': 'engineer',
                'developer':   'engineer',
                'dev':         'engineer',
                'analytics':   'analyst',
                'architecture': 'architect',
                'ml':           'ai',
                'aiml':         'ai',
                'scientific':   'scientist'
            }
            
            tokens = set()
            for t in raw_tokens:
                # Strip leading/trailing punctuation except specific markers if they are alone
                t = t.strip('.') 
                if t and t not in stop:
                    # Apply variants (e.g. engineering -> engineer)
                    tokens.add(variants.get(t, t))
            return tokens - {''}

        name_tokens  = tokenize(profile_name)
        title_tokens = tokenize(job_title)

        if not name_tokens or not title_tokens:
            return 0.0

        intersection = name_tokens & title_tokens
        union        = name_tokens | title_tokens
        
        # Jaccard Score (Mathematical overlap percentage)
        jaccard = len(intersection) / (len(union) or 1)
        
        # Subset Score (Percentage of the profile's meaningful words found in title)
        # Allows matching when your profile name is a subset of a long job title.
        subset  = len(intersection) / len(name_tokens)
        
        # REFINEMENT: If the profile name is only 1 token (e.g. "Engineer"), 
        # a subset match of 1.0 is too common. We'll average Jaccard and Subset 
        # to ensure the job title specificity is taken into account.
        if len(name_tokens) <= 1:
            return (jaccard + subset) / 2
        
        return max(jaccard, subset)

    def score_profiles(self, text, job_title: str = "", name_boost_mode: str = "off"):
        """
        Takes raw job description text and returns ranked profiles.
        Uses TF weighted scoring with logarithmic scaling to prevent keyword stuffing bias.

        name_boost_mode controls how the profile-name affinity feature works:
          "exact"  - If a profile name matches the job title with >= 0.60 Jaccard
                     affinity it is returned as the automatic winner, skipping all
                     other candidates.  Best for very specific role names.
          "high"   - A strong tiebreaker bonus (up to 80% of median keyword score).
                     The name-matched profile will win unless another profile
                     scored dramatically better on keywords.
          "low"    - A gentle nudge bonus (up to 20% of median keyword score).
                     Keyword quality still dominates; name match is a light hint.
          "off"    - Feature disabled entirely; pure keyword scoring.
        
        self.semantic_matcher: (Optional) If provided, adds a semantic similarity boost.
        """
        text = text.lower()

        # 1. Harvest all distinct keywords into a universal set for optimized scanning
        all_kws = set()
        for p in self.profiles:
            uni_kws = p.get('unique_keywords')
            if isinstance(uni_kws, list):
                for k in uni_kws:
                    if str(k).strip():
                        all_kws.add(str(k).strip().lower())

            gen_kws = p.get('keywords')
            if isinstance(gen_kws, list):
                for k in gen_kws:
                    if str(k).strip():
                        all_kws.add(str(k).strip().lower())

        # 2. Count exact Term Frequencies (TF) using intelligent Regex boundaries
        tf_map = {}
        for kw in all_kws:
            pattern = self.build_keyword_pattern(kw)
            if not pattern:
                continue
            matches = list(re.finditer(pattern, text))
            if matches:
                tf_map[kw] = len(matches)

        # 3. Mathematically evaluate each profile
        results = []
        for profile in self.profiles:
            name      = profile.get('name', 'Unknown')
            file_path = profile.get('file_path')

            uni_raw = profile.get('unique_keywords')
            uni_kws = [str(k).strip().lower() for k in uni_raw if str(k).strip()] if isinstance(uni_raw, list) else []

            gen_raw = profile.get('keywords')
            gen_kws = [str(k).strip().lower() for k in gen_raw if str(k).strip()] if isinstance(gen_raw, list) else []

            # Prevent double-dipping: keyword in both lists belongs to Unique only
            uni_set = set(uni_kws)
            gen_kws = [kw for kw in gen_kws if kw not in uni_set]

            used_uni = set(kw for kw in uni_kws if kw in tf_map)
            used_gen = set(kw for kw in gen_kws if kw in tf_map)

            # Algorithmic Weights (TF-IDF style)
            uni_score   = sum(3.0 * math.log2(1 + tf_map[kw]) for kw in used_uni)
            gen_score   = sum(1.0 * math.log2(1 + tf_map[kw]) for kw in used_gen)
            total_score = uni_score + gen_score

            # Check name affinity (Moved early)
            affinity = 0.0
            if job_title:
                affinity = round(self._name_affinity_score(name, job_title), 3)

            # Mode selection
            m_mode = profile.get('boost_mode', name_boost_mode) or name_boost_mode
            m_mode = m_mode.strip().lower()

            # Skip profile ONLY if zero keywords AND it doesn't have a high Name Match in "EXACT" mode
            is_good_name_match = (m_mode == "exact" and affinity >= 0.55)
            if not used_uni and not used_gen and not is_good_name_match:
                continue

            results.append({
                'name':               name,
                'file_path':          file_path,
                'score':              round(total_score, 2),
                'uni_score':          round(uni_score, 2),
                'gen_score':          round(gen_score, 2),
                'matched_uni':        used_uni,
                'matched_gen':        used_gen,
                'name_affinity':      affinity,
                'name_boost':         0.0,
                'semantic_score':     0.0,
                'learning_boost':     0.0,
                'boost_mode':         m_mode,
                'profile_boost_mode': m_mode,
                'id':                 profile.get('id')
            })

        if not results:
            return results

        # ── 4. Name-affinity boost (final processing) ──────────────────────
        if job_title:
            sorted_scores  = sorted(r['score'] for r in results)
            median_score   = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 1.0

            for r in results:
                # Per-profile mode, falling back to the caller's default
                mode = r.get('profile_boost_mode', name_boost_mode) or name_boost_mode
                mode = mode.strip().lower()
                if mode not in self.BOOST_MODES:
                    mode = "high"
                r['boost_mode'] = mode

                if mode == "off" or not job_title:
                    continue

                if mode == "exact":
                    EXACT_THRESHOLD = 0.55
                    if r['name_affinity'] >= EXACT_THRESHOLD:
                        r['name_boost'] = 9999.0
                        r['score']      = round(r['score'] + 9999.0, 2)
                        print(f"  [EXACT MATCH] '{r['name']}' auto-selected "
                              f"(affinity={r['name_affinity']:.2f}) for job: '{job_title}'")
                else:
                    BOOST_CAP = {"high": 0.80, "low": 0.20}
                    cap_pct   = BOOST_CAP.get(mode, 0.40)
                    MAX_BOOST = median_score * cap_pct
                    bonus     = round(r['name_affinity'] * MAX_BOOST, 2)
                    r['name_boost'] = bonus
                    r['score']      = round(r['score'] + bonus, 2)

        # ── 5. Semantic & Learning Feedback (Vector RAG Logic) ────────────────
        # Use simple fallback if AI is still loading or failed
        if self.semantic_matcher and hasattr(self.semantic_matcher, 'model') and self.semantic_matcher.model:
            try:
                sem_results = self.semantic_matcher.score_job(job_title, text)
                sem_map = {r['profile_id']: r['semantic_score'] for r in sem_results}
                
                for r in results:
                    p_id = r.get('id')
                    s_score = sem_map.get(p_id, 0.0)
                    r['semantic_score'] = s_score
                    
                    # 30% of Semantic Score is added to keyword points.
                    s_bonus = round(s_score * 0.3, 2) 
                    r['score'] = round(r['score'] + s_bonus, 2)
            except Exception as e:
                # Silently fail and use keyword-only matching if AI layer errors
                print(f"Warning: Semantic Matching failed, falling back to keywords: {e}")

        if self.learning_engine:
            # Check similarity to past successes for each profile
            for r in results:
                p_id = r.get('id')
                past_jobs = self.learning_engine.get_past_successes(p_id)
                if not past_jobs:
                    continue
                
                # Simplistic learning: for each past success, if current JD is similar, boost.
                # In a more advanced RAG, we'd use vector search here.
                # For now, we'll give a static +5 points if there are ANY past successes, 
                # signaling "Reliable Profile".
                l_bonus = 5.0 
                r['learning_boost'] = l_bonus
                r['score'] = round(r['score'] + l_bonus, 2)

        # Rank by total mathematical score descending (re-sort after boosts)
        results.sort(key=lambda x: x['score'], reverse=True)

        return results
