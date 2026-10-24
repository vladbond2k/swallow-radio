# jpfly — дешёвые билеты в Японию

Собирает цены из **Google Flights** (живые, через [fast-flights](https://github.com/AWeirdDev/fast-flights)) и **Aviasales** (официальный бесплатный API, цены, найденные пользователями за последние дни) по всем датам вылета и длинам поездки, и показывает всё в одной таблице с фильтрами и сортировкой.

- Google: перебирает билеты в одну сторону на каждый день туда и обратно, склеивает в поездки (можно прилететь в Токио, улететь из Осаки), лучшие 20 перепроверяет как один билет туда-обратно.
- Aviasales: билеты туда-обратно из кеша — быстро, есть лоукостеры, но цена может быть устаревшей.

Результат: `out/report.html` (открыть в браузере) и `out/trips.csv`.

## Онлайн (GitHub Actions + Pages)

Отчёт: **https://vladbond2k.github.io/swallow-radio/** — обновляется каждый день и по кнопке.

Настройка один раз:
1. Settings → Pages → Source: **GitHub Actions**.
2. Settings → Secrets and variables → Actions → New repository secret: `TRAVELPAYOUTS_TOKEN` (токен Aviasales, необязательно).
3. Actions → Search flights → Run workflow. Через ~10 минут отчёт по ссылке выше.

Параметры поиска — в `config.toml` (можно править прямо на GitHub).

## Запуск локально

```bash
git clone https://github.com/vladbond2k/swallow-radio && cd swallow-radio
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
# при желании поправь config.toml: аэропорты, даты, длина поездки
jpfly                   # ~5–15 минут на первый прогон, повторные быстрые (кеш)
open out/report.html    # Windows: start out\report.html
```

Без сети попробовать: `jpfly --demo`.

**Aviasales**: зарегистрируйся на [travelpayouts.com](https://www.travelpayouts.com), возьми API-токен в профиле и вставь в `[aviasales] token` в `config.toml` (или `export TRAVELPAYOUTS_TOKEN=...`). Без токена работает только Google.

## Нюансы

- Google при большом числе запросов может начать отдавать капчу: держи `workers` 2–3, `delay` ≥ 1. Упавший прогон просто перезапусти — уже скачанное берётся из `.cache/`.
- Цены в отчёте — снимок; финальную цену смотри по ссылке перед покупкой.
- Число запросов к Google ≈ (домашние аэропорты × японские аэропорты × дни). Хочешь быстрее — сократи аэропорты в конфиге.
