from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('scan/', views.scan, name='scan'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # API endpoints
    path('api/verify-qr/', views.verify_qr, name='verify_qr'),
    path('api/checkin/', views.checkin, name='checkin'),
    path('api/checkout/', views.checkout, name='checkout'),
]