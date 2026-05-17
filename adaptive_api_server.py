import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
from datetime import datetime
import hashlib
import os
from pathlib import Path
import logging
import base64
from typing import Dict, List, Any, Optional
import mimetypes
import threading
import pymongo
from pymongo import MongoClient

# --- Optional .env loader (no external dependency) ---
def _load_env_from_dotenv():
    """Load environment variables from a local .env file if present.
    Only sets variables that are not already present in os.environ."""
    try:
        env_path = Path('.env')
        if env_path.exists():
            with env_path.open('r', encoding='utf-8') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            try:
                logger.info("Loaded environment variables from .env")
            except Exception:
                # logger may not be configured yet; ignore
                pass
    except Exception as e:
        try:
            logger.warning(f"Failed to load .env: {e}")
        except Exception:
            pass

def _apply_fix_to_question_in_place(question: Dict, fixed: Dict) -> None:
    """Mutate a question dict in-place with a sanitized fix object."""
    question['text'] = (
        (fixed.get('added_context') + ' ') if fixed.get('added_context') else ''
    ) + fixed.get('text', question.get('text', ''))
    question['options'] = fixed['options']
    question['answer'] = fixed['answer']

def _prewarm_sanitizer_all_questions() -> Dict[str, int]:
    """Disabled - question fixing functionality removed.
    Returns empty stats dict."""
    return {'total': 0, 'fixed': 0, 'skipped': 0}

def _rule_based_fix_question(question: Dict) -> Optional[Dict]:
    # Ratio + sum: e.g., boys:girls = a:b, boys+girls=N, find boys and girls
    import re as _re2
    m_ratio_sum = _re2.search(r"boys\s*[:=]\s*girls\s*[=:]?\s*(\d+)\s*[:/]\s*(\d+)[^\d]+boys\s*\+\s*girls\s*=\s*(\d+)", low)
    if m_ratio_sum:
        a = int(m_ratio_sum.group(1))
        b = int(m_ratio_sum.group(2))
        total = int(m_ratio_sum.group(3))
        s = a + b
        if total % s == 0:
            k = total // s
            boys = a * k
            girls = b * k
            correct_pair = f"Boys = {boys}, Girls = {girls}"
            # Generate plausible distractors
            distractors = []
            for delta in [-20, -10, 10, 20, -5, 5]:
                b2 = boys + delta
                g2 = girls - delta
                if b2 > 0 and g2 > 0 and (b2 != boys or g2 != girls):
                    distractors.append(f"Boys = {b2}, Girls = {g2}")
                if len(distractors) >= 3:
                    break
            values = [correct_pair] + distractors[:3]
            # Shuffle deterministically
            import random as _rnd2
            _rnd2.seed(str(question.get('id')))
            _rnd2.shuffle(values)
            opts = {lab: values[i] for i, lab in enumerate(['A','B','C','D'])}
            answer = [lab for lab, val in opts.items() if val == correct_pair][0]
            return {
                'text': text,
                'added_context': '',
                'options': opts,
                'answer': answer,
                'notes': 'rule-based ratio+sum pair fix applied'
            }
        else:
            # Not divisible, so not possible
            opts = {'A': 'Not possible with given data', 'B': 'Cannot be determined', 'C': 'Insufficient information', 'D': 'None of these'}
            return {
                'text': text,
                'added_context': '',
                'options': opts,
                'answer': 'A',
                'notes': 'rule-based ratio+sum not possible'
            }
    # General context enrichment by topic
    topic = (question.get('topic') or '').strip().lower()
    text = (question.get('text') or question.get('question_text') or '').strip()
    low = text.lower()
    context_map = {
        'probability': "Suppose two people, A and B, are participating in a race.",
        'varc': "Read the following passage and answer the question:",
        'verbal': "Read the following passage and answer the question:",
        'logic': "Consider the following logical scenario:",
        'reasoning': "Consider the following logical scenario:",
        'geometry': "Refer to the following geometric figure or description:",
        'algebra': "Solve the following algebraic problem:",
        'arithmetic': "Solve the following arithmetic problem:",
        'modern math': "Solve the following modern math problem:",
        'number system': "Solve the following number system problem:",
        'mensuration': "Refer to the following mensuration scenario:",
        'data interpretation': "Interpret the following data and answer the question:",
        'statistics': "Analyze the following statistical data:",
        'trigonometry': "Solve the following trigonometry problem:",
        'coordinate geometry': "Refer to the following coordinate geometry scenario:",
        'sets': "Consider the following set theory scenario:",
        'functions': "Analyze the following function:",
        'series': "Analyze the following series:",
        'permutation': "Consider the following permutation and combination scenario:",
        'combination': "Consider the following permutation and combination scenario:",
        'time and work': "Solve the following time and work problem:",
        'time and distance': "Solve the following time and distance problem:",
        'simple interest': "Solve the following simple interest problem:",
        'compound interest': "Solve the following compound interest problem:",
        'profit and loss': "Solve the following profit and loss problem:",
        'ratio': "Solve the following ratio and proportion problem:",
        'proportion': "Solve the following ratio and proportion problem:",
        'mixtures': "Solve the following mixtures and alligation problem:",
        'alligation': "Solve the following mixtures and alligation problem:",
        'partnership': "Solve the following partnership problem:",
        'average': "Solve the following average problem:",
        'age': "Solve the following age problem:",
        'calendar': "Solve the following calendar problem:",
        'clock': "Solve the following clock problem:",
        'direction': "Refer to the following direction scenario:",
        'blood relation': "Consider the following family tree or relationship:",
        'coding': "Decode the following code or pattern:",
        'decoding': "Decode the following code or pattern:",
        'puzzle': "Solve the following logical puzzle:",
        'sitting arrangement': "Consider the following seating arrangement:",
        'input output': "Analyze the following input-output pattern:",
        'syllogism': "Analyze the following syllogism:",
        'statement conclusion': "Analyze the following statement and conclusion:",
        'statement assumption': "Analyze the following statement and assumption:",
        'statement argument': "Analyze the following statement and argument:",
        'statement course of action': "Analyze the following statement and course of action:",
        'direction sense': "Refer to the following direction sense scenario:",
        'seating arrangement': "Consider the following seating arrangement:",
        'logical reasoning': "Consider the following logical reasoning scenario:",
    }
    # Only add context if not already present and not already handled above
    # Special handling for VARC/verbal: if prompt says 'Read the following passage' but no passage is present, inject a generic sample passage
    if topic in ['varc', 'verbal', 'reading'] and 'read the following passage' in low:
        # Heuristic: if text does not contain a quoted or multi-line passage, add a generic one
        if len(text.splitlines()) < 2 and 'passage:' not in low:
            sample_passage = (
                "Passage: Mobile phones have become an essential part of modern life. "
                "Many social media influencers prefer phones with high storage capacity to store photos and videos. "
                "Some brands are more popular among influencers due to their advanced features."
            )
            return {
                'text': text,
                'added_context': sample_passage,
                'options': question.get('options', {'A':'','B':'','C':'','D':''}),
                'answer': question.get('answer','A'),
                'notes': 'rule-based sample passage injected for VARC'
            }
    if topic in context_map and not any(context_map[topic].lower() in low for _ in [0]):
        return {
            'text': text,
            'added_context': context_map[topic],
            'options': question.get('options', {'A':'','B':'','C':'','D':''}),
            'answer': question.get('answer','A'),
            'notes': f'rule-based context added for topic: {topic}'
        }
    """Deterministic fixes for common math patterns when Gemini is unavailable.
    Returns a dict similar to _gemini_fix_question or None if no rule applies."""
    import re as _re
    text = (question.get('text') or question.get('question_text') or '').strip()
    low = text.lower()

    # Pattern: ratio of boys to girls is a:b. If boys is N, what is girls? (or vice versa)
    m_ratio = _re.search(r"ratio\s+of\s+boys\s*to\s*girls\s*is\s*(\d+)\s*[:/]\s*(\d+)", low)
    if m_ratio:
        a = int(m_ratio.group(1))
        b = int(m_ratio.group(2))
        m_boys = _re.search(r"if\s+boys\s+(?:is|are)\s*(\d+)", low)
        m_girls = _re.search(r"if\s+girls\s+(?:is|are)\s*(\d+)", low)
        if m_boys or m_girls:
            if m_boys:
                n = int(m_boys.group(1))
                # boys : girls = a : b => girls = n * b / a
                if a != 0 and (n * b) % a == 0:
                    girls = (n * b) // a
                    correct = girls
                else:
                    # Inconsistent data, include Not possible option
                    correct = None
            else:
                n = int(m_girls.group(1))
                # boys : girls = a : b => boys = n * a / b
                if b != 0 and (n * a) % b == 0:
                    boys = (n * a) // b
                    correct = boys
                else:
                    correct = None

            # Build options
            opts = {}
            labels = ['A','B','C','D']
            if correct is not None:
                # plausible distractors near the correct value
                distractors = []
                for delta in (-50, -25, 25, 50, -10, 10, -5, 5):
                    cand = correct + delta
                    if cand > 0 and cand != correct:
                        distractors.append(cand)
                    if len(distractors) >= 3:
                        break
                values = [correct] + distractors[:3]
                # Shuffle deterministically based on id for consistency
                import random as _rnd
                _rnd.seed(str(question.get('id')))
                _rnd.shuffle(values)
                for i, lab in enumerate(labels):
                    opts[lab] = str(values[i])
                answer = labels[values.index(correct)]
            else:
                # Not solvable cleanly
                opts = {'A': 'Not possible with given data', 'B': 'Cannot be determined', 'C': 'Insufficient information', 'D': 'None of these'}
                answer = 'A'

            return {
                'text': text,
                'added_context': '',
                'options': opts,
                'answer': answer,
                'notes': 'rule-based ratio fix applied'
            }

        return None
    # Probability context enrichment
    text = (question.get('text') or question.get('question_text') or '').strip()
    low = text.lower()
    # If the question is about probability and lacks a scenario, add a generic context
    if 'probability' in low and ('neither' in low or 'both' in low or 'at least' in low or 'at most' in low or 'only one' in low):
        # Only add context if not already present
        if not any(word in low for word in ['bag', 'dice', 'coin', 'deck', 'cards', 'urn', 'marbles', 'balls', 'students', 'people', 'race', 'event', 'experiment']):
            added_context = "Suppose two people, A and B, are participating in a race. "
            return {
                'text': text,
                'added_context': added_context,
                'options': question.get('options', {'A':'','B':'','C':'','D':''}),
                'answer': question.get('answer','A'),
                'notes': 'rule-based probability context added'
            }

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Load environment variables
_load_env_from_dotenv()

# MongoDB setup
try:
    MONGODB_URI = os.environ.get('MONGODB_URI')
    if not MONGODB_URI:
        raise Exception("MONGODB_URI not found in environment variables")
    
    client = MongoClient(MONGODB_URI)
    db = client.adaptiq_db
    students_collection = db.students
    
    # Test the connection
    client.admin.command('ping')
    print("✅ MongoDB connection successful!")
    
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    # Fallback to file-based storage
    client = None
    db = None
    students_collection = None

# Global variables
trained_model = None
student_sessions = {}
image_cache = {}

# Global question usage tracking to prevent duplicates across all assessments
question_usage_log = {}  # question_id -> {count, last_used, profiles}

# Cross-student uniqueness tracking
global_question_allocations = {
    'in_use': set(),                    # Questions currently assigned to active sessions
    'permanently_used': set(),          # Questions used in completed assessments
    'reserved_by_session': {},          # session_id -> set of question_ids
    'reserved_by_profile': {},          # profile_id -> set of question_ids
    'difficulty_pools': {               # Track remaining questions by difficulty
        'Very Easy': set(),
        'Easy': set(), 
        'Moderate': set(),
        'Difficult': set()
    },
    'topic_pools': {}                   # Track remaining questions by topic
}

def load_question_usage_from_history():
    """Load question usage statistics from persistent history across all profiles"""
    global question_usage_log, global_question_allocations
    question_usage_log = {}
    
    # Initialize difficulty and topic pools
    if trained_model and hasattr(trained_model, 'questions'):
        for question in trained_model.questions.values():
            qid = str(question['id'])
            difficulty = question.get('difficulty', 'Moderate')
            topic = question.get('topic', 'Unknown')
            
            global_question_allocations['difficulty_pools'].setdefault(difficulty, set()).add(qid)
            global_question_allocations['topic_pools'].setdefault(topic, set()).add(qid)
    
    if students_collection is not None:
        try:
            # Load from MongoDB
            all_profiles = students_collection.find({}, {"profile_id": 1, "responses": 1})
            for profile_doc in all_profiles:
                profile_id = profile_doc.get('profile_id')
                responses = profile_doc.get('responses', [])
                
                for response in responses:
                    question_id = response.get('question_id')
                    if question_id:
                        if question_id not in question_usage_log:
                            question_usage_log[question_id] = {
                                'count': 0,
                                'last_used': None,
                                'profiles': set()
                            }
                        question_usage_log[question_id]['count'] += 1
                        question_usage_log[question_id]['profiles'].add(profile_id)
                        
                        # Track latest usage time
                        timestamp = response.get('timestamp')
                        if timestamp and (not question_usage_log[question_id]['last_used'] or 
                                        timestamp > question_usage_log[question_id]['last_used']):
                            question_usage_log[question_id]['last_used'] = timestamp
            
            logger.info(f"📊 Loaded question usage for {len(question_usage_log)} questions from MongoDB")
        except Exception as e:
            logger.error(f"Failed to load question usage from MongoDB: {e}")
    
    # Fallback: load from file-based history
    if not question_usage_log and HISTORY_DIR.exists():
        try:
            for history_file in HISTORY_DIR.glob("*.json"):
                profile_id = history_file.stem
                with history_file.open('r', encoding='utf-8') as f:
                    hist = json.load(f)
                    responses = hist.get('responses', [])
                    
                    for response in responses:
                        question_id = response.get('question_id')
                        if question_id:
                            if question_id not in question_usage_log:
                                question_usage_log[question_id] = {
                                    'count': 0,
                                    'last_used': None,
                                    'profiles': set()
                                }
                            question_usage_log[question_id]['count'] += 1
                            question_usage_log[question_id]['profiles'].add(profile_id)
                            
                            timestamp = response.get('timestamp')
                            if timestamp and (not question_usage_log[question_id]['last_used'] or 
                                            timestamp > question_usage_log[question_id]['last_used']):
                                question_usage_log[question_id]['last_used'] = timestamp
            
            logger.info(f"📊 Loaded question usage for {len(question_usage_log)} questions from file history")
        except Exception as e:
            logger.error(f"Failed to load question usage from files: {e}")

def track_question_usage(question_id: str, profile_id: str):
    """Track when a question is answered by a specific profile (called during answer submission)"""
    if question_id not in question_usage_log:
        question_usage_log[question_id] = {
            'count': 0,
            'last_used': None,
            'profiles': set()
        }
    
    # Only increment if this profile hasn't answered this question before
    if profile_id not in question_usage_log[question_id]['profiles']:
        question_usage_log[question_id]['count'] += 1
        question_usage_log[question_id]['profiles'].add(profile_id)
        question_usage_log[question_id]['last_used'] = datetime.now().isoformat()
        
        # Mark question as permanently used in global allocations
        global_question_allocations['permanently_used'].add(question_id)
        
        # Remove from all pools
        for difficulty_pool in global_question_allocations['difficulty_pools'].values():
            difficulty_pool.discard(question_id)
        for topic_pool in global_question_allocations['topic_pools'].values():
            topic_pool.discard(question_id)
        
        # Log usage statistics
        usage = question_usage_log[question_id]
        logger.info(f"📊 Question {question_id} answered by profile {profile_id} - Total usage: {usage['count']} times by {len(usage['profiles'])} profiles")

def get_question_usage_stats():
    """Get comprehensive question usage statistics"""
    total_questions = len(question_usage_log)
    total_usage = sum(q['count'] for q in question_usage_log.values())
    
    if total_questions == 0:
        return {
            'total_questions_used': 0,
            'total_usage_count': 0,
            'average_usage_per_question': 0,
            'most_used_questions': [],
            'least_used_questions': []
        }
    
    # Find most and least used questions
    sorted_by_usage = sorted(
        question_usage_log.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )
    
    return {
        'total_questions_used': total_questions,
        'total_usage_count': total_usage,
        'average_usage_per_question': total_usage / total_questions,
        'most_used_questions': sorted_by_usage[:5],
        'least_used_questions': sorted_by_usage[-5:] if len(sorted_by_usage) > 5 else []
    }

def reserve_questions_for_session(session_id: str, profile_id: str, question_ids: List[str]) -> bool:
    """Reserve questions for a specific session to ensure cross-student uniqueness"""
    try:
        # Check if any questions are already in use
        conflicts = []
        for qid in question_ids:
            if qid in global_question_allocations['in_use']:
                conflicts.append(qid)
        
        if conflicts:
            logger.warning(f"Cannot reserve questions {conflicts} - already in use")
            return False
        
        # Reserve all questions
        for qid in question_ids:
            global_question_allocations['in_use'].add(qid)
        
        # Track reservation by session and profile
        global_question_allocations['reserved_by_session'][session_id] = set(question_ids)
        global_question_allocations['reserved_by_profile'][profile_id] = set(question_ids)
        
        logger.info(f"🔒 Reserved {len(question_ids)} questions for session {session_id} (profile {profile_id})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reserve questions: {e}")
        return False

def release_session_questions(session_id: str, profile_id: str):
    """Release questions when session ends (move to permanently used)"""
    if session_id in global_question_allocations['reserved_by_session']:
        used_questions = global_question_allocations['reserved_by_session'][session_id]
        
        # Move from 'in_use' to 'permanently_used'
        global_question_allocations['permanently_used'].update(used_questions)
        global_question_allocations['in_use'] -= used_questions
        
        # Clean up reservations
        del global_question_allocations['reserved_by_session'][session_id]
        if profile_id in global_question_allocations['reserved_by_profile']:
            del global_question_allocations['reserved_by_profile'][profile_id]
        
        logger.info(f"✅ Released {len(used_questions)} questions from session {session_id}")

def get_available_questions_for_cross_student_uniqueness(exclude_profile_history: set = None) -> Dict[str, List]:
    """Get questions that haven't been used by ANY student yet"""
    if exclude_profile_history is None:
        exclude_profile_history = set()
    
    # Questions that are globally unavailable
    globally_unavailable = (global_question_allocations['in_use'] | 
                          global_question_allocations['permanently_used'] |
                          exclude_profile_history)
    
    available_by_difficulty = {}
    available_by_topic = {}
    
    if trained_model and hasattr(trained_model, 'questions'):
        for question in trained_model.questions.values():
            qid = str(question['id'])
            
            if qid not in globally_unavailable and trained_model.is_question_complete(question):
                difficulty = question.get('difficulty', 'Moderate')
                topic = question.get('topic', 'Unknown')
                
                available_by_difficulty.setdefault(difficulty, []).append(question)
                available_by_topic.setdefault(topic, []).append(question)
    
    return {
        'by_difficulty': available_by_difficulty,
        'by_topic': available_by_topic,
        'total_available': sum(len(questions) for questions in available_by_difficulty.values())
    }

def smart_question_allocation_for_cross_student_uniqueness(num_students: int, questions_per_student: int) -> Dict:
    """Intelligently allocate questions to ensure fairness across students"""
    available = get_available_questions_for_cross_student_uniqueness()
    total_needed = num_students * questions_per_student
    total_available = available['total_available']
    
    if total_available < total_needed:
        logger.error(f"❌ Insufficient questions: need {total_needed}, have {total_available}")
        return {'success': False, 'error': 'Insufficient questions'}
    
    # Calculate fair distribution across difficulties
    by_difficulty = available['by_difficulty']
    allocation_plan = {}
    
    for difficulty, questions in by_difficulty.items():
        available_count = len(questions)
        per_student = available_count // num_students
        allocation_plan[difficulty] = {
            'available': available_count,
            'per_student': per_student,
            'total_allocated': per_student * num_students,
            'remaining': available_count - (per_student * num_students)
        }
    
    return {
        'success': True,
        'allocation_plan': allocation_plan,
        'total_available': total_available,
        'total_needed': total_needed,
        'feasible': total_available >= total_needed
    }

def validate_no_duplicate_questions(student_id: str, selected_question_ids: List[str]) -> bool:
    """Validate that no questions are duplicated in current assessment"""
    profile_id = student_sessions.get(student_id, {}).get('profile_id')
    if not profile_id:
        return True
    
    # Check against all previously answered questions
    hist = _load_history(profile_id)
    prev_answered = set(r['question_id'] for r in hist.get('responses', []) if r.get('question_id'))
    
    # Check for duplicates
    duplicates = set(selected_question_ids) & prev_answered
    if duplicates:
        logger.error(f"🚨 DUPLICATE QUESTIONS DETECTED for profile {profile_id}: {duplicates}")
        return False
    
    logger.info(f"✅ No duplicate questions detected for profile {profile_id}")
    return True

# --- Student history persistence helpers ---
HISTORY_DIR = Path('data') / 'student_history'
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def _compute_profile_id(name: str, grade: str) -> str:
    base = f"{(name or '').strip().lower()}|{(grade or '').strip().lower()}"
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]

def _load_history(profile_id: str) -> dict:
    """Load student history from MongoDB or fallback to file storage"""
    if students_collection is not None:
        try:
            # Try to load from MongoDB
            doc = students_collection.find_one({"profile_id": profile_id})
            if doc:
                # Remove MongoDB's _id field and return the data
                doc.pop('_id', None)
                return doc
            else:
                # Return default structure if no document found
                return {"profile": {}, "sessions": {}, "responses": []}
        except Exception as e:
            print(f"MongoDB load error: {e}, falling back to file storage")
    
    # Fallback to file-based storage
    fp = HISTORY_DIR / f"{profile_id}.json"
    if not fp.exists():
        return {"profile": {}, "sessions": {}, "responses": []}
    try:
        with fp.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"profile": {}, "sessions": {}, "responses": []}

def _save_history(profile_id: str, data: dict):
    """Save student history to MongoDB and optionally keep file backup"""
    if students_collection is not None:
        try:
            # Ensure profile_id is in the data
            data['profile_id'] = profile_id
            data['last_updated'] = datetime.now()
            
            # Use upsert to update or insert the document
            students_collection.replace_one(
                {"profile_id": profile_id}, 
                data, 
                upsert=True
            )
            print(f"✅ Student data saved to MongoDB for profile: {profile_id}")
            return
        except Exception as e:
            print(f"MongoDB save error: {e}, falling back to file storage")
    
    # Fallback to file-based storage
    fp = HISTORY_DIR / f"{profile_id}.json"
    try:
        with fp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"File save error: {e}")

def get_all_students():
    """Get all students from MongoDB"""
    if students_collection is not None:
        try:
            students = list(students_collection.find({}, {"_id": 0}))
            return students
        except Exception as e:
            print(f"Error fetching all students: {e}")
    return []

def get_student_stats():
    """Get overall student statistics"""
    if students_collection is not None:
        try:
            total_students = students_collection.count_documents({})
            active_students = students_collection.count_documents({
                "last_updated": {"$gte": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}
            })
            
            # Aggregate response statistics
            pipeline = [
                {"$unwind": "$responses"},
                {"$group": {
                    "_id": None,
                    "total_responses": {"$sum": 1},
                    "correct_responses": {"$sum": {"$cond": ["$responses.is_correct", 1, 0]}}
                }}
            ]
            
            result = list(students_collection.aggregate(pipeline))
            total_responses = result[0]["total_responses"] if result else 0
            correct_responses = result[0]["correct_responses"] if result else 0
            overall_accuracy = (correct_responses / total_responses * 100) if total_responses > 0 else 0
            
            return {
                "total_students": total_students,
                "active_students_today": active_students,
                "total_responses": total_responses,
                "overall_accuracy": round(overall_accuracy, 2)
            }
        except Exception as e:
            print(f"Error getting student stats: {e}")
    
    return {
        "total_students": 0,
        "active_students_today": 0,
        "total_responses": 0,
        "overall_accuracy": 0
    }

def delete_student_data(profile_id: str):
    """Delete a student's data from MongoDB"""
    if students_collection is not None:
        try:
            result = students_collection.delete_one({"profile_id": profile_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting student data: {e}")
    return False

class AdaptiveAssessmentEngine:
    """
    Enhanced adaptive assessment engine with image support
    """
    
    def __init__(self, model_data: Dict):
        self.model_data = model_data
        self.questions = {q['id']: q for q in model_data['questions']}
        self.item_parameters = model_data['question_parameters']
        self.topics = model_data['topics']
        self.image_mappings = model_data.get('image_mappings', {})
        
        # IRT Model parameters - Start with Very Easy questions
        self.default_ability = -1.5  # Starting ability level (ensures Very Easy start)
        self.ability_range = (-3.0, 3.0)  # Ability range
        
        logger.info(f"Initialized adaptive engine with {len(self.questions)} questions")
        logger.info(f"Questions with images: {sum(1 for q in self.questions.values() if q.get('has_image'))}")
    
    def calculate_probability(self, ability: float, item_id: str) -> float:
        """Calculate probability of correct response using 2PL IRT model"""
        if item_id not in self.item_parameters:
            return 0.5  # Default probability
        
        params = self.item_parameters[item_id]
        a = params['discrimination']  # Discrimination parameter
        b = params['difficulty']      # Difficulty parameter
        c = params.get('guessing', 0.25)  # Guessing parameter (default 25% for 4-option MCQ)
        
        try:
            # 3PL model: P(correct) = c + (1-c) * (1 / (1 + exp(-a(θ-b))))
            prob = c + (1 - c) * (1 / (1 + np.exp(-a * (ability - b))))
            return max(0.01, min(0.99, prob))  # Clamp probability
        except (OverflowError, ZeroDivisionError):
            return 0.5
    
    def select_next_question(self, student_id: str, answered_questions: List[str] = None, 
                           target_topic: str = None, target_difficulty: str = None,
                           cross_student_unique: bool = False) -> Optional[Dict]:
        """Select the next most informative question for the student using advanced adaptive algorithm"""
        
        if answered_questions is None:
            answered_questions = []

        # Get student's current ability estimate and performance history
        ability = self.get_student_ability(student_id)
        session = student_sessions.get(student_id, {})
        responses = session.get('responses', [])

        # Exclude all previously answered questions for this profile (across all sessions)
        profile_id = session.get('profile_id')
        prev_answered = set()
        if profile_id:
            hist = _load_history(profile_id)
            prev_answered = set(r['question_id'] for r in hist.get('responses', []) if r.get('question_id'))
            logger.info(f"Profile {profile_id} has {len(prev_answered)} previously answered questions across all sessions")

        logger.info(f"Selecting question for student {student_id} with ability {ability:.3f}")
        logger.info(f"Current session answered {len(answered_questions)} questions: {answered_questions}")

        # Get available questions (ensure we exclude all previously answered questions)
        all_answered = set(answered_questions) | prev_answered
        
        # For cross-student uniqueness, also exclude globally used questions
        if cross_student_unique:
            globally_used = (global_question_allocations['in_use'] | 
                           global_question_allocations['permanently_used'])
            all_answered = all_answered | globally_used
            logger.info(f"Cross-student mode: excluding {len(globally_used)} globally used questions")
        
        # Convert all IDs to strings for consistent comparison and prevent duplicates
        all_answered_str = set(str(qid) for qid in all_answered)
        
        # Filter questions more robustly
        available_questions = []
        for q in self.questions.values():
            q_id_str = str(q['id'])
            if (q_id_str not in all_answered_str and 
                self.is_question_complete(q)):
                available_questions.append(q)
        
        logger.info(f"Question filtering: {len(all_answered)} total answered, {len(available_questions)} available out of {len(self.questions)} total questions")
        
        # Additional safety check: if we're running out of questions, warn the user
        if len(available_questions) < 10:
            logger.warning(f"⚠️  Only {len(available_questions)} questions remaining for profile {profile_id}! Consider expanding question pool.")
            
        # If no questions available for cross-student uniqueness, try fallback strategies
        if len(available_questions) == 0 and cross_student_unique:
            logger.error(f"❌ No available questions for cross-student unique mode for profile {profile_id}!")
            
            # Fallback 1: Try with topic-based allocation
            if target_topic:
                available = get_available_questions_for_cross_student_uniqueness(prev_answered)
                topic_questions = available['by_topic'].get(target_topic, [])
                if topic_questions:
                    available_questions = topic_questions
                    logger.info(f"🔄 Fallback: Found {len(available_questions)} questions in topic {target_topic}")
            
            # Fallback 2: Use questions with minimal cross-student overlap
            if not available_questions:
                logger.warning("🔄 Final fallback: allowing minimal cross-student overlap")
                cross_student_unique = False  # Disable strict uniqueness
                available_questions = [
                    q for q in self.questions.values()
                    if str(q['id']) not in set(str(qid) for qid in prev_answered) and
                    self.is_question_complete(q)
                ]
        
        # Regular fallback for exhausted individual questions
        elif len(available_questions) == 0:
            logger.error(f"❌ No available questions for profile {profile_id}! All {len(self.questions)} questions have been answered.")
            # Option 1: Allow re-answering questions from old sessions (older than 30 days)
            if profile_id:
                hist = _load_history(profile_id)
                old_responses = []
                recent_cutoff = (datetime.now() - pd.Timedelta(days=30)).isoformat()
                
                for r in hist.get('responses', []):
                    if r.get('timestamp', '') < recent_cutoff:
                        old_responses.append(r['question_id'])
                
                if old_responses:
                    logger.info(f"🔄 Allowing re-answering of {len(old_responses)} questions older than 30 days")
                    # Remove old questions from exclusion list
                    filtered_answered = all_answered - set(old_responses)
                    available_questions = [
                        q for q in self.questions.values()
                        if str(q['id']) not in set(str(qid) for qid in filtered_answered) and
                        self.is_question_complete(q)
                    ]
        
        logger.info(f"Final available questions: {len(available_questions)} questions ready for selection")
        
        # Filter by topic if specified
        if target_topic:
            available_questions = [
                q for q in available_questions 
                if q['topic'].lower() == target_topic.lower()
            ]
        
        # Enhanced adaptive difficulty targeting based on student ability and struggle patterns
        if not target_difficulty:
            # For first question, always start with Very Easy
            if len(responses) == 0:
                target_difficulty = "Very Easy"
                logger.info(f"First question - starting with Very Easy for new student {student_id}")
            else:
                target_difficulty = self.get_adaptive_optimal_difficulty(student_id, ability)
                logger.info(f"Auto-selected difficulty: {target_difficulty} for ability {ability:.3f}")
        
        # Enhanced difficulty filtering with struggle-aware selection
        if target_difficulty:
            session = student_sessions.get(student_id, {})
            struggle_detected = session.get('struggle_detected', False)
            consecutive_wrong = session.get('consecutive_wrong', 0)
            
            primary_questions = [
                q for q in available_questions 
                if q['difficulty'].lower() == target_difficulty.lower()
            ]
            
            # If student is struggling, be more restrictive about difficulty expansion
            if struggle_detected or consecutive_wrong >= 2:
                # For struggling students, prefer easier questions only
                if len(primary_questions) < 5:  # Lower threshold for struggling students
                    easier_difficulties = self.get_easier_difficulties(target_difficulty)
                    easier_questions = [
                        q for q in available_questions 
                        if q['difficulty'] in easier_difficulties
                    ]
                    available_questions = primary_questions + easier_questions
                    logger.info(f"🔴 STRUGGLE ADAPTATION: Expanded to easier difficulties only ({target_difficulty} + {easier_difficulties})")
                else:
                    available_questions = primary_questions
                    logger.info(f"🔴 STRUGGLE FOCUS: Strict difficulty filtering to {target_difficulty} only")
            else:
                # Normal students: use standard adjacent difficulty expansion
                if len(primary_questions) < 10:
                    adjacent_difficulties = self.get_adjacent_difficulties(target_difficulty)
                    secondary_questions = [
                        q for q in available_questions 
                        if q['difficulty'] in adjacent_difficulties
                    ]
                    available_questions = primary_questions + secondary_questions
                else:
                    available_questions = primary_questions
        
        if not available_questions:
            logger.warning(f"No available questions for student {student_id}")
            return None
        
        # Enhanced question selection algorithm
        best_question = self.select_optimal_question(available_questions, ability, responses)
        
        # Prepare question for serving (include image data if needed)
        if best_question:
            best_question = self.prepare_question_for_serving(best_question)
            
            # Final validation - ensure this question hasn't been answered before
            if not validate_no_duplicate_questions(student_id, [best_question['id']]):
                logger.error(f"🚨 Selected duplicate question {best_question['id']}! Attempting to select alternative...")
                # Try to select an alternative question
                remaining_questions = [q for q in available_questions if q['id'] != best_question['id']]
                if remaining_questions:
                    alternative = self.select_optimal_question(remaining_questions, ability, responses)
                    if alternative:
                        best_question = self.prepare_question_for_serving(alternative)
                        logger.info(f"✅ Selected alternative question {best_question['id']}")
                    else:
                        logger.error("❌ No alternative questions available!")
                        return None
                else:
                    logger.error("❌ No remaining questions to select from!")
                    return None
            
            logger.info(f"✅ Selected question {best_question['id']} (difficulty: {best_question['difficulty']}, topic: {best_question['topic']})")
        
        return best_question
    
    def get_optimal_difficulty_for_ability(self, ability: float) -> str:
        """Map student ability to optimal question difficulty with step-by-step progression"""
        # More gradual progression - always start Very Easy and move up slowly
        if ability <= -1.0:
            return "Very Easy"
        elif ability <= 0.0:
            return "Easy" 
        elif ability <= 1.0:
            return "Moderate"
        else:
            return "Difficult"
    
    def get_adaptive_optimal_difficulty(self, student_id: str, ability: float) -> str:
        """Enhanced difficulty selection that considers struggle patterns and performance history"""
        
        session = student_sessions.get(student_id, {})
        consecutive_wrong = session.get('consecutive_wrong', 0)
        struggle_detected = session.get('struggle_detected', False)
        recent_performance = session.get('recent_performance_window', [])
        
        # Base difficulty from ability
        base_difficulty = self.get_optimal_difficulty_for_ability(ability)
        
        # Override difficulty selection for struggling students
        if struggle_detected or consecutive_wrong >= 2:
            
            # Severe struggle: Force Very Easy questions
            if consecutive_wrong >= 4:
                selected_difficulty = "Very Easy"
                logger.warning(f"🚨 EMERGENCY MODE: Forcing Very Easy questions due to {consecutive_wrong} consecutive wrong")
            
            # Moderate struggle: Force Easy or Very Easy
            elif consecutive_wrong >= 3:
                selected_difficulty = "Very Easy" if base_difficulty not in ["Very Easy", "Easy"] else "Very Easy"
                logger.warning(f"🔴 STRUGGLE MODE: Forcing Very Easy questions due to {consecutive_wrong} consecutive wrong")
            
            # Early struggle signs: Drop one difficulty level
            elif consecutive_wrong >= 2:
                difficulty_map = {
                    "Difficult": "Moderate",
                    "Moderate": "Easy", 
                    "Easy": "Very Easy",
                    "Very Easy": "Very Easy"
                }
                selected_difficulty = difficulty_map.get(base_difficulty, "Easy")
                logger.warning(f"⚠️  ADAPTIVE DROP: Reducing from {base_difficulty} to {selected_difficulty} due to {consecutive_wrong} consecutive wrong")
            
            # Poor recent performance: Be more conservative
            elif len(recent_performance) >= 3:
                recent_accuracy = sum(recent_performance) / len(recent_performance)
                if recent_accuracy < 0.5:  # Less than 50% accuracy
                    difficulty_map = {
                        "Difficult": "Easy",  # Drop 2 levels
                        "Moderate": "Very Easy",  # Drop 2 levels
                        "Easy": "Very Easy",
                        "Very Easy": "Very Easy"
                    }
                    selected_difficulty = difficulty_map.get(base_difficulty, "Easy")
                    logger.warning(f"📉 PERFORMANCE DROP: Reducing from {base_difficulty} to {selected_difficulty} due to {recent_accuracy:.1%} recent accuracy")
                else:
                    selected_difficulty = base_difficulty
            else:
                selected_difficulty = base_difficulty
        
        else:
            # Student is doing well, use normal difficulty progression
            selected_difficulty = base_difficulty
            
            # Bonus: If student has been consistently correct, consider slight increase
            consecutive_correct = session.get('consecutive_correct', 0)
            if consecutive_correct >= 3 and len(recent_performance) >= 3:
                recent_accuracy = sum(recent_performance) / len(recent_performance)
                if recent_accuracy >= 0.8:  # 80%+ accuracy
                    # Consider moving up one level (but not too aggressively)
                    difficulty_upgrade = {
                        "Very Easy": "Easy",
                        "Easy": "Moderate",
                        "Moderate": "Moderate",  # Don't auto-upgrade to Difficult
                        "Difficult": "Difficult"
                    }
                    upgraded_difficulty = difficulty_upgrade.get(base_difficulty, base_difficulty)
                    if upgraded_difficulty != base_difficulty:
                        logger.info(f"📈 PERFORMANCE BOOST: Upgrading from {base_difficulty} to {upgraded_difficulty} due to strong performance")
                        selected_difficulty = upgraded_difficulty
        
        # Final validation: Never go beyond what ability suggests by more than 1 level
        difficulty_levels = ["Very Easy", "Easy", "Moderate", "Difficult"]
        try:
            base_index = difficulty_levels.index(base_difficulty)
            selected_index = difficulty_levels.index(selected_difficulty)
            
            # Don't drop more than 2 levels below ability-suggested difficulty
            if selected_index < base_index - 2:
                selected_difficulty = difficulty_levels[max(0, base_index - 2)]
                logger.info(f"🔧 CONSTRAINT: Limited difficulty reduction to {selected_difficulty}")
                
        except ValueError:
            # Fallback if difficulty not found
            selected_difficulty = "Easy"
        
        return selected_difficulty
    
    def get_adjacent_difficulties(self, target_difficulty: str) -> List[str]:
        """Get adjacent difficulty levels for flexibility"""
        difficulty_order = ["Very Easy", "Easy", "Moderate", "Difficult"]
        
        try:
            index = difficulty_order.index(target_difficulty)
            adjacent = []
            if index > 0:
                adjacent.append(difficulty_order[index - 1])
            if index < len(difficulty_order) - 1:
                adjacent.append(difficulty_order[index + 1])
            return adjacent
        except ValueError:
            return ["Easy", "Moderate"]
    
    def get_easier_difficulties(self, target_difficulty: str) -> List[str]:
        """Get only easier difficulty levels for struggling students"""
        difficulty_order = ["Very Easy", "Easy", "Moderate", "Difficult"]
        
        try:
            index = difficulty_order.index(target_difficulty)
            # Return all easier difficulties
            easier = difficulty_order[:index]
            return easier
        except ValueError:
            return ["Very Easy", "Easy"]
    
    def select_optimal_question(self, available_questions: List[Dict], ability: float, responses: List[Dict]) -> Optional[Dict]:
        """Enhanced question selection with struggle-aware prioritization"""
        
        if not available_questions:
            return None
        
        # Get recently used topics and difficulties for diversity
        recent_topics = [self.questions[r['question_id']]['topic'] for r in responses[-5:] if r['question_id'] in self.questions]
        recent_difficulties = [self.questions[r['question_id']]['difficulty'] for r in responses[-3:] if r['question_id'] in self.questions]
        
        # Check if student is struggling (need student_id to access session)
        struggle_detected = False
        consecutive_wrong = 0
        if responses and hasattr(responses[-1], 'get'):
            # Try to find student session from responses
            for student_id, session in student_sessions.items():
                if session.get('responses') and len(session['responses']) > 0:
                    if session['responses'][-1].get('question_id') == responses[-1].get('question_id'):
                        struggle_detected = session.get('struggle_detected', False)
                        consecutive_wrong = session.get('consecutive_wrong', 0)
                        break
        
        question_scores = []
        
        for question in available_questions:
            score = 0
            question_difficulty = question.get('difficulty', 'Moderate')
            
            # 1. Information value (Fisher Information) - reduced weight for struggling students
            information = self.calculate_information(ability, question['id'])
            info_weight = 0.20 if struggle_detected else 0.35  # Reduced for struggling students
            score += information * info_weight
            
            # 2. Ability-difficulty match - enhanced for struggling students
            difficulty_match = self.calculate_difficulty_match(ability, question)
            match_weight = 0.35 if struggle_detected else 0.25  # Increased for struggling students
            score += difficulty_match * match_weight
            
            # 3. Struggle-specific confidence building bonus
            if struggle_detected or consecutive_wrong >= 2:
                confidence_bonus = self.calculate_confidence_building_score(question, consecutive_wrong)
                score += confidence_bonus * 0.25  # Significant weight for confidence building
                
                # Extra bonus for Very Easy questions when really struggling
                if consecutive_wrong >= 3 and question_difficulty == "Very Easy":
                    score += 0.3
                    logger.debug(f"Emergency Very Easy bonus for question {question['id']}")
            
            # 4. Enhanced topic diversity (stronger penalty for recently used topics)
            topic_diversity = self.calculate_enhanced_topic_diversity(question, recent_topics, recent_difficulties)
            diversity_weight = 0.15 if struggle_detected else 0.25  # Reduced for struggling students
            score += topic_diversity * diversity_weight
            
            # 5. Question quality indicators
            quality_score = self.calculate_question_quality_score(question)
            score += quality_score * 0.1
            
            # 6. Add small randomness to prevent always picking same "optimal" question
            randomness = np.random.uniform(0.0, 0.05)
            score += randomness
            
            question_scores.append((question, score))
        
        # Sort by score and return best question with adaptive candidate selection
        question_scores.sort(key=lambda x: x[1], reverse=True)
        
        # For struggling students, be more conservative in selection (prefer top choice)
        if struggle_detected or consecutive_wrong >= 3:
            # Select from top 2 candidates only for struggling students
            top_candidates = question_scores[:min(2, len(question_scores))]
            # Heavily weight the top candidate (80% chance)
            weights = [0.8, 0.2][:len(top_candidates)]
        else:
            # Normal students: select from top 3 candidates
            top_candidates = question_scores[:min(3, len(question_scores))]
            weights = [0.5, 0.3, 0.2][:len(top_candidates)]
        
        # Normalize weights to ensure they sum to 1.0 (fixes numpy probability error)
        weights = np.array(weights[:len(top_candidates)])
        weights = weights / weights.sum()
        
        # Weighted random selection
        candidates = [q[0] for q in top_candidates]
        selected = np.random.choice(candidates, p=weights)
        
        # Enhanced logging
        struggle_status = f" | STRUGGLE: {consecutive_wrong} wrong" if struggle_detected else ""
        logger.info(f"Selected question {selected['id']} (topic: {selected['topic']}, difficulty: {selected['difficulty']}){struggle_status}")
        logger.info(f"Question text preview: '{selected['text'][:50]}...'")
        
        return selected
    
    def calculate_confidence_building_score(self, question: Dict, consecutive_wrong: int) -> float:
        """Calculate bonus score for questions that help build student confidence"""
        
        difficulty = question.get('difficulty', 'Moderate')
        topic = question.get('topic', '').lower()
        
        confidence_score = 0.0
        
        # Strong preference for easier questions when struggling
        if consecutive_wrong >= 4:
            difficulty_bonus = {
                "Very Easy": 1.0,
                "Easy": 0.3,
                "Moderate": 0.0,
                "Difficult": -0.5
            }
        elif consecutive_wrong >= 2:
            difficulty_bonus = {
                "Very Easy": 0.8,
                "Easy": 0.6,
                "Moderate": 0.2,
                "Difficult": -0.2
            }
        else:
            difficulty_bonus = {
                "Very Easy": 0.4,
                "Easy": 0.3,
                "Moderate": 0.2,
                "Difficult": 0.0
            }
        
        confidence_score += difficulty_bonus.get(difficulty, 0.0)
        
        # Bonus for topics known to be more accessible
        accessible_topics = ['arithmetic', 'basic', 'fundamental', 'simple']
        if any(keyword in topic for keyword in accessible_topics):
            confidence_score += 0.2
        
        # Slight bonus for shorter questions (less overwhelming)
        question_length = len(question.get('text', ''))
        if question_length < 100:  # Shorter questions
            confidence_score += 0.1
        
        return confidence_score
    
    def calculate_difficulty_match(self, ability: float, question: Dict) -> float:
        """Calculate how well question difficulty matches student ability"""
        difficulty = question['difficulty']
        
        # Map difficulty to numeric scale
        difficulty_map = {
            "Very Easy": -1.5,
            "Easy": -0.5,
            "Moderate": 0.5,
            "Difficult": 1.5
        }
        
        difficulty_value = difficulty_map.get(difficulty, 0)
        
        # Calculate match score (inverse of distance)
        distance = abs(ability - difficulty_value)
        match_score = max(0, 1 - distance / 3)  # Normalize to 0-1
        
        return match_score
    
    def calculate_topic_diversity(self, question: Dict, responses: List[Dict]) -> float:
        """Encourage topic diversity in question selection"""
        if not responses:
            return 1.0
        
        question_topic = question['topic']
        recent_topics = [
            self.questions[r['question_id']]['topic'] 
            for r in responses[-5:] 
            if r['question_id'] in self.questions
        ]
        
        # Count occurrences of this topic in recent questions
        topic_count = recent_topics.count(question_topic)
        
        # Return diversity score (lower if topic appears frequently)
        return max(0.1, 1 - (topic_count * 0.2))
    
    def calculate_enhanced_topic_diversity(self, question: Dict, recent_topics: List[str], recent_difficulties: List[str]) -> float:
        """Enhanced topic and difficulty diversity calculation"""
        diversity_score = 1.0
        
        question_topic = question['topic']
        question_difficulty = question['difficulty']
        
        # Penalty for repeating topics (stronger penalty for more recent repetitions)
        for i, topic in enumerate(reversed(recent_topics)):
            if topic == question_topic:
                # More recent = higher penalty (exponential decay)
                penalty = 0.4 * (0.7 ** i)  # Penalty decreases with distance
                diversity_score -= penalty
        
        # Additional penalty for repeating same difficulty too often
        difficulty_count = recent_difficulties.count(question_difficulty)
        if difficulty_count > 1:
            diversity_score -= 0.2 * (difficulty_count - 1)
        
        # Bonus for questions from underrepresented topics
        unique_recent_topics = set(recent_topics)
        if question_topic not in unique_recent_topics and len(unique_recent_topics) > 0:
            diversity_score += 0.3  # Bonus for new topic
        
        return max(0.1, diversity_score)
    
    def is_question_complete(self, question: Dict) -> bool:
        """Check if a question has complete and valid content (maximally relaxed for capacity)"""
        # Check if question text exists
        text = question.get('text', '').strip()
        if len(text) < 5:  # Extremely relaxed - just needs some text
            return False
        
        # Check if options exist
        options = question.get('options', {})
        if not options:
            return False
        
        # Check if at least 2 options have any content at all
        valid_options = 0
        for opt_key in ['A', 'B', 'C', 'D']:
            option_text = options.get(opt_key, '').strip()
            if option_text:  # Just needs to exist
                valid_options += 1
        
        if valid_options < 2:  # At least 2 options
            return False
        
        # Check if answer exists and is valid
        answer = question.get('answer', '').strip()
        if not answer or answer not in ['A', 'B', 'C', 'D']:
            return False
        
        # Only filter out questions that are JUST single-word category labels
        text_lower = text.lower().strip()
        category_patterns = ['arithmetic', 'algebra', 'geometry', 'reasoning', 'mathematics', 'varc', 'modern math']
        if text_lower in category_patterns:
            return False
            
        return True
    
    def calculate_question_quality_score(self, question: Dict) -> float:
        """Calculate question quality based on various factors"""
        score = 0.5  # Base score
        
        # Bonus for questions with images (often more engaging)
        if question.get('has_image'):
            score += 0.3
        
        # Bonus for complete option sets
        options = question.get('options', {})
        if len(options) >= 4:
            score += 0.2
        
        # Bonus for reasonable question length
        text_length = len(question.get('text', ''))
        if 20 <= text_length <= 200:
            score += 0.1
        
        return min(1.0, score)
    
    def calculate_information(self, ability: float, item_id: str) -> float:
        """Calculate Fisher information for an item at given ability level"""
        prob = self.calculate_probability(ability, item_id)
        
        if item_id not in self.item_parameters:
            return 0.0
        
        a = self.item_parameters[item_id]['discrimination']
        c = self.item_parameters[item_id].get('guessing', 0.25)
        
        try:
            # Fisher information for 3PL model
            numerator = (a ** 2) * ((prob - c) ** 2) * (1 - prob)
            denominator = prob * ((1 - c) ** 2)
            
            if denominator > 0:
                return numerator / denominator
            else:
                return 0.0
        except (ZeroDivisionError, OverflowError):
            return 0.0
    
    def update_student_ability(self, student_id: str, question_id: str, response: bool):
        """Enhanced ability update with adaptive difficulty adjustment based on performance patterns"""
        
        if student_id not in student_sessions:
            student_sessions[student_id] = {
                'ability': self.default_ability,
                'responses': [],
                'ability_history': [self.default_ability],
                'start_time': datetime.now(),
                'last_update': datetime.now(),
                'consecutive_wrong': 0,
                'consecutive_correct': 0,
                'struggle_detected': False,
                'recent_performance_window': []
            }
        
        session = student_sessions[student_id]
        
        # Add response to history
        session['responses'].append({
            'question_id': question_id,
            'response': response,
            'timestamp': datetime.now(),
            'probability': self.calculate_probability(session['ability'], question_id)
        })
        
        # Track answered questions to avoid repetition
        if 'answered_questions' not in session:
            session['answered_questions'] = []
        if question_id not in session['answered_questions']:
            session['answered_questions'].append(question_id)
        
        # Update performance tracking
        self._update_performance_tracking(session, response)
        
        # Get current question difficulty to determine step size
        current_question = self.questions.get(question_id, {})
        current_difficulty = current_question.get('difficulty', 'Moderate')
        current_ability = session['ability']
        
        # Enhanced adaptive ability update based on performance patterns
        new_ability = self._calculate_adaptive_ability_change(
            session, current_ability, current_difficulty, response
        )
        
        # Ensure ability stays within bounds
        new_ability = max(self.ability_range[0], min(self.ability_range[1], new_ability))
        
        session['ability'] = new_ability
        session['ability_history'].append(new_ability)
        session['last_update'] = datetime.now()
        
        old_diff = self.get_optimal_difficulty_for_ability(current_ability)
        new_diff = self.get_optimal_difficulty_for_ability(new_ability)
        
        # Log performance insights
        struggle_status = "🔴 STRUGGLING" if session.get('struggle_detected') else "✅ Normal"
        logger.info(f"Updated ability for {student_id}: {current_ability:.3f} -> {new_ability:.3f} "
                   f"({old_diff} -> {new_diff}) after {current_difficulty} question | "
                   f"Consecutive wrong: {session.get('consecutive_wrong', 0)} | Status: {struggle_status}")
        
        return new_ability
    
    def _update_performance_tracking(self, session: Dict, response: bool):
        """Update performance tracking metrics for adaptive adjustment"""
        
        # Update consecutive counters
        if response:  # Correct answer
            session['consecutive_correct'] = session.get('consecutive_correct', 0) + 1
            session['consecutive_wrong'] = 0
        else:  # Wrong answer
            session['consecutive_wrong'] = session.get('consecutive_wrong', 0) + 1
            session['consecutive_correct'] = 0
        
        # Maintain recent performance window (last 5 questions)
        if 'recent_performance_window' not in session:
            session['recent_performance_window'] = []
        
        session['recent_performance_window'].append(response)
        if len(session['recent_performance_window']) > 5:
            session['recent_performance_window'].pop(0)
        
        # Detect struggling patterns
        self._detect_struggle_patterns(session)
    
    def _detect_struggle_patterns(self, session: Dict):
        """Detect if student is struggling and needs easier questions"""
        
        consecutive_wrong = session.get('consecutive_wrong', 0)
        recent_performance = session.get('recent_performance_window', [])
        
        # Pattern 1: 3+ consecutive wrong answers = immediate struggle
        if consecutive_wrong >= 3:
            session['struggle_detected'] = True
            logger.warning(f"🔴 STRUGGLE DETECTED: {consecutive_wrong} consecutive wrong answers")
            return
        
        # Pattern 2: Poor performance in recent window (< 40% in last 5)
        if len(recent_performance) >= 5:
            recent_accuracy = sum(recent_performance) / len(recent_performance)
            if recent_accuracy < 0.4:
                session['struggle_detected'] = True
                logger.warning(f"🔴 STRUGGLE DETECTED: Low recent accuracy ({recent_accuracy:.1%})")
                return
        
        # Pattern 3: Alternating wrong/right but mostly wrong (2 out of last 3)
        if len(recent_performance) >= 3:
            recent_wrong_count = sum(1 for r in recent_performance[-3:] if not r)
            if recent_wrong_count >= 2:
                session['struggle_detected'] = True
                logger.warning(f"🔴 STRUGGLE DETECTED: {recent_wrong_count}/3 recent questions wrong")
                return
        
        # Reset struggle detection if performance improves
        if consecutive_wrong == 0 and len(recent_performance) >= 3:
            recent_correct_count = sum(1 for r in recent_performance[-3:] if r)
            if recent_correct_count >= 2:  # 2+ correct in last 3
                if session.get('struggle_detected'):
                    logger.info("✅ RECOVERY DETECTED: Student performance improving, clearing struggle flag")
                session['struggle_detected'] = False
    
    def _calculate_adaptive_ability_change(self, session: Dict, current_ability: float, 
                                         current_difficulty: str, response: bool) -> float:
        """Calculate ability change with adaptive adjustment based on struggle detection"""
        
        consecutive_wrong = session.get('consecutive_wrong', 0)
        consecutive_correct = session.get('consecutive_correct', 0)
        struggle_detected = session.get('struggle_detected', False)
        
        # Base ability adjustments (same as before)
        base_adjustment = 0.0
        
        if response:  # Correct answer
            if current_difficulty == "Very Easy":
                base_adjustment = 0.7
            elif current_difficulty == "Easy":  
                base_adjustment = 0.6
            elif current_difficulty == "Moderate":
                base_adjustment = 0.5
            else:  # Difficult
                base_adjustment = 0.3
        else:  # Wrong answer
            if current_difficulty == "Difficult":
                base_adjustment = -0.5
            elif current_difficulty == "Moderate":
                base_adjustment = -0.6
            elif current_difficulty == "Easy":
                base_adjustment = -0.7
            else:  # Very Easy
                base_adjustment = -0.3
        
        # Adaptive adjustments based on performance patterns
        if response:  # Correct answer adjustments
            # Bonus for breaking a wrong streak
            if consecutive_wrong > 0:
                streak_bonus = min(0.2, consecutive_wrong * 0.05)
                base_adjustment += streak_bonus
                logger.info(f"✅ Streak broken bonus: +{streak_bonus:.2f} (was {consecutive_wrong} wrong)")
            
            # Extra bonus for consistent correct answers (confidence building)
            if consecutive_correct >= 2:
                confidence_bonus = min(0.15, consecutive_correct * 0.03)
                base_adjustment += confidence_bonus
        
        else:  # Wrong answer adjustments
            # Enhanced penalty for struggle patterns
            if struggle_detected:
                # More aggressive ability reduction when struggling
                if consecutive_wrong >= 3:
                    struggle_penalty = min(0.4, consecutive_wrong * 0.1)
                    base_adjustment -= struggle_penalty
                    logger.warning(f"🔴 Struggle penalty applied: -{struggle_penalty:.2f}")
                
                # Force ability toward easier questions when struggling badly
                if consecutive_wrong >= 4:
                    # Push toward Very Easy territory
                    target_ability = -1.5  # Very Easy range
                    if current_ability > target_ability:
                        emergency_reduction = min(0.8, (current_ability - target_ability) * 0.3)
                        base_adjustment -= emergency_reduction
                        logger.warning(f"🚨 EMERGENCY difficulty reduction: -{emergency_reduction:.2f}")
        
        # Apply the adjustment
        new_ability = current_ability + base_adjustment
        
        # Additional adaptive bounds based on struggle state
        if struggle_detected:
            # Cap maximum ability to prevent questions that are too hard
            if consecutive_wrong >= 3:
                max_ability = -0.8  # Force Easy/Very Easy questions
                new_ability = min(new_ability, max_ability)
            elif consecutive_wrong >= 2:
                max_ability = -0.2  # Cap at Easy questions
                new_ability = min(new_ability, max_ability)
        
        return new_ability
    
    def estimate_ability_mle(self, responses: List[Dict]) -> float:
        """Estimate ability using Maximum Likelihood Estimation with adaptive learning rate"""
        
        if not responses:
            return self.default_ability
        
        def likelihood(ability):
            log_likelihood = 0
            for response in responses:
                prob = self.calculate_probability(ability, response['question_id'])
                if response['response']:
                    log_likelihood += np.log(max(prob, 1e-10))
                else:
                    log_likelihood += np.log(max(1 - prob, 1e-10))
            return -log_likelihood  # Negative for minimization
        
        # Use finer grid search for better precision
        abilities = np.linspace(self.ability_range[0], self.ability_range[1], 121)
        likelihoods = [likelihood(a) for a in abilities]
        
        best_ability = abilities[np.argmin(likelihoods)]
        
        # Apply adaptive smoothing based on number of responses
        if len(responses) < 5:
            # For early responses, move more conservatively toward estimated ability
            current_ability = self.get_student_ability(responses[0].get('student_id', ''))
            smoothing_factor = 0.3 + (len(responses) * 0.1)  # 0.3 to 0.7
            best_ability = current_ability + smoothing_factor * (best_ability - current_ability)
        
        # Constrain to reasonable range
        return max(self.ability_range[0], min(self.ability_range[1], best_ability))
    
    def get_student_ability(self, student_id: str) -> float:
        """Get current ability estimate for student"""
        if student_id in student_sessions:
            return student_sessions[student_id]['ability']
        return self.default_ability
    
    def prepare_question_for_serving(self, question: Dict) -> Dict:
        """Prepare question for API response, including image data if needed"""
        prepared_question = question.copy()
        
        # Add image data if question has an image
        if question.get('has_image') and question.get('image_id'):
            image_id = question['image_id']
            if image_id in self.image_mappings:
                image_info = self.image_mappings[image_id]
                prepared_question['image_url'] = f"/api/image/{image_id}"
                prepared_question['image_info'] = {
                    'id': image_id,
                    'format': self.get_image_format(image_info['full_path'])
                }
        
        return prepared_question
    
    def get_image_format(self, image_path: str) -> str:
        """Get image format from file extension"""
        ext = Path(image_path).suffix.lower()
        format_map = {
            '.png': 'PNG',
            '.jpg': 'JPEG',
            '.jpeg': 'JPEG',
            '.gif': 'GIF',
            '.bmp': 'BMP',
            '.webp': 'WEBP'
        }
        return format_map.get(ext, 'PNG')
    
    def get_assessment_summary(self, student_id: str) -> Dict:
        """Get comprehensive assessment summary for student"""
        if student_id not in student_sessions:
            return {'error': 'Student session not found'}
        
        session = student_sessions[student_id]
        responses = session['responses']
        
        if not responses:
            return {'error': 'No responses found'}
        
        # Calculate performance metrics
        total_questions = len(responses)
        correct_answers = sum(1 for r in responses if r['response'])
        accuracy = correct_answers / total_questions if total_questions > 0 else 0
        
        # Topic-wise performance
        topic_performance = {}
        for response in responses:
            question_id = response['question_id']
            if question_id in self.questions:
                topic = self.questions[question_id]['topic']
                if topic not in topic_performance:
                    topic_performance[topic] = {'correct': 0, 'total': 0}
                topic_performance[topic]['total'] += 1
                if response['response']:
                    topic_performance[topic]['correct'] += 1
        
        # Add accuracy to topic performance
        for topic in topic_performance:
            topic_performance[topic]['accuracy'] = (
                topic_performance[topic]['correct'] / topic_performance[topic]['total']
            )
        
        # Difficulty-wise performance
        difficulty_performance = {}
        for response in responses:
            question_id = response['question_id']
            if question_id in self.questions:
                difficulty = self.questions[question_id]['difficulty']
                if difficulty not in difficulty_performance:
                    difficulty_performance[difficulty] = {'correct': 0, 'total': 0}
                difficulty_performance[difficulty]['total'] += 1
                if response['response']:
                    difficulty_performance[difficulty]['correct'] += 1
        
        # Add accuracy to difficulty performance
        for difficulty in difficulty_performance:
            difficulty_performance[difficulty]['accuracy'] = (
                difficulty_performance[difficulty]['correct'] / difficulty_performance[difficulty]['total']
            )
        
        # Calculate time spent
        time_spent_minutes = (session['last_update'] - session['start_time']).total_seconds() / 60
        
        return {
            'success': True,
            'student_id': student_id,
            'current_ability': session['ability'],
            'ability_history': session['ability_history'],
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'overall_accuracy': accuracy,
            'topic_performance': topic_performance,
            'difficulty_performance': difficulty_performance,
            'start_time': session['start_time'].isoformat(),
            'last_update': session['last_update'].isoformat(),
            'session_duration_minutes': time_spent_minutes,
            'final_results': {
                'final_score': round(accuracy * 100, 1),
                'ability_level': f"{session['ability']:.2f}",
                'questions_answered': total_questions,
                'time_spent_minutes': round(time_spent_minutes, 1)
            },
            'recommendations': self._generate_recommendations(topic_performance, difficulty_performance, session['ability'])
        }
    
    def _generate_recommendations(self, topic_performance: Dict, difficulty_performance: Dict, ability: float) -> List[str]:
        """Generate personalized learning recommendations as structured objects with struggle-aware insights"""
        def rec(icon: str, title: str, description: str, priority: str) -> Dict[str, str]:
            return { 'icon': icon, 'title': title, 'description': description, 'priority': priority }

        recs: List[Dict[str, str]] = []

        # Analyze topic performance
        weak_topics = []
        strong_topics = []
        for topic, perf in topic_performance.items():
            if perf.get('accuracy', 0) < 0.6:
                weak_topics.append(topic)
            elif perf.get('accuracy', 0) >= 0.8:
                strong_topics.append(topic)

        # Analyze difficulty performance
        weak_difficulties = []
        struggling_badly = False
        for difficulty, perf in difficulty_performance.items():
            if perf.get('accuracy', 0) < 0.5:
                weak_difficulties.append(difficulty)
            if difficulty in ["Very Easy", "Easy"] and perf.get('accuracy', 0) < 0.4:
                struggling_badly = True

        # Enhanced ability-based guidance with struggle detection
        if struggling_badly or (ability < -1.5 and len([d for d in weak_difficulties if d in ["Very Easy", "Easy"]]) > 0):
            recs.append(rec('🆘', 'Take a break & reset', 'Step back, review basics, and return with fresh focus. Learning takes time!', 'high'))
            recs.append(rec('🧱', 'Master fundamentals first', 'Focus exclusively on Very Easy questions until you feel confident.', 'high'))
            recs.append(rec('📖', 'Concept review', 'Review basic concepts and formulas before attempting more questions.', 'high'))
            recs.append(rec('👥', 'Get help', 'Consider asking a teacher, tutor, or study group for additional support.', 'medium'))
        elif ability < -1.0:
            recs.append(rec('🧱', 'Build strong foundations', 'Focus on fundamentals with Very Easy questions to gain confidence.', 'high'))
            recs.append(rec('➗', 'Practice basics regularly', 'Daily practice on basic arithmetic and algebra will help you progress steadily.', 'medium'))
            recs.append(rec('⏳', 'Take your time', 'Don\'t rush - accuracy is more important than speed right now.', 'medium'))
        elif ability < 0:
            recs.append(rec('🎯', 'Consolidate core skills', 'Work on Easy to Moderate questions to build accuracy and speed.', 'medium'))
            recs.append(rec('📘', 'Review key concepts', 'Revisit fundamental concepts before attempting harder problems.', 'medium'))
        elif ability < 1.0:
            recs.append(rec('🚀', 'Increase challenge gradually', 'Attempt more Moderate questions and sprinkle in a few Difficult ones.', 'low'))
            recs.append(rec('⏱️', 'Time management', 'Practice timed quizzes to improve consistency and endurance.', 'low'))
        else:
            recs.append(rec('🏆', 'Advance to tougher sets', 'You are ready for more Difficult problems and competitive practice.', 'low'))
            recs.append(rec('🤝', 'Teach to learn', 'Explaining concepts to peers can reinforce your mastery.', 'low'))

        # Enhanced topic-specific guidance
        if weak_topics:
            if len(weak_topics) > 3:
                recs.append(rec('📚', 'Focus on 2-3 topics', f"Too many weak areas. Focus on just: {', '.join(weak_topics[:2])} first.", 'high'))
            else:
                recs.append(rec('📚', 'Focus topics', f"Allocate extra practice to: {', '.join(weak_topics[:3])}.", 'high'))
        
        if strong_topics and not struggling_badly:
            recs.append(rec('⭐', 'Leverage strengths', f"Keep sharpening: {', '.join(strong_topics[:2])}.", 'low'))

        # Enhanced difficulty-specific guidance
        if weak_difficulties:
            if "Very Easy" in weak_difficulties:
                recs.append(rec('🔥', 'Emergency basics', 'Your foundation needs work. Focus ONLY on Very Easy questions for now.', 'high'))
            else:
                pretty = ', '.join(weak_difficulties)
                recs.append(rec('🧩', 'Difficulty focus', f"Spend more sessions on {pretty} questions to lift accuracy.", 'medium'))

        # Motivational recommendations for struggling students
        if struggling_badly:
            recs.append(rec('💪', 'Stay positive', 'Learning is a journey. Every mistake is a step toward understanding!', 'low'))
        
        # Limit to 6 items max for UI (increased for struggling students who need more guidance)
        return recs[:6]
    
    def get_struggle_feedback(self, student_id: str) -> Dict[str, Any]:
        """Get specialized feedback and recommendations for struggling students"""
        
        session = student_sessions.get(student_id, {})
        consecutive_wrong = session.get('consecutive_wrong', 0)
        struggle_detected = session.get('struggle_detected', False)
        recent_performance = session.get('recent_performance_window', [])
        responses = session.get('responses', [])
        
        if not struggle_detected and consecutive_wrong < 2:
            return {'struggling': False}
        
        # Calculate struggle metrics
        total_questions = len(responses)
        if total_questions == 0:
            return {'struggling': False}
        
        recent_accuracy = sum(recent_performance) / len(recent_performance) if recent_performance else 0
        overall_accuracy = sum(1 for r in responses if r.get('response', False)) / total_questions
        
        # Generate specific struggle feedback
        feedback = {
            'struggling': True,
            'consecutive_wrong': consecutive_wrong,
            'recent_accuracy': round(recent_accuracy * 100, 1),
            'overall_accuracy': round(overall_accuracy * 100, 1),
            'recommendations': [],
            'encouragement': self._get_encouragement_message(consecutive_wrong),
            'next_steps': []
        }
        
        # Specific recommendations based on struggle severity
        if consecutive_wrong >= 4:
            feedback['recommendations'].extend([
                "Take a 5-10 minute break to reset your focus",
                "Review basic concepts before continuing", 
                "We'll give you Very Easy questions to rebuild confidence",
                "Consider asking for help from a teacher or tutor"
            ])
            feedback['next_steps'] = [
                "Focus on Very Easy questions only",
                "Don't worry about speed - accuracy first",
                "Review any concepts you're unsure about"
            ]
        elif consecutive_wrong >= 2:
            feedback['recommendations'].extend([
                "Slow down and read each question carefully",
                "We'll provide slightly easier questions",
                "Focus on accuracy over speed",
                "Review your recent mistakes to learn from them"
            ])
            feedback['next_steps'] = [
                "Take easier questions to build momentum", 
                "Read all answer choices before selecting",
                "Double-check your work when possible"
            ]
        
        return feedback
    
    def _get_encouragement_message(self, consecutive_wrong: int) -> str:
        """Get appropriate encouragement based on struggle level"""
        
        if consecutive_wrong >= 4:
            messages = [
                "Learning is a journey with ups and downs. You're building important problem-solving skills!",
                "Every expert was once a beginner. Take your time and focus on understanding.",
                "Mistakes are proof that you're learning. Let's take a step back and build your confidence.",
                "You're working on challenging material. It's normal to struggle - that's how we grow!"
            ]
        elif consecutive_wrong >= 2:
            messages = [
                "Don't worry about getting some wrong - that's how we learn what to focus on!",
                "You're doing fine! Let's adjust the difficulty to help you succeed.",
                "Learning happens when we challenge ourselves. Let's find the right level for you.",
                "Every mistake teaches us something. You're making progress!"
            ]
        else:
            messages = [
                "You're doing great! Keep up the focused effort.",
                "Nice work! Learning takes practice and you're showing great dedication."
            ]
        
        import random
        return random.choice(messages)


@app.route('/api/student/personalized_report', methods=['POST'])
def generate_personalized_report():
    """Generate a Gemini-powered personalized report using aggregated diagnosis data.
    Request JSON: { profile_id? , student_name?, student_grade?, api_key? , model? }
    Response JSON: { success, report_markdown, strengths, weaknesses, learning_path }
    """
    if not trained_model:
        return jsonify({'success': False, 'error': 'Model not loaded'}), 500

    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}

    profile_id = data.get('profile_id')
    name = data.get('student_name') or data.get('studentName')
    grade = data.get('student_grade') or data.get('studentGrade')
    if not profile_id:
        if not (name and grade):
            return jsonify({'success': False, 'error': 'profile_id or (student_name and student_grade) required'}), 400
        profile_id = _compute_profile_id(name, grade)

    # Gather diagnosis (reuse logic similar to /api/student/diagnosis)
    hist = _load_history(profile_id)
    responses = list(hist.get('responses', []))
    live_sessions = [s for s in student_sessions.values() if s.get('profile_id') == profile_id]
    for sess in live_sessions:
        for r in sess.get('responses', []):
            qid = r.get('question_id')
            q = trained_model.questions.get(qid, {})
            responses.append({
                'session_id': 'live',
                'timestamp': r.get('timestamp', datetime.now().isoformat()),
                'question_id': qid,
                'topic': q.get('topic'),
                'difficulty': q.get('difficulty'),
                'is_correct': r.get('response', False),
                'ability_after': sess.get('ability')
            })

    # Aggregate
    topic_stats: Dict[str, Dict[str, int]] = {}
    diff_stats: Dict[str, Dict[str, int]] = {}
    ability_vals: List[float] = []
    for r in responses:
        topic = r.get('topic') or 'Unknown'
        diff = r.get('difficulty') or 'Unknown'
        ok = bool(r.get('is_correct'))
        topic_stats.setdefault(topic, {'correct': 0, 'total': 0})
        topic_stats[topic]['total'] += 1
        topic_stats[topic]['correct'] += 1 if ok else 0
        diff_stats.setdefault(diff, {'correct': 0, 'total': 0})
        diff_stats[diff]['total'] += 1
        diff_stats[diff]['correct'] += 1 if ok else 0
        if r.get('ability_after') is not None:
            ability_vals.append(float(r.get('ability_after')))

    def rate(d: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, float]]:
        out = {}
        for k, v in d.items():
            total = max(1, v['total'])
            out[k] = { **v, 'accuracy': round((v['correct']/total)*100, 1) }
        return out

    per_topic = rate(topic_stats)
    per_difficulty = rate(diff_stats)
    overall_accuracy = round((sum(v['correct'] for v in topic_stats.values()) / max(1, sum(v['total'] for v in topic_stats.values()))) * 100, 1)
    current_ability = ability_vals[-1] if ability_vals else trained_model.default_ability

    # Prepare a fallback learning path from our rule-based engine
    fallback_recs = trained_model._generate_recommendations(per_topic, per_difficulty, current_ability)

    # Build prompt for Gemini AI-Powered Personalized Report
    api_key = os.environ.get('GEMINI_API_KEY')
    model_name = data.get('model') or 'gemini-pro'

    if not api_key:
        # Return a graceful fallback if no key
        basic = {
            'success': True,
            'provider': 'fallback',
            'report_markdown': (
                f"### Personalized Report (Fallback)\n"
                f"Overall accuracy: {overall_accuracy}%\n\n"
                f"- Current estimated ability: {round(current_ability, 2)}\n"
                f"- Strong topics: {', '.join([t for t, s in per_topic.items() if s['accuracy'] >= 80]) or '—'}\n"
                f"- Focus topics: {', '.join([t for t, s in per_topic.items() if s['accuracy'] < 60]) or '—'}\n\n"
                f"#### Recommended Next Steps\n"
            ),
            'learning_path': fallback_recs,
            'strengths': [t for t, s in per_topic.items() if s['accuracy'] >= 80],
            'weaknesses': [t for t, s in per_topic.items() if s['accuracy'] < 60],
            'overall_accuracy': overall_accuracy,
            'current_ability': round(current_ability, 2),
        }
        return jsonify(basic)

    # Try using Gemini/GenAI if the library is available, but fail gracefully to deterministic fallback
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        # Prefer querying supported models dynamically where available
        model_to_try = None
        try:
            # List models and pick first one that supports text generation (if API supports this)
            available = []
            try:
                # Some SDKs provide list_models(); wrap defensively
                available = [m.id for m in getattr(genai, 'list_models', lambda: [])()]
            except Exception:
                # fallback to known names if list_models is not present
                available = []

            # Candidate names (kept as a fallback list)
            candidates = ['gemini-pro', 'gemini-1.0-pro', 'models/gemini-pro', 'gemini-1.5-pro']
            # Prefer any candidate that appears in available; otherwise try candidates in order
            for c in candidates:
                if c in available:
                    model_to_try = c
                    break
            if not model_to_try and available:
                model_to_try = available[0]
        except Exception as e:
            logger.warning(f"Could not list models: {e}")
            model_to_try = None

        # Compose the content for a generation attempt
        summary = {
            'overall_accuracy': overall_accuracy,
            'current_ability': round(current_ability, 2),
            'per_topic': per_topic,
            'per_difficulty': per_difficulty,
        }

        system_prompt = (
            "You are an expert learning coach for K-12 assessments. "
            "Generate an AI-Powered Personalized Report based on the student's performance data. "
            "Be concise, encouraging, and give clear next steps. Output JSON with keys: report_markdown, strengths, weaknesses, learning_path." 
        )

        prompt = f"SYSTEM:\n{system_prompt}\n\nSTUDENT_PERFORMANCE_DATA:\n{json.dumps(summary, ensure_ascii=False)}\n\nRespond only with JSON."

        text = None
        if model_to_try:
            try:
                model = genai.GenerativeModel(model_to_try)
                resp = model.generate_content(prompt)
                text = resp.text or ''
            except Exception as model_err:
                logger.warning(f"Model {model_to_try} generation failed: {model_err}")
                text = None

        # If generation returned something, try to parse JSON safely
        parsed = None
        if text:
            try:
                if '```' in text:
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start != -1 and end != -1:
                        text = text[start:end]
                parsed = json.loads(text)
            except Exception as e:
                logger.warning(f"Failed to parse model output as JSON: {e}")
                parsed = None

        # If anything fails, return deterministic fallback (always succeed)
        if not parsed or 'report_markdown' not in parsed:
            # Deterministic fallback report
            report_md = (
                f"### Personalized Report\n\n"
                f"Overall accuracy: {overall_accuracy}%\n\n"
                f"Estimated ability: {round(current_ability, 2)}\n\n"
                f"Top strengths: {', '.join([t for t, s in per_topic.items() if s['accuracy'] >= 80]) or '—'}\n\n"
                f"Focus areas: {', '.join([t for t, s in per_topic.items() if s['accuracy'] < 60]) or '—'}\n\n"
                "Recommended next steps:\n"
            )
            # Add short bullets from fallback_recs
            for rec in fallback_recs:
                report_md += f"- {rec.get('title','Practice')} — {rec.get('description','Practice more')}\n"

            response = {
                'success': True,
                'provider': 'fallback',
                'report_markdown': report_md,
                'learning_path': fallback_recs,
                'strengths': [t for t, s in per_topic.items() if s['accuracy'] >= 80],
                'weaknesses': [t for t, s in per_topic.items() if s['accuracy'] < 60],
                'overall_accuracy': overall_accuracy,
                'current_ability': round(current_ability, 2),
            }
            return jsonify(response)

        # If parsed looks good, merge fallback learning path if missing
        if 'learning_path' not in parsed or not parsed['learning_path']:
            parsed['learning_path'] = fallback_recs

        parsed.setdefault('overall_accuracy', overall_accuracy)
        parsed.setdefault('current_ability', round(current_ability, 2))
        return jsonify({ 'success': True, 'provider': model_to_try or 'gemini', **parsed })

    except ModuleNotFoundError:
        # GenAI SDK not installed — return deterministic fallback
        logger.warning('google-generativeai not installed; returning fallback personalized report')
        report_md = (
            f"### Personalized Report\n\n"
            f"Overall accuracy: {overall_accuracy}%\n\n"
            f"Estimated ability: {round(current_ability, 2)}\n\n"
            f"Top strengths: {', '.join([t for t, s in per_topic.items() if s['accuracy'] >= 80]) or '—'}\n\n"
            f"Focus areas: {', '.join([t for t, s in per_topic.items() if s['accuracy'] < 60]) or '—'}\n\n"
            "Recommended next steps:\n"
        )
        for rec in fallback_recs:
            report_md += f"- {rec.get('title','Practice')} — {rec.get('description','Practice more')}\n"

        return jsonify({
            'success': True,
            'provider': 'fallback',
            'report_markdown': report_md,
            'learning_path': fallback_recs,
            'strengths': [t for t, s in per_topic.items() if s['accuracy'] >= 80],
            'weaknesses': [t for t, s in per_topic.items() if s['accuracy'] < 60],
            'overall_accuracy': overall_accuracy,
            'current_ability': round(current_ability, 2),
        })


def load_trained_model(model_path: str = 'trained_adaptive_assessment_model.json'):
    """Load the trained adaptive assessment model"""
    global trained_model
    
    try:
        from pathlib import Path
        base = Path(model_path)
        fixed_candidate = base.with_name(base.stem + '_ai_fixed.json')
        chosen = fixed_candidate if fixed_candidate.exists() and 'ai_fixed' not in base.name else base
        with open(chosen, 'r', encoding='utf-8') as f:
            model_data = json.load(f)
        
        trained_model = AdaptiveAssessmentEngine(model_data)
        logger.info(f"Successfully loaded trained model from {str(chosen)}")
        logger.info(f"Model contains {len(model_data['questions'])} questions")
        logger.info(f"Model version: {model_data['model_metadata'].get('version', 'unknown')}")
        
        # Initialize cross-student uniqueness pools
        load_question_usage_from_history()
        
        return True
        
    except FileNotFoundError:
        logger.error(f"Model file not found: {model_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        return False


# API Routes

@app.route('/api/assessment/start_cross_student_unique', methods=['POST'])
def start_cross_student_unique_assessment():
    """Start an assessment with cross-student uniqueness guarantee"""
    if not trained_model:
        return jsonify({'success': False, 'error': 'Model not loaded'}), 500
    
    try:
        data = request.get_json()
        student_name = data.get('student_name')
        student_grade = data.get('student_grade')
        num_questions = data.get('num_questions', 30)
        
        if not student_name or not student_grade:
            return jsonify({'success': False, 'error': 'Student name and grade required'}), 400
        
        # Generate session and profile IDs
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{student_name}"
        profile_id = _compute_profile_id(student_name, student_grade)
        
        # Check cross-student uniqueness feasibility
        available = get_available_questions_for_cross_student_uniqueness()
        if available['total_available'] < num_questions:
            return jsonify({
                'success': False,
                'error': f'Insufficient unique questions available. Need {num_questions}, have {available["total_available"]}',
                'available_questions': available['total_available'],
                'suggestion': 'Reduce number of questions or wait for question pool refresh'
            }), 400
        
        # Create student session
        student_sessions[session_id] = {
            'profile_id': profile_id,
            'student_name': student_name,
            'student_grade': student_grade,
            'ability': trained_model.default_ability,
            'responses': [],
            'start_time': datetime.now(),
            'last_update': datetime.now(),
            'cross_student_unique': True,
            'questions_allocated': 0,
            'target_questions': num_questions
        }
        
        # Pre-allocate questions for fairness
        allocated_questions = []
        
        # Smart allocation across difficulties for balanced assessment
        allocation_plan = smart_question_allocation_for_cross_student_uniqueness(1, num_questions)
        if not allocation_plan['success']:
            return jsonify({
                'success': False,
                'error': allocation_plan['error']
            }), 400
        
        # Get first question using cross-student unique mode
        first_question = trained_model.select_next_question(
            session_id, 
            cross_student_unique=True
        )
        
        if not first_question:
            return jsonify({
                'success': False,
                'error': 'No questions available for cross-student unique assessment'
            }), 500
        
        # Reserve the first question
        if not reserve_questions_for_session(session_id, profile_id, [first_question['id']]):
            return jsonify({
                'success': False,
                'error': 'Failed to reserve question - may already be in use'
            }), 409
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'profile_id': profile_id,
            'first_question': first_question,
            'allocation_plan': allocation_plan,
            'available_questions': available['total_available'],
            'cross_student_unique': True,
            'message': 'Cross-student unique assessment started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting cross-student unique assessment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/assessment/get_next_question_unique', methods=['POST'])
def get_next_question_cross_student_unique():
    """Get next question with cross-student uniqueness"""
    if not trained_model:
        return jsonify({'success': False, 'error': 'Model not loaded'}), 500
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        answered_questions = data.get('answered_questions', [])
        
        if session_id not in student_sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        session = student_sessions[session_id]
        if not session.get('cross_student_unique', False):
            return jsonify({'success': False, 'error': 'Session not configured for cross-student uniqueness'}), 400
        
        # Check if we've reached the target number of questions
        if len(answered_questions) >= session.get('target_questions', 30):
            # Release session questions
            release_session_questions(session_id, session['profile_id'])
            return jsonify({
                'success': True,
                'completed': True,
                'message': 'Assessment completed - all questions answered'
            })
        
        # Get next question with cross-student uniqueness
        question = trained_model.select_next_question(
            session_id,
            answered_questions,
            cross_student_unique=True
        )
        
        if not question:
            # Try to release current session and get alternative
            release_session_questions(session_id, session['profile_id'])
            return jsonify({
                'success': False,
                'error': 'No more unique questions available',
                'suggestion': 'Assessment terminated early due to question pool exhaustion'
            }), 404
        
        # Reserve the new question
        if not reserve_questions_for_session(session_id, session['profile_id'], [question['id']]):
            return jsonify({
                'success': False,
                'error': 'Question already in use by another student',
                'retry': True
            }), 409
        
        return jsonify({
            'success': True,
            'question': question,
            'remaining_questions': session.get('target_questions', 30) - len(answered_questions) - 1,
            'cross_student_unique': True
        })
        
    except Exception as e:
        logger.error(f"Error getting next unique question: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/assessment/status_cross_student', methods=['GET'])
def get_cross_student_uniqueness_status():
    """Get status of cross-student uniqueness system"""
    try:
        available = get_available_questions_for_cross_student_uniqueness()
        allocation_analysis = smart_question_allocation_for_cross_student_uniqueness(30, 30)
        
        active_sessions = sum(1 for s in student_sessions.values() if s.get('cross_student_unique', False))
        
        return jsonify({
            'success': True,
            'system_status': {
                'available_questions': available['total_available'],
                'permanently_used': len(global_question_allocations['permanently_used']),
                'currently_in_use': len(global_question_allocations['in_use']),
                'active_unique_sessions': active_sessions,
                'questions_by_difficulty': {k: len(v) for k, v in available['by_difficulty'].items()},
                'questions_by_topic': {k: len(v) for k, v in available['by_topic'].items()}
            },
            'allocation_analysis': allocation_analysis,
            'recommendations': {
                'max_concurrent_students': available['total_available'] // 30,
                'suggested_questions_per_student': min(30, available['total_available'] // 30) if available['total_available'] >= 30 else available['total_available'],
                'pool_utilization': f"{(len(global_question_allocations['permanently_used']) / len(trained_model.questions)) * 100:.1f}%"
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    mongodb_status = "connected" if students_collection is not None else "disconnected"
    student_stats = get_student_stats() if students_collection is not None else {}
    
    return jsonify({
        'status': 'healthy',
        'model_loaded': trained_model is not None,
        'gemini_ready': bool(os.environ.get('GEMINI_API_KEY')),
        'mongodb_status': mongodb_status,
        'student_stats': student_stats,
        'cross_student_uniqueness': {
            'available_questions': get_available_questions_for_cross_student_uniqueness()['total_available'],
            'permanently_used': len(global_question_allocations['permanently_used']),
            'currently_reserved': len(global_question_allocations['in_use'])
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/assessment/submit_answer_unique', methods=['POST'])
def submit_answer_cross_student_unique():
    """Submit answer for cross-student unique assessment"""
    if not trained_model:
        return jsonify({'success': False, 'error': 'Model not loaded'}), 500
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        question_id = data.get('question_id')
        answer = data.get('answer')
        
        if not all([session_id, question_id, answer]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        if session_id not in student_sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        session = student_sessions[session_id]
        profile_id = session['profile_id']
        
        # Validate question was reserved for this session
        reserved_questions = global_question_allocations.get('reserved_by_session', {}).get(session_id, set())
        if question_id not in reserved_questions:
            return jsonify({'success': False, 'error': 'Question not reserved for this session'}), 400
        
        # Get question details
        question = trained_model.questions.get(question_id)
        if not question:
            return jsonify({'success': False, 'error': 'Question not found'}), 404
        
        # Check answer
        correct_answer = question.get('answer', '').upper()
        user_answer = answer.upper()
        is_correct = user_answer == correct_answer
        
        # Update student ability
        new_ability = trained_model.update_student_ability(session_id, question_id, is_correct)
        
        # Track question usage (this marks it as permanently used)
        track_question_usage(question_id, profile_id)
        
        # Save response to history
        response_data = {
            'session_id': session_id,
            'timestamp': datetime.now().isoformat(),
            'question_id': question_id,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'ability_after': new_ability,
            'cross_student_unique': True
        }
        
        # Update session
        session['responses'].append(response_data)
        session['last_update'] = datetime.now()
        session['ability'] = new_ability
        session['questions_allocated'] += 1
        
        # Save to persistent storage
        hist = _load_history(profile_id)
        hist['responses'].append(response_data)
        _save_history(profile_id, hist)
        
        return jsonify({
            'success': True,
            'is_correct': is_correct,
            'correct_answer': correct_answer,
            'new_ability': new_ability,
            'questions_completed': len(session['responses']),
            'cross_student_unique': True,
            'explanation': question.get('explanation', 'No explanation available')
        })
        
    except Exception as e:
        logger.error(f"Error submitting answer for unique assessment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/students', methods=['GET'])
def get_all_students_endpoint():
    """Get all students data"""
    try:
        students = get_all_students()
        return jsonify({
            'success': True,
            'students': students,
            'total_count': len(students)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/student/<profile_id>', methods=['DELETE'])
def delete_student_endpoint(profile_id):
    """Delete a specific student's data"""
    try:
        success = delete_student_data(profile_id)
        if success:
            return jsonify({'success': True, 'message': f'Student {profile_id} deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Student not found or could not be deleted'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/stats', methods=['GET'])
def get_system_stats():
    """Get overall system statistics"""
    try:
        stats = get_student_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sanitize/prewarm', methods=['POST'])
def admin_prewarm_sanitizer():
    if not trained_model:
        return jsonify({'success': False, 'error': 'Model not loaded'}), 500
    stats = _prewarm_sanitizer_all_questions()
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/admin/sanitize/<qid>', methods=['POST'])
def admin_sanitize_single(qid: str):
    """Question sanitization feature has been disabled"""
    return jsonify({'success': False, 'error': 'Question sanitization feature has been disabled'}), 501

@app.route('/api/model/info', methods=['GET'])
def get_model_info():
    """Get information about the loaded model"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 404
    
    metadata = trained_model.model_data['model_metadata']
    return jsonify({
        'model_info': metadata,
        'total_questions': len(trained_model.questions),
        'total_topics': len(trained_model.topics),
        'questions_with_images': sum(1 for q in trained_model.questions.values() if q.get('has_image')),
        'available_topics': list(trained_model.topics.keys())
    })

@app.route('/api/student/start', methods=['POST'])
def start_assessment():
    """Start a new assessment session for a student"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    student_id = data.get('student_id')
    student_name = data.get('student_name') or data.get('studentName')
    student_grade = data.get('student_grade') or data.get('studentGrade')
    # Optional explicit profile_id to uniquely scope history per authenticated user
    provided_profile_id = data.get('profile_id')
    # Optional: max questions per assessment (default 20, clamp 1..100)
    try:
        max_questions = int(data.get('max_questions', 20))
    except Exception:
        max_questions = 20
    max_questions = max(1, min(100, max_questions))
    
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400
    
    # Initialize student session
    # Use provided profile_id if available; otherwise fall back to name+grade hash
    profile_id = provided_profile_id or _compute_profile_id(student_name or '', student_grade or '')
    student_sessions[student_id] = {
        'ability': trained_model.default_ability,
        'responses': [],
        'ability_history': [trained_model.default_ability],
        'start_time': datetime.now(),
        'last_update': datetime.now(),
        'max_questions': max_questions,
        'student_name': student_name,
        'student_grade': student_grade,
        'profile_id': profile_id
    }
    
    # Get first question
    first_question = trained_model.select_next_question(student_id)
    
    if not first_question:
        return jsonify({'error': 'No questions available'}), 500
    
    # Ensure profile file exists/update basic profile
    hist = _load_history(profile_id)
    hist['profile'] = {
        'name': student_name,
        'grade': student_grade,
        'profile_id': profile_id
    }
    hist.setdefault('sessions', {})
    hist['sessions'][student_id] = {
        'started_at': datetime.now().isoformat(),
        'max_questions': max_questions
    }
    _save_history(profile_id, hist)

    return jsonify({
        'message': 'Assessment started successfully',
        'student_id': student_id,
        'initial_ability': trained_model.default_ability,
        'first_question': first_question,
        'max_questions': max_questions,
        'profile_id': profile_id
    })

@app.route('/api/student/question', methods=['POST'])
def get_next_question():
    """Get the next question for a student"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    student_id = data.get('student_id')
    answered_questions = data.get('answered_questions', [])
    target_topic = data.get('topic')
    target_difficulty = data.get('difficulty')
    
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400
    
    # Enforce per-session question limit
    session = student_sessions.get(student_id, {})
    max_questions = session.get('max_questions', 20)
    answered_count = len(session.get('responses', []))
    if answered_count >= max_questions:
        return jsonify({'error': 'No more questions available (limit reached)'}), 404

    question = trained_model.select_next_question(
        student_id, answered_questions, target_topic, target_difficulty
    )
    
    if not question:
        return jsonify({'error': 'No more questions available'}), 404
    
    return jsonify({
        'question': question,
        'current_ability': trained_model.get_student_ability(student_id)
    })

@app.route('/api/student/submit', methods=['POST'])
def submit_answer():
    """Submit an answer and get feedback with enhanced struggle detection"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    student_id = data.get('student_id')
    question_id = data.get('question_id')
    student_answer = data.get('answer')
    
    if not all([student_id, question_id, student_answer]):
        return jsonify({'error': 'student_id, question_id, and answer are required'}), 400
    
    # Get the correct answer
    if question_id not in trained_model.questions:
        return jsonify({'error': 'Question not found'}), 404
    
    correct_answer = trained_model.questions[question_id]['answer']
    is_correct = student_answer.upper() == correct_answer.upper()
    
    # Update student ability with enhanced tracking
    new_ability = trained_model.update_student_ability(student_id, question_id, is_correct)
    
    # Prepare comprehensive progress data for frontend
    session = student_sessions.get(student_id, {})
    responses = session.get('responses', [])
    answered_count = len(responses)
    
    # Calculate current score
    correct_count = sum(1 for r in responses if r.get('response', False))
    current_score = round((correct_count / answered_count * 100)) if answered_count > 0 else 0
    
    # Calculate knowledge level
    if answered_count >= 3:
        recent_correct = sum(1 for r in responses[-3:] if r.get('response', False))
        recent_performance = recent_correct / min(3, len(responses[-3:]))
        overall_performance = correct_count / answered_count
        knowledge_level = 0.6 * recent_performance + 0.4 * overall_performance
    else:
        knowledge_level = correct_count / answered_count if answered_count > 0 else 0
    
    # Enhanced streak calculation
    consecutive_correct = session.get('consecutive_correct', 0)
    consecutive_incorrect = session.get('consecutive_wrong', 0)
    
    updated_progress = {
        'questions_answered': answered_count,
        'ability_estimate': new_ability,
        'predicted_success_probability': 0.5 + (new_ability / 6),
        'current_score': current_score,
        'knowledge_level': knowledge_level,
        'consecutive_correct': consecutive_correct,
        'consecutive_incorrect': consecutive_incorrect,
        'struggling': session.get('struggle_detected', False)
    }
    
    # Enhanced adaptation info
    current_difficulty = trained_model.get_adaptive_optimal_difficulty(student_id, new_ability)
    adaptation_info = {
        'new_ability': new_ability,
        'difficulty_change': current_difficulty,
        'current_difficulty': current_difficulty,
        'next_difficulty_hint': current_difficulty,
        'struggle_detected': session.get('struggle_detected', False)
    }
    
    # Generate enhanced feedback
    base_feedback = 'Correct! Well done!' if is_correct else f'Incorrect. The correct answer was {correct_answer}.'
    
    # Add struggle-specific feedback if needed
    struggle_feedback = trained_model.get_struggle_feedback(student_id)
    if struggle_feedback.get('struggling'):
        enhanced_feedback = {
            'basic_feedback': base_feedback,
            'struggle_detected': True,
            'encouragement': struggle_feedback.get('encouragement', ''),
            'recommendations': struggle_feedback.get('recommendations', []),
            'next_steps': struggle_feedback.get('next_steps', []),
            'consecutive_wrong': struggle_feedback.get('consecutive_wrong', 0)
        }
    else:
        enhanced_feedback = {
            'basic_feedback': base_feedback,
            'struggle_detected': False
        }
    
    # Record to history
    try:
        profile_id = session.get('profile_id')
        if profile_id:
            # Track question usage when answer is submitted (not when selected)
            track_question_usage(question_id, profile_id)
            
            hist = _load_history(profile_id)
            hist.setdefault('responses', [])
            q = trained_model.questions.get(question_id, {})
            hist['responses'].append({
                'session_id': student_id,
                'timestamp': datetime.now().isoformat(),
                'question_id': question_id,
                'topic': q.get('topic'),
                'difficulty': q.get('difficulty'),
                'is_correct': is_correct,
                'ability_after': new_ability,
                'struggle_detected': session.get('struggle_detected', False)
            })
            # update sessions meta
            hist.setdefault('sessions', {})
            sess_meta = hist['sessions'].get(student_id, {})
            sess_meta['last_activity'] = datetime.now().isoformat()
            sess_meta['answered'] = (sess_meta.get('answered', 0) or 0) + 1
            hist['sessions'][student_id] = sess_meta
            _save_history(profile_id, hist)
    except Exception as e:
        logger.error(f"Failed to record history: {e}")

    return jsonify({
        'is_correct': is_correct,
        'correct_answer': correct_answer,
        'new_ability': new_ability,
        'feedback': enhanced_feedback,
        'updated_progress': updated_progress,
        'adaptation_info': adaptation_info
    })

@app.route('/api/student/summary', methods=['GET'])
def get_student_summary():
    """Get comprehensive assessment summary for a student"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    student_id = request.args.get('student_id')
    
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400
    
    summary = trained_model.get_assessment_summary(student_id)
    
    return jsonify(summary)

@app.route('/api/student/struggle-support', methods=['GET'])
def get_struggle_support():
    """Get specialized support and guidance for struggling students"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    student_id = request.args.get('student_id')
    
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400
    
    if student_id not in student_sessions:
        return jsonify({'error': 'Student session not found'}), 404
    
    # Get struggle-specific feedback
    struggle_feedback = trained_model.get_struggle_feedback(student_id)
    
    # Add additional support resources
    session = student_sessions[student_id]
    responses = session.get('responses', [])
    
    if struggle_feedback.get('struggling'):
        # Analyze recent question types for targeted help
        recent_questions = responses[-5:] if len(responses) >= 5 else responses
        topics_struggled = []
        difficulties_struggled = []
        
        for response in recent_questions:
            if not response.get('response', False):  # Wrong answer
                question_id = response.get('question_id')
                if question_id in trained_model.questions:
                    q = trained_model.questions[question_id]
                    topics_struggled.append(q.get('topic'))
                    difficulties_struggled.append(q.get('difficulty'))
        
        # Count most problematic areas
        from collections import Counter
        topic_issues = Counter(topics_struggled)
        difficulty_issues = Counter(difficulties_struggled)
        
        struggle_feedback['problem_analysis'] = {
            'most_challenging_topics': topic_issues.most_common(3),
            'most_challenging_difficulties': difficulty_issues.most_common(3),
            'total_recent_questions': len(recent_questions),
            'recent_wrong_answers': len([r for r in recent_questions if not r.get('response', False)])
        }
        
        # Generate targeted practice recommendations
        struggle_feedback['practice_suggestions'] = []
        
        if topic_issues:
            top_problem_topic = topic_issues.most_common(1)[0][0]
            struggle_feedback['practice_suggestions'].append(
                f"Focus extra practice on {top_problem_topic} - this seems to be your biggest challenge right now"
            )
        
        if 'Very Easy' not in difficulty_issues and session.get('consecutive_wrong', 0) >= 3:
            struggle_feedback['practice_suggestions'].append(
                "Start with Very Easy questions to rebuild confidence before moving up"
            )
        
        struggle_feedback['practice_suggestions'].append(
            "Take breaks between questions to avoid mental fatigue"
        )
        
        # Study strategy recommendations
        struggle_feedback['study_strategies'] = [
            "Review basic concepts before attempting new questions",
            "Work through each question step-by-step, don't rush",
            "Keep notes of topics you find challenging", 
            "Practice a few questions daily rather than many at once",
            "Ask for help when you're stuck - that's how we learn!"
        ]
        
    return jsonify({
        'success': True,
        'student_id': student_id,
        'support': struggle_feedback,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/student/diagnosis', methods=['GET'])
def get_student_diagnosis():
    """Aggregate strengths and weaknesses across sessions for a student profile.
    Expects either profile_id, or student_name and student_grade.
    """
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500

    profile_id = request.args.get('profile_id')
    name = request.args.get('student_name') or request.args.get('studentName')
    grade = request.args.get('student_grade') or request.args.get('studentGrade')
    if not profile_id:
        if not (name and grade):
            return jsonify({'error': 'profile_id or (student_name and student_grade) required'}), 400
        profile_id = _compute_profile_id(name, grade)

    hist = _load_history(profile_id)
    responses = hist.get('responses', [])
    # Include current live session responses if any
    live_sessions = [s for s in student_sessions.values() if s.get('profile_id') == profile_id]
    for sess in live_sessions:
        for r in sess.get('responses', []):
            qid = r.get('question_id')
            q = trained_model.questions.get(qid, {})
            responses.append({
                'session_id': 'live',
                'timestamp': r.get('timestamp', datetime.now().isoformat()),
                'question_id': qid,
                'topic': q.get('topic'),
                'difficulty': q.get('difficulty'),
                'is_correct': r.get('response', False),
                'ability_after': sess.get('ability')
            })

    # Aggregate per-topic and per-difficulty
    topic_stats = {}
    diff_stats = {}
    ability_trend = []
    sessions_trend = {}

    for r in responses:
        topic = r.get('topic') or 'Unknown'
        diff = r.get('difficulty') or 'Unknown'
        is_correct = bool(r.get('is_correct'))
        ability_after = r.get('ability_after')
        session_id = r.get('session_id', 'unknown')

        s = topic_stats.setdefault(topic, {'correct': 0, 'total': 0})
        s['total'] += 1
        s['correct'] += 1 if is_correct else 0

        d = diff_stats.setdefault(diff, {'correct': 0, 'total': 0})
        d['total'] += 1
        d['correct'] += 1 if is_correct else 0

        if ability_after is not None:
            ability_trend.append({'t': r.get('timestamp'), 'ability': ability_after})

        sess = sessions_trend.setdefault(session_id, {'correct': 0, 'total': 0})
        sess['total'] += 1
        sess['correct'] += 1 if is_correct else 0

    # Prepare output
    def _rate(obj):
        out = {}
        for k, v in obj.items():
            acc = round((v['correct'] / v['total'] * 100), 1) if v['total'] else 0.0
            out[k] = {**v, 'accuracy': acc}
        return out

    result = {
        'profile': hist.get('profile', {'profile_id': profile_id}),
        'per_topic': _rate(topic_stats),
        'per_difficulty': _rate(diff_stats),
        'ability_trend': ability_trend,
        'sessions_trend': {k: {**v, 'accuracy': round((v['correct']/v['total']*100),1) if v['total'] else 0.0} for k, v in sessions_trend.items()},
        'total_responses': len(responses),
        'overall_accuracy': round(sum(topic_stats[k]['correct'] for k in topic_stats) / sum(topic_stats[k]['total'] for k in topic_stats) * 100, 1) if any(topic_stats[k]['total'] > 0 for k in topic_stats) else 0.0,
        'current_ability': ability_trend[-1]['ability'] if ability_trend else 0.0
    }

    return jsonify({'success': True, 'diagnosis': result})

@app.route('/api/image/<image_id>', methods=['GET'])
def serve_image(image_id):
    """Serve question images with improved mapping"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    logger.info(f"Looking for image: {image_id}")
    
    # First try the trained model's image mappings
    if image_id in trained_model.image_mappings:
        image_info = trained_model.image_mappings[image_id]
        image_path = Path(image_info['full_path'])
        
        logger.info(f"Found in mappings: {image_path}")
        
        if image_path.exists():
            mime_type, _ = mimetypes.guess_type(str(image_path))
            if not mime_type:
                mime_type = 'image/png'
            
            try:
                logger.info(f"SUCCESS: Serving mapped image: {image_path}")
                return send_file(str(image_path), mimetype=mime_type)
            except Exception as e:
                logger.error(f"Error serving mapped image {image_id}: {e}")
    
    # Extract question number from image_id
    question_num = None
    if image_id.startswith('img_'):
        try:
            question_num = image_id.replace('img_', '')
            logger.info(f"Extracted question number: {question_num}")
        except:
            logger.error(f"Could not extract question number from {image_id}")
            return jsonify({'error': 'Invalid image ID format'}), 400
    
    # Build comprehensive list of possible image paths for this question
    possible_image_paths = []
    
    if question_num:
        # Primary paths based on question number
        base_paths = [
            f"data/Geometry/Moderate_hard/Geometry(Moderate+Difficult)/Q{question_num}.png",
            f"data/Geometry/Easy_veryeasy/Geometry(easy+very easy)/Q{question_num}.png",
            f"data/Geometry/Coordinate Geometry/Q{question_num}.png",
        ]
        
        # Add variations for compound questions (Q32&33, Q47&Q48, etc.)
        compound_variations = [
            f"data/Geometry/Moderate_hard/Geometry(Moderate+Difficult)/Q{question_num}&{int(question_num)+1}.png",
            f"data/Geometry/Moderate_hard/Geometry(Moderate+Difficult)/Q{int(question_num)-1}&{question_num}.png",
            f"data/Geometry/Easy_veryeasy/Geometry(easy+very easy)/Q{question_num}&{int(question_num)+1}.png",
            f"data/Geometry/Easy_veryeasy/Geometry(easy+very easy)/Q{int(question_num)-1}&{question_num}.png",
        ]
        
        possible_image_paths.extend(base_paths)
        
        # Only add compound variations if question_num is numeric
        try:
            int(question_num)
            possible_image_paths.extend(compound_variations)
        except ValueError:
            pass
    
    # Try each possible path
    for path_str in possible_image_paths:
        image_path = Path(path_str)
        logger.info(f"Trying path: {image_path}")
        
        if image_path.exists():
            mime_type, _ = mimetypes.guess_type(str(image_path))
            if not mime_type:
                mime_type = 'image/png'
            
            try:
                logger.info(f"SUCCESS: Found and serving image: {image_path}")
                return send_file(str(image_path), mimetype=mime_type)
            except Exception as e:
                logger.error(f"Error serving image from {image_path}: {e}")
                continue
    
    # If still not found, search the questions in the model for this specific question
    if hasattr(trained_model, 'adaptive_engine') and trained_model.adaptive_engine:
        for qid, question in trained_model.adaptive_engine.questions.items():
            question_id_from_model = str(question.get('id', ''))
            
            if question_id_from_model == question_num:
                logger.info(f"Found question {qid} matching ID {question_num}")
                
                # Check if question has specific image information
                image_path_str = question.get('image_path')
                if image_path_str and image_path_str != 'None':
                    image_path = Path(image_path_str)
                    logger.info(f"Question specifies image path: {image_path}")
                    
                    if image_path.exists():
                        mime_type, _ = mimetypes.guess_type(str(image_path))
                        if not mime_type:
                            mime_type = 'image/png'
                        
                        try:
                            logger.info(f"SUCCESS: Serving image from question metadata: {image_path}")
                            return send_file(str(image_path), mimetype=mime_type)
                        except Exception as e:
                            logger.error(f"Error serving image from question metadata: {e}")
                
                break
    
    # If we reach here, the image was not found
    logger.error(f"Image not found for {image_id} (question {question_num})")
    logger.error(f"Searched paths: {possible_image_paths}")
    
    # DO NOT serve any fallback test image - return proper 404
    return jsonify({
        'error': 'Image not found', 
        'image_id': image_id,
        'searched_paths': possible_image_paths
    }), 404

@app.route('/api/topics', methods=['GET'])
def get_topics():
    """Get all available topics and their statistics"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    return jsonify({
        'topics': trained_model.topics
    })

@app.route('/api/questions/search', methods=['POST'])
def search_questions():
    """Search questions by criteria"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    topic = data.get('topic')
    difficulty = data.get('difficulty')
    has_image = data.get('has_image')
    limit = data.get('limit', 10)
    
    questions = list(trained_model.questions.values())
    
    # Apply filters
    if topic:
        questions = [q for q in questions if q['topic'].lower() == topic.lower()]
    
    if difficulty:
        questions = [q for q in questions if q['difficulty'].lower() == difficulty.lower()]
    
    if has_image is not None:
        questions = [q for q in questions if q.get('has_image') == has_image]
    
    # Limit results
    questions = questions[:limit]
    
    # Prepare questions for serving
    prepared_questions = [
        trained_model.prepare_question_for_serving(q) for q in questions
    ]
    
    return jsonify({
        'questions': prepared_questions,
        'total_found': len(prepared_questions)
    })

# ==============================================
# FRONTEND COMPATIBILITY ENDPOINTS
# ==============================================
# These endpoints maintain compatibility with the existing frontend

@app.route('/api/start-assessment', methods=['POST'])
def start_assessment_compatible():
    """Frontend-compatible start assessment endpoint"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    # Extract name and grade from frontend
    student_name = data.get('studentName', 'Unknown')
    student_grade = data.get('studentGrade', 'Unknown')
    
    # Create unique student ID
    student_id = f"{student_name}_{student_grade}_{int(datetime.now().timestamp() * 1000)}"
    
    # Initialize student session
    student_sessions[student_id] = {
        'ability': trained_model.default_ability,
        'responses': [],
        'ability_history': [trained_model.default_ability],
        'answered_questions': [],  # Track answered questions to avoid repetition (using list instead of set)
        'start_time': datetime.now(),
        'last_update': datetime.now(),
        'name': student_name,
        'grade': student_grade
    }
    
    # Get first question
    first_question = trained_model.select_next_question(student_id)
    
    if not first_question:
        return jsonify({'error': 'No questions available'}), 500
    
    return jsonify({
        'success': True,
        'session_id': student_id,
        'starting_difficulty': 'Very Easy',
        'message': 'Assessment started successfully'
    })

@app.route('/api/get-question', methods=['POST'])
def get_question_compatible():
    """Frontend-compatible get question endpoint"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id is required'}), 400
    
    if session_id not in student_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    # Get answered questions from both responses and tracking list
    session = student_sessions[session_id]
    answered_from_responses = [r['question_id'] for r in session.get('responses', [])]
    answered_from_list = session.get('answered_questions', [])
    answered_questions = list(set(answered_from_responses + answered_from_list))  # Combine and deduplicate
    
    # Check if assessment should complete (e.g., after 20 questions)
    if len(answered_questions) >= 20:
        return jsonify({
            'success': False,
            'assessment_complete': True,
            'message': 'Assessment completed'
        })
    
    # Get next question
    question = trained_model.select_next_question(session_id, answered_questions)
    
    if not question:
        return jsonify({
            'success': False,
            'assessment_complete': True,
            'message': 'No more questions available'
        })
    
    # Convert to frontend format
    frontend_question = {
        'id': question['id'],
        'question_text': question['text'],
        'option_a': question['options'].get('A', ''),
        'option_b': question['options'].get('B', ''),
        'option_c': question['options'].get('C', ''),
        'option_d': question['options'].get('D', ''),
        'answer': question['answer'].lower(),
        'difficulty': question['difficulty'],
        'topic': question.get('topic', 'General'),
        'image_path': question.get('image_path'),
        'has_image': question.get('has_image', False)
    }
    
    # Create comprehensive progress info
    current_ability = session['ability']
    responses = session.get('responses', [])
    answered_count = len(answered_questions)
    
    # Calculate current score
    correct_count = sum(1 for r in responses if r.get('response', False))
    current_score = round((correct_count / answered_count * 100)) if answered_count > 0 else 0
    
    # Calculate knowledge level
    if answered_count >= 3:
        recent_correct = sum(1 for r in responses[-3:] if r.get('response', False))
        recent_performance = recent_correct / min(3, len(responses[-3:]))
        overall_performance = correct_count / answered_count
        knowledge_level = 0.6 * recent_performance + 0.4 * overall_performance
    else:
        knowledge_level = correct_count / answered_count if answered_count > 0 else 0
    
    # Calculate streaks
    consecutive_correct = 0
    consecutive_incorrect = 0
    
    for r in reversed(responses):
        if r.get('response', False):
            if consecutive_incorrect == 0:
                consecutive_correct += 1
            else:
                break
        else:
            if consecutive_correct == 0:
                consecutive_incorrect += 1
            else:
                break
    
    progress = {
        'questions_answered': answered_count,
        'predicted_success_probability': 0.5 + (current_ability / 6),  # Normalize to 0-1
        'current_difficulty': question['difficulty'],
        'ability_estimate': current_ability,
        'current_score': current_score,
        'knowledge_level': knowledge_level,
        'consecutive_correct': consecutive_correct,
        'consecutive_incorrect': consecutive_incorrect
    }
    
    return jsonify({
        'success': True,
        'question': frontend_question,
        'student_progress': progress
    })

@app.route('/api/submit-response', methods=['POST'])
def submit_response_compatible():
    """Frontend-compatible submit response endpoint"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    selected_option = data.get('selected_option')
    is_correct = data.get('is_correct')
    
    if not all([session_id, question_id, selected_option is not None]):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    if session_id not in student_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    # Convert selected option to match our format
    if selected_option in ['a', 'b', 'c', 'd']:
        selected_option = selected_option.upper()
    
    # Get correct answer and validate
    question = trained_model.questions.get(question_id)
    if not question:
        return jsonify({'success': False, 'error': 'Question not found'}), 404
    
    correct_answer = question['answer']
    actual_is_correct = selected_option == correct_answer
    
    # Update student ability
    new_ability = trained_model.update_student_ability(session_id, question_id, actual_is_correct)
    
    # Prepare response with comprehensive progress data
    session = student_sessions[session_id]
    responses = session.get('responses', [])
    answered_count = len(responses)
    
    feedback_text = "Correct! Well done." if actual_is_correct else f"Incorrect. The correct answer was {correct_answer}."
    
    # Calculate current score
    correct_count = sum(1 for r in responses if r.get('response', False))
    current_score = round((correct_count / answered_count * 100)) if answered_count > 0 else 0
    
    # Calculate knowledge level (recent performance weighted)
    if answered_count >= 3:
        recent_correct = sum(1 for r in responses[-3:] if r.get('response', False))
        recent_performance = recent_correct / min(3, len(responses[-3:]))
        overall_performance = correct_count / answered_count
        knowledge_level = 0.6 * recent_performance + 0.4 * overall_performance
    else:
        knowledge_level = correct_count / answered_count if answered_count > 0 else 0
    
    # Calculate streaks
    consecutive_correct = 0
    consecutive_incorrect = 0
    
    # Count current streak from the end
    for r in reversed(responses):
        if r.get('response', False):
            if consecutive_incorrect == 0:  # Still in correct streak
                consecutive_correct += 1
            else:
                break
        else:
            if consecutive_correct == 0:  # Still in incorrect streak
                consecutive_incorrect += 1
            else:
                break
    
    progress = {
        'questions_answered': answered_count,
        'ability_estimate': new_ability,
        'predicted_success_probability': 0.5 + (new_ability / 6),
        'current_score': current_score,
        'knowledge_level': knowledge_level,
        'consecutive_correct': consecutive_correct,
        'consecutive_incorrect': consecutive_incorrect
    }
    
    adaptation_info = {
        'new_ability': new_ability,
        'difficulty_change': trained_model.get_optimal_difficulty_for_ability(new_ability)
    }
    
    return jsonify({
        'success': True,
        'is_correct': actual_is_correct,
        'correct_answer': correct_answer,
        'feedback': feedback_text,
        'updated_progress': progress,
        'adaptation_info': adaptation_info
    })

@app.route('/api/get-assessment-results', methods=['POST'])
def get_assessment_results_compatible():
    """Frontend-compatible get results endpoint"""
    if not trained_model:
        return jsonify({'error': 'Model not loaded'}), 500
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id or session_id not in student_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    # Get assessment summary from our enhanced system
    try:
        summary_response = get_student_summary()
        if hasattr(summary_response, 'get_json'):
            summary = summary_response.get_json()
        else:
            summary = summary_response
        
        session = student_sessions[session_id]
        responses = session.get('responses', [])
        
        # Calculate statistics
        total_questions = len(responses)
        correct_answers = sum(1 for r in responses if r.get('response', False))
        accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # Prepare results in frontend format
        results = {
            'success': True,
            'student_name': session.get('name', 'Student'),
            'student_grade': session.get('grade', 'Unknown'),
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'accuracy_percentage': round(accuracy, 1),
            'final_ability': session['ability'],
            'ability_level': trained_model.get_optimal_difficulty_for_ability(session['ability']),
            'time_taken': str(datetime.now() - session['start_time']).split('.')[0],
            'detailed_performance': summary if 'error' not in summary else {}
        }
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error generating assessment results: {e}")
        # Fallback response
        session = student_sessions[session_id]
        responses = session.get('responses', [])
        total_questions = len(responses)
        correct_answers = sum(1 for r in responses if r.get('response', False))
        
        return jsonify({
            'success': True,
            'student_name': session.get('name', 'Student'),
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'accuracy_percentage': round((correct_answers / max(total_questions, 1)) * 100, 1),
            'final_ability': session['ability'],
            'time_taken': str(datetime.now() - session['start_time']).split('.')[0]
        })


@app.route('/api/train-model', methods=['POST'])
def train_model_endpoint():
    """Endpoint to retrain the adaptive assessment model"""
    try:
        logger.info("Starting model training...")
        
        # Import training functionality
        import sys
        import importlib.util
        
        # Load the trainer module
        spec = importlib.util.spec_from_file_location("trainer", "train_adaptive_model.py")
        trainer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(trainer_module)
        
        # Create trainer instance and train
        trainer = trainer_module.AdaptiveAssessmentTrainer()
        model_data = trainer.train_model()
        trainer.save_model('trained_adaptive_assessment_model.json')
        
        # Reload the trained model in the server
        global trained_model
        if load_trained_model():
            logger.info("Model retrained and reloaded successfully!")
            return jsonify({
                'success': True,
                'message': 'Model trained and reloaded successfully',
                'questions_count': len(model_data.get('questions', [])),
                'topics_count': len(model_data.get('topics', {})),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Training completed but failed to reload model'
            }), 500
            
    except Exception as e:
        logger.error(f"Training failed: {e}")
        return jsonify({
            'success': False,
            'error': f'Training failed: {str(e)}'
        }), 500

@app.route('/api/admin/question-usage-stats', methods=['GET'])
def get_question_usage_stats():
    """Get question usage statistics for monitoring duplicate prevention"""
    try:
        stats = get_question_usage_stats()
        
        # Add additional insights
        if trained_model:
            total_questions_in_pool = len(trained_model.questions)
            stats['total_questions_in_pool'] = total_questions_in_pool
            stats['unused_questions'] = total_questions_in_pool - stats['total_questions_used']
            stats['usage_efficiency'] = (stats['total_questions_used'] / total_questions_in_pool * 100) if total_questions_in_pool > 0 else 0
        
        # Get profile-wise statistics
        profile_stats = {}
        for question_id, usage in question_usage_log.items():
            for profile_id in usage['profiles']:
                if profile_id not in profile_stats:
                    profile_stats[profile_id] = {'questions_answered': 0, 'last_activity': None}
                profile_stats[profile_id]['questions_answered'] += 1
                if not profile_stats[profile_id]['last_activity'] or usage['last_used'] > profile_stats[profile_id]['last_activity']:
                    profile_stats[profile_id]['last_activity'] = usage['last_used']
        
        stats['profile_statistics'] = {
            'total_active_profiles': len(profile_stats),
            'average_questions_per_profile': sum(p['questions_answered'] for p in profile_stats.values()) / len(profile_stats) if profile_stats else 0,
            'top_profiles_by_activity': sorted(
                [(pid, pstats) for pid, pstats in profile_stats.items()],
                key=lambda x: x[1]['questions_answered'],
                reverse=True
            )[:10]
        }
        
        return jsonify({
            'success': True,
            'statistics': stats,
            'timestamp': datetime.now().isoformat(),
            'message': f"Question usage tracked across {len(question_usage_log)} questions and {len(profile_stats)} profiles"
        })
        
    except Exception as e:
        logger.error(f"Error getting question usage stats: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to get usage statistics: {str(e)}'
        }), 500

@app.route('/api/admin/validate-question-pool', methods=['GET'])
def validate_question_pool():
    """Validate question pool for potential duplicates and issues"""
    try:
        if not trained_model:
            return jsonify({'error': 'Model not loaded'}), 500
        
        validation_results = {
            'total_questions': len(trained_model.questions),
            'duplicate_content': [],
            'missing_fields': [],
            'question_distribution': {},
            'recommendations': []
        }
        
        # Check for potential content duplicates (similar text)
        questions_list = list(trained_model.questions.values())
        for i, q1 in enumerate(questions_list):
            for j, q2 in enumerate(questions_list[i+1:], i+1):
                # Simple text similarity check
                q1_text = q1.get('text', '').lower().strip()
                q2_text = q2.get('text', '').lower().strip()
                if q1_text and q2_text and q1_text == q2_text:
                    validation_results['duplicate_content'].append({
                        'question_1': q1['id'],
                        'question_2': q2['id'],
                        'text': q1_text[:100] + '...' if len(q1_text) > 100 else q1_text
                    })
        
        # Check for missing required fields
        required_fields = ['id', 'text', 'options', 'answer', 'topic', 'difficulty']
        for q in questions_list:
            missing = [field for field in required_fields if not q.get(field)]
            if missing:
                validation_results['missing_fields'].append({
                    'question_id': q.get('id', 'unknown'),
                    'missing_fields': missing
                })
        
        # Analyze question distribution
        for q in questions_list:
            topic = q.get('topic', 'Unknown')
            difficulty = q.get('difficulty', 'Unknown')
            
            if topic not in validation_results['question_distribution']:
                validation_results['question_distribution'][topic] = {}
            if difficulty not in validation_results['question_distribution'][topic]:
                validation_results['question_distribution'][topic][difficulty] = 0
            validation_results['question_distribution'][topic][difficulty] += 1
        
        # Generate recommendations
        if validation_results['duplicate_content']:
            validation_results['recommendations'].append(f"Found {len(validation_results['duplicate_content'])} potential duplicate questions - review and remove duplicates")
        
        if validation_results['missing_fields']:
            validation_results['recommendations'].append(f"Found {len(validation_results['missing_fields'])} questions with missing fields - complete question data")
        
        # Check distribution balance
        for topic, difficulties in validation_results['question_distribution'].items():
            total_in_topic = sum(difficulties.values())
            if total_in_topic < 20:
                validation_results['recommendations'].append(f"Topic '{topic}' has only {total_in_topic} questions - consider adding more")
        
        if not validation_results['recommendations']:
            validation_results['recommendations'].append("Question pool looks good! No major issues detected.")
        
        return jsonify({
            'success': True,
            'validation': validation_results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error validating question pool: {e}")
        return jsonify({
            'success': False,
            'error': f'Validation failed: {str(e)}'
        }), 500


if __name__ == '__main__':
    # Load the trained model on startup
    _load_env_from_dotenv()
    if load_trained_model():
        # Load question usage history to prevent duplicates
        load_question_usage_from_history()
        logger.info("Starting adaptive assessment API server...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        logger.error("Failed to load model. Please run train_adaptive_model.py first.")
        print("Please run: python train_adaptive_model.py")