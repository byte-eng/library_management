from django.urls import path
from . import views

urlpatterns = [
    path('',views.signup, name='signup'),
    path('signin/', views.signin, name='signin'),
    path('home/', views.home, name='home'),
    path('librarian/', views.librarian, name='librarian'),
    path('logout/', views.logout_view, name='logout'),
    path('request-issue/<int:book_id>/', views.request_issue, name='request_issue'),
    path('student-dashboard/', views.student_dashboard, name='student_dashboard'),
    path('approve-issue/<int:issue_id>/', views.approve_issue, name='approve_issue'),
    path('return-book/<int:issue_id>/', views.return_book, name='return_book'),

    path('pay-single/<int:issue_id>/', views.create_checkout_session_single),
    path('pay-all/', views.create_checkout_session_all),
    path('payment-success/', views.payment_success),
]