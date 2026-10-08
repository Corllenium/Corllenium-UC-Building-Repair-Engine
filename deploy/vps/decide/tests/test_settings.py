from decide_service.settings import Settings


def test_defaults_keep_jev_off():
    s = Settings.from_env({})
    assert s.jev_enabled is False and s.daily_token_cap == 1_000_000 and s.min_confidence == 0.8
    assert s.owner_users == frozenset({"gab"}) and s.engine_user == "uc-engine" and s.database_url == ""


def test_env_values_are_read_and_the_url_is_not_in_repr():
    s = Settings.from_env({"DECIDE_JEV_ENABLED": "true", "DECIDE_DAILY_TOKEN_CAP": "500", "DECIDE_MIN_CONFIDENCE": "0.9",
                           "DECIDE_OWNER_USERS": "gab, ana", "DECIDE_DATABASE_URL": "postgresql://u:secret@h/db"})
    assert s.jev_enabled is True and s.daily_token_cap == 500 and s.min_confidence == 0.9
    assert s.owner_users == frozenset({"gab", "ana"}) and s.database_url.endswith("@h/db")
    assert "secret" not in repr(s)
