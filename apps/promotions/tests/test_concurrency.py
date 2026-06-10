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

    def test_no_oversell_with_quantity_2_and_odd_stock(self):
        """Списание по 2 при остатке 7: 3 брони, хвост 1 — не в минус (H6)."""
        promo = Promotion.objects.create(
            title={"de": "Aktion"},
            status="active",
            available_quantity=7,
            auto_confirm=True,
        )

        def worker(i):
            connection.close()
            try:
                reserve(promo, name=f"D{i}", email=f"d{i}@load.test", quantity=2)
                return 2
            except OutOfStock:
                return 0

        with ThreadPoolExecutor(max_workers=12) as pool:
            sold = list(pool.map(worker, range(12)))

        promo.refresh_from_db()
        self.assertEqual(sum(sold), 6)  # 3 брони по 2
        self.assertEqual(promo.available_quantity, 1)  # хвост остался, минуса нет
