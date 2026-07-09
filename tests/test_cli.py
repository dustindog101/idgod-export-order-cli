from idgod_order_cli.cli import build_parser, main


def test_order_subcommand_with_positional_file():
    args = build_parser().parse_args(
        ["order", "tests/fixtures/orders-two.csv", "--dry-run", "-y"]
    )
    assert args.command == "order"
    assert args.file == "tests/fixtures/orders-two.csv"
    assert args.dry_run is True


def test_implicit_order_subcommand_for_file():
    args = build_parser().parse_args(
        ["order", "tests/fixtures/orders-two.csv", "-y"]
    )
    assert args.file.endswith("orders-two.csv")


def test_main_prepends_order_for_bare_file(tmp_path):
    f = tmp_path / "one.csv"
    f.write_text(
        "State,First Name,Last Name,DOB,City,ZIP\n"
        "WA,A,B,01/01/2000,Seattle,98101\n",
        encoding="utf-8",
    )
    assert main([str(f), "--dry-run", "-y"]) == 0


def test_order_defaults_full_flow():
    args = build_parser().parse_args(
        [
            "order",
            "tests/fixtures/orders-two.csv",
            "--email",
            "a@b.com",
            "--fallback-photo",
            "/tmp/x.jpg",
        ]
    )
    assert args.captcha_solver == "auto"
    assert args.captcha_attempts == 10
    assert args.no_fetch_payment is False
    assert args.payment_method is None
    assert args.shipping_method is None

    from idgod_order_cli.cli import _parse_state_variants

    variants = _parse_state_variants(args.state_variant)
    assert variants == {}  # → cheapest_state True in _cmd_order


def test_payment_and_shipping_choices():
    args = build_parser().parse_args(
        [
            "order",
            "x.csv",
            "--email",
            "a@b.com",
            "--payment-method",
            "litecoin",
            "--shipping-method",
            "express",
        ]
    )
    assert args.payment_method == "litecoin"
    assert args.shipping_method == "express"


def test_proxy_file_uses_first_only():
    from idgod_order_cli.cli import _collect_proxies

    args = build_parser().parse_args(
        ["order", "x.csv", "--proxy-file", "proxies/webshare.txt", "--email", "a@b.com"]
    )
    proxies = _collect_proxies(args)
    assert len(proxies) == 1


def test_probe_subcommand():
    args = build_parser().parse_args(["probe", "--tor", "--method", "httpx"])
    assert args.command == "probe"
    assert args.tor is True
