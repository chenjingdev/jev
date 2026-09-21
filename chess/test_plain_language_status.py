import json

import checkmate
import checkmate_prompt
import plain_language_status


def test_requests_contain_no_checkmate_term():
    for row in checkmate.cases():
        _, side = checkmate_prompt.explicit_state(row, "fen")
        for condition in plain_language_status.CONDITIONS:
            specs = plain_language_status.question_specs(side, condition, row["index"])
            rendered = json.dumps({
                name: {"instructions": question.instructions, "criteria": dict(question.criteria)}
                for name, question in specs.items()
            }).lower()
            assert "checkmate" not in rendered


def test_expected_categories_match_ground_truth():
    for row in checkmate.cases():
        expected = plain_language_status.expected_for(row)
        if row["expected"]:
            assert expected == {"danger": "immediate_loss", "escape": "no_escape"}
        else:
            assert expected == {"danger": "can_continue", "escape": "has_escape"}


def test_option_order_shuffle_preserves_meaning():
    for row in checkmate.cases():
        _, side = checkmate_prompt.explicit_state(row, "fen")
        base = plain_language_status.question_specs(side, "base", row["index"])
        shuffled = plain_language_status.question_specs(side, "shuffle", row["index"])
        for name in plain_language_status.QUESTION_NAMES:
            assert dict(base[name].criteria) == {
                key: shuffled[name].criteria[key] for key in base[name].criteria
            }
