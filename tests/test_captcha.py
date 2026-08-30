from idgod_order_cli.captcha import captcha_variants, normalize_captcha_text


def test_normalize_strips_noise():
    assert normalize_captcha_text("  ab-12!  ") == "ab12"


def test_captcha_variants_case():
    variants = captcha_variants("Ab3x")
    assert variants == ["Ab3x", "ab3x", "AB3X"]


def test_captcha_variants_empty():
    assert captcha_variants("!!!") == []


def test_pick_consensus():
    from idgod_order_cli.captcha import pick_consensus

    result = pick_consensus(
        [
            {"solver": "ppllocr", "guess": "ab12cd", "raw_text": "ab12cd", "text": "ab12cd"},
            {"solver": "ddddocr", "guess": "ab12", "raw_text": "ab12", "text": "ab12"},
            {"solver": "ddddocr", "guess": "ab12", "raw_text": "ab12x", "text": "ab12x", "variant": "contrast"},
        ]
    )
    assert result is not None
    assert result["guess"] == "ab12"
    assert result["consensus_votes"] == 2


def test_preprocess_returns_raw_without_pillow():
    from idgod_order_cli.captcha import preprocess_captcha_variants

    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    variants = preprocess_captcha_variants(data)
    assert variants[0][0] == "raw"
    assert variants[0][1] == data


def test_plausible_captcha_length():
    from idgod_order_cli.captcha import plausible_captcha_length

    assert plausible_captcha_length("ab12")
    assert plausible_captcha_length("Ab3xY")
    assert not plausible_captcha_length("ENXGHFXHG")
    assert not plausible_captcha_length("ab")


def test_unpack_captcha_result():
    from idgod_order_cli.captcha import unpack_captcha_result

    result = {
        "solver": "ddddocr",
        "text": "Ab3xY",
        "raw_text": "Ab3xY",
        "guess": "ab3xy",
        "consensus_votes": 8,
        "ocr_reads": 12,
    }
    guess, raw, solver, votes, reads = unpack_captcha_result(result)
    assert guess == "ab3xy"
    assert raw == "Ab3xY"
    assert solver == "ddddocr"
    assert votes == 8
    assert reads == 12


def test_best_captcha_guess_trims_overlong():
    from idgod_order_cli.captcha import best_captcha_guess

    guess = best_captcha_guess("XXFWKUGs")
    assert 4 <= len(guess) <= 6
    assert guess == "xxfwk"
    assert 4 <= len(best_captcha_guess("ENXGHFXHG")) <= 6
    assert best_captcha_guess("Ab3x") == "ab3x"
