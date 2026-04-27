from followthemoney import model


def test_custom_schemata_are_loaded() -> None:
    meeting = model.get("Meeting")
    donation = model.get("Donation")
    gift = model.get("Gift")
    hospitality = model.get("Hospitality")

    assert meeting is not None
    assert donation is not None
    assert gift is not None
    assert hospitality is not None

    assert meeting.is_a("Event")
    assert donation.is_a("Payment")
    assert gift.is_a("Payment")
    assert hospitality.is_a("Payment")
    assert hospitality.is_a("Event")
