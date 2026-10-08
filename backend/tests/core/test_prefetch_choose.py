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
