from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models


class Turf(models.Model):
    """Represents a turf listing submitted by an owner."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    # Basic Information
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='turfs',
    )
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    address = models.TextField()
    google_maps_url = models.URLField(blank=True, default='')
    description = models.TextField(validators=[MaxLengthValidator(500)])

    # Facilities
    facilities = models.JSONField(default=list, blank=True)
    additional_facilities = models.CharField(max_length=500, blank=True, default='')

    # System Fields
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    rejection_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.city} ({self.get_status_display()})"


class Slot(models.Model):
    """Represents a bookable time slot for a turf."""

    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name='slots',
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    label = models.CharField(max_length=100, blank=True, default='')
    is_booked = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=[
            ("available", "Available"),
            ("held", "Held"),
            ("booked", "Booked")
        ],
        default="available"
    )
    hold_expiry = models.DateTimeField(null=True, blank=True)

    class Meta:
        # turf + date + start_time must be unique
        unique_together = ('turf', 'date', 'start_time')

    def __str__(self):
        status = "Booked" if self.is_booked else "Available"
        return f"{self.turf.name} | {self.date} {self.start_time}–{self.end_time} ({status})"


class TurfImage(models.Model):
    """Stores uploaded images for a turf listing."""

    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='turf_images/')

    def __str__(self):
        return f"Image for {self.turf.name}"


class VerificationDocument(models.Model):
    """Government verification documents for a turf listing."""

    turf = models.OneToOneField(
        Turf,
        on_delete=models.CASCADE,
        related_name='verification',
    )
    identity_proof = models.FileField(upload_to='verification_docs/')
    ownership_agreement = models.FileField(upload_to='verification_docs/')
    municipal_permission = models.FileField(upload_to='verification_docs/')
    gst_certificate = models.FileField(upload_to='verification_docs/', blank=True, null=True)

    def __str__(self):
        return f"Documents for {self.turf.name}"


class Booking(models.Model):
    """Represents a turf booking made by a player."""
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='turf_bookings',
    )
    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name='turf_bookings',
    )
    date = models.DateField()
    slots = models.ManyToManyField(Slot, related_name='turf_bookings')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled")
        ],
        default="pending"
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.id} | {self.turf.name} | {self.date}"


class Payment(models.Model):
    """Represents a payment transaction for a booking."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    payment_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("pending", "Pending")
        ],
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.payment_id} | {self.status} | ₹{self.amount}"
