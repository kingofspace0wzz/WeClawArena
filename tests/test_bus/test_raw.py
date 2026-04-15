from clawsocialarena.bus.raw import RawMessageBus
from clawsocialarena.protocols import MessageBus


def test_implements_protocol():
    bus = RawMessageBus()
    assert isinstance(bus, MessageBus)


async def test_raw_bus_delivers_messages():
    bus = RawMessageBus()
    action_id = await bus.send(sender_id="a", recipient_id="b", content="hi")
    assert isinstance(action_id, str)
    assert (await bus.recv(recipient_id="b")) == ("a", "hi")


async def test_raw_bus_has_no_log_attribute():
    """RawMessageBus must not expose an action_log or shadow_log."""
    bus = RawMessageBus()
    assert not hasattr(bus, "_log")
    assert not hasattr(bus, "_shadow")
