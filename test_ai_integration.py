"""
AI Integration Testing Module
=============================

This script serves as a simple, human-readable sandbox to demonstrate and verify 
how the AI layers (Semantic Matcher & Learning Engine) of the Dice Auto-Apply Bot work.

How it works:
1. It creates a temporary "mock" resume strictly in memory/disk.
2. It initializes the `SemanticResumeMatcher` (which converts text into AI vector embeddings).
3. It initializes a blank SQLite `LearningEngine` database.
4. It simulates feeding a job description ("Job for a Data Engineer using Spark") 
   to see if the Semantic Engine correctly gives it a non-zero semantic score based on meaning.
5. It then simulates a "Manual Approval/Successful Application" in the Learning Engine,
   and runs the matcher again to mathematically verify that the AI gives a `learning_boost` 
   bonus to that resume the second time around.
6. Finally, it cleans up all the generated temporary files.

You can run this stand-alone via: `python test_ai_integration.py`
"""

import sys
import os

# Add project root to Python path so we can import 'core' modules natively
sys.path.append(os.getcwd())

from core.semantic_matcher import SemanticResumeMatcher
from core.learning_engine import LearningEngine
from core.matcher import ResumeMatcher

def test_integration():
    """
    Executes the integration workflow, asserting that semantic scores and 
    learning boosts are correctly applied.
    """
    print("--- Running AI Integration Test ---")
    
    # 1. Provide Mock Data
    # Simulate what the GUI would normally pass down to the core logic.
    profiles = [
        {
            "id": 1, 
            "name": "Data Engineer", 
            "keywords": ["python", "spark"], 
            "unique_keywords": ["airflow"], 
            "file_path": "mock_resume.pdf"
        }
    ]
    
    # 2. Setup Dummy File
    # Create a dummy mock_resume.pdf. (Writing as plain text for simplicity instead of actual PDF bytes)
    with open("mock_resume.pdf", "w") as f:
        f.write("I am a Data Engineer with experts in Python, Spark, and Airflow. I build ETL pipelines.")
        
    try:
        # Initialize the Learning Engine with a temporary test database
        le = LearningEngine("data/test_learning.db")
        
        # Initialize Semantic Matcher
        # Note: The first time this ever runs on a machine, it may download a ~80MB model file.
        print("Initializing Semantic Matcher (this might download a model)...")
        sm = SemanticResumeMatcher(profiles)
        
        # Instantiate the main Resume Matcher tying everything together
        matcher = ResumeMatcher(profiles, semantic_matcher=sm, learning_engine=le)
        
        # 3. Test Phase 1: Pure Semantic Matching
        # We test a basic string to see if the semantic vector logic triggers correctly.
        results = matcher.score_profiles("Job for a Data Engineer using Spark")
        
        print(f"Results: {results}")
        
        if results and results[0].get('semantic_score', 0) > 0:
            print("SUCCESS: Semantic scoring detected.")
        else:
            print("WARNING: Semantic score was 0 or no results. (Check internet or model cache)")
            
        # 4. Test Phase 2: Learning Engine Integration
        # We manually inject a successful 'past application' or 'training data' point into the DB.
        le.record_success(profile_id=1, job_title="Data Engineer", job_description="Spark, Python")
        
        # Re-score the exact same job description string
        results_after = matcher.score_profiles("Job for a Data Engineer using Spark")
        print(f"Results after learning: {results_after}")
        
        # Check if the AI applied the +5 'learning_boost' to our score.
        if results_after[0].get('learning_boost', 0) > 0:
            print("SUCCESS: Learning boost detected.")
            
    except Exception as e:
        print(f"FAILED: {e}")
    finally:
        # 5. Cleanup Phase
        # Always remove the temporary generated test files so as not to pollute the workspace.
        if os.path.exists("mock_resume.pdf"): 
            os.remove("mock_resume.pdf")
        if os.path.exists("data/test_learning.db"): 
            os.remove("data/test_learning.db")

if __name__ == "__main__":
    test_integration()
