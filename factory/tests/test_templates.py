import pytest
from pathlib import Path
import jinja2


def get_template_env():
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader("factory/templates"),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )


def test_all_templates_parse():
    """Verify all 10 templates parse without syntax errors."""
    env = get_template_env()
    templates = list(Path("factory/templates").glob("*.j2"))
    assert len(templates) == 10, f"Expected 10 templates, found {len(templates)}"
    for t in templates:
        env.get_template(t.name)  # Raises if syntax error


def test_silver_template_renders():
    env = get_template_env()
    template = env.get_template("clickhouse_silver.sql.j2")
    config = {
        "source": {"name": "test_entity"},
        "columns": [
            {"name": "id", "clickhouse_type": "Int32", "is_key": True},
            {"name": "value", "clickhouse_type": "String"},
        ],
        "silver": {
            "engine": "MergeTree",
            "order_by": ["id"],
            "partition_by": None,
        },
    }
    result = template.render(config=config)
    assert "silver.test_entity" in result
    assert "MergeTree" in result
