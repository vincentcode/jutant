"""An argument the model chooses from the pack's values: the call is then made in code."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from core.features.prefetch import chosen_calls, planned_calls
from core.packs.manifest import ArgumentDef
from core.types import ArgumentSource, ModelReply, Prefetch
from providers.llm.fake import FakeModel
from tests.builders import FEATURES

KINDS = (("joint_opening", "Opening an account held by two people"), ("address", "A new address"))
REQUIREMENTS = Prefetch("services.get_requirements", {"request_type": ArgumentSource(choose=KINDS)})
FEATURE = replace(FEATURES[0], prefetch=(REQUIREMENTS,))


async def test_the_model_picks_a_value_and_the_call_is_made_with_it() -> None:
    model = FakeModel(replies=[ModelReply("joint_opening")])
    [call] = await chosen_calls(model, FEATURE, "who signs for a joint account?")
    assert (call.name, call.arguments) == (
        "services.get_requirements",
        {"request_type": "joint_opening"},
    )
    listing = model.calls[0].messages[0].content
    assert "address: A new address" in listing and "none: none of these" in listing


@pytest.mark.parametrize("reply", ["none", "a joint thing, I think"])
async def test_none_or_no_clear_pick_makes_no_call(reply: str) -> None:
    model = FakeModel(replies=[ModelReply(reply)])
    assert await chosen_calls(model, FEATURE, "how do I open a savings account?") == []


async def test_a_chosen_call_is_not_planned_from_the_words() -> None:
    assert planned_calls(FEATURE, "joint_opening please") == []


def test_choose_is_one_source_of_an_argument() -> None:
    assert ArgumentDef(choose={"a": "A"}).choose == {"a": "A"}
    with pytest.raises(ValidationError):
        ArgumentDef(choose={"a": "A"}, question=True)


ACCOUNT = ArgumentSource(detail="account")
STATUS = Prefetch("accounts.get_status", {"account_number": ACCOUNT}, when="holds or balance")
SIGNERS = Prefetch("accounts.get_mandate", {"account_number": ACCOUNT}, when="who may sign")
CHEQUE = Prefetch(
    "accounts.get_cheque",
    {"account_number": ACCOUNT, "cheque_number": ArgumentSource(detail="cheque")},
    when="a cheque",
)
LOOKUPS = replace(FEATURES[0], prefetch=(STATUS, SIGNERS, CHEQUE))


async def test_of_the_calls_with_a_when_only_the_one_picked_is_made() -> None:
    model = FakeModel(replies=[ModelReply("2")])
    [call] = await chosen_calls(model, LOOKUPS, "who signs?", {}, {"account": "0011223344"})
    assert (call.name, call.arguments) == ("accounts.get_mandate", {"account_number": "0011223344"})
    listing = model.calls[0].messages[0].content
    assert "1: holds or balance" in listing and "none: none of these" in listing
    assert planned_calls(LOOKUPS, "who signs?", {}, {"account": "0011223344"}) == []


@pytest.mark.parametrize("reply", ["none", "3"])  # none fits; or it lacks its cheque number
async def test_no_call_when_none_fits_or_its_details_are_missing(reply: str) -> None:
    model = FakeModel(replies=[ModelReply(reply)])
    assert await chosen_calls(model, LOOKUPS, "hm", {}, {"account": "0011223344"}) == []
