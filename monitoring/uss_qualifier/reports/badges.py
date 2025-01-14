from typing import Dict, Callable, TypeVar, Type

import bc_jsonpath_ng.ext

from monitoring.uss_qualifier.configurations.configuration import ParticipantID
from monitoring.uss_qualifier.reports.badge_definitions import (
    AllConditions,
    SpecificCondition,
    AnyCondition,
    NoFailedChecksCondition,
    RequirementsCheckedCondition,
    BadgeGrantedCondition,
    BadgeGrantCondition,
)
from monitoring.uss_qualifier.reports.report import TestSuiteReport
from monitoring.uss_qualifier.requirements.definitions import RequirementID
from monitoring.uss_qualifier.requirements.documentation import (
    resolve_requirements_collection,
)

SpecificConditionType = TypeVar("SpecificConditionType", bound=SpecificCondition)
_badge_condition_evaluators: Dict[
    Type, Callable[[SpecificConditionType, ParticipantID, TestSuiteReport], bool]
] = {}


def badge_condition_evaluator(condition_type: Type):
    """Decorator to label a function that evaluates a specific condition for granting a badge.

    Args:
        condition_type: A Type that inherits from badge_definitions.SpecificCondition.
    """

    def register_evaluator(func):
        _badge_condition_evaluators[condition_type] = func
        return func

    return register_evaluator


def condition_satisfied_for_test_suite(
    grant_condition: BadgeGrantCondition,
    participant_id: ParticipantID,
    report: TestSuiteReport,
) -> bool:
    """Determine if a condition for granting a badge is satisfied based on a Test Suite report.

    Args:
        grant_condition: Badge-granting condition to check.
        participant_id: Participant for which the badge would be granted.
        report: Test Suite report upon which the badge (and grant condition) are based.

    Returns: True if the condition was satisfied, False if not.
    """
    populated_fields = [
        field_name
        for field_name in grant_condition
        if grant_condition[field_name] is not None
    ]
    if not populated_fields:
        raise ValueError(
            "No specific condition specified for grant_condition in BadgeGrantCondition"
        )
    if len(populated_fields) > 1:
        raise ValueError(
            "Multiple conditions specified for grant_condition in BadgeGrantCondition: "
            + ", ".join(populated_fields)
        )
    specific_condition = grant_condition[populated_fields[0]]
    condition_evaluator = _badge_condition_evaluators.get(
        type(specific_condition), None
    )
    if condition_evaluator is None:
        raise RuntimeError(
            f"Could not find evaluator for condition type {type(specific_condition).__name__}"
        )
    return condition_evaluator(specific_condition, participant_id, report)


@badge_condition_evaluator(AllConditions)
def evaluate_all_conditions_condition(
    condition: AllConditions, participant_id: ParticipantID, report: TestSuiteReport
) -> bool:
    for subcondition in condition.conditions:
        if not condition_satisfied_for_test_suite(subcondition, participant_id, report):
            return False
    return True


@badge_condition_evaluator(AnyCondition)
def evaluate_any_condition_condition(
    condition: AnyCondition, participant_id: ParticipantID, report: TestSuiteReport
) -> bool:
    for subcondition in condition.conditions:
        if condition_satisfied_for_test_suite(subcondition, participant_id, report):
            return True
    return False


@badge_condition_evaluator(NoFailedChecksCondition)
def evaluate_no_failed_checks_condition(
    condition: NoFailedChecksCondition,
    participant_id: ParticipantID,
    report: TestSuiteReport,
) -> bool:
    for _ in report.query_failed_checks(participant_id):
        return False
    return True


@badge_condition_evaluator(RequirementsCheckedCondition)
def evaluate_requirements_checked_conditions(
    condition: RequirementsCheckedCondition,
    participant_id: ParticipantID,
    report: TestSuiteReport,
) -> bool:
    req_checked: Dict[RequirementID, bool] = {
        req_id: False for req_id in resolve_requirements_collection(condition.checked)
    }
    for passed_check in report.query_passed_checks(participant_id):
        for req_id in passed_check.requirements:
            if req_id in req_checked:
                req_checked[req_id] = True
    return all(req_checked.values())


@badge_condition_evaluator(BadgeGrantedCondition)
def evaluate_badge_granted_condition(
    condition: BadgeGrantedCondition,
    participant_id: ParticipantID,
    report: TestSuiteReport,
) -> bool:
    path = condition.badge_location if "badge_location" in condition else "$"
    matching_reports = bc_jsonpath_ng.ext.parse(path).find(report)
    result = False
    for matching_report in matching_reports:
        if isinstance(matching_report.value, TestSuiteReport):
            badges = matching_report.value.badges_granted.get(participant_id, set())
            if condition.badge_id in badges:
                result = True
            else:
                return False
    return result
