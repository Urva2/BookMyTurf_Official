from django.urls import path
from . import views

urlpatterns = [
    path('add-turf/', views.add_turf, name='add_turf'),
    path('edit-turf/<int:turf_id>/', views.edit_turf, name='edit_turf'),
    path('browse/', views.browse_turfs, name='browse_turfs'),
    path('<int:turf_id>/', views.turf_detail, name='turf_detail'),
    path('slot/delete/<int:slot_id>/', views.delete_slot, name='delete_slot'),
    path('slot/hold/', views.hold_slot, name='hold_slot'),
    path('booking/summary/', views.booking_summary, name='booking_summary'),
    path('payment/', views.payment_page, name='payment_page'),
    path('payment/process/', views.payment_process, name='payment_process'),
    path('booking/success/<int:booking_id>/', views.booking_success, name='booking_success'),
    path('booking/cancel/', views.cancel_booking, name='cancel_booking'),
]
