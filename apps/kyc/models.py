"""apps/kyc/models.py — KYC Document model"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class KYCDocument(models.Model):
    DOC_GHANA_CARD = 'ghana_card'
    DOC_PASSPORT = 'passport'
    DOC_DRIVERS = 'drivers_license'
    DOC_VOTER_ID = 'voter_id'
    DOC_BUSINESS_REG = 'business_registration'
    DOC_CHOICES = [
        (DOC_GHANA_CARD, 'Ghana Card (National ID)'),
        (DOC_PASSPORT, 'International Passport'),
        (DOC_DRIVERS, "Driver's License"),
        (DOC_VOTER_ID, "Voter's ID Card"),
        (DOC_BUSINESS_REG, 'Business Registration Certificate'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_UNDER_REVIEW = 'under_review'
    STATUS_VERIFIED = 'verified'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Submission'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kyc_documents'
    )
    document_type = models.CharField(max_length=30, choices=DOC_CHOICES)
    document_number = models.CharField(max_length=50)
    front_image = models.ImageField(upload_to='kyc/%Y/%m/')
    back_image = models.ImageField(upload_to='kyc/%Y/%m/', null=True, blank=True)
    selfie_image = models.ImageField(upload_to='kyc_selfies/%Y/%m/', null=True, blank=True)

    address = models.TextField()
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    ghana_post_gps = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.TextField(blank=True)

    business_name = models.CharField(max_length=200, blank=True)
    tin_number = models.CharField(max_length=30, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kyc_reviews'
    )

    class Meta:
        db_table = 'gh_kyc_documents'
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.user.email} - {self.get_document_type_display()} - {self.status}"

    def approve(self, admin_user):
        self.status = self.STATUS_VERIFIED
        self.reviewed_at = timezone.now()
        self.reviewed_by = admin_user
        self.save()
        self.user.kyc_status = 'verified'
        self.user.is_verified_seller = True
        self.user.save(update_fields=['kyc_status', 'is_verified_seller'])

    def reject(self, admin_user, reason):
        self.status = self.STATUS_REJECTED
        self.rejection_reason = reason
        self.reviewed_at = timezone.now()
        self.reviewed_by = admin_user
        self.save()
        self.user.kyc_status = 'rejected'
        self.user.save(update_fields=['kyc_status'])
