# Simple Customer Guide (Current)

## 1) What the bot does
- Tracks a competitor's price from a product URL.
- Automatically updates your product price according to the selected pricing mode.
- Supports multiple products in each profile (`GGSEL` / `DIGISELLER`).
- Can send automatic instructions to buyers in order chats.

## 2) Main menu
- `📊 Статус` — short summary for the current active product.
- `📦 Товары` — add a product and/or bind a competitor URL.
- `⬅ Пред. товар` / `➡ След. товар` — switch the active product.
- `🧩 Профиль` — select the marketplace (`GGSEL` or `DIGISELLER`).
- `⚙ Настройки` — pricing mode, automatic pricing and instructions.

> The bot UI is currently Russian, so button labels are kept exactly as they appear in Telegram.

## 3) Quick start
1. Select a marketplace with `🧩 Профиль`.
2. Add a product: `📦 Товары` → send its `ID`.
3. Bind a competitor:
   - immediately: `ID https://competitor-url`
   - or later using the same format.
4. Enable automatic pricing: `⚙ Настройки` → `🔔 Авто: ВКЛ`.
5. Open `📊 Статус` and verify that it shows:
   - your product,
   - the competitor price,
   - the intended pricing mode.

## 4) Managing products
- Add a product: send its `ID` in `📦 Товары`.
- Add a `product + competitor` pair: send `ID URL`.
- Show the list: send `list` in `📦 Товары`.
- Remove a product: `⚙ Настройки` → `🗑 Удалить товар`, then send an `ID` or `active`.

Important:
- The bot monitors **every product in the list**.
- Settings are edited for the **active product**, selected with `⬅/➡`.

## 5) Pricing modes
Switch modes through `⚙ Настройки` → `🔀 Режим`.

- `Следование` (Follow)
  - price = exactly the competitor price, with 4 decimal places.
  - example: `0.3560 -> 0.3560`

- `Демпинг` (Undercut)
  - based on the storefront price rounded to 2 decimals: `round(competitor_price, 2) - 0.0051`
  - example: `0.3505 -> 0.35 -> 0.3449`

- `Повышение` (Raise)
  - based on the storefront price rounded to 2 decimals: `round(competitor_price, 2) + 0.0049`
  - example: `0.3505 -> 0.35 -> 0.3549`

## 6) Automatic order-chat instructions
Configure these under `⚙ Настройки`:

- `💬 Инструкции: ВКЛ/ВЫКЛ`
- `📭 Только пустой чат: ВКЛ/ВЫКЛ`
  - ON: send only when the chat is empty.
  - OFF: sending is also allowed in a non-empty chat.
- `🧠 Умный непустой: ВКЛ/ВЫКЛ`
  - additional filtering for non-empty chats to avoid completed conversations.
- `🧭 Режим отправки` for the active product:
  - `После заказа` — send immediately after a new order appears.
  - `После 1-го сообщения` — send only after the buyer's first message.
  - `Только при коде` — send only when the buyer's message contains the configured code.

## 7) Instruction rules by product option
Open `⚙ Настройки` → `📝 Правила инстр.`.

How it works:
- The bot lists the available product-option variants.
- Enable or disable variants with the inline buttons under the message.
- If at least one rule is enabled, instructions are sent only for enabled variants.
- If a rule has no custom text, the instruction text is taken from the product card.

Optional commands in this mode:
- `text <number> <text>` — set custom text for a specific variant.
- `clear <number>` — clear custom text.
- `reset` — reset the rules.
- `done` — exit the editor.

## 8) Reading status
In `📊 Статус`, check:
- `Площадка` and `Активный товар`.
- `Моя цена` and `Выставлено ботом`.
- `Цена конкурента` + `URL`.
- `Режим` and `Авто: ВКЛ/ВЫКЛ`.
- the automatic-instructions block, when the profile supports it.

## 9) If something did not work
- Price did not change:
  - verify that a competitor `URL` is bound;
  - verify that `🔔 Авто` is enabled;
  - verify that you selected the intended profile and active product.
- Instruction was not sent:
  - verify `💬 Инструкции: ВКЛ`;
  - verify `🧭 Режим отправки`;
  - verify `📭 Только пустой чат` and `📝 Правила инстр.` rules.
