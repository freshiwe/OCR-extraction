from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_invoice, name='upload_invoice'),
    path('invoice/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('history/', views.upload_history, name='upload_history'),
    path('verify/<int:invoice_id>/', views.verify_invoice, name='verify_invoice'),
]