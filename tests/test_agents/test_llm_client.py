from clawsocialarena.agents.llm_client import LLMClient, MockLLMClient, LLMMessage


def test_mock_client_implements_protocol():
    c = MockLLMClient(canned_responses=["hi"])
    assert isinstance(c, LLMClient)


def test_mock_client_returns_canned_responses_in_order():
    c = MockLLMClient(canned_responses=["first", "second"])
    msg1 = c.complete(messages=[LLMMessage(role="user", content="q1")], tools=None, params={})
    msg2 = c.complete(messages=[LLMMessage(role="user", content="q2")], tools=None, params={})
    assert msg1.content == "first"
    assert msg2.content == "second"


def test_mock_client_loops_if_exhausted():
    c = MockLLMClient(canned_responses=["only"])
    msg1 = c.complete(messages=[], tools=None, params={})
    msg2 = c.complete(messages=[], tools=None, params={})
    assert msg1.content == msg2.content == "only"
