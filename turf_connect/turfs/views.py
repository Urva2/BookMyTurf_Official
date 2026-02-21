from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden

from .forms import AddTurfForm
from .models import Turf, TurfImage, VerificationDocument


@login_required(login_url='login')
def add_turf(request):
    """Allow turf owners to submit a new turf listing."""
    if request.user.role != 'owner':
        return HttpResponseForbidden("Access denied.")

    if request.method == 'POST':
        form = AddTurfForm(request.POST, request.FILES)
        if form.is_valid():
            # 1. Save Turf (owner + status set here, not from form)
            turf = form.save(commit=False)
            turf.owner = request.user
            turf.status = 'pending'
            turf.save()

            # 2. Save uploaded turf images
            for img in request.FILES.getlist('turf_images'):
                TurfImage.objects.create(turf=turf, image=img)

            # 3. Save verification documents
            VerificationDocument.objects.create(
                turf=turf,
                identity_proof=form.cleaned_data['identity_proof'],
                ownership_agreement=form.cleaned_data['ownership_agreement'],
                municipal_permission=form.cleaned_data['municipal_permission'],
                gst_certificate=form.cleaned_data.get('gst_certificate'),
            )

            messages.success(request, 'Turf submitted for verification! You will be notified once approved.')
            return redirect('owner_dashboard')
        else:
            messages.error(request, 'Please correct the errors below and try again.')
    else:
        form = AddTurfForm()

    return render(request, 'addturf.html', {'form': form})


@login_required(login_url='login')
def edit_turf(request, turf_id):
    """Allow turf owners to edit and resubmit a rejected turf."""
    if request.user.role != 'owner':
        return HttpResponseForbidden("Access denied.")


    turf = get_object_or_404(Turf, id=turf_id, owner=request.user)

    if turf.status != 'rejected':
        return HttpResponseForbidden("Only rejected turfs can be edited.")

    if request.method == 'POST':
        form = AddTurfForm(request.POST, request.FILES, instance=turf)
        if form.is_valid():
            turf = form.save(commit=False)
            turf.status = 'pending'
            turf.rejection_reason = ''
            turf.save()

            # Replace images if new ones uploaded
            new_images = request.FILES.getlist('turf_images')
            if new_images:
                TurfImage.objects.filter(turf=turf).delete()
                for img in new_images:
                    TurfImage.objects.create(turf=turf, image=img)

            # Replace verification documents if new ones uploaded
            doc = VerificationDocument.objects.filter(turf=turf).first()
            if doc:
                if 'identity_proof' in request.FILES:
                    doc.identity_proof = form.cleaned_data['identity_proof']
                if 'ownership_agreement' in request.FILES:
                    doc.ownership_agreement = form.cleaned_data['ownership_agreement']
                if 'municipal_permission' in request.FILES:
                    doc.municipal_permission = form.cleaned_data['municipal_permission']
                if 'gst_certificate' in request.FILES:
                    doc.gst_certificate = form.cleaned_data['gst_certificate']
                doc.save()

            messages.success(request, 'Turf resubmitted for verification!')
            return redirect('owner_dashboard')
        else:
            messages.error(request, 'Please correct the errors below and try again.')
    else:
        form = AddTurfForm(instance=turf)

    return render(request, 'addturf.html', {
        'form': form,
        'editing': True,
        'turf': turf,
    })



def browse_turfs(request):
    turfs = Turf.objects.filter(status="approved")

    data = []
    for turf in turfs:
        data.append({
            "id": turf.id,
            "name": turf.name,
            "city": turf.city,
            "state": turf.state,
            "description": turf.description[:120],
            "locationKey": turf.city.lower(),
            "price": 1000,
            "rating": 5.0,
            "facilities": turf.facilities,
            "verified": True
        })

    return render(request, "browse.html", {
        "turf_json": data
    })


def turf_detail(request, turf_id):
    """Display detailed information for a specific turf."""

    turf = get_object_or_404(Turf, id=turf_id, status='approved')
    return render(request, 'turfdetail.html', {'turf': turf})

def slot_management(request, id):
    """Display the slot management page for a specific turf."""
    if request.user.role != 'owner':
        return HttpResponseForbidden("Access denied.")
    
    turf = get_object_or_404(Turf, id=id, owner=request.user)
    return render(request, 'slotmanagement.html', {'turf': turf})
