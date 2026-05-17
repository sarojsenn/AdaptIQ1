import json
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional
import base64

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdaptiveAssessmentTrainer:
    """
    Comprehensive trainer for adaptive assessment model using all datasets
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.questions_data = []
        self.model_data = {
            "questions": [],
            "topics": {},
            "difficulty_levels": {},
            "question_parameters": {},
            "model_metadata": {},
            "image_mappings": {}
        }
        
    def load_all_datasets(self) -> List[Dict]:
        """Load all JSON datasets from the data directory and expanded dataset"""
        logger.info("Loading all datasets...")
        
        # First check if we have expanded dataset
        expanded_dataset_path = Path('expanded_questions_dataset.json')
        if expanded_dataset_path.exists():
            logger.info("Loading expanded dataset with 2000+ questions...")
            try:
                with open(expanded_dataset_path, 'r', encoding='utf-8') as f:
                    expanded_data = json.load(f)
                    self.questions_data = expanded_data['questions']
                    logger.info(f"Loaded {len(self.questions_data)} questions from expanded dataset")
                    return self.questions_data
            except Exception as e:
                logger.error(f"Error loading expanded dataset: {e}")
                logger.info("Falling back to loading individual datasets...")
        
        # Original loading code as fallback
        # Define all dataset files
        dataset_files = [
            "Block1Arithmetic.json",
            "Block3Probability.json",
            "Block5Algebra.json",
            "BLOCK_2_NumberSystem_Arranged.json",
            "BLOCK_6_LogicalReasoning.json", 
            "BLOCK_7_VARC.json",
            "questions.json"
        ]
        
        # Add Block3ModernMath.json separately with special handling
        special_files = ["Block3ModernMath.json"]
        
        # Load main dataset files
        for file_name in dataset_files:
            file_path = self.data_dir / file_name
            if file_path.exists():
                try:
                    # Try different encodings
                    data = None
                    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                data = json.load(f)
                                break
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                    
                    if data is None:
                        logger.error(f"Could not decode {file_name} with any encoding")
                        continue
                    
                    # Handle different data structures
                    questions = self._extract_questions_from_data(data, file_name)
                    if questions:
                        self.questions_data.extend(questions)
                        logger.info(f"Loaded {len(questions)} questions from {file_name}")
                    else:
                        logger.warning(f"No questions found in {file_name}")
                        
                except Exception as e:
                    logger.error(f"Error loading {file_name}: {e}")
                    # Try to read as text and check first few lines
                    try:
                        with open(file_path, 'r', encoding='utf-8-sig') as f:
                            first_line = f.readline().strip()
                            if first_line.startswith('{'):
                                logger.info(f"Retrying {file_name} with BOM handling...")
                                f.seek(0)
                                data = json.load(f)
                                questions = self._extract_questions_from_data(data, file_name)
                                if questions:
                                    self.questions_data.extend(questions)
                                    logger.info(f"Successfully loaded {len(questions)} questions from {file_name}")
                    except Exception as e2:
                        logger.error(f"Final attempt failed for {file_name}: {e2}")
                        continue
        
        # Handle special files with different approach
        for file_name in special_files:
            file_path = self.data_dir / file_name
            if file_path.exists():
                try:
                    # Force read with utf-8-sig to handle BOM
                    with open(file_path, 'r', encoding='utf-8-sig') as f:
                        content = f.read()
                        # Remove any BOM characters
                        content = content.replace('\ufeff', '')
                        data = json.loads(content)
                        
                    questions = self._extract_questions_from_data(data, file_name)
                    if questions:
                        self.questions_data.extend(questions)
                        logger.info(f"Loaded {len(questions)} questions from {file_name} (special handling)")
                    else:
                        logger.warning(f"No questions found in {file_name}")
                        
                except Exception as e:
                    logger.error(f"Error loading {file_name} with special handling: {e}")
        
        # Load geometry datasets recursively
        geometry_dir = self.data_dir / "Geometry"
        if geometry_dir.exists():
            self._load_geometry_datasets(geometry_dir)
            
        logger.info(f"Total questions loaded: {len(self.questions_data)}")
        return self.questions_data
    
    def _load_geometry_datasets(self, geometry_dir: Path):
        """Load all geometry datasets including those with images"""
        for root, dirs, files in os.walk(geometry_dir):
            for file in files:
                if file.endswith('.json'):
                    file_path = Path(root) / file
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                # Process questions with potential image references
                                processed_data = self._process_questions_with_images(data, Path(root))
                                self.questions_data.extend(processed_data)
                                logger.info(f"Loaded {len(processed_data)} questions from {file_path}")
                    except Exception as e:
                        logger.error(f"Error loading {file_path}: {e}")
    
    def _process_questions_with_images(self, questions: List[Dict], base_path: Path) -> List[Dict]:
        """Process questions and handle image references"""
        processed_questions = []
        
        for question in questions:
            # Create a copy to avoid modifying original
            processed_question = question.copy()
            
            # Handle image field
            if 'image' in question and question['image']:
                image_path = question['image']
                
                # Handle relative image paths
                if not os.path.isabs(image_path):
                    full_image_path = base_path / image_path
                else:
                    full_image_path = Path(image_path)
                
                # Check if image exists
                if full_image_path.exists():
                    processed_question['image_path'] = str(full_image_path)
                    processed_question['has_image'] = True
                    
                    # Create image_id based on question ID for proper mapping
                    question_id = processed_question.get('id', processed_question.get('question_id', 'unknown'))
                    image_id = f"img_{question_id}"
                    
                    # Store image mapping for serving
                    self.model_data['image_mappings'][image_id] = {
                        'original_path': image_path,
                        'full_path': str(full_image_path),
                        'question_id': question_id
                    }
                    processed_question['image_id'] = image_id
                    
                    logger.info(f"Found image for question {question_id}: {image_path} -> {image_id}")
                else:
                    logger.warning(f"Image not found: {full_image_path}")
                    processed_question['has_image'] = False
            else:
                processed_question['has_image'] = False
            
            processed_questions.append(processed_question)
        
        return processed_questions
    
    def _extract_questions_from_data(self, data: Any, filename: str) -> List[Dict]:
        """Extract questions from different JSON data structures"""
        questions = []
        
        try:
            if isinstance(data, list):
                # Direct list of questions (Block1Arithmetic.json format)
                questions = data
                
            elif isinstance(data, dict):
                if 'questions' in data:
                    # Format with questions array (Block3ModernMath.json, etc.)
                    questions_array = data['questions']
                    
                    # Process each question and normalize structure
                    for q in questions_array:
                        normalized_q = self._normalize_block_question(q, data)
                        if normalized_q:
                            questions.append(normalized_q)
                            
                elif 'block_info' in data and 'questions' in data:
                    # Format with block_info (BLOCK_2_NumberSystem_Arranged.json)
                    questions_array = data['questions']
                    block_info = data['block_info']
                    
                    for q in questions_array:
                        normalized_q = self._normalize_block_question(q, block_info)
                        if normalized_q:
                            questions.append(normalized_q)
                            
                else:
                    logger.warning(f"Unknown data structure in {filename}")
                    
        except Exception as e:
            logger.error(f"Error extracting questions from {filename}: {e}")
            
        return questions
    
    def _normalize_block_question(self, question: Dict, context: Dict) -> Optional[Dict]:
        """Normalize questions from block datasets to unified format"""
        try:
            # Extract basic info
            question_id = question.get('id', 'unknown')
            question_text = question.get('question_text', '').strip()
            
            if not question_text:
                return None
            
            # Extract options from array format
            options_dict = {}
            if 'options' in question and isinstance(question['options'], list):
                for opt in question['options']:
                    if isinstance(opt, dict) and 'option' in opt and 'text' in opt:
                        options_dict[opt['option']] = opt['text']
            
            # Extract correct answer
            correct_answer = question.get('correct_answer', question.get('answer', ''))
            if isinstance(correct_answer, dict) and 'option' in correct_answer:
                correct_answer = correct_answer['option']
            
            # Extract difficulty
            difficulty = self._extract_difficulty_from_block(question, context)
            
            # Extract topic info
            block_name = question.get('block', context.get('block', context.get('subject', 'Unknown')))
            subtopic = question.get('chapter_subtopic', question.get('subtopic', ''))
            
            normalized_question = {
                'id': question_id,
                'text': question_text,
                'options': options_dict,
                'answer': correct_answer,
                'difficulty': difficulty,
                'topic': block_name,
                'subtopic': subtopic,
                'question_type': question.get('question_type', 'MCQ'),
                'has_image': False,  # Block questions typically don't have images
                'image_id': None,
                'image_path': None,
                'data_or_paragraph': question.get('data_paragraph', '')
            }
            
            return normalized_question
            
        except Exception as e:
            logger.error(f"Error normalizing block question {question.get('id', 'unknown')}: {e}")
            return None
    
    def _extract_difficulty_from_block(self, question: Dict, context: Dict) -> str:
        """Extract difficulty from block question format"""
        
        # First check for explicit difficulty_level field
        if 'difficulty_level' in question:
            difficulty = question['difficulty_level']
            return self._normalize_difficulty_value(difficulty)
        
        # Check in question data_paragraph
        data_para = question.get('data_paragraph', '').upper()
        
        if 'VERY EASY' in data_para:
            return 'Very Easy'
        elif 'EASY' in data_para:
            return 'Easy'
        elif 'MODERATE' in data_para:
            return 'Moderate'
        elif 'DIFFICULT' in data_para or 'HARD' in data_para:
            return 'Difficult'
        elif 'VERY DIFFICULT' in data_para:
            return 'Very Difficult'
        
        # Check in question text
        question_text = question.get('question_text', '').upper()
        if 'VERY EASY' in question_text:
            return 'Very Easy'
        elif 'EASY' in question_text:
            return 'Easy'
        elif 'MODERATE' in question_text:
            return 'Moderate'
        elif 'DIFFICULT' in question_text or 'HARD' in question_text:
            return 'Difficult'
        
        # Default based on question type or position
        question_type = question.get('question_type', '').upper()
        if 'BASIC' in question_type:
            return 'Easy'
        elif 'ADVANCED' in question_type:
            return 'Difficult'
        
        return 'Moderate'  # Default
    
    def _normalize_difficulty_value(self, difficulty: str) -> str:
        """Normalize difficulty value to standard format"""
        if not difficulty:
            return 'Moderate'
        
        difficulty = str(difficulty).strip()
        difficulty_mapping = {
            'VERY EASY': 'Very Easy',
            'VERY_EASY': 'Very Easy',
            'Very Easy': 'Very Easy',
            'EASY': 'Easy',
            'Easy': 'Easy',
            'MODERATE': 'Moderate',
            'Moderate': 'Moderate',
            'DIFFICULT': 'Difficult',
            'HARD': 'Difficult',
            'Difficult': 'Difficult',
            'VERY DIFFICULT': 'Very Difficult',
            'VERY_DIFFICULT': 'Very Difficult',
            'Very Difficult': 'Very Difficult'
        }
        
        return difficulty_mapping.get(difficulty, 'Moderate')
    
    def normalize_question_format(self, questions: List[Dict]) -> List[Dict]:
        """Normalize different question formats to a unified structure"""
        logger.info("Normalizing question formats...")
        
        normalized_questions = []
        
        for i, question in enumerate(questions):
            try:
                normalized_q = self._normalize_single_question(question, i)
                if normalized_q:
                    normalized_questions.append(normalized_q)
            except Exception as e:
                logger.error(f"Error normalizing question {i}: {e}")
                continue
        
        logger.info(f"Normalized {len(normalized_questions)} questions")
        return normalized_questions
    
    def _normalize_single_question(self, question: Dict, index: int) -> Optional[Dict]:
        """Normalize a single question to unified format"""
        
        # Generate unique ID if missing
        question_id = question.get('id', question.get('question_id', f'Q{index + 1:04d}'))
        
        # Extract question text
        question_text = (
            question.get('text') or 
            question.get('question_text') or 
            question.get('question') or
            ""
        ).strip()
        
        if not question_text:
            logger.warning(f"Empty question text for question {question_id}")
            return None
        
        # Extract options
        options = self._extract_options(question)
        
        # Extract answer
        answer = self._extract_answer(question)
        
        # Extract difficulty
        difficulty = self._extract_difficulty(question)
        
        # Extract topic/subtopic
        topic = question.get('block', question.get('topic', question.get('subtopic', 'General')))
        subtopic = question.get('subtopic', question.get('category', ''))
        
        normalized_question = {
            'id': str(question_id),
            'text': question_text,
            'options': options,
            'answer': answer,
            'difficulty': difficulty,
            'topic': topic,
            'subtopic': subtopic,
            'question_type': question.get('questionType', question.get('type', 'MCQ')),
            'has_image': question.get('has_image', False),
            'image_id': question.get('image_id'),
            'image_path': question.get('image_path'),
            'data_or_paragraph': question.get('dataOrParagraph', question.get('data', question.get('paragraph')))
        }
        
        return normalized_question
    
    def _extract_options(self, question: Dict) -> Dict[str, str]:
        """Extract and normalize options from various formats"""
        options = {}
        
        # Handle different option formats
        if 'options' in question:
            if isinstance(question['options'], dict):
                # Format: {"A": "option1", "B": "option2", ...}
                options = question['options']
            elif isinstance(question['options'], list):
                # Format: ["option1", "option2", "option3", "option4"]
                option_keys = ['A', 'B', 'C', 'D']
                for i, opt in enumerate(question['options']):
                    if i < len(option_keys):
                        options[option_keys[i]] = str(opt)
        else:
            # Handle separate option fields
            option_fields = ['option_a', 'option_b', 'option_c', 'option_d']
            option_keys = ['A', 'B', 'C', 'D']
            
            for i, field in enumerate(option_fields):
                if field in question and question[field]:
                    options[option_keys[i]] = str(question[field])
        
        return options
    
    def _extract_answer(self, question: Dict) -> str:
        """Extract correct answer from various formats"""
        answer = question.get('answer', question.get('correct_answer', question.get('correctAnswer', '')))
        
        # Normalize answer format
        if isinstance(answer, str):
            answer = answer.upper().strip()
            
        return answer
    
    def _extract_difficulty(self, question: Dict) -> str:
        """Extract and normalize difficulty level"""
        difficulty = question.get('difficulty', question.get('level', 'MODERATE'))
        
        # Normalize difficulty levels
        difficulty_mapping = {
            'VERY_EASY': 'Very Easy',
            'VERY EASY': 'Very Easy', 
            'EASY': 'Easy',
            'MODERATE': 'Moderate',
            'DIFFICULT': 'Difficult',
            'HARD': 'Difficult',
            'VERY_DIFFICULT': 'Very Difficult',
            'VERY DIFFICULT': 'Very Difficult'
        }
        
        normalized_difficulty = difficulty_mapping.get(difficulty.upper(), difficulty)
        return normalized_difficulty
    
    def calculate_item_parameters(self, questions: List[Dict]) -> Dict:
        """Calculate IRT parameters for each question"""
        logger.info("Calculating item parameters...")
        
        item_parameters = {}
        
        # Difficulty level mappings for IRT parameters
        difficulty_params = {
            'Very Easy': {'b': -1.5, 'a_base': 0.8},
            'Easy': {'b': -0.5, 'a_base': 1.0},
            'Moderate': {'b': 0.0, 'a_base': 1.2},
            'Difficult': {'b': 1.0, 'a_base': 1.4},
            'Very Difficult': {'b': 1.5, 'a_base': 1.6}
        }
        
        for question in questions:
            question_id = question['id']
            difficulty = question['difficulty']
            
            # Get base parameters
            base_params = difficulty_params.get(difficulty, difficulty_params['Moderate'])
            
            # Add some randomization for more realistic parameters
            b_param = base_params['b'] + np.random.normal(0, 0.1)
            a_param = max(0.1, base_params['a_base'] + np.random.normal(0, 0.2))
            
            # Adjust discrimination based on question quality indicators
            quality_score = self._assess_question_quality(question)
            a_param *= quality_score
            
            item_parameters[question_id] = {
                'difficulty': b_param,
                'discrimination': a_param,
                'guessing': 0.25,  # 25% chance for 4-option MCQ
                'topic': question['topic'],
                'subtopic': question['subtopic'],
                'has_image': question['has_image']
            }
        
        return item_parameters
    
    def _assess_question_quality(self, question: Dict) -> float:
        """Assess question quality to adjust discrimination parameter"""
        quality_score = 1.0
        
        # Check if question has complete options
        options = question.get('options', {})
        if len(options) >= 4:
            quality_score += 0.1
        
        # Check if question has image (might be more discriminating)
        if question.get('has_image'):
            quality_score += 0.1
        
        # Check question text length (not too short, not too long)
        text_length = len(question.get('text', ''))
        if 50 <= text_length <= 300:
            quality_score += 0.1
        
        # Ensure quality score is reasonable
        return min(max(quality_score, 0.5), 2.0)
    
    def build_topic_hierarchy(self, questions: List[Dict]) -> Dict:
        """Build topic hierarchy and statistics"""
        logger.info("Building topic hierarchy...")
        
        topics = {}
        
        for question in questions:
            topic = question['topic']
            subtopic = question['subtopic']
            difficulty = question['difficulty']
            
            if topic not in topics:
                topics[topic] = {
                    'subtopics': {},
                    'total_questions': 0,
                    'difficulty_distribution': {},
                    'questions_with_images': 0
                }
            
            if subtopic not in topics[topic]['subtopics']:
                topics[topic]['subtopics'][subtopic] = {
                    'questions': [],
                    'difficulty_distribution': {},
                    'questions_with_images': 0
                }
            
            # Add question ID to subtopic
            topics[topic]['subtopics'][subtopic]['questions'].append(question['id'])
            
            # Update counters
            topics[topic]['total_questions'] += 1
            
            # Update difficulty distribution
            if difficulty not in topics[topic]['difficulty_distribution']:
                topics[topic]['difficulty_distribution'][difficulty] = 0
            topics[topic]['difficulty_distribution'][difficulty] += 1
            
            if difficulty not in topics[topic]['subtopics'][subtopic]['difficulty_distribution']:
                topics[topic]['subtopics'][subtopic]['difficulty_distribution'][difficulty] = 0
            topics[topic]['subtopics'][subtopic]['difficulty_distribution'][difficulty] += 1
            
            # Count questions with images
            if question.get('has_image'):
                topics[topic]['questions_with_images'] += 1
                topics[topic]['subtopics'][subtopic]['questions_with_images'] += 1
        
        return topics
    
    def train_model(self) -> Dict:
        """Complete training pipeline"""
        logger.info("Starting adaptive assessment model training...")
        
        # Load all datasets
        raw_questions = self.load_all_datasets()
        
        if not raw_questions:
            raise ValueError("No questions found in datasets")
        
        # Normalize question formats
        normalized_questions = self.normalize_question_format(raw_questions)
        
        if not normalized_questions:
            raise ValueError("No questions could be normalized")
        
        # Calculate item parameters
        item_parameters = self.calculate_item_parameters(normalized_questions)
        
        # Build topic hierarchy
        topics = self.build_topic_hierarchy(normalized_questions)
        
        # Calculate difficulty level statistics
        difficulty_levels = self._calculate_difficulty_stats(normalized_questions)
        
        # Build final model data
        self.model_data.update({
            'questions': normalized_questions,
            'topics': topics,
            'difficulty_levels': difficulty_levels,
            'question_parameters': item_parameters,
            'model_metadata': {
                'total_questions': len(normalized_questions),
                'total_topics': len(topics),
                'questions_with_images': sum(1 for q in normalized_questions if q.get('has_image')),
                'training_date': datetime.now().isoformat(),
                'version': '2.0',
                'description': 'Adaptive Assessment Model with Image Support'
            }
        })
        
        logger.info("Model training completed successfully!")
        logger.info(f"Total questions: {len(normalized_questions)}")
        logger.info(f"Questions with images: {sum(1 for q in normalized_questions if q.get('has_image'))}")
        logger.info(f"Total topics: {len(topics)}")
        
        return self.model_data
    
    def _calculate_difficulty_stats(self, questions: List[Dict]) -> Dict:
        """Calculate statistics for each difficulty level"""
        difficulty_stats = {}
        
        for question in questions:
            difficulty = question['difficulty']
            
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {
                    'count': 0,
                    'topics': set(),
                    'questions_with_images': 0,
                    'average_discrimination': 0,
                    'average_difficulty_param': 0
                }
            
            difficulty_stats[difficulty]['count'] += 1
            difficulty_stats[difficulty]['topics'].add(question['topic'])
            
            if question.get('has_image'):
                difficulty_stats[difficulty]['questions_with_images'] += 1
        
        # Convert sets to lists for JSON serialization
        for difficulty in difficulty_stats:
            difficulty_stats[difficulty]['topics'] = list(difficulty_stats[difficulty]['topics'])
        
        return difficulty_stats
    
    def save_model(self, output_path: str = 'trained_adaptive_model.json'):
        """Save the trained model to JSON file"""
        logger.info(f"Saving model to {output_path}...")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.model_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Model saved successfully to {output_path}")
            
            # Print summary
            self._print_model_summary()
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
            raise
    
    def _print_model_summary(self):
        """Print a summary of the trained model"""
        metadata = self.model_data['model_metadata']
        topics = self.model_data['topics']
        
        print("\n" + "="*60)
        print("ADAPTIVE ASSESSMENT MODEL TRAINING SUMMARY")
        print("="*60)
        print(f"Total Questions: {metadata['total_questions']}")
        print(f"Questions with Images: {metadata['questions_with_images']}")
        print(f"Total Topics: {metadata['total_topics']}")
        print(f"Training Date: {metadata['training_date']}")
        print(f"Model Version: {metadata['version']}")
        
        print("\nTopics Distribution:")
        for topic, data in topics.items():
            print(f"  {topic}: {data['total_questions']} questions ({data['questions_with_images']} with images)")
            
        print("\nDifficulty Distribution:")
        for difficulty, data in self.model_data['difficulty_levels'].items():
            print(f"  {difficulty}: {data['count']} questions ({data['questions_with_images']} with images)")
        
        print("="*60)


def main():
    """Main training function"""
    trainer = AdaptiveAssessmentTrainer()
    
    try:
        # Train the model
        model_data = trainer.train_model()
        
        # Save the model
        trainer.save_model('trained_adaptive_assessment_model.json')
        
        print("\nTraining completed successfully!")
        print("Model saved as: trained_adaptive_assessment_model.json")
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise


if __name__ == "__main__":
    main()