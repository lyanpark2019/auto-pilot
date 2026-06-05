from scripts._dogfood_noop import dogfood_identity


def test_identity() -> None:
    assert dogfood_identity(7) == 7
