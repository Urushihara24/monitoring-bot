from scripts import smoke_instruction_data as sid


def test_ggsel_product_ids_prefers_chat_list_then_default(monkeypatch):
    monkeypatch.setattr(
        sid.config,
        'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS',
        [4697439, '4697439', 'bad', 4700000],
        raising=False,
    )
    monkeypatch.setattr(
        sid.config,
        'GGSEL_PRODUCT_ID',
        4697439,
        raising=False,
    )

    ids = sid._ggsel_product_ids()

    assert ids == [4697439, 4700000]


def test_ggsel_product_ids_fallback_to_default_product_id(monkeypatch):
    monkeypatch.setattr(
        sid.config,
        'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS',
        [],
        raising=False,
    )
    monkeypatch.setattr(
        sid.config,
        'GGSEL_PRODUCT_ID',
        4697439,
        raising=False,
    )

    ids = sid._ggsel_product_ids()

    assert ids == [4697439]
