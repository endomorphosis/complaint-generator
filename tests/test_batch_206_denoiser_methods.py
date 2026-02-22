"""
Unit tests for Batch 206: ComplaintDenoiser analysis methods.

Tests the 10 question history and policy analysis methods added to ComplaintDenoiser.
"""

import pytest
from complaint_phases.denoiser import ComplaintDenoiser


@pytest.fixture
def denoiser():
    """Create a ComplaintDenoiser instance for testing."""
    return ComplaintDenoiser()


# ============================================================================ #
# Test total_questions_asked()
# ============================================================================ #

class TestTotalQuestionsAsked:
    def test_no_questions(self, denoiser):
        assert denoiser.total_questions_asked() == 0
    
    def test_single_question(self, denoiser):
        denoiser.questions_asked.append({'type': 'who', 'text': 'Who is responsible?'})
        assert denoiser.total_questions_asked() == 1
    
    def test_multiple_questions(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'type': 'what', 'text': 'Q2'},
            {'type': 'when', 'text': 'Q3'}
        ])
        assert denoiser.total_questions_asked() == 3


# ============================================================================ #
# Test question_pool_size()
# ============================================================================ #

class TestQuestionPoolSize:
    def test_empty_pool(self, denoiser):
        assert denoiser.question_pool_size() == 0
    
    def test_single_candidate(self, denoiser):
        denoiser.questions_pool.append({'type': 'where', 'text': 'Where did it happen?'})
        assert denoiser.question_pool_size() == 1
    
    def test_multiple_candidates(self, denoiser):
        denoiser.questions_pool.extend([
            {'type': 'why', 'text': 'Q1'},
            {'type': 'how', 'text': 'Q2'},
            {'type': 'remedy', 'text': 'Q3'},
            {'type': 'evidence', 'text': 'Q4'}
        ])
        assert denoiser.question_pool_size() == 4


# ============================================================================ #
# Test question_type_frequency()
# ============================================================================ #

class TestQuestionTypeFrequency:
    def test_empty_history(self, denoiser):
        assert denoiser.question_type_frequency() == {}
    
    def test_single_type(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'type': 'who', 'text': 'Q2'}
        ])
        freq = denoiser.question_type_frequency()
        assert freq == {'who': 2}
    
    def test_multiple_types(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'type': 'what', 'text': 'Q2'},
            {'type': 'who', 'text': 'Q3'},
            {'type': 'when', 'text': 'Q4'},
            {'type': 'what', 'text': 'Q5'},
            {'type': 'what', 'text': 'Q6'}
        ])
        freq = denoiser.question_type_frequency()
        assert freq == {'who': 2, 'what': 3, 'when': 1}
    
    def test_missing_type_field(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'text': 'Q2'},  # Missing type
            {'type': 'what', 'text': 'Q3'}
        ])
        freq = denoiser.question_type_frequency()
        assert freq == {'who': 1, 'unknown': 1, 'what': 1}


# ============================================================================ #
# Test most_frequent_question_type()
# ============================================================================ #

class TestMostFrequentQuestionType:
    def test_no_questions(self, denoiser):
        assert denoiser.most_frequent_question_type() == 'none'
    
    def test_single_type(self, denoiser):
        denoiser.questions_asked.append({'type': 'evidence', 'text': 'Q1'})
        assert denoiser.most_frequent_question_type() == 'evidence'
    
    def test_clear_winner(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'type': 'what', 'text': 'Q2'},
            {'type': 'who', 'text': 'Q3'},
            {'type': 'who', 'text': 'Q4'}
        ])
        assert denoiser.most_frequent_question_type() == 'who'
    
    def test_tie_returns_one(self, denoiser):
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Q1'},
            {'type': 'what', 'text': 'Q2'}
        ])
        # Should return one of them (implementation uses max which picks arbitrarily)
        result = denoiser.most_frequent_question_type()
        assert result in ['who', 'what']


# ============================================================================ #
# Test average_gain_per_question()
# ============================================================================ #

class TestAverageGainPerQuestion:
    def test_no_gains(self, denoiser):
        assert denoiser.average_gain_per_question() == 0.0
    
    def test_single_gain(self, denoiser):
        denoiser._recent_gains.append(2.5)
        assert denoiser.average_gain_per_question() == 2.5
    
    def test_multiple_gains(self, denoiser):
        denoiser._recent_gains.extend([1.0, 2.0, 3.0])
        assert denoiser.average_gain_per_question() == 2.0
    
    def test_negative_gains(self, denoiser):
        denoiser._recent_gains.extend([-1.0, 0.0, 1.0])
        assert denoiser.average_gain_per_question() == 0.0
    
    def test_zero_gains(self, denoiser):
        denoiser._recent_gains.extend([0.0, 0.0, 0.0])
        assert denoiser.average_gain_per_question() == 0.0


# ============================================================================ #
# Test gain_variance()
# ============================================================================ #

class TestGainVariance:
    def test_no_gains(self, denoiser):
        assert denoiser.gain_variance() == 0.0
    
    def test_single_gain(self, denoiser):
        denoiser._recent_gains.append(5.0)
        assert denoiser.gain_variance() == 0.0
    
    def test_identical_gains(self, denoiser):
        denoiser._recent_gains.extend([3.0, 3.0, 3.0])
        assert denoiser.gain_variance() < 1e-10
    
    def test_varied_gains(self, denoiser):
        denoiser._recent_gains.extend([1.0, 2.0, 3.0])
        variance = denoiser.gain_variance()
        # Mean = 2.0, variance = ((1-2)^2 + (2-2)^2 + (3-2)^2) / 3 = 2/3
        assert abs(variance - (2/3)) < 0.01


# ============================================================================ #
# Test momentum_enabled_for_types()
# ============================================================================ #

class TestMomentumEnabledForTypes:
    def test_no_momentum(self, denoiser):
        assert denoiser.momentum_enabled_for_types() == []
    
    def test_single_type(self, denoiser):
        denoiser._type_gain_ema['who'] = 1.5
        assert denoiser.momentum_enabled_for_types() == ['who']
    
    def test_multiple_types(self, denoiser):
        denoiser._type_gain_ema['who'] = 1.5
        denoiser._type_gain_ema['what'] = 2.0
        denoiser._type_gain_ema['when'] = 0.5
        types = denoiser.momentum_enabled_for_types()
        assert set(types) == {'who', 'what', 'when'}


# ============================================================================ #
# Test highest_momentum_type()
# ============================================================================ #

class TestHighestMomentumType:
    def test_no_momentum(self, denoiser):
        assert denoiser.highest_momentum_type() == 'none'
    
    def test_single_type(self, denoiser):
        denoiser._type_gain_ema['remedy'] = 3.2
        assert denoiser.highest_momentum_type() == 'remedy'
    
    def test_clear_winner(self, denoiser):
        denoiser._type_gain_ema['who'] = 1.0
        denoiser._type_gain_ema['what'] = 5.0
        denoiser._type_gain_ema['when'] = 2.0
        assert denoiser.highest_momentum_type() == 'what'
    
    def test_negative_momentum(self, denoiser):
        denoiser._type_gain_ema['who'] = -1.0
        denoiser._type_gain_ema['what'] = -0.5
        # Should return 'what' as it has higher (less negative) value
        assert denoiser.highest_momentum_type() == 'what'


# ============================================================================ #
# Test is_exploration_active()
# ============================================================================ #

class TestIsExplorationActive:
    def test_default_disabled(self, denoiser):
        # Default is False (from _env_bool with default=False)
        assert denoiser.is_exploration_active() is False
    
    def test_enabled(self, denoiser):
        denoiser.exploration_enabled = True
        assert denoiser.is_exploration_active() is True
    
    def test_disabled_explicitly(self, denoiser):
        denoiser.exploration_enabled = False
        assert denoiser.is_exploration_active() is False


# ============================================================================ #
# Test stagnation_detection_window()
# ============================================================================ #

class TestStagnationDetectionWindow:
    def test_default_value(self, denoiser):
        # Default is 4 from __init__
        assert denoiser.stagnation_detection_window() == 4
    
    def test_modified_value(self, denoiser):
        denoiser.stagnation_window = 10
        assert denoiser.stagnation_detection_window() == 10
    
    def test_zero_window(self, denoiser):
        denoiser.stagnation_window = 0
        assert denoiser.stagnation_detection_window() == 0


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch206Integration:
    def test_comprehensive_denoiser_analysis(self, denoiser):
        """Test that all Batch 206 methods work together correctly."""
        # Populate with realistic data
        denoiser.questions_asked.extend([
            {'type': 'who', 'text': 'Who is responsible?'},
            {'type': 'what', 'text': 'What happened?'},
            {'type': 'who', 'text': 'Who else was involved?'},
            {'type': 'when', 'text': 'When did it occur?'},
            {'type': 'what', 'text': 'What evidence exists?'}
        ])
        
        denoiser.questions_pool.extend([
            {'type': 'why', 'text': 'Why did it happen?'},
            {'type': 'remedy', 'text': 'What remedy do you seek?'}
        ])
        
        denoiser._recent_gains.extend([2.0, 3.0, 1.5, 4.0])
        
        denoiser._type_gain_ema['who'] = 2.5
        denoiser._type_gain_ema['what'] = 3.0
        denoiser._type_gain_ema['when'] = 1.0
        
        denoiser.exploration_enabled = True
        denoiser.stagnation_window = 5
        
        # Verify all methods work
        assert denoiser.total_questions_asked() == 5
        assert denoiser.question_pool_size() == 2
        
        freq = denoiser.question_type_frequency()
        assert freq == {'who': 2, 'what': 2, 'when': 1}
        assert denoiser.most_frequent_question_type() in ['who', 'what']
        
        avg_gain = denoiser.average_gain_per_question()
        assert abs(avg_gain - 2.625) < 0.01
        
        variance = denoiser.gain_variance()
        assert variance > 0.0
        
        types = denoiser.momentum_enabled_for_types()
        assert set(types) == {'who', 'what', 'when'}
        assert denoiser.highest_momentum_type() == 'what'
        
        assert denoiser.is_exploration_active() is True
        assert denoiser.stagnation_detection_window() == 5
