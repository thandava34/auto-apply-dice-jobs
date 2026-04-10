"""
Semantic Resume Matcher
=======================

This module intercepts raw text inputs and maps them into lower-dimensional dense vectors
(embeddings) using Hugging Face's `sentence-transformers` library and PyTorch. 

By comparing the cosine similarity between the Job Description embedding and a 
Candidate Resume embedding, the engine can conceptually 'understand' when two phrases 
have the same meaning (e.g. "Software Developer" vs. "Code Engineer") even if they 
don't share exact matching keyword strings.
"""

import os
from core.file_utils import extract_text_from_file

class SemanticResumeMatcher:
    """
    Initializes a local NLP model capable of calculating semantic proximity.
    
    Args:
        profiles (list): List of profile dictionaries generated from user configuration.
        model_name (str): The HF model to use. Defaults to `all-MiniLM-L6-v2` because 
                          it's lightweight (~80MB), fast on CPUs, and highly effective for RAG.
    """
    def __init__(self, profiles, model_name='all-MiniLM-L6-v2'):
        self.profiles = profiles
        self.model_name = model_name
        self.model = None
        self.profile_embeddings = {}
        self._initialize_model()
        self._index_profiles()

    def _initialize_model(self):
        """Loads the SentenceTransformer model (CPU by default)."""
        try:
            global torch, np, SentenceTransformer, util
            import torch
            import numpy as np
            from sentence_transformers import SentenceTransformer, util
            
            # We use local folder for caching to avoid re-downloading if possible
            cache_folder = os.path.join(os.path.dirname(__file__), "..", "models")
            if not os.path.exists(cache_folder):
                os.makedirs(cache_folder)
            
            print(f"Loading semantic model: {self.model_name}...")
            self.model = SentenceTransformer(self.model_name, cache_folder=cache_folder)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Error loading semantic model: {e}")

    def _index_profiles(self):
        """Pre-calculates embeddings for all configured resume file contents."""
        if not self.model:
            return

        for p in self.profiles:
            profile_id = p.get('id')
            file_path = p.get('file_path')
            
            if profile_id is None or not file_path or not os.path.exists(file_path):
                continue
                
            print(f"Indexing profile: {p.get('name')} ({file_path})...")
            resume_text = extract_text_from_file(file_path)
            if resume_text.strip():
                # We embed the whole resume. For very long resumes, we might 
                # want to chunk, but for matching, the mean pooling of 
                # all-MiniLM is usually sufficient.
                embedding = self.model.encode(resume_text, convert_to_tensor=True)
                self.profile_embeddings[profile_id] = embedding
            else:
                print(f"Warning: No text extracted from {file_path}")

    def score_job(self, job_title, job_description):
        """
        Scores all indexed profiles against a job.
        returns: list of {profile_id, semantic_score}
        """
        if not self.model or not self.profile_embeddings:
            return []

        # We combine title and description for a holistic semantic "fingerprint"
        job_query = f"Job Title: {job_title}\n\nDescription: {job_description}"
        query_embedding = self.model.encode(job_query, convert_to_tensor=True)

        results = []
        for profile_id, prof_embedding in self.profile_embeddings.items():
            # Cosine similarity (0.0 to 1.0)
            score = util.cos_sim(query_embedding, prof_embedding).item()
            results.append({
                "profile_id": profile_id,
                "semantic_score": round(score * 100, 2)
            })
            
        # Sort by score descending
        results.sort(key=lambda x: x["semantic_score"], reverse=True)
        return results

    def delete_profile(self, profile_id):
        """Removes a profile's embedding from memory."""
        if profile_id in self.profile_embeddings:
            del self.profile_embeddings[profile_id]
            print(f"Removed semantic embedding for profile {profile_id}")

if __name__ == "__main__":
    # Test stub
    pass
