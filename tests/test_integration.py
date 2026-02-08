"""
Integration tests for the complaint generator application

Note: These tests may skip if dependencies are not available.
"""
import pytest
from unittest.mock import Mock


class TestComplaintGeneratorIntegration:
    """Integration tests for the complaint generator"""
    
    @pytest.mark.integration
    def test_mediator_with_mock_backend(self):
        """Test mediator with a mock backend"""
        try:
            from mediator import Mediator
            
            # Create a mock backend
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mock_backend.return_value = 'Test response from backend'
            
            # Create mediator with mock backend
            mediator = Mediator(backends=[mock_backend])
            
            # Test that mediator can query backend
            response = mediator.query_backend('Test prompt')
            assert response == 'Test response from backend'
            
            # Verify backend was called
            mock_backend.assert_called_once_with('Test prompt')
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
        
    @pytest.mark.integration
    def test_full_mediator_workflow(self):
        """Test a complete mediator workflow"""
        try:
            from mediator import Mediator
            from mediator.state import State
            
            # Setup
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mock_backend.return_value = 'Generated question'
            
            mediator = Mediator(backends=[mock_backend])
            
            # Test state management
            initial_state = mediator.get_state()
            assert isinstance(initial_state, dict)
            
            # Test reset
            mediator.reset()
            assert isinstance(mediator.state, State)
            
            # Test logging
            mediator.log('test_event', data='test_data')
            assert len(mediator.state.log) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

