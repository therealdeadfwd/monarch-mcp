"""Live e2e tests for transaction-rule tools — lifecycle + live error paths.

Monarch lowercases rule criteria values, so a rule created with merchant value
"MCP-Test-..." is stored/returned as "mcp-test-...".
"""
# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest

pytestmark = pytest.mark.integration


def _find_rule_id(rules, needle):
    needle = needle.lower()
    for rule in rules:
        values = [c.get("value", "") for c in (rule.get("merchant_name_criteria") or [])]
        values += [c.get("value", "") for c in (rule.get("original_statement_criteria") or [])]
        if any(needle in (v or "").lower() for v in values):
            return rule.get("id")
    return None


async def test_rule_create_list_delete_lifecycle(
    live_write_client, call_json, call_text, maybe_json, category_id
):
    merchant = "MCP-Test-Rule-Merchant"
    created = maybe_json(
        await call_text(
            live_write_client, "create_transaction_rule",
            {"set_category_id": category_id, "merchant_name_value": merchant},
        )
    )
    assert isinstance(created, dict) and created.get("created") is True, created

    rule_id = None
    try:
        rules = await call_json(live_write_client, "get_transaction_rules")
        assert isinstance(rules, list)
        rule_id = _find_rule_id(rules, merchant)
        assert rule_id, f"created rule not found in get_transaction_rules: {rules}"
    finally:
        if rule_id:
            deleted = maybe_json(
                await call_text(
                    live_write_client, "delete_transaction_rule", {"rule_id": rule_id}
                )
            )
            assert deleted == {"deleted": True, "rule_id": rule_id}

    # confirm it is gone
    rules_after = await call_json(live_write_client, "get_transaction_rules")
    assert _find_rule_id(rules_after, merchant) is None


async def test_delete_rule_invalid_id_is_graceful(live_write_client, call_text, maybe_json):
    text = await call_text(
        live_write_client, "delete_transaction_rule", {"rule_id": "000000000000000000"}
    )
    assert "Traceback" not in text, text[:300]
    data = maybe_json(text)
    # Monarch returns "Not found" → decorator yields an "Error ..." string.
    assert text.startswith("Error ") or (isinstance(data, dict) and "error" in data), text[:300]
