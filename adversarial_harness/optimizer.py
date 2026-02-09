"""
Optimizer Module

Analyzes critic feedback and provides optimization recommendations.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class OptimizationReport:
    """Report with optimization insights and recommendations."""
    timestamp: str
    num_sessions_analyzed: int
    
    # Aggregate metrics
    average_score: float
    score_trend: str  # improving, declining, stable
    
    # Analysis by component
    question_quality_avg: float
    information_extraction_avg: float
    empathy_avg: float
    efficiency_avg: float
    coverage_avg: float
    
    # Top issues
    common_weaknesses: List[str]
    common_strengths: List[str]
    
    # Recommendations
    recommendations: List[str]
    priority_improvements: List[str]
    
    # Detailed insights
    best_session_id: str = None
    worst_session_id: str = None
    best_score: float = 0.0
    worst_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'num_sessions_analyzed': self.num_sessions_analyzed,
            'average_score': self.average_score,
            'score_trend': self.score_trend,
            'question_quality_avg': self.question_quality_avg,
            'information_extraction_avg': self.information_extraction_avg,
            'empathy_avg': self.empathy_avg,
            'efficiency_avg': self.efficiency_avg,
            'coverage_avg': self.coverage_avg,
            'common_weaknesses': self.common_weaknesses,
            'common_strengths': self.common_strengths,
            'recommendations': self.recommendations,
            'priority_improvements': self.priority_improvements,
            'best_session_id': self.best_session_id,
            'worst_session_id': self.worst_session_id,
            'best_score': self.best_score,
            'worst_score': self.worst_score
        }


class Optimizer:
    """
    Analyzes critic feedback to provide optimization recommendations.
    
    The optimizer:
    - Aggregates scores across sessions
    - Identifies patterns in successes and failures
    - Generates actionable recommendations
    - Tracks improvement over time
    """
    
    def __init__(self):
        """Initialize optimizer."""
        self.history = []
    
    def analyze(self, results: List[Any]) -> OptimizationReport:
        """
        Analyze session results and generate optimization report.
        
        Args:
            results: List of SessionResult objects
            
        Returns:
            OptimizationReport with insights and recommendations
        """
        logger.info(f"Analyzing {len(results)} session results")
        
        # Filter successful results
        successful = [r for r in results if r.success and r.critic_score]
        
        if not successful:
            logger.warning("No successful results to analyze")
            return self._empty_report(len(results))
        
        # Calculate aggregate metrics
        scores = [r.critic_score.overall_score for r in successful]
        avg_score = sum(scores) / len(scores)
        
        question_quality_scores = [r.critic_score.question_quality for r in successful]
        info_extraction_scores = [r.critic_score.information_extraction for r in successful]
        empathy_scores = [r.critic_score.empathy for r in successful]
        efficiency_scores = [r.critic_score.efficiency for r in successful]
        coverage_scores = [r.critic_score.coverage for r in successful]
        
        # Find best and worst
        best_result = max(successful, key=lambda r: r.critic_score.overall_score)
        worst_result = min(successful, key=lambda r: r.critic_score.overall_score)
        
        # Aggregate feedback
        all_strengths = []
        all_weaknesses = []
        all_suggestions = []
        
        for result in successful:
            all_strengths.extend(result.critic_score.strengths)
            all_weaknesses.extend(result.critic_score.weaknesses)
            all_suggestions.extend(result.critic_score.suggestions)
        
        # Find most common
        common_strengths = self._most_common(all_strengths, top_n=5)
        common_weaknesses = self._most_common(all_weaknesses, top_n=5)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            avg_score,
            question_quality_scores,
            info_extraction_scores,
            empathy_scores,
            efficiency_scores,
            coverage_scores,
            common_weaknesses,
            all_suggestions
        )
        
        # Determine priority improvements
        priority_improvements = self._determine_priorities(
            question_quality_scores,
            info_extraction_scores,
            empathy_scores,
            efficiency_scores,
            coverage_scores
        )
        
        # Determine trend
        trend = self._determine_trend(scores)
        
        report = OptimizationReport(
            timestamp=datetime.utcnow().isoformat(),
            num_sessions_analyzed=len(successful),
            average_score=avg_score,
            score_trend=trend,
            question_quality_avg=sum(question_quality_scores) / len(question_quality_scores),
            information_extraction_avg=sum(info_extraction_scores) / len(info_extraction_scores),
            empathy_avg=sum(empathy_scores) / len(empathy_scores),
            efficiency_avg=sum(efficiency_scores) / len(efficiency_scores),
            coverage_avg=sum(coverage_scores) / len(coverage_scores),
            common_weaknesses=common_weaknesses,
            common_strengths=common_strengths,
            recommendations=recommendations,
            priority_improvements=priority_improvements,
            best_session_id=best_result.session_id,
            worst_session_id=worst_result.session_id,
            best_score=best_result.critic_score.overall_score,
            worst_score=worst_result.critic_score.overall_score
        )
        
        self.history.append(report)
        logger.info(f"Analysis complete. Average score: {avg_score:.3f}, Trend: {trend}")
        
        return report
    
    def _most_common(self, items: List[str], top_n: int = 5) -> List[str]:
        """Find most common items."""
        if not items:
            return []
        
        from collections import Counter
        counter = Counter(items)
        return [item for item, count in counter.most_common(top_n)]
    
    def _generate_recommendations(self,
                                  avg_score: float,
                                  question_quality: List[float],
                                  info_extraction: List[float],
                                  empathy: List[float],
                                  efficiency: List[float],
                                  coverage: List[float],
                                  weaknesses: List[str],
                                  suggestions: List[str]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Score-based recommendations
        if avg_score < 0.5:
            recommendations.append("Overall performance is below average. Focus on fundamental improvements.")
        elif avg_score < 0.7:
            recommendations.append("Performance is moderate. Targeted improvements can significantly boost quality.")
        else:
            recommendations.append("Performance is good. Focus on consistency and edge cases.")
        
        # Component-specific recommendations
        avg_question_quality = sum(question_quality) / len(question_quality)
        if avg_question_quality < 0.6:
            recommendations.append("Improve question formulation: make questions more specific and relevant.")
        
        avg_info_extraction = sum(info_extraction) / len(info_extraction)
        if avg_info_extraction < 0.6:
            recommendations.append("Enhance information extraction: ask follow-up questions when responses are vague.")
        
        avg_empathy = sum(empathy) / len(empathy)
        if avg_empathy < 0.6:
            recommendations.append("Increase empathy: acknowledge complainant's feelings and concerns.")
        
        avg_efficiency = sum(efficiency) / len(efficiency)
        if avg_efficiency < 0.6:
            recommendations.append("Improve efficiency: avoid repetitive questions and streamline the process.")
        
        avg_coverage = sum(coverage) / len(coverage)
        if avg_coverage < 0.6:
            recommendations.append("Expand topic coverage: ensure all important aspects are addressed.")
        
        # Add unique suggestions from critics
        unique_suggestions = list(set(suggestions))
        recommendations.extend(unique_suggestions[:3])  # Top 3 suggestions
        
        return recommendations
    
    def _determine_priorities(self,
                             question_quality: List[float],
                             info_extraction: List[float],
                             empathy: List[float],
                             efficiency: List[float],
                             coverage: List[float]) -> List[str]:
        """Determine priority improvements based on lowest scores."""
        components = {
            'question_quality': sum(question_quality) / len(question_quality),
            'information_extraction': sum(info_extraction) / len(info_extraction),
            'empathy': sum(empathy) / len(empathy),
            'efficiency': sum(efficiency) / len(efficiency),
            'coverage': sum(coverage) / len(coverage)
        }
        
        # Sort by score (lowest first)
        sorted_components = sorted(components.items(), key=lambda x: x[1])
        
        # Return bottom 3 as priorities
        priorities = []
        for component, score in sorted_components[:3]:
            if score < 0.7:  # Only if below threshold
                priorities.append(f"Improve {component.replace('_', ' ')}: current avg {score:.2f}")
        
        return priorities
    
    def _determine_trend(self, scores: List[float]) -> str:
        """Determine if scores are improving, declining, or stable."""
        if len(scores) < 3:
            return "insufficient_data"
        
        # Simple linear trend
        first_half = scores[:len(scores)//2]
        second_half = scores[len(scores)//2:]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        diff = second_avg - first_avg
        
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        else:
            return "stable"
    
    def _empty_report(self, num_sessions: int) -> OptimizationReport:
        """Create empty report when no successful sessions."""
        return OptimizationReport(
            timestamp=datetime.utcnow().isoformat(),
            num_sessions_analyzed=0,
            average_score=0.0,
            score_trend="no_data",
            question_quality_avg=0.0,
            information_extraction_avg=0.0,
            empathy_avg=0.0,
            efficiency_avg=0.0,
            coverage_avg=0.0,
            common_weaknesses=["All sessions failed"],
            common_strengths=[],
            recommendations=["Debug system failures before optimization"],
            priority_improvements=["Fix system stability"]
        )
    
    def get_history(self) -> List[OptimizationReport]:
        """Get optimization history."""
        return self.history.copy()
    
    def compare_reports(self, report1: OptimizationReport, report2: OptimizationReport) -> Dict[str, Any]:
        """
        Compare two optimization reports.
        
        Args:
            report1: Earlier report
            report2: Later report
            
        Returns:
            Dictionary with comparison metrics
        """
        return {
            'score_change': report2.average_score - report1.average_score,
            'question_quality_change': report2.question_quality_avg - report1.question_quality_avg,
            'info_extraction_change': report2.information_extraction_avg - report1.information_extraction_avg,
            'empathy_change': report2.empathy_avg - report1.empathy_avg,
            'efficiency_change': report2.efficiency_avg - report1.efficiency_avg,
            'coverage_change': report2.coverage_avg - report1.coverage_avg,
            'trend_change': f"{report1.score_trend} -> {report2.score_trend}"
        }
