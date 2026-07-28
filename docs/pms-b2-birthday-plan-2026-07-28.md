# PMS-B2: ДР-кампания «Geburtstagsgruß» — план v1

**Дата:** 2026-07-28 · **Статус:** одобрено («Делай все по очереди», п.1).
**⚠️ Миграция `promotions/0023`** (Customer.birthday DateField null + choices
kind — без изменения данных).

Идея (CRM-анализ §8 + LS-5 v2): персональное поздравление с купоном в день
рождения — самое конверсионное авто-касание малого бизнеса. Вся механика уже
есть (B4 CouponCampaign + send_coupon_campaign + UWG-гейт) — добавляем поле,
вид кампании и beat.

## Модель
- `Customer.birthday` DateField null/blank (обычные PII; DSGVO-purge
  обезличивания дополняется `birthday=None`).
- `CouponCampaign.KIND_BIRTHDAY` («Geburtstag»); статусы active/paused как у
  auto_winback; настройки на самой кампании-синглтоне (без Tenant-миграции).

## Ввод даты
- CRM: `CustomerForm` += birthday (input type=date, опционально).
- ЛК гостя: `profile_view` — поле «Geburtstag» (стирание = None; гость сам
  решает, дарить ли дату).

## Beat `send_birthday_coupons` (раз в сутки, все схемы)
- По активным birthday-кампаниям: получатели = consented_customers()
  [+tag кампании] с birthday.month/day == сегодня; **29.02 в невисокосный год
  празднуем 28.02** (гость не теряет поздравление).
- Годовой дедуп как у win-back: у кого есть ваучер этой кампании младше
  300 дней — скип (окно < 365 повторных писем не даёт, но устойчиво к сдвигам).
- Отправка/коды: `send_coupon_campaign(customers=...)` (идемпотентность и
  UWG §7 — по построению).

## Кабинет
- Панель «🎂 Geburtstagsgruß» на `/promotions/kampagnen/` — копия панели
  Auto Win-back: тумблер + Rabatt % + Gültig Tage + Betreff
  (`action == "birthday"`, синглтон get-or-create).

## Тесты
- beat: именинник opt-in получает код/письмо; не-opt-in и «не сегодня» — нет;
  повторный прогон в тот же день и через месяц — дедуп; 29.02→28.02.
- Ввод: CRM-форма и ЛК сохраняют/стирают дату; purge обнуляет birthday.

Один батч: миграция → beat → панели ввода → тесты → i18n ×4.
