from clawsocialarena.protocols import MessageBus, ActionLogger, PolicyHook, ScenarioIO


def test_all_protocols_exported():
    for p in (MessageBus, ActionLogger, PolicyHook, ScenarioIO):
        assert hasattr(p, "__protocol_attrs__") or hasattr(p, "_is_protocol")
