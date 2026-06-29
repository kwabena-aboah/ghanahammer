"""apps/kyc/views.py — KYC views"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.kyc.models import KYCDocument

GHANA_REGIONS = [
    'Greater Accra', 'Ashanti', 'Western', 'Central', 'Eastern',
    'Volta', 'Northern', 'Upper East', 'Upper West', 'Brong-Ahafo',
    'Oti', 'Bono', 'Bono East', 'Ahafo', 'North East', 'Savannah',
]


@login_required
def kyc_overview(request):
    documents = KYCDocument.objects.filter(user=request.user).order_by('-submitted_at')
    status = request.user.kyc_status
    steps = [
        ('Create Account', True),
        ('Submit ID Documents', status in ('submitted', 'verified', 'rejected')),
        ('Under Review', status in ('submitted', 'verified')),
        ('Verified', status == 'verified'),
    ]
    return render(request, 'kyc/overview.html', {
        'documents': documents,
        'latest': documents.first(),
        'steps': steps,
    })


@login_required
def kyc_submit(request):
    user = request.user
    if user.kyc_status == 'verified':
        messages.info(request, 'Your identity is already verified.')
        return redirect('kyc_overview')

    if request.method == 'POST':
        doc_type = request.POST.get('document_type')
        doc_number = request.POST.get('document_number')
        front = request.FILES.get('front_image')
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        region = request.POST.get('region', '').strip()

        if not all([doc_type, doc_number, front, address, city, region]):
            messages.error(request, 'All required fields must be filled.')
        else:
            KYCDocument.objects.create(
                user=user,
                document_type=doc_type,
                document_number=doc_number,
                front_image=front,
                back_image=request.FILES.get('back_image'),
                selfie_image=request.FILES.get('selfie_image'),
                address=address,
                city=city,
                region=region,
                business_name=request.POST.get('business_name', ''),
                tin_number=request.POST.get('tin_number', ''),
                ghana_post_gps=request.POST.get('ghana_post_gps', ''),
                status=KYCDocument.STATUS_UNDER_REVIEW,
            )
            user.kyc_status = 'submitted'
            user.save(update_fields=['kyc_status'])
            messages.success(request, "Documents submitted. We'll verify within 24–48 hours.")
            return redirect('kyc_overview')

    return render(request, 'kyc/submit.html', {
        'doc_choices': KYCDocument.DOC_CHOICES,
        'regions': GHANA_REGIONS,
    })
