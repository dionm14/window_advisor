from wa_pure import psychro


def test_to_celsius_variants():
    assert psychro.to_celsius(80.06, "°F") == (80.06 - 32) * 5 / 9
    assert psychro.to_celsius(20.0, "°C") == 20.0
    assert psychro.to_celsius(20.0, None) == 20.0
    assert psychro.to_celsius(293.15, "K") == 20.0
    assert psychro.to_celsius(None, "°F") is None


def test_sat_vapor_pressure_at_20c():
    assert abs(psychro.sat_vapor_pressure(20.0) - 2339) < 30


def test_dewpoint_at_50_rh_20c():
    td = psychro.dewpoint(20.0, 50.0)
    assert abs(td - 9.3) < 0.5


def test_enthalpy_monotone_in_temp():
    a = psychro.enthalpy(15.0, 50.0)
    b = psychro.enthalpy(25.0, 50.0)
    assert b > a


def test_enthalpy_monotone_in_rh():
    a = psychro.enthalpy(25.0, 30.0)
    b = psychro.enthalpy(25.0, 80.0)
    assert b > a


def test_humidity_ratio_zero_at_dry():
    assert psychro.humidity_ratio(25.0, 0.0) == 0.0


def test_wet_bulb_bounded_by_temp_and_dewpoint():
    t, rh = 30.0, 60.0
    td = psychro.dewpoint(t, rh)
    tw = psychro.wet_bulb(t, rh)
    assert td <= tw <= t
