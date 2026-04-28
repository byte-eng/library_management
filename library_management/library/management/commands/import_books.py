import csv
from django.core.management.base import BaseCommand
from library.models import Book, Author, Category

class Command(BaseCommand):
    help = 'Import books from CSV'

    def handle(self, *args, **kwargs):
        file_path = 'data/books.csv'

        try:
            with open(file_path, encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    title = row.get('title', '').strip()
                    author_name = row.get('authors', '').split('/')[0].strip()
                    category_name = row.get('categories', '').strip() or 'General'

                    if not title or not author_name:
                        continue

                    category_name = category_name.split('/')[0]

                    author, _ = Author.objects.get_or_create(name=author_name)
                    category, _ = Category.objects.get_or_create(name=category_name)

                    Book.objects.get_or_create(
                        title=title,
                        author=author,
                        category=category,
                        defaults={
                            'total_copies': 1,
                            'available_copies': 1
                        }
                    )

            self.stdout.write(self.style.SUCCESS('success'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('Fail'))