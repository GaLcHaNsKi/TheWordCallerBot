# Telegram-бот совместного чтения Библии

Бот для супергрупп Telegram с темами: ежедневно публикует главу Синодального перевода, хранит прогресс в MySQL, учитывает активность только в привязанной теме и публикует недельные номинации.

## Установка

Нужны Python 3.11+, MySQL и бот Telegram. В BotFather отключите **Privacy Mode**; в группе дайте боту права администратора и право писать в темах.

```bash
sudo mysql -e "CREATE DATABASE bible_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'bible_bot'@'localhost' IDENTIFIED BY 'длинный-пароль'; GRANT ALL PRIVILEGES ON bible_bot.* TO 'bible_bot'@'localhost'; FLUSH PRIVILEGES;"
cd /opt/bible-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Заполните `BOT_TOKEN` и параметры MySQL в `.env`, затем выполните:

```bash
.venv/bin/python -m app.main
```

Миграция и каталог 66 книг применяются автоматически при первом запуске. Для systemd отредактируйте пути и пользователя в `bible-bot.service`, затем:

```bash
sudo cp bible-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bible-bot
sudo systemctl status bible-bot
journalctl -u bible-bot -f
```

## Настройка в Telegram

1. В нужной теме выполните `/bind` от имени администратора.
2. Выберите книгу: `/setbook ин` или `/setbook рим 5`.
3. При необходимости измените `/timezone`, `/time` и `/weektime`.

По умолчанию используется UTC, главы выходят в 08:00, еженедельный отчёт — в воскресенье в 21:00. Первый отчёт охватывает время от `/bind`.

## Команды

Публичные: `/help`, `/books`, `/status`, `/progress`, `/today`, `/stats`, `/report`, `/report last`.

Административные: `/bind`, `/setbook`, `/time`, `/weektime`, `/timezone`, `/pause`, `/resume`, `/postnow`.

## Тесты

```bash
.venv/bin/pytest -q
```

Тесты не обращаются к Telegram и не делают массовых публикаций.

## Эксплуатационные заметки

- Все даты в MySQL — UTC; локальное время применяется только для расписаний и временных номинаций.
- Полные тексты пользовательских сообщений не записываются.
- При недоступности Midvash используется сохранённый кэш главы.
- Перед рабочим запуском проверьте RSS: `ps -o rss= -p $(systemctl show -p MainPID --value bible-bot)`.
