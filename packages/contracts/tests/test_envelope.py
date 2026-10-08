from fsp_contracts import Envelope, new_envelope


def test_envelope_roundtrip():
    env = new_envelope("offer.sent", "core", {"offer_id": "x"}, correlation_id="rid")
    again = Envelope.model_validate_json(env.model_dump_json())
    assert again == env
    assert again.schema_version == 1
    assert again.occurred_at.tzinfo is not None
