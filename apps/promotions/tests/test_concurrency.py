"""DoD anti-oversell: 100 параллельных запросов на 50 единиц → 50/50/0.

TransactionTestCase (не TestCase) — иначе параллельные коннекты не увидят
данные. Реальные потоки: блокировка на стороне БД (row-lock), не на GIL.
См. docs/references/patterns/anti-oversell.md.
"""

from concurrent.futures import ThreadPoolExecutor

from django.db import connection
from django.test import TransactionTestCase

from apps.promotions.models import Promotion, Reservation
from apps.promotions.services import OutOfStock, reserve


class ReserveConcurrencyTest(TransactionTestCase):
    def test_no_oversell_under_parallel_load(self):
        promo = Promotion.objects.create(
            title={"de": "Aktion"},
            status="active",
            available_quantity=50,
            max_per_customer=1,
            auto_confirm=True,
        )

        def worker(_):
            connection.close()  # своё соединение на поток
            try:
                reserve(promo, name="Anon", email="", quantity=1)
                return True
            except OutOfStock:
                return False

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(worker, range(100)))

        promo.refresh_from_db()
        self.assertEqual(sum(results), 50)  # ровно 50 успешных
        self.assertEqual(results.count(False), 50)  # ровно 50 отказов
        self.assertEqual(promo.available_quantity, 0)  # ноль перепродаж
        self.assertEqual(Reservation.objects.filter(promotion=promo).count(), 50)
