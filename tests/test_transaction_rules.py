"""Tests for transaction-rule CRUD tools and the rule_to_update_input helper."""
# pylint: disable=missing-function-docstring

import json

from monarch_mcp.transaction_rules import (
    RULE_INPUT_FIELDS,
    rule_to_update_input,
)


# ── Sample fixtures ────────────────────────────────────────────────────


SAMPLE_RULE = {
    "id": "rule-1",
    "order": 1,
    "merchantCriteriaUseOriginalStatement": False,
    "merchantCriteria": None,
    "originalStatementCriteria": [
        {"operator": "eq", "value": "AMZN", "__typename": "RuleStringCriteria"},
    ],
    "merchantNameCriteria": [
        {"operator": "contains", "value": "Amazon",
         "__typename": "RuleStringCriteria"},
    ],
    "amountCriteria": {
        "operator": "gt",
        "isExpense": True,
        "value": 10,
        "valueRange": None,
        "__typename": "RuleAmountCriteria",
    },
    "categoryIds": ["cat-1"],
    "accountIds": ["acct-1"],
    "setMerchantAction": {
        "id": "merchant-1",
        "name": "Amazon",
        "__typename": "Merchant",
    },
    "setCategoryAction": {
        "id": "cat-1",
        "name": "Shopping",
        "icon": ":shopping_cart:",
        "__typename": "Category",
    },
    "addTagsAction": [
        {"id": "tag-1", "name": "online", "color": "#abc",
         "__typename": "TransactionTag"},
        {"id": "tag-2", "name": "review", "color": "#def",
         "__typename": "TransactionTag"},
    ],
    "linkGoalAction": None,
    "linkSavingsGoalAction": None,
    "reviewStatusAction": "reviewed",
    "splitTransactionsAction": None,
    "__typename": "TransactionRuleV2",
}


# ── rule_to_update_input helper ────────────────────────────────────────


def test_rule_to_update_input_extracts_ids():
    payload = rule_to_update_input(SAMPLE_RULE, {})

    # Plain id strings, not nested objects.
    assert payload["setCategoryAction"] == "cat-1"
    # setMerchantAction is the merchant *name* string.
    assert payload["setMerchantAction"] == "Amazon"
    # addTagsAction is a flat list of ids.
    assert payload["addTagsAction"] == ["tag-1", "tag-2"]


def test_rule_to_update_input_strips_typename():
    payload = rule_to_update_input(SAMPLE_RULE, {})

    def _has_typename(obj):
        if isinstance(obj, dict):
            if "__typename" in obj:
                return True
            return any(_has_typename(v) for v in obj.values())
        if isinstance(obj, list):
            return any(_has_typename(v) for v in obj)
        return False

    assert not _has_typename(payload)


def test_rule_to_update_input_overrides_take_precedence():
    overrides = {
        "setCategoryAction": "cat-overridden",
        "addTagsAction": ["tag-new"],
        "categoryIds": ["cat-x", "cat-y"],
    }

    payload = rule_to_update_input(SAMPLE_RULE, overrides)

    assert payload["setCategoryAction"] == "cat-overridden"
    assert payload["addTagsAction"] == ["tag-new"]
    assert payload["categoryIds"] == ["cat-x", "cat-y"]
    # Untouched fields preserved.
    assert payload["setMerchantAction"] == "Amazon"


def test_rule_to_update_input_preserves_id():
    assert rule_to_update_input(SAMPLE_RULE, {})["id"] == "rule-1"
    assert (
        rule_to_update_input(SAMPLE_RULE, {"setMerchantAction": "Other"})["id"]
        == "rule-1"
    )


# ── MCP tool tests ─────────────────────────────────────────────────────


async def test_get_transaction_rules_returns_list(mcp_client, mock_monarch_client):
    mock_monarch_client.gql_call.return_value = {
        "transactionRules": [SAMPLE_RULE],
    }

    result = json.loads(
        (await mcp_client.call_tool("get_transaction_rules", {})).content[0].text
    )

    assert result["transactionRules"][0]["id"] == "rule-1"
    call_kwargs = mock_monarch_client.gql_call.call_args[1]
    assert call_kwargs["operation"] == "GetTransactionRules"
    assert call_kwargs["variables"] == {}


async def test_create_transaction_rule_passes_input(mcp_write_client, mock_monarch_client):
    mock_monarch_client.gql_call.return_value = {
        "createTransactionRuleV2": {"errors": None},
    }
    rule_input = {
        "merchantNameCriteria": [{"operator": "contains", "value": "Test"}],
        "setCategoryAction": "cat-99",
        "applyToExistingTransactions": False,
    }

    result = json.loads(
        (await mcp_write_client.call_tool(
            "create_transaction_rule",
            {"rule_input": rule_input},
        )).content[0].text
    )

    assert result["createTransactionRuleV2"]["errors"] is None
    call_kwargs = mock_monarch_client.gql_call.call_args[1]
    assert call_kwargs["operation"] == "Common_CreateTransactionRuleMutationV2"
    assert call_kwargs["variables"] == {"input": rule_input}


async def test_update_transaction_rule_merges_overrides(
    mcp_write_client, mock_monarch_client,
):
    # First call returns rules list, second call returns update payload.
    mock_monarch_client.gql_call.side_effect = [
        {"transactionRules": [SAMPLE_RULE]},
        {"updateTransactionRuleV2": {"errors": None}},
    ]

    result = json.loads(
        (await mcp_write_client.call_tool(
            "update_transaction_rule",
            {
                "rule_id": "rule-1",
                "overrides": {"setCategoryAction": "cat-overridden"},
            },
        )).content[0].text
    )

    assert result["updateTransactionRuleV2"]["errors"] is None
    assert mock_monarch_client.gql_call.call_count == 2

    # Inspect the second call (the update mutation).
    update_call_kwargs = mock_monarch_client.gql_call.call_args_list[1][1]
    assert (
        update_call_kwargs["operation"]
        == "Common_UpdateTransactionRuleMutationV2"
    )
    payload = update_call_kwargs["variables"]["input"]
    assert payload["id"] == "rule-1"
    # Override applied.
    assert payload["setCategoryAction"] == "cat-overridden"
    # Existing fields preserved + normalised.
    assert payload["setMerchantAction"] == "Amazon"
    assert payload["addTagsAction"] == ["tag-1", "tag-2"]
    assert payload["categoryIds"] == ["cat-1"]
    # __typename stripped.
    assert "__typename" not in payload["amountCriteria"]
    # All input fields covered.
    for field in RULE_INPUT_FIELDS:
        if field in SAMPLE_RULE:
            assert field in payload


async def test_update_transaction_rule_missing_id_raises(
    mcp_write_client, mock_monarch_client,
):
    mock_monarch_client.gql_call.return_value = {"transactionRules": []}

    text = (await mcp_write_client.call_tool(
        "update_transaction_rule",
        {"rule_id": "does-not-exist", "overrides": {}},
    )).content[0].text

    assert "Error" in text
    assert "does-not-exist" in text


async def test_delete_transaction_rule_passes_id(
    mcp_write_client, mock_monarch_client,
):
    # Server returns deleted: false even on success — should NOT be treated
    # as a failure by the tool.
    mock_monarch_client.gql_call.return_value = {
        "deleteTransactionRule": {"deleted": False, "errors": None},
    }

    result = json.loads(
        (await mcp_write_client.call_tool(
            "delete_transaction_rule",
            {"rule_id": "rule-99"},
        )).content[0].text
    )

    assert result["deleteTransactionRule"]["errors"] is None
    call_kwargs = mock_monarch_client.gql_call.call_args[1]
    assert call_kwargs["operation"] == "Common_DeleteTransactionRule"
    assert call_kwargs["variables"] == {"id": "rule-99"}


async def test_write_tools_disabled_in_read_only(mcp_client, mock_monarch_client):  # pylint: disable=unused-argument
    tools = [t.name for t in (await mcp_client.list_tools())]
    assert "create_transaction_rule" not in tools
    assert "update_transaction_rule" not in tools
    assert "delete_transaction_rule" not in tools
    # Read tool stays exposed.
    assert "get_transaction_rules" in tools
