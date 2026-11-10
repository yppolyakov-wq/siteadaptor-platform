"""M21.6: привести Impressum бизнеса к действующему праву (без выдумывания данных).

    python manage.py fix_impressum --schema haanerteeladen
    python manage.py fix_impressum --schema haanerteeladen --apply \\
        --oeko-code DE-ÖKO-006 --rename "Schweizer Irina=Irina Schweizer"

По умолчанию показывает «было → стало» и ничего не пишет; ``--apply`` записывает
LegalDoc (Impressum, de). Что § 5 DDG требует, а в тексте не видно, — печатается.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_tenant_model, schema_context

from apps.imports import cscart

_BIO_RE = re.compile(r"\b(?:bio|öko)\b", re.I)


class Command(BaseCommand):
    help = "Impressum: убрать ODR-ссылку и неверные обозначения, проверить § 5 DDG."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--apply", action="store_true", help="Записать (иначе показ).")
        parser.add_argument("--oeko-code", default="", help="Код контрольного органа DE-ÖKO-0xx.")
        parser.add_argument(
            "--rename",
            action="append",
            default=[],
            help="Точная замена «было=стало», можно повторять.",
        )

    def handle(self, *args, **opts):
        from apps.catalog.models import Product
        from apps.core.models import LegalDoc

        code = opts["oeko_code"].strip()
        if code and not cscart._OEKO_CODE_RE.match(code):
            raise CommandError("--oeko-code: format DE-ÖKO-012")
        renames = []
        for item in opts["rename"]:
            old, sep, new = item.partition("=")
            if not sep or not old.strip() or not new.strip():
                raise CommandError(f"--rename {item!r}: expected OLD=NEW")
            renames.append((old.strip(), new.strip()))
        tenant = get_tenant_model().objects.filter(schema_name=opts["schema"]).first()
        if tenant is None:
            raise CommandError(f"business {opts['schema']!r} not found")

        with schema_context(tenant.schema_name):
            doc = LegalDoc.objects.filter(kind="impressum", locale="de").first()
            source = doc.text if doc and doc.text.strip() else ""
            if not source:
                self.stdout.write(
                    "no own Impressum text — the generated one from the fields is used"
                )
                source = tenant.impressum_text()
            cleaned, fixes = cscart.clean_impressum(source, oeko_code=code, renames=tuple(renames))
            has_bio = any(
                _BIO_RE.search(str(name))
                for name in Product.objects.filter(is_active=True).values_list("name", flat=True)
            )
            self.stdout.write("--- before\n" + source + "\n--- after\n" + cleaned + "\n---")
            for fix in fixes:
                self.stdout.write(f"  fixed: {fix}")
            for gap in cscart.impressum_gaps(cleaned):
                self.stdout.write(f"  ! missing: {gap}")
            if has_bio and "Öko-Kontrollstelle:" not in cleaned:
                self.stdout.write(
                    "  ! Bio products in the catalog: Öko-Kontrollstelle code required "
                    "(--oeko-code DE-ÖKO-0xx)"
                )
            if not opts["apply"]:
                self.stdout.write("dry-run: nothing written (use --apply)")
                return
            if cleaned == (doc.text if doc else ""):
                self.stdout.write("unchanged")
                return
            LegalDoc.objects.update_or_create(
                kind="impressum", locale="de", defaults={"text": cleaned}
            )
            self.stdout.write("Impressum saved")
