"""
Unit tests for Batch 211: PhaseManager analysis methods.

Tests the 10 phase transition, iteration, and loss tracking methods added to PhaseManager.
"""

import pytest
from datetime import datetime
from complaint_phases.phase_manager import PhaseManager, ComplaintPhase


@pytest.fixture
def phase_manager():
    """Create a PhaseManager instance for testing."""
    return PhaseManager()


def create_transition(from_phase, to_phase, iteration=0):
    """Helper to create a phase transition record."""
    return {
        'from_phase': from_phase.value if isinstance(from_phase, ComplaintPhase) else from_phase,
        'to_phase': to_phase.value if isinstance(to_phase, ComplaintPhase) else to_phase,
        'timestamp': datetime.utcnow().isoformat(),
        'iteration': iteration
    }


def create_iteration(loss, phase, iteration_num):
    """Helper to create an iteration record."""
    return {
        'iteration': iteration_num,
        'loss': loss,
        'phase': phase.value if isinstance(phase, ComplaintPhase) else phase,
        'metrics': {},
        'timestamp': datetime.utcnow().isoformat()
    }


# ============================================================================ #
# Test total_phase_transitions()
# ============================================================================ #

class TestTotalPhaseTransitions:
    def test_no_transitions(self, phase_manager):
        assert phase_manager.total_phase_transitions() == 0
    
    def test_single_transition(self, phase_manager):
        phase_manager.phase_history.append(
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE)
        )
        assert phase_manager.total_phase_transitions() == 1
    
    def test_multiple_transitions(self, phase_manager):
        transitions = [
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION)
        ]
        phase_manager.phase_history.extend(transitions)
        assert phase_manager.total_phase_transitions() == 2


# ============================================================================ #
# Test transitions_to_phase()
# ============================================================================ #

class TestTransitionsToPhase:
    def test_no_transitions(self, phase_manager):
        assert phase_manager.transitions_to_phase(ComplaintPhase.EVIDENCE) == 0
    
    def test_no_matching_transitions(self, phase_manager):
        phase_manager.phase_history.append(
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE)
        )
        assert phase_manager.transitions_to_phase(ComplaintPhase.FORMALIZATION) == 0
    
    def test_single_matching_transition(self, phase_manager):
        phase_manager.phase_history.append(
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE)
        )
        assert phase_manager.transitions_to_phase(ComplaintPhase.EVIDENCE) == 1
    
    def test_multiple_matching_transitions(self, phase_manager):
        phase_manager.phase_history.extend([
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION),
            create_transition(ComplaintPhase.FORMALIZATION, ComplaintPhase.EVIDENCE),
        ])
        assert phase_manager.transitions_to_phase(ComplaintPhase.EVIDENCE) == 2


# ============================================================================ #
# Test phase_transition_frequency()
# ============================================================================ #

class TestPhaseTransitionFrequency:
    def test_no_transitions(self, phase_manager):
        assert phase_manager.phase_transition_frequency() == {}
    
    def test_single_phase(self, phase_manager):
        phase_manager.phase_history.append(
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE)
        )
        freq = phase_manager.phase_transition_frequency()
        assert freq == {'evidence': 1}
    
    def test_multiple_phases(self, phase_manager):
        phase_manager.phase_history.extend([
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION),
            create_transition(ComplaintPhase.FORMALIZATION, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION),
        ])
        freq = phase_manager.phase_transition_frequency()
        assert freq == {'evidence': 2, 'formalization': 2}


# ============================================================================ #
# Test most_visited_phase()
# ============================================================================ #

class TestMostVisitedPhase:
    def test_no_transitions(self, phase_manager):
        assert phase_manager.most_visited_phase() == 'none'
    
    def test_single_phase(self, phase_manager):
        phase_manager.phase_history.append(
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE)
        )
        assert phase_manager.most_visited_phase() == 'evidence'
    
    def test_clear_winner(self, phase_manager):
        phase_manager.phase_history.extend([
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION),
            create_transition(ComplaintPhase.FORMALIZATION, ComplaintPhase.EVIDENCE),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION),
            create_transition(ComplaintPhase.FORMALIZATION, ComplaintPhase.EVIDENCE),
        ])
        # evidence: 3, formalization: 2
        assert phase_manager.most_visited_phase() == 'evidence'


# ============================================================================ #
# Test total_iterations()
# ============================================================================ #

class TestTotalIterations:
    def test_initial_count(self, phase_manager):
        assert phase_manager.total_iterations() == 0
    
    def test_after_incrementing(self, phase_manager):
        phase_manager.iteration_count = 5
        assert phase_manager.total_iterations() == 5


# ============================================================================ #
# Test iterations_in_phase()
# ============================================================================ #

class TestIterationsInPhase:
    def test_no_iterations(self, phase_manager):
        assert phase_manager.iterations_in_phase(ComplaintPhase.INTAKE) == 0
    
    def test_no_matching_phase(self, phase_manager):
        phase_manager.loss_history.append(
            create_iteration(0.5, ComplaintPhase.INTAKE, 1)
        )
        assert phase_manager.iterations_in_phase(ComplaintPhase.EVIDENCE) == 0
    
    def test_single_matching_iteration(self, phase_manager):
        phase_manager.loss_history.append(
            create_iteration(0.5, ComplaintPhase.EVIDENCE, 1)
        )
        assert phase_manager.iterations_in_phase(ComplaintPhase.EVIDENCE) == 1
    
    def test_multiple_matching_iterations(self, phase_manager):
        phase_manager.loss_history.extend([
            create_iteration(0.5, ComplaintPhase.EVIDENCE, 1),
            create_iteration(0.4, ComplaintPhase.FORMALIZATION, 2),
            create_iteration(0.3, ComplaintPhase.EVIDENCE, 3),
        ])
        assert phase_manager.iterations_in_phase(ComplaintPhase.EVIDENCE) == 2


# ============================================================================ #
# Test average_loss()
# ============================================================================ #

class TestAverageLoss:
    def test_no_iterations(self, phase_manager):
        assert phase_manager.average_loss() == 0.0
    
    def test_single_iteration(self, phase_manager):
        phase_manager.loss_history.append(
            create_iteration(0.5, ComplaintPhase.INTAKE, 1)
        )
        assert phase_manager.average_loss() == 0.5
    
    def test_multiple_iterations(self, phase_manager):
        phase_manager.loss_history.extend([
            create_iteration(0.6, ComplaintPhase.INTAKE, 1),
            create_iteration(0.4, ComplaintPhase.EVIDENCE, 2),
            create_iteration(0.2, ComplaintPhase.FORMALIZATION, 3),
        ])
        # Average: (0.6 + 0.4 + 0.2) / 3 = 0.4
        assert abs(phase_manager.average_loss() - 0.4) < 0.01


# ============================================================================ #
# Test minimum_loss()
# ============================================================================ #

class TestMinimumLoss:
    def test_no_iterations(self, phase_manager):
        assert phase_manager.minimum_loss() == float('inf')
    
    def test_single_iteration(self, phase_manager):
        phase_manager.loss_history.append(
            create_iteration(0.5, ComplaintPhase.INTAKE, 1)
        )
        assert phase_manager.minimum_loss() == 0.5
    
    def test_multiple_iterations(self, phase_manager):
        phase_manager.loss_history.extend([
            create_iteration(0.6, ComplaintPhase.INTAKE, 1),
            create_iteration(0.2, ComplaintPhase.EVIDENCE, 2),
            create_iteration(0.4, ComplaintPhase.FORMALIZATION, 3),
        ])
        assert phase_manager.minimum_loss() == 0.2


# ============================================================================ #
# Test has_phase_data_key()
# ============================================================================ #

class TestHasPhaseDataKey:
    def test_empty_phase_data(self, phase_manager):
        assert phase_manager.has_phase_data_key(ComplaintPhase.INTAKE, 'key1') is False
    
    def test_key_exists(self, phase_manager):
        phase_manager.phase_data[ComplaintPhase.INTAKE]['key1'] = 'value1'
        assert phase_manager.has_phase_data_key(ComplaintPhase.INTAKE, 'key1') is True
    
    def test_key_does_not_exist(self, phase_manager):
        phase_manager.phase_data[ComplaintPhase.INTAKE]['key1'] = 'value1'
        assert phase_manager.has_phase_data_key(ComplaintPhase.INTAKE, 'key2') is False
    
    def test_key_in_different_phase(self, phase_manager):
        phase_manager.phase_data[ComplaintPhase.EVIDENCE]['key1'] = 'value1'
        assert phase_manager.has_phase_data_key(ComplaintPhase.INTAKE, 'key1') is False


# ============================================================================ #
# Test phase_data_coverage()
# ============================================================================ #

class TestPhaseDataCoverage:
    def test_no_data(self, phase_manager):
        # All phases start empty, so coverage is 0.0
        assert phase_manager.phase_data_coverage() == 0.0
    
    def test_one_phase_with_data(self, phase_manager):
        phase_manager.phase_data[ComplaintPhase.INTAKE]['key1'] = 'value1'
        # 1 out of 3 phases has data
        coverage = phase_manager.phase_data_coverage()
        assert abs(coverage - (1/3)) < 0.01
    
    def test_all_phases_with_data(self, phase_manager):
        phase_manager.phase_data[ComplaintPhase.INTAKE]['key1'] = 'value1'
        phase_manager.phase_data[ComplaintPhase.EVIDENCE]['key2'] = 'value2'
        phase_manager.phase_data[ComplaintPhase.FORMALIZATION]['key3'] = 'value3'
        assert phase_manager.phase_data_coverage() == 1.0


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch211Integration:
    def test_comprehensive_phase_manager_analysis(self, phase_manager):
        """Test that all Batch 211 methods work together correctly."""
        # Simulate phase transitions
        phase_manager.phase_history.extend([
            create_transition(ComplaintPhase.INTAKE, ComplaintPhase.EVIDENCE, iteration=1),
            create_transition(ComplaintPhase.EVIDENCE, ComplaintPhase.FORMALIZATION, iteration=5),
            create_transition(ComplaintPhase.FORMALIZATION, ComplaintPhase.EVIDENCE, iteration=8),
        ])
        
        # Simulate iterations
        phase_manager.iteration_count = 10
        phase_manager.loss_history.extend([
            create_iteration(0.8, ComplaintPhase.INTAKE, 1),
            create_iteration(0.6, ComplaintPhase.EVIDENCE, 2),
            create_iteration(0.5, ComplaintPhase.EVIDENCE, 3),
            create_iteration(0.4, ComplaintPhase.EVIDENCE, 4),
            create_iteration(0.3, ComplaintPhase.FORMALIZATION, 5),
            create_iteration(0.25, ComplaintPhase.FORMALIZATION, 6),
            create_iteration(0.2, ComplaintPhase.FORMALIZATION, 7),
            create_iteration(0.35, ComplaintPhase.EVIDENCE, 8),
            create_iteration(0.3, ComplaintPhase.EVIDENCE, 9),
            create_iteration(0.28, ComplaintPhase.EVIDENCE, 10),
        ])
        
        # Add phase data
        phase_manager.phase_data[ComplaintPhase.INTAKE]['denoised'] = True
        phase_manager.phase_data[ComplaintPhase.EVIDENCE]['evidence_count'] = 5
        
        # Test all methods
        assert phase_manager.total_phase_transitions() == 3
        assert phase_manager.transitions_to_phase(ComplaintPhase.EVIDENCE) == 2
        assert phase_manager.transitions_to_phase(ComplaintPhase.FORMALIZATION) == 1
        
        freq = phase_manager.phase_transition_frequency()
        assert freq == {'evidence': 2, 'formalization': 1}
        assert phase_manager.most_visited_phase() == 'evidence'
        
        assert phase_manager.total_iterations() == 10
        assert phase_manager.iterations_in_phase(ComplaintPhase.INTAKE) == 1
        assert phase_manager.iterations_in_phase(ComplaintPhase.EVIDENCE) == 6
        assert phase_manager.iterations_in_phase(ComplaintPhase.FORMALIZATION) == 3
        
        avg = phase_manager.average_loss()
        # Total: 0.8 + 0.6 + 0.5 + 0.4 + 0.3 + 0.25 + 0.2 + 0.35 + 0.3 + 0.28 = 4.08
        # Avg = 4.08 / 10 = 0.408
        assert abs(avg - 0.408) < 0.01
        
        assert phase_manager.minimum_loss() == 0.2
        
        assert phase_manager.has_phase_data_key(ComplaintPhase.INTAKE, 'denoised') is True
        assert phase_manager.has_phase_data_key(ComplaintPhase.EVIDENCE, 'evidence_count') is True
        assert phase_manager.has_phase_data_key(ComplaintPhase.FORMALIZATION, 'anything') is False
        
        coverage = phase_manager.phase_data_coverage()
        # 2 out of 3 phases have data
        assert abs(coverage - (2/3)) < 0.01
