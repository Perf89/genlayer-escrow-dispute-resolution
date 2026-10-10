"""
Offline tests for the strict verdict validation in escrow_dispute_resolution.py.

Pure Python, no GenLayer runtime needed: loads only the helper functions
(_validate_verdict, _parse_llm_json) straight from the contract source, so
these tests always exercise the exact code that gets deployed.

    python3 tests/test_verdict_validation.py
"""
import json
import pathlib
import typing

SRC = (pathlib.Path(__file__).parent.parent / "escrow_dispute_resolution.py").read_text()
start = SRC.index('ERROR_EXPECTED = "[EXPECTED]"')
end = SRC.index("@allow_storage")
ns = {"json": json, "typing": typing}
exec(SRC[start:end], ns)
validate, parse = ns["_validate_verdict"], ns["_parse_llm_json"]


def rejects(case):
    try:
        validate(case)
    except ValueError:
        return True
    return False


def test_accepts_well_formed():
    out = validate({"work_satisfies_description": True, "reasoning": "matches the brief"})
    assert out == {"work_satisfies_description": True, "reasoning": "matches the brief"}


def test_accepts_false_verdict():
    out = validate({"work_satisfies_description": False, "reasoning": "missing the API"})
    assert out["work_satisfies_description"] is False


def test_satisfied_must_be_real_boolean():
    for bad in ("true", "false", "False", 0, 1, None):
        assert rejects({"work_satisfies_description": bad, "reasoning": "x"}), bad


def test_reasoning_must_be_string():
    for bad in (5, None, ["a"], {"a": 1}):
        assert rejects({"work_satisfies_description": True, "reasoning": bad}), bad


def test_missing_fields_and_wrong_container():
    assert rejects({"reasoning": "x"})
    assert rejects({"work_satisfies_description": True})
    assert rejects([True, "x"])
    assert rejects("not a dict")


def test_reasoning_is_truncated():
    out = validate({"work_satisfies_description": True, "reasoning": "x" * 900})
    assert len(out["reasoning"]) == 500


def test_parse_tolerates_code_fences():
    assert parse('{"a": 1}') == {"a": 1}
    assert parse('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_accepts_already_parsed_object():
    # exec_prompt may hand back a parsed object instead of text
    assert parse({"a": 1}) == {"a": 1}
    verdict = {"work_satisfies_description": True, "reasoning": "ok"}
    assert validate(parse(verdict))["work_satisfies_description"] is True


def test_parse_rejects_non_text_non_object():
    for bad in (None, 5, 1.5, True):
        try:
            parse(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_parse_rejects_invalid_json_text():
    try:
        parse("not json at all")
    except ValueError:  # json.JSONDecodeError is a ValueError
        return
    raise AssertionError("accepted invalid JSON")


def test_payouts_go_through_evm_recipient_interface():
    # Regression: payouts to plain wallets must use an EVM interface.
    # gl.get_contract_at(addr).emit_transfer(...) targets a GenLayer contract
    # and the transfer fails for a wallet address (value never arrives).
    code = "\n".join(
        line for line in SRC.splitlines()
        if not line.strip().startswith(("#", '"""')) and "gl.get_contract_at(...)" not in line
    )
    assert "@gl.evm.contract_interface" in SRC
    assert "_ExternalRecipient(recipient).emit_transfer(value=amount)" in SRC
    assert ".emit_transfer(" in SRC
    assert "get_contract_at(job." not in code
    # every payout goes through the single helper
    assert SRC.count("self._pay(") == 4


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
