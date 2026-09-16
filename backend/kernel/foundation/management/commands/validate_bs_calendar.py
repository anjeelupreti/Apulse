"""Check a Bikram Sambat table before trusting it with invoice dates.

    manage.py validate_bs_calendar path/to/bs_calendar.json

Reports the years covered and the Gregorian date of each Nepali New Year, so the output can be
compared line by line against a published calendar. See COMPLIANCE_REGISTER CR-CAL-01.
"""

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from shared.nepali_calendar import CalendarTableError, load_table_from_json
from shared.nepali_calendar.fiscal import fiscal_year_from_label


class Command(BaseCommand):
    help = "Validate a Bikram Sambat calendar table and print its New Year dates."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--show-years", action="store_true", help="List every Nepali New Year date."
        )

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002 (Django signature)
        try:
            table = load_table_from_json(options["path"])
        except CalendarTableError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Table is internally consistent: BS {table.min_year}-{table.max_year} "
                f"({table.max_year - table.min_year + 1} years)"
            )
        )
        if table.source:
            self.stdout.write(f"source: {table.source}")

        self.stdout.write(
            self.style.WARNING(
                "Consistency is not proof. Compare the New Year dates below against a published "
                "calendar before this is used on tax documents (CR-CAL-01)."
            )
        )

        if options["show_years"]:
            for year in sorted(table.year_starts):
                start = table.year_starts[year]
                self.stdout.write(f"  Baisakh 1, {year} = {start.isoformat()}")

        # The last year cannot form a fiscal year, which needs Ashadh of the following year.
        from shared.nepali_calendar.table import load_table

        load_table(table)
        try:
            first = fiscal_year_from_label(str(table.min_year))
            last = fiscal_year_from_label(str(table.max_year - 1))
            self.stdout.write(
                f"fiscal years: {first.label} ({first.start_ad} to {first.end_ad}) "
                f"through {last.label} ({last.start_ad} to {last.end_ad})"
            )
        finally:
            load_table(None)
