from django.contrib import admin
from .models import Profile,Issue,Fine

@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display=['id','student', 'book', 'status', 'issue_date', 'due_date', 'return_date']
    list_filter=['status']
    search_fields=['book__title', 'student__user__username']
    list_editable=['status']

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display=['user','role','is_approved']
    list_editable=['is_approved']

@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display=['issue', 'amount', 'is_paid']
    list_editable=['is_paid']
