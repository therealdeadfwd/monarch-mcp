"""GraphQL operations and helpers for Monarch Money transaction rules.

The community ``monarchmoneycommunity`` library does not currently wrap
the transaction-rules GraphQL surface, so we drive the operations
directly via ``client.gql_call`` using documents sniffed from the
official Monarch Money web app.

Two helpers are exposed for reuse by the MCP server module:

* :data:`RULE_INPUT_FIELDS` — the tuple of fields accepted by both the
  ``CreateTransactionRuleInput`` and ``UpdateTransactionRuleInput``
  GraphQL inputs.
* :func:`rule_to_update_input` — builds an ``UpdateTransactionRuleInput``
  payload by starting from an existing rule (as returned by
  ``GetTransactionRules``) and layering caller-supplied overrides on
  top.  Necessary because the update mutation has *replace* semantics:
  any field omitted from the payload is reset to ``null`` server-side.
"""

from typing import Any, Dict, Iterable, Tuple


# ── GraphQL documents ──────────────────────────────────────────────────


GET_RULES_QUERY = """
query GetTransactionRules {
  transactionRules {
    id
    order
    ...TransactionRuleFields
    __typename
  }
}

fragment TransactionRuleFields on TransactionRuleV2 {
  id
  merchantCriteriaUseOriginalStatement
  merchantCriteria { operator value __typename }
  originalStatementCriteria { operator value __typename }
  merchantNameCriteria { operator value __typename }
  amountCriteria {
    operator isExpense value
    valueRange { lower upper __typename }
    __typename
  }
  categoryIds
  accountIds
  categories { id name icon __typename }
  accounts { id displayName icon logoUrl __typename }
  criteriaOwnerIsJoint
  criteriaOwnerUserIds
  criteriaOwnerUsers { id displayName profilePictureUrl __typename }
  criteriaBusinessEntityIds
  criteriaBusinessEntityIsUnassigned
  criteriaBusinessEntities { id name logoUrl color __typename }
  setMerchantAction { id name __typename }
  setCategoryAction { id name icon __typename }
  addTagsAction { id name color __typename }
  linkGoalAction { id name imageStorageProvider imageStorageProviderId __typename }
  linkSavingsGoalAction { id name imageStorageProvider imageStorageProviderId __typename }
  needsReviewByUserAction { id displayName __typename }
  unassignNeedsReviewByUserAction
  sendNotificationAction
  setHideFromReportsAction
  reviewStatusAction
  actionSetOwnerIsJoint
  actionSetOwner { id displayName profilePictureUrl __typename }
  actionSetBusinessEntity { id name logoUrl color __typename }
  actionSetBusinessEntityIsUnassigned
  recentApplicationCount
  lastAppliedAt
  splitTransactionsAction {
    amountType
    splitsInfo {
      categoryId merchantName amount goalId savingsGoalId tags
      hideFromReports reviewStatus needsReviewByUserId ownerUserId
      ownerIsJoint businessEntityId businessEntityIsUnassigned
      __typename
    }
    __typename
  }
  __typename
}
"""


CREATE_RULE_MUTATION = """
mutation Common_CreateTransactionRuleMutationV2($input: CreateTransactionRuleInput!) {
  createTransactionRuleV2(input: $input) {
    errors { ...PayloadErrorFields __typename }
    __typename
  }
}

fragment PayloadErrorFields on PayloadError {
  fieldErrors { field messages __typename }
  message code __typename
}
"""


UPDATE_RULE_MUTATION = """
mutation Common_UpdateTransactionRuleMutationV2($input: UpdateTransactionRuleInput!) {
  updateTransactionRuleV2(input: $input) {
    errors {
      fieldErrors { field messages __typename }
      message code __typename
    }
    __typename
  }
}
"""


DELETE_RULE_MUTATION = """
mutation Common_DeleteTransactionRule($id: ID!) {
  deleteTransactionRule(id: $id) {
    deleted
    errors {
      fieldErrors { field messages __typename }
      message code __typename
    }
    __typename
  }
}
"""


# ── Helpers ────────────────────────────────────────────────────────────


RULE_INPUT_FIELDS: Tuple[str, ...] = (
    "merchantCriteriaUseOriginalStatement",
    "merchantCriteria",
    "originalStatementCriteria",
    "merchantNameCriteria",
    "amountCriteria",
    "categoryIds",
    "accountIds",
    "setMerchantAction",
    "setCategoryAction",
    "addTagsAction",
    "linkGoalAction",
    "linkSavingsGoalAction",
    "reviewStatusAction",
    "splitTransactionsAction",
    "applyToExistingTransactions",
)


def _strip_meta(obj: Any) -> Any:
    """Recursively strip ``__typename`` keys from any nested mappings/lists."""
    if isinstance(obj, dict):
        return {k: _strip_meta(v) for k, v in obj.items() if k != "__typename"}
    if isinstance(obj, list):
        return [_strip_meta(item) for item in obj]
    return obj


def _extract_id(value: Any) -> Any:
    """Return ``value['id']`` when value is a dict, else value untouched."""
    if isinstance(value, dict):
        return value.get("id", value)
    return value


def _extract_ids(value: Any) -> Any:
    """Map a list of ``{id, ...}`` dicts to a list of plain ids."""
    if isinstance(value, list):
        return [_extract_id(item) for item in value]
    return value


def rule_to_update_input(
    rule: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Build an ``UpdateTransactionRuleInput`` payload.

    The ``updateTransactionRuleV2`` mutation has *replace* semantics:
    any input field omitted is reset to ``null``.  This helper preserves
    the existing rule by copying every input-shaped field from the
    fetched rule, layering ``overrides`` on top, and normalising the
    nested action shapes (which the read fragment expands into objects
    but the input expects as plain ids / strings).

    Args:
        rule: The rule as returned by ``GetTransactionRules`` (a single
            entry from ``transactionRules``).
        overrides: User-supplied field overrides.  Any key in
            :data:`RULE_INPUT_FIELDS` wins over the existing value.

    Returns:
        A dict suitable as the ``input`` variable of the update
        mutation, including the rule's ``id``.
    """
    payload: Dict[str, Any] = {"id": rule["id"]}

    for field in RULE_INPUT_FIELDS:
        if field in overrides:
            payload[field] = _strip_meta(overrides[field])
            continue
        if field not in rule:
            continue
        value = _strip_meta(rule[field])
        if field == "setMerchantAction" and isinstance(value, dict):
            # Input expects the merchant *name* string, not the object.
            payload[field] = value.get("name")
        elif field in (
            "setCategoryAction",
            "linkGoalAction",
            "linkSavingsGoalAction",
        ):
            payload[field] = _extract_id(value)
        elif field == "addTagsAction":
            payload[field] = _extract_ids(value)
        else:
            payload[field] = value

    return payload


__all__: Iterable[str] = (
    "GET_RULES_QUERY",
    "CREATE_RULE_MUTATION",
    "UPDATE_RULE_MUTATION",
    "DELETE_RULE_MUTATION",
    "RULE_INPUT_FIELDS",
    "rule_to_update_input",
)
