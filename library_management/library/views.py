from django.shortcuts import render,redirect,get_object_or_404
from django.http import JsonResponse
from django.db.models import Q,Count
from .models import Profile,Student,Author,Category,Book,Issue,Fine,Payment
from django.contrib import messages
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from datetime import timedelta
from django.utils import timezone
import math,stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def signup(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        department = request.POST.get('department')

        if not first_name or not last_name or not email or not password or not role:
            messages.error(request, "All Fields Required")
            return redirect('signup')
        
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter Valid Email")
            return redirect('signup')
        
        if role == 'student' and not department:
            messages.error(request, "Department Required")
            return redirect('signup')

        if User.objects.filter(username=email).exists():
            messages.error(request, "Already Exists")
            return redirect('signup')
        
        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request, e.messages)
            return redirect('signup')
        
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        profile = user.profile
        profile.role = role

        if role=='student':
            profile.is_approved = True
        elif role=='librarian':
            profile.is_approved = False
        else:
            profile.is_approved = True

        profile.save()

        if role == 'student':
            Student.objects.create(
                user = user,
                department = department
            )
        messages.success(request, "Created Successfully")
        return redirect('signin')


    return render(request, "signup.html")



def logout_view(request):
    logout(request)
    return redirect('signin')



def signin(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not email or not password:
            messages.error(request, "All fields Required")

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter Valid Email")
            return redirect('signin')
        
        user = authenticate(request, username=email, password=password)

        if not user:
            messages.error(request, "Invalid")
            return redirect('signin')
        
        profile = user.profile

        if profile.role == 'librarian' and not profile.is_approved:
            messages.error(request, "Not Approved")
            return redirect('signin')
        
        login(request, user)

        if profile.role == 'student':
            return redirect('home')
        elif profile.role == 'librarian':
            return redirect('librarian')
        else:
            return redirect('home')
        
    return render(request, 'signin.html')



def get_button_label(book, user):
    issues = book.issue_set.all()

    user_issue = None
    for i in issues:
        if i.student.user == user:
            user_issue = i
            break

    if user_issue:
        if user_issue.status == 'requested':
            return "Requested"
        elif user_issue.status == 'issued':
            return "Issued"
        
    if any(i.status == 'issued' for i in issues):
        return "Not Available"
    
    if any(i.status == 'requested' for i in issues):
        return "Registered"
    
    return "Request Issue"



@never_cache
@login_required
def home(request):
    title = request.GET.get('title', '').strip()
    author = request.GET.get('author', '').strip()
    category = request.GET.get('category', '').strip()
    sort = request.GET.get('sort', '')

    profile = request.user.profile
    role = profile.role

    books = Book.objects.all()

    # Search
    if title:
        books = books.filter(title__icontains = title)
    if author:
        books = books.filter(author__name__icontains = author)
    if category:
        books = books.filter(category__name__icontains = category)

    # Filter
    if sort == 'title_asc':
        books = books.order_by('title')
    elif sort == 'title_desc':
        books = books.order_by('-title')
    elif sort == 'newest':
        books = books.order_by('-id')
    elif sort == 'oldest':
        books = books.order_by('id')

    # Suggestions
    titles = books.values_list('title', flat=True).distinct()[:5]
    authors = books.values_list('author__name', flat=True).distinct()[:5] 
    categories = books.values_list('category__name', flat=True).distinct()[:5]

    paginator = Paginator(books,12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for book in page_obj:
        book.button_label = get_button_label(book, request.user)

    if request.headers.get('X-Custom-Header') == 'AJAX':
        data = []
        for book in page_obj:
            item = {
                'id': book.id,
                'title': book.title,
                'author': book.author.name,
                'category': book.category.name,
                'button': book.button_label,
            }
            data.append(item)
        
        return JsonResponse({
            'books':data,
            'has_previous':page_obj.has_previous(),
            'has_next':page_obj.has_next(),
            'current_page':page_obj.number,
            'total_pages':paginator.num_pages,
            'previous_page':page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page':page_obj.next_page_number() if page_obj.has_next() else None,

            'titles':list(titles),
            'authors':list(authors),
            'categories':list(categories),

            'role':role,
        })

    return render(request, 'home.html', {'page_obj':page_obj, 'role':role})


@never_cache
@login_required
def student_dashboard(request):
    user = request.user
    sort = request.GET.get('sort')

    try:
        student = Student.objects.get(user=user)
    except:
        return redirect('home')

    issues = Issue.objects.filter(student=student)

    if sort == 'requested':
        issues = issues.filter(status = 'requested')
    if sort == 'issued':
        issues = issues.filter(status = 'issued')
    if sort == 'returned':
        issues = issues.filter(status = 'returned')


    def get_fine(issue):
        if issue.status == 'issued' and issue.due_date:
            late_time = timezone.now() - issue.due_date

            if late_time.total_seconds() <= 0:
                return 0
            
            late_days = math.ceil(late_time.total_seconds() / (60*60*24))
            amount = late_days*20
        
            Fine.objects.update_or_create(
                issue = issue,
                defaults={'amount':amount}
            )
            return amount
        
        if issue.status == 'returned':
            fine = Fine.objects.filter(issue=issue).first()
            return float(fine.amount) if fine else 0

        return 0
    
    total_fine = 0

    for issue in issues:
        issue.calculated_fine = get_fine(issue)
        issue.is_paid = Fine.objects.filter(issue=issue, is_paid=True).exists()
        total_fine += issue.calculated_fine

    has_payable_fines = Fine.objects.filter(issue__student=student, issue__status='returned', is_paid=False).exists()

    if request.headers.get('X-Custom-Header') == 'AJAX':
        data = []

        for issue in issues:
            data.append({
                'id':issue.id,
                'title':issue.book.title,
                'author':issue.book.author.name,
                'category':issue.book.category.name,
                'status':issue.status,
                'fine':get_fine(issue),
                'is_paid':Fine.objects.filter(issue=issue, is_paid=True).exists()
            })

        return JsonResponse({'issues':data,'has_payable_fines':has_payable_fines})

    return render(request, 's_dashboard.html', {'issues':issues,'STRIPE_PUBLISHABLE_KEY':settings.STRIPE_PUBLISHABLE_KEY})



@login_required
def request_issue(request, book_id):
    if request.method == "POST":

        user = request.user
        student = Student.objects.get(user=user)
        if not student:
            return JsonResponse({'error':"Student Not Found"})
        
        book = Book.objects.get(id=book_id)

        if Issue.objects.filter(student=student, book=book, status__in=['requested','issued']).exists():
            return JsonResponse({'status':'exists'})
        
        if Issue.objects.filter(book=book, status='issued').exists():
            return JsonResponse({'status':'not_available'})
        
        if Issue.objects.filter(book=book, status='requested').exists():
            return JsonResponse({'status':'already_requested'})
        
        Issue.objects.create(
            student=student,
            book=book,
            status='requested'
        )

        return JsonResponse({'status':'ok'})


@login_required
def approve_issue(request, issue_id):
    issue = Issue.objects.get(id = issue_id)

    if issue.status != 'requested':
        return JsonResponse({'error':'Invalid'})
    
    issue.status = 'issued'

    now = timezone.now()
    issue.issue_date = now
    issue.due_date = now + timedelta(days=7)

    issue.book.available_copies -= 1
    issue.book.save()
    issue.save()

    print("SAVED DUE:", issue.due_date)

    return JsonResponse({'status':'ok'})


@login_required
def return_book(request, issue_id):
    issue = Issue.objects.get(id=issue_id)

    if issue.status != 'issued':
        return JsonResponse({'error':'Invalid'})
    
    issue.status='returned'
    issue.return_date = timezone.now()

    issue.book.available_copies += 1
    issue.book.save()
    issue.save()

    late_time  = issue.return_date - issue.due_date

    if late_time.total_seconds()>0:
        late_days = math.ceil(late_time.total_seconds() / (60*60*24))

        Fine.objects.update_or_create(
            issue=issue,
            defaults={'amount': late_days*20}
        )
    
    return JsonResponse({'status':'ok'})



@login_required
def create_checkout_session_single(request, issue_id):

    issue = Issue.objects.get(id=issue_id)
    fine = Fine.objects.filter(issue=issue, is_paid=False).first()
    if not fine:
        return JsonResponse({'error':'No Fine'})

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'inr',
                'product_data': {
                    'name': f'Fine - {issue.book.title}',
                },
                'unit_amount': int(fine.amount * 100),
            },
            'quantity': 1,
        }],
        mode='payment',

        metadata={
            'type': 'single',
            'fine_id': str(fine.id),
            'user_id':str(request.user.id)
        },

        success_url='http://127.0.0.1:8000/payment-success/?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='http://127.0.0.1:8000/student-dashboard/',
    )

    return JsonResponse({'id':session.id})



@login_required
def create_checkout_session_all(request):
    student = Student.objects.get(user = request.user)

    fines = Fine.objects.filter(issue__student = student, issue__status='returned' ,is_paid = False)
    total = sum(f.amount for f in fines)

    if total<=0:
        return JsonResponse({'error':'NO Pending fines'})

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'inr',
                'product_data': {
                    'name': 'Total Fine (Returned Book Only)',
                },
                'unit_amount': int(total * 100),
            },
            'quantity': 1,
        }],
        mode='payment',

        metadata={
            'type': 'all',
            'user_id': str(request.user.id),
        },

        success_url='http://127.0.0.1:8000/payment-success/?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='http://127.0.0.1:8000/student-dashboard/'
    )

    return JsonResponse({'id':session.id})



@login_required
def payment_success(request):
    session_id = request.GET.get('session_id')

    if not session_id:
        return redirect('student_dashboard')

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except:
        return redirect('student_dashboard')
    
    if session.payment_status != 'paid':
        return redirect('student_dashboard')
    
    metadata = session.metadata
    payment_type = metadata['type']

    if payment_type == 'single':
        fine_id =  metadata['fine_id']
        try:
            fine = Fine.objects.get(id=fine_id, is_paid=False)
            fine.is_paid = True
            fine.save()

            Payment.objects.create(
                user = request.user,
                amount = fine.amount,
                stripe_session_id = session.id,
                status = 'paid'
            )
        except Fine.DoesNotExist:
            pass

    elif payment_type == 'all':
        user_id = metadata['user_id']

        student = Student.objects.get(user__id=user_id)
        fines = Fine.objects.filter(issue__student=student, issue__status='returned' ,is_paid=False)

        total = sum(f.amount for f in fines)
        fines.update(is_paid=True)

        Payment.objects.create(
            user = request.user,
            amount = total,
            stripe_session_id = session.id,
            status = 'paid'
        )

    return render(request, 'payment_success.html')



#    Librarian 



@login_required
def librarian(request):
    return render(request, 'librarian/l_dashboard.html')

#  Book Management

@login_required
def book_management(request):
    book_list = Book.objects.all()

    search = request.GET.get('search', '').strip()

    if search:
        book_list = book_list.filter(
            Q(title__icontains = search) |
            Q(author__name__icontains = search) |
            Q(category__name__icontains = search)
        )

    paginator = Paginator(book_list, 12)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    if request.headers.get('X-Custom-Header') == 'AJAX':
        data = []

        for book in page_obj:
            is_issued = Issue.objects.filter(book=book, status='issued').exists()
            status = "Issued" if is_issued else "Available"
        
            data.append({
                'id':book.id,
                'title': book.title,
                'author': book.author.name,
                'category': book.category.name,
                'status' : status
            })

        return JsonResponse({
            'books': data,
            'has_previous':page_obj.has_previous(),
            'has_next':page_obj.has_next(),
            'current_page':page_obj.number,
            'total_pages':paginator.num_pages,
            'previous_page':page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page':page_obj.next_page_number() if page_obj.has_next() else None,
        })
    
    return render(request, 'librarian/partials/books.html', {'page_obj':page_obj})


@login_required
def search_author_category(request):
    query = request.GET.get('q', '').strip()

    authors = list(Author.objects.filter(name__icontains=query).values('id', 'name')[:5])
    categories = list(Category.objects.filter(name__icontains=query).values('id', 'name')[:5])

    return JsonResponse({
        'authors':authors,
        'categories':categories
    })


@login_required
def add_book(request):
    if request.method == "POST":
        title = request.POST.get("title")
        author_id = request.POST.get("author")
        category_id = request.POST.get('category')

        if not title or not author_id or not category_id:
            return JsonResponse({'success': False})
    
        author = get_object_or_404(Author, id=author_id)
        category = get_object_or_404(Category, id=category_id)

        Book.objects.create(
            title=title,
            author=author,
            category=category,
        )

    return JsonResponse({'success': True})


@login_required
def delete_book(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)

        is_issued = Issue.objects.filter(book=book, status='issued').exists()
        if is_issued:
            return JsonResponse({'success': False, 'error': 'Book is issued'})
        
        book.delete()
        return JsonResponse({'success':True})
    
    return JsonResponse({"success":False})


#  Author Management

@login_required
def author_management(request):
    authors = Author.objects.annotate(book_count = Count('book'))

    search = request.GET.get('search', '').strip()
    if search:
        authors = authors.filter(name__icontains = search)

    paginator = Paginator(authors, 12)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    if request.headers.get('X-Custom-Header') == 'AJAX':
        data = []

        for a in page_obj:
            data.append({
                'id':a.id,
                'name':a.name,
                'book_count':a.book_count
            })
        
        return JsonResponse({
            'authors':data,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'librarian/partials/authors.html' )


@login_required
def add_author(request):
    if request.method == "POST":
        name = request.POST.get("name", '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Name required'})

        if Author.objects.filter(name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': 'Already Exists'})

        Author.objects.create(name=name)
        return JsonResponse({'success':True})

@login_required
def delete_author(request, author_id):
    author = get_object_or_404(Author, id=author_id)
    author.delete()
    return JsonResponse({'success': 'True'})


#  Issue Management

@login_required
def issue_management(request):
    issues = Issue.objects.all()
    search =  request.GET.get('search', '').strip()

    if search:
        issues = issues.filter(
            Q(student__user__first_name__icontains=search) |
            Q(student__user__last_name__icontains=search)
        )

    paginator = Paginator(issues, 12)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    if request.headers.get('X-Custom-Header') == "AJAX":
        data = []

        for i in page_obj:
            fine = Fine.objects.filter(issue = i).first()

            data.append({
                'id':i.id,
                'student': f"{i.student.user.first_name} {i.student.user.last_name}",
                'book': i.book.title,
                'status': i.status,
                'issue_date':i.issue_date.strftime("%Y-%m-%d") if i.issue_date else "",
                'return_date': i.return_date.strftime("%Y-%m-%d") if i.return_date else "",
                'fine':str(fine.amount) if fine else 0,
            })
        
        return JsonResponse({
            'issues':data,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'librarian/partials/issues.html')