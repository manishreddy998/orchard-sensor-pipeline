from src.synth_sensors import generate


def test_generator_is_deterministic_and_labelled():
    m1, t1, reg = generate()
    m2, _, _ = generate()
    assert m1.equals(m2)
    assert len(reg) == 36
    assert {"spike", "stuck"} <= set(t1.fault.unique())
    assert t1.duplicates_sent.sum() == len(m1) - len(t1)
