"""Tests for src/services/policy_settings.py.

Covers:
  - validate_overrides(): pure-function, no mocks required
  - update_user_policy(): Supabase admin client is mocked at the service level
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.services.policy_engine import CONSTRAINTS
from src.services.policy_settings import (
    OverrideValidationError,
    update_user_policy,
    validate_overrides,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pick a well-known constraint key for boundary / range tests so the expected
# values are always derived from the real CONSTRAINTS dict, never hard-coded.
_SAMPLE_KEY = "max_single_position_pct"
_SAMPLE_MIN = CONSTRAINTS[_SAMPLE_KEY]["min"]    # 3
_SAMPLE_MAX = CONSTRAINTS[_SAMPLE_KEY]["max"]    # 10


def _make_mock_admin(select_data=None):
    """Return a MagicMock that faithfully mimics the Supabase admin client chain.

    The mock satisfies these call patterns used in update_user_policy():

        admin.table("user_policy")
             .select("policy_mode, preset_id, policy_overrides, cooldown_until")
             .eq("user_id", user_id)
             .execute()
        --> SimpleNamespace(data=select_data or [])

        admin.table("user_policy")
             .upsert(..., on_conflict="user_id")
             .execute()
        --> MagicMock (return value not inspected)

        admin.table("policy_change_log")
             .insert(...)
             .execute()
        --> MagicMock (return value not inspected)

    Because both `upsert` and `insert` are chained off `.table(...)`, we route
    the correct execute() response by inspecting which table was called.
    """
    mock = MagicMock()

    # user_policy table: select chain returns select_data; upsert chain is a no-op
    user_policy_table = MagicMock()
    select_chain = MagicMock()
    select_chain.eq.return_value.execute.return_value = SimpleNamespace(
        data=select_data if select_data is not None else []
    )
    user_policy_table.select.return_value = select_chain
    user_policy_table.upsert.return_value.execute.return_value = MagicMock()

    # policy_change_log table: insert chain is a no-op
    change_log_table = MagicMock()
    change_log_table.insert.return_value.execute.return_value = MagicMock()

    def _table_router(name):
        if name == "user_policy":
            return user_policy_table
        if name == "policy_change_log":
            return change_log_table
        return MagicMock()

    mock.table.side_effect = _table_router
    return mock, user_policy_table, change_log_table


# ---------------------------------------------------------------------------
# Class 1: validate_overrides (pure-function tests, no mocks)
# ---------------------------------------------------------------------------


class TestValidateOverrides:
    def test_beginner_returns_empty(self):
        """BEGINNER mode must discard any supplied overrides and return {}."""
        result = validate_overrides("BEGINNER", {_SAMPLE_KEY: _SAMPLE_MIN + 1})
        assert result == {}

    def test_preset_returns_empty(self):
        """PRESET mode must discard any supplied overrides and return {}."""
        result = validate_overrides("PRESET", {_SAMPLE_KEY: _SAMPLE_MIN + 1})
        assert result == {}

    def test_advanced_valid_overrides(self):
        """ADVANCED mode must return valid overrides unchanged."""
        overrides = {_SAMPLE_KEY: _SAMPLE_MIN + 1}
        result = validate_overrides("ADVANCED", overrides)
        assert result == overrides

    def test_advanced_unknown_key(self):
        """ADVANCED mode must reject keys that are not in CONSTRAINTS."""
        with pytest.raises(OverrideValidationError, match="Unknown override key"):
            validate_overrides("ADVANCED", {"nonexistent_setting": 5})

    def test_advanced_value_too_high(self):
        """ADVANCED mode must reject values above the constraint maximum."""
        with pytest.raises(OverrideValidationError, match="outside"):
            validate_overrides("ADVANCED", {_SAMPLE_KEY: _SAMPLE_MAX + 1})

    def test_advanced_value_too_low(self):
        """ADVANCED mode must reject values below the constraint minimum."""
        with pytest.raises(OverrideValidationError, match="outside"):
            validate_overrides("ADVANCED", {_SAMPLE_KEY: _SAMPLE_MIN - 1})

    def test_advanced_boundary_min(self):
        """ADVANCED mode must accept a value equal to the constraint minimum."""
        overrides = {_SAMPLE_KEY: _SAMPLE_MIN}
        result = validate_overrides("ADVANCED", overrides)
        assert result == overrides

    def test_advanced_boundary_max(self):
        """ADVANCED mode must accept a value equal to the constraint maximum."""
        overrides = {_SAMPLE_KEY: _SAMPLE_MAX}
        result = validate_overrides("ADVANCED", overrides)
        assert result == overrides

    def test_advanced_empty_overrides(self):
        """ADVANCED mode with an empty overrides dict must return {}."""
        result = validate_overrides("ADVANCED", {})
        assert result == {}


# ---------------------------------------------------------------------------
# Class 2: update_user_policy (Supabase admin is mocked)
# ---------------------------------------------------------------------------


class TestUpdateUserPolicy:
    @patch("src.services.policy_settings.get_supabase_admin")
    def test_new_user_preset_change_sets_cooldown(self, mock_get_admin):
        """A new user (no existing row) must receive a 24-hour cooldown."""
        mock_admin, _, _ = _make_mock_admin(select_data=[])
        mock_get_admin.return_value = mock_admin

        result = update_user_policy(
            user_id="new-user-001",
            policy_mode="PRESET",
            preset_id="active",
            effective_overrides={},
        )

        assert result["cooldown_until"] is not None

    @patch("src.services.policy_settings.get_supabase_admin")
    def test_same_preset_no_cooldown(self, mock_get_admin):
        """Saving the identical preset must NOT trigger a cooldown."""
        existing_row = {
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
            "cooldown_until": None,
        }
        mock_admin, _, _ = _make_mock_admin(select_data=[existing_row])
        mock_get_admin.return_value = mock_admin

        result = update_user_policy(
            user_id="user-002",
            policy_mode="PRESET",
            preset_id="balanced",
            effective_overrides={},
        )

        assert result["cooldown_until"] is None

    @patch("src.services.policy_settings.get_supabase_admin")
    def test_mode_change_sets_cooldown(self, mock_get_admin):
        """Switching from PRESET to ADVANCED mode must trigger a 24-hour cooldown."""
        existing_row = {
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
            "cooldown_until": None,
        }
        mock_admin, _, _ = _make_mock_admin(select_data=[existing_row])
        mock_get_admin.return_value = mock_admin

        result = update_user_policy(
            user_id="user-003",
            policy_mode="ADVANCED",
            preset_id="balanced",
            effective_overrides={_SAMPLE_KEY: _SAMPLE_MIN + 1},
        )

        assert result["cooldown_until"] is not None

    @patch("src.services.policy_settings.get_supabase_admin")
    def test_change_log_written(self, mock_get_admin):
        """The policy_change_log insert must record accurate old and new values."""
        existing_row = {
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {},
            "cooldown_until": None,
        }
        mock_admin, _, change_log_table = _make_mock_admin(select_data=[existing_row])
        mock_get_admin.return_value = mock_admin

        new_overrides = {_SAMPLE_KEY: _SAMPLE_MIN + 2}
        update_user_policy(
            user_id="user-004",
            policy_mode="ADVANCED",
            preset_id="balanced",
            effective_overrides=new_overrides,
        )

        change_log_table.insert.assert_called_once()
        inserted_payload = change_log_table.insert.call_args[0][0]

        assert inserted_payload["user_id"] == "user-004"
        assert inserted_payload["old_mode"] == "BEGINNER"
        assert inserted_payload["new_mode"] == "ADVANCED"
        assert inserted_payload["old_preset"] == "beginner"
        assert inserted_payload["new_preset"] == "balanced"
        assert inserted_payload["old_overrides"] == {}
        assert inserted_payload["new_overrides"] == new_overrides

    @patch("src.services.policy_settings.get_supabase_admin")
    def test_db_error_propagates(self, mock_get_admin):
        """A database error inside execute() must propagate uncaught."""
        mock_admin = MagicMock()
        # Make the SELECT chain raise immediately
        mock_admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception(
            "DB connection refused"
        )
        mock_get_admin.return_value = mock_admin

        with pytest.raises(Exception, match="DB connection refused"):
            update_user_policy(
                user_id="user-005",
                policy_mode="PRESET",
                preset_id="balanced",
                effective_overrides={},
            )
