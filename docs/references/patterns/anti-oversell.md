# Pattern: Anti-Oversell (резервации без перепродажи)

Статус: Phase 1, Sprint 3.
Ссылается из: `phase1-plan-additions.md` §3.1.

## Проблема

Несколько покупателей одновременно резервируют ограниченную акцию
(`Promotion.available_quantity`). Наивный код

```python
promo = Promotion.objects.get(id=promotion_id)   # читаем остаток
if promo.available_quantity >= qty:              # проверяем
    promo.available_quantity -= qty              # списываем в Python
    promo.save()
```

содержит гонку «read → check → write»: между чтением и сохранением другой
запрос успевает списать тот же остаток → перепродажа (oversell).

## Решение: conditional UPDATE с F()

Списание и проверка выполняются **одним атомарным SQL-UPDATE** на стороне БД.
PostgreSQL берёт row-lock на время апдейта, поэтому два параллельных UPDATE
по одной строке сериализуются автоматически — даже на дефолтном уровне
изоляции READ COMMITTED.

```python
# apps/promotions/services.py
from django.db import transaction
from django.db.models import F
from django.utils import timezone


class OutOfStock(Exception):
    """Недостаточно доступного количества для резерва."""


@transaction.atomic
def reserve(promotion_id: int, *, customer, quantity: int = 1):
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    # Атомарное условное списание. rows == 0 ⇒ остатка не хватило ИЛИ акция
    # уже не active. Гонки нет: условие и декремент в одном UPDATE.
    rows = (
        Promotion.objects.filter(
            id=promotion_id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
    )
    if rows == 0:
        raise OutOfStock()

    # Остаток уже списан — создаём резерв в той же транзакции.
    return Reservation.objects.create(
        promotion_id=promotion_id,
        customer=customer,
        quantity=quantity,
        status="confirmed",
        reserved_at=timezone.now(),
    )
```

### Почему этого достаточно

- `UPDATE ... WHERE available_quantity >= N` под капотом берёт `FOR UPDATE`
  на затронутую строку. Параллельный UPDATE ждёт коммита первого и
  перечитывает актуальное значение (`READ COMMITTED` re-evaluation). Поэтому
  суммарно нельзя списать больше, чем есть.
- `F()` гарантирует, что декремент считает БД от текущего значения, а не от
  прочитанного в Python (которое могло устареть).
- `select_for_update()` **не нужен** для самого списания и только сужает
  пропускную способность лишней блокировкой.

## Когда нужен SERIALIZABLE

Conditional UPDATE закрывает случай «остаток в одной строке». Если бизнес-
операция многошаговая и должна быть консистентна целиком (например: списать
остаток **и** проверить агрегатный лимит по нескольким акциям / записать в
связанную таблицу, от которой зависит решение), оборачиваем в SERIALIZABLE и
ретраим сериализационные сбои:

```python
from django.db import transaction, OperationalError
from psycopg import errors

def reserve_serializable(...):
    for attempt in range(3):
        try:
            with transaction.atomic():
                connection.cursor().execute(
                    "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
                )
                ...  # многошаговая логика
            return result
        except OperationalError as exc:
            if isinstance(exc.__cause__, errors.SerializationFailure) and attempt < 2:
                continue            # ретраим конфликт
            raise
```

Для Phase 1 (один остаток на акцию) хватает базового conditional UPDATE —
SERIALIZABLE избыточен.

## Возврат остатка (отмена резерва)

Симметричный инкремент, тоже одним UPDATE:

```python
@transaction.atomic
def cancel(reservation_id: int):
    res = (
        Reservation.objects.select_for_update()
        .filter(id=reservation_id, status="confirmed")
        .first()
    )
    if res is None:
        return  # идемпотентно: уже отменён/не существует
    Promotion.objects.filter(id=res.promotion_id).update(
        available_quantity=F("available_quantity") + res.quantity
    )
    res.status = "cancelled"
    res.save(update_fields=["status", "updated_at"])
```

`select_for_update()` тут уместен — он защищает от двойной отмены того же
резерва (double-refund).

## Тестирование (обязательный DoD)

Тест должен быть **настоящим параллельным**, иначе он маскирует гонку.

- `TransactionTestCase`, **не** `TestCase` — последний оборачивает тест в одну
  транзакцию, и параллельные коннекты не увидят данные.
- Реальные потоки через `ThreadPoolExecutor`. Под GIL это валидно: потоки
  блокируются на стороне БД (row-lock), а не на Python-байткоде.
- Каждый поток открывает своё соединение: вызывать
  `connection.close()` в начале воркера, чтобы Django выдал новый коннект.

```python
from concurrent.futures import ThreadPoolExecutor
from django.db import connection
from django.test import TransactionTestCase


class ReserveConcurrencyTest(TransactionTestCase):
    def test_no_oversell_under_parallel_load(self):
        promo = PromotionFactory(status="active", available_quantity=50)

        def worker(_):
            connection.close()  # своё соединение на поток
            try:
                reserve(promo.id, customer=CustomerFactory(), quantity=1)
                return True
            except OutOfStock:
                return False

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(worker, range(100)))

        promo.refresh_from_db()
        assert sum(results) == 50            # ровно 50 успешных
        assert results.count(False) == 50    # ровно 50 отказов
        assert promo.available_quantity == 0 # ноль перепродаж
        assert Reservation.objects.filter(promotion=promo).count() == 50
```

## Чек-лист

- [ ] Списание — один `UPDATE` с `available_quantity__gte` + `F()`.
- [ ] `rows == 0` → `OutOfStock`, не молчаливый успех.
- [ ] Резерв создаётся в той же `transaction.atomic()`, что и списание.
- [ ] Отмена идемпотентна и возвращает остаток через `F()`.
- [ ] Параллельный тест на `TransactionTestCase` + `ThreadPoolExecutor`.
- [ ] DoD: 100 параллельных запросов на 50 единиц → 50/50/0.
