"""Tests for FS-011: configs/ asset templates + schemas + validate_configs script.

Acceptance (docs/final_state_round_task_list.md FS-011):
- five YAML templates pass their schemas;
- glossary schema contains all 13 fields of spec §7.8 and the 12-category enum;
- templates contain no real translated terms (sanitized fixtures only).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_configs.py"
CONFIGS_DIR = REPO_ROOT / "configs"
SCHEMAS_DIR = REPO_ROOT / "schemas"

GLOSSARY_FIELDS_SPEC_7_8 = [
    "source_term",
    "target_term",
    "reading",
    "category",
    "description",
    "first_seen_chapter",
    "confidence",
    "locked",
    "approved_by_user",
    "aliases",
    "notes",
    "created_at",
    "updated_at",
]

GLOSSARY_CATEGORIES_SPEC_7_8 = {
    "person_name",
    "place_name",
    "organization_name",
    "skill_name",
    "item_name",
    "title",
    "race",
    "magic",
    "system_term",
    "game_term",
    "do_not_translate",
    "other",
}

WORLD_CATEGORIES_SPEC_7_10 = {
    "faction",
    "country",
    "region",
    "magic_system",
    "level_system",
    "skill_system",
    "currency",
    "religion",
    "race",
    "organization",
    "game_system",
    "quest_system",
    "achievement_system",
    "other",
}

# Sanitization marker: template fixture entries must be fictional samples.
SAMPLE_MARKER = "サンプル"


def _load_module():
    mod_name = "light_novel_validate_configs_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def validator():
    return _load_module()


@pytest.fixture(scope="module")
def glossary_schema():
    return json.loads((SCHEMAS_DIR / "glossary.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def glossary_template():
    return yaml.safe_load((CONFIGS_DIR / "glossary.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. All five templates pass their schemas
# ---------------------------------------------------------------------------


def test_all_templates_pass_schemas(validator):
    summary = validator.validate_all()
    failures = [r for r in summary["results"] if not r["valid"]]
    assert summary["status"] == "PASS", failures
    assert len(summary["results"]) == 5


@pytest.mark.parametrize(
    "config_name",
    [
        "glossary.yaml",
        "character_profile.yaml",
        "style_profile.yaml",
        "world_bible.yaml",
        "model_profiles.yaml",
    ],
)
def test_template_exists_and_has_schema_version(config_name):
    data = yaml.safe_load((CONFIGS_DIR / config_name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("schema_version") == 1


# ---------------------------------------------------------------------------
# 2. Glossary schema: 13 fields of spec §7.8 + 12-category enum
# ---------------------------------------------------------------------------


def test_glossary_schema_requires_all_13_fields(glossary_schema):
    entry = glossary_schema["definitions"]["glossary_entry"]
    assert set(entry["required"]) == set(GLOSSARY_FIELDS_SPEC_7_8)
    for field in GLOSSARY_FIELDS_SPEC_7_8:
        assert field in entry["properties"], f"missing property definition: {field}"


def test_glossary_schema_has_12_category_enum(glossary_schema):
    enum = glossary_schema["definitions"]["glossary_entry"]["properties"]["category"]["enum"]
    assert len(enum) == 12
    assert set(enum) == GLOSSARY_CATEGORIES_SPEC_7_8


def test_world_bible_schema_has_14_category_enum():
    schema = json.loads((SCHEMAS_DIR / "world_bible.schema.json").read_text(encoding="utf-8"))
    enum = schema["definitions"]["world_entry"]["properties"]["category"]["enum"]
    assert len(enum) == 14
    assert set(enum) == WORLD_CATEGORIES_SPEC_7_10


# ---------------------------------------------------------------------------
# 3. Negative cases: invalid data must be rejected
# ---------------------------------------------------------------------------


def _first_entry(glossary_template):
    return copy.deepcopy(glossary_template["entries"][0])


def test_glossary_missing_field_rejected(validator, glossary_schema, glossary_template):
    entry = _first_entry(glossary_template)
    entry.pop("locked")
    errors = validator.validate_data({"schema_version": 1, "entries": [entry]}, glossary_schema)
    assert errors and any("locked" in e for e in errors)


def test_glossary_invalid_category_rejected(validator, glossary_schema, glossary_template):
    entry = _first_entry(glossary_template)
    entry["category"] = "not_a_real_category"
    errors = validator.validate_data({"schema_version": 1, "entries": [entry]}, glossary_schema)
    assert errors and any("category" in e for e in errors)


def test_glossary_confidence_out_of_range_rejected(validator, glossary_schema, glossary_template):
    entry = _first_entry(glossary_template)
    entry["confidence"] = 1.5
    errors = validator.validate_data({"schema_version": 1, "entries": [entry]}, glossary_schema)
    assert errors and any("confidence" in e for e in errors)


def test_model_profiles_api_key_rejected(validator):
    schema = json.loads((SCHEMAS_DIR / "model_profiles.schema.json").read_text(encoding="utf-8"))
    data = yaml.safe_load((CONFIGS_DIR / "model_profiles.yaml").read_text(encoding="utf-8"))
    bad = copy.deepcopy(data)
    bad["profiles"][0]["api_key"] = "sk-fake-not-a-real-key"
    errors = validator.validate_data(bad, schema)
    assert errors, "schema must reject profiles carrying api_key"


def test_model_profiles_invalid_role_rejected(validator):
    schema = json.loads((SCHEMAS_DIR / "model_profiles.schema.json").read_text(encoding="utf-8"))
    data = yaml.safe_load((CONFIGS_DIR / "model_profiles.yaml").read_text(encoding="utf-8"))
    bad = copy.deepcopy(data)
    bad["profiles"][0]["role"] = "publish"
    errors = validator.validate_data(bad, schema)
    assert errors and any("role" in e for e in errors)


def test_character_profile_bad_address_map_rejected(validator):
    schema = json.loads(
        (SCHEMAS_DIR / "character_profile.schema.json").read_text(encoding="utf-8")
    )
    data = yaml.safe_load((CONFIGS_DIR / "character_profile.yaml").read_text(encoding="utf-8"))
    bad = copy.deepcopy(data)
    bad["characters"][0]["address_map"] = [{"to": "someone"}]  # missing "address"
    errors = validator.validate_data(bad, schema)
    assert errors and any("address" in e for e in errors)


# ---------------------------------------------------------------------------
# 4. Sanitization: templates must not contain real translated terms
# ---------------------------------------------------------------------------


def test_glossary_template_is_sanitized(glossary_template):
    entries = glossary_template["entries"]
    assert entries, "template should showcase at least one fictional entry"
    for entry in entries:
        assert SAMPLE_MARKER in entry["source_term"], (
            "glossary template entries must be fictional samples "
            f"(source_term should contain {SAMPLE_MARKER!r}): {entry['source_term']!r}"
        )


def test_character_template_is_sanitized():
    data = yaml.safe_load((CONFIGS_DIR / "character_profile.yaml").read_text(encoding="utf-8"))
    for char in data["characters"]:
        assert SAMPLE_MARKER in char["name"]


def test_world_bible_template_is_sanitized():
    data = yaml.safe_load((CONFIGS_DIR / "world_bible.yaml").read_text(encoding="utf-8"))
    for entry in data["entries"]:
        assert SAMPLE_MARKER in entry["name"]


def test_model_profiles_template_has_no_secrets():
    raw = (CONFIGS_DIR / "model_profiles.yaml").read_text(encoding="utf-8")
    lowered = raw.lower()
    for marker in ("sk-or-", "api_key:", "apikey:", "token:", "secret:"):
        assert marker not in lowered, f"model_profiles template must not contain {marker!r}"


# ---------------------------------------------------------------------------
# 5. CLI smoke
# ---------------------------------------------------------------------------


def test_cli_json_pass(validator, capsys):
    code = validator.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert len(payload["results"]) == 5


def test_cli_missing_dir_exit_2(validator, tmp_path):
    code = validator.main(["--configs-dir", str(tmp_path / "nope"), "--json"])
    assert code == 2
