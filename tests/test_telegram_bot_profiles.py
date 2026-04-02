from src.telegram_bot import TelegramBot


def test_profile_selection_defaults_to_ggsel():
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 2},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    assert bot._active_profile(chat_id=123) == 'ggsel'


def test_profile_set_and_read():
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 2},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot._set_profile(123, 'digiseller')
    assert bot._active_profile(chat_id=123) == 'digiseller'
