import pytest
import asyncio

from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.protocols import MessageBus


def test_implements_protocol():
    bus = InProcessMessageBus()
    assert isinstance(bus, MessageBus)


async def test_send_and_receive():
    bus = InProcessMessageBus()
    action_id = await bus.send(sender_id="alice", recipient_id="bob", content="hi")
    assert isinstance(action_id, str)
    msg = await bus.recv(recipient_id="bob")
    assert msg == ("alice", "hi")


async def test_recv_empty_returns_none():
    bus = InProcessMessageBus()
    msg = await asyncio.wait_for(bus.recv(recipient_id="bob"), timeout=0.05)
    assert msg is None


async def test_fifo_order():
    bus = InProcessMessageBus()
    await bus.send(sender_id="a", recipient_id="b", content="1")
    await bus.send(sender_id="a", recipient_id="b", content="2")
    assert (await bus.recv(recipient_id="b"))[1] == "1"
    assert (await bus.recv(recipient_id="b"))[1] == "2"
