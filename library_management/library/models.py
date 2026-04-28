from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone

class Profile(models.Model):
    ROLE_CHOICES = [
        ('guest','Guest'),
        ('student','Student'),
        ('librarian','Librarian')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.role}"
    

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student_id = models.AutoField(primary_key=True)
    department = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.student_id}"


class Author(models.Model):
    name = models.CharField(max_length=400)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name
    

class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.title


class Issue(models.Model):
    STATUS_CHOICES = [
        ('requested','Requested'),
        ('issued','Issued'),
        ('returned','Returned')
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    status = models.CharField(max_length=80, choices=STATUS_CHOICES)

    request_date = models.DateTimeField(auto_now_add=True)
    issue_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.status == 'issued' and not self.issue_date:
            self.issue_date = timezone.now()
            self.due_date = self.issue_date + timedelta(minutes=1)

        if self.status == 'returned' and not self.return_date:
            self.return_date = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.book} ({self.status})"


class Fine(models.Model):
    issue = models.OneToOneField(Issue, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.issue} {self.amount}"


class Payment(models.Model):
    fine = models.ManyToManyField(Fine)
    stripe_payment_id = models.CharField(max_length=255, null=True, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"Payment ₹{self.amount}"


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, role='guest')