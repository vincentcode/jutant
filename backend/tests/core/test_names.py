"""Finding a thing by its name: a pack's search proposes, code confirms the name in the question."""

from core.context.entities import named
from core.types import (
    ArgumentSource,
    Caller,
    Citation,
    EntityType,
    Feature,
    ModelReply,
    Prefetch,
    ToolResult,
)
from providers.llm.fake import FakeModel
from tests.builders import make_rig, record_result, spec

PRODUCT = EntityType(
    "product", r"\b([A-Z]{3}-[A-Z]{3})\b", name_field="name", find="services.search_products"
)
NAMES = {
    "standard savings": ("product", "SAV-STD"),
    "business current": ("product", "CUR-BIZ"),
    "youth savings": ("product", "SAV-YTH"),
}
LOOKUP = Feature(
    "product_lookup",
    "record_lookup",
    "Product lookup",
    "Facts about a named bank product.",
    "Answer about the product.",
    ("services.search_products", "services.get_product"),
    (),
    prefetch=(
        Prefetch("services.get_product", {"product_code": ArgumentSource(entity="product")}),
    ),
)
FOUND = ToolResult(
    "",
    ok=True,
    data=[
        {"code": "SAV-STD", "name": "Standard Savings"},
        {"code": "SAV-YTH", "name": "Youth Savings"},
    ],
    citations=(Citation("record", "Product", "SAV-STD"), Citation("record", "Product", "SAV-YTH")),
)
SAVINGS = record_result(
    "Product", "SAV-STD", {"code": "SAV-STD", "name": "Standard Savings", "rate": "8.5%"}
)


def test_a_name_in_the_question_is_found_with_small_slips() -> None:
    assert named("how much interest does standard savings pay", NAMES, "product") == "SAV-STD"
    assert named("Standard Savings rate?", NAMES, "product") == "SAV-STD"
    assert named("standrd savings interest rate", NAMES, "product") == "SAV-STD"
    assert named("what's the fee on business current", NAMES, "product") == "CUR-BIZ"


def test_no_name_or_two_names_find_nothing() -> None:
    assert named("what savings products are there?", NAMES, "product") is None  # "savings" alone
    assert named("standard savings or youth savings?", NAMES, "product") is None  # which one?
    assert named("standard savings", NAMES, "account") is None  # another kind of thing
    assert named("short", {"short": ("product", "X")}, "product") == "X"  # short names: exact only
    assert named("shirt", {"short": ("product", "X")}, "product") is None


async def test_a_product_named_in_the_question_is_looked_up_in_code() -> None:
    model = FakeModel(replies=[ModelReply("rate"), ModelReply("Standard Savings pays 8.5%.")])
    rig = await make_rig(
        model,
        results={"services.search_products": FOUND, "services.get_product": SAVINGS},
        specs=[spec("services.search_products"), spec("services.get_product", {"type": "object"})],
        features=(LOOKUP,),
        entity_types=(PRODUCT,),
        default="product_lookup",
    )
    conversation = await rig.conversations.create(rig_caller())
    events = [
        e
        async for e in rig.orchestrator.ask(
            rig_caller(),
            conversation,
            "how much interest does standard savings pay",
            "product_lookup",
        )
    ]
    calls = [(c.call.name, c.call.arguments) for c in rig.tools.calls]
    assert calls == [
        ("services.search_products", {"query": "how much interest does standard savings pay"}),
        ("services.get_product", {"product_code": "SAV-STD"}),
    ]
    assert events[-1].answer.text == "Standard Savings pays 8.5%."
    assert [c.locator for c in events[-1].answer.citations] == ["SAV-STD"]  # not every search hit


async def test_a_name_the_search_does_not_confirm_leaves_it_to_the_model() -> None:
    model = FakeModel(replies=[ModelReply("We have savings products.")])
    rig = await make_rig(
        model,
        results={"services.search_products": FOUND},
        specs=[spec("services.search_products"), spec("services.get_product", {"type": "object"})],
        features=(LOOKUP,),
        entity_types=(PRODUCT,),
        default="product_lookup",
    )
    conversation = await rig.conversations.create(rig_caller())
    events = [
        e
        async for e in rig.orchestrator.ask(
            rig_caller(), conversation, "which savings products are there?", "product_lookup"
        )
    ]
    assert [c.call.name for c in rig.tools.calls] == ["services.search_products"]
    assert "Youth Savings" in model.calls[0].messages[-1].content  # the hits, to choose from
    assert events[-1].answer.text == "We have savings products."


def rig_caller() -> Caller:
    return Caller("S1", "teller", "staff")
