from idgod_order_cli.captcha import captcha_variants, normalize_captcha_text


def test_normalize_strips_noise():
    assert normalize_captcha_text("  ab-12!  ") == "ab12"


def test_captcha_variants_case():
    variants = captcha_variants("Ab3x")
    assert variants == ["Ab3x", "ab3x", "AB3X"]


def test_captcha_variants_empty():
    assert captcha_variants("!!!") == []


def test_plausible_captcha_length():
    from idgod_order_cli.captcha import plausible_captcha_length

    assert plausible_captcha_length("ab12")
    assert plausible_captcha_length("Ab3xY")
    assert not plausible_captcha_length("ENXGHFXHG")
    assert not plausible_captcha_length("ab")


def test_best_captcha_guess_trims_overlong():
    from idgod_order_cli.captcha import best_captcha_guess

    guess = best_captcha_guess("XXFWKUGs")
    assert 4 <= len(guess) <= 6
    assert guess == "xxfwk"
    assert 4 <= len(best_captcha_guess("ENXGHFXHG")) <= 6
    assert best_captcha_guess("Ab3x") == "ab3x"
