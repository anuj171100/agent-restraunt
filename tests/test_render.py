from datetime import datetime

from src.models import Inputs
from src.render import render_transcript, write_run

LUNCH = Inputs(city="London", meal="lunch", diet="vegetarian", note="sit-down")


def test_transcript_shows_the_call_the_result_and_the_answer():
    text = render_transcript(
        LUNCH,
        [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "Recommend restaurants for this trip."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "fetch_page",
                            "arguments": '{"url": "https://mildreds.co.uk/menus"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Roast vegetable tart 14.50",
            },
            {"role": "assistant", "content": "Primary: Mildreds"},
        ],
    )
    assert "City: London" in text
    assert "## fetch_page" in text
    assert "https://mildreds.co.uk/menus" in text
    assert "### Result (fetch_page)" in text
    assert "Roast vegetable tart 14.50" in text
    assert "## Final answer" in text
    assert "Primary: Mildreds" in text
    assert "instructions" not in text


def test_write_run_uses_the_timestamp_and_does_not_overwrite(tmp_path):
    moment = datetime(2026, 10, 25, 21, 12, 0)
    first = write_run(tmp_path, "one", now=moment)
    second = write_run(tmp_path, "two", now=moment)
    assert first.name == "20261025-211200.md"
    assert first.read_text(encoding="utf-8") == "one"
    assert second.name != first.name
    assert second.read_text(encoding="utf-8") == "two"
