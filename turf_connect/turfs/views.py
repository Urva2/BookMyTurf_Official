from django.shortcuts import render, redirect, get_object_or_404
import json
import uuid
import random
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt # Optional, but often helpful for API-like views
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from .forms import AddTurfForm
from .models import Turf, TurfImage, VerificationDocument, Slot, Booking, Payment


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


def expire_pending_bookings():
    """Find and cancel all pending bookings that have expired, releasing their slots."""
    now = timezone.now()
    expired_bookings = Booking.objects.filter(status="pending", expires_at__lt=now)
    
    if not expired_bookings.exists():
        return

    with transaction.atomic():
        for booking in expired_bookings:
            # Release all slots associated with this booking
            booking.slots.update(status="available", hold_expiry=None)
            
            # Cancel the booking
            booking.status = "cancelled"
            booking.save()


def turf_detail(request, turf_id):
    """Display detailed information for a specific turf."""
    expire_pending_bookings()
    
    turf = get_object_or_404(Turf, id=turf_id, status='approved')
    
    # Filter future slots for the player view
    now = timezone.localtime()
    
    # Auto-cleanup expired holds
    Slot.objects.filter(status="held", hold_expiry__lt=now).update(status="available", hold_expiry=None)
    
    today = now.date()
    now_time = now.time()
    
    future_slots = Slot.objects.filter(
        Q(turf=turf),
        Q(date__gt=today) | Q(date=today, end_time__gt=now_time)
    ).order_by('date', 'start_time')
    
    slots_data = [
        {
            'id': slot.id,
            'date': slot.date.strftime('%Y-%m-%d'),
            'start': slot.start_time.strftime('%H:%M'),
            'startDisp': slot.start_time.strftime('%I:%M %p').lstrip('0'),
            'endDisp': slot.end_time.strftime('%I:%M %p').lstrip('0'),
            'price': str(slot.price),
            'status': slot.status, # Include actual status
            'isBooked': slot.is_booked,
            'label': slot.label
        }
        for slot in future_slots
    ]
    slots_json = json.dumps(slots_data)
    
    return render(request, 'turfdetail.html', {
        'turf': turf,
        'future_slots': future_slots,
        'slots_json': slots_json,
        'today': today,
        'now_time': now_time,
    })

def slot_management(request, id):
    """Display the slot management page for a specific turf."""
    if request.user.role != 'owner':
        return HttpResponseForbidden("Access denied.")
    
    turf = get_object_or_404(Turf, id=id, owner=request.user)
    
    # Current date and time for filtering past slots
    now = timezone.localtime()
    today = now.date()
    now_time = now.time()

    # Handle Edit ID for Modal Pre-fill
    edit_slot_obj = None
    edit_id = request.GET.get('edit_id')
    if edit_id:
        edit_slot_obj = Slot.objects.filter(
            Q(id=edit_id), 
            Q(turf=turf),
            Q(date__gt=today) | Q(date=today, end_time__gt=now_time)
        ).first()
    
    # Retrieve preview_count from session if available
    preview_count = request.session.pop('bulk_preview_count', None)
    
    # Selection of Date (Default to today)
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    # Fetch slots for this turf and date, ordered by start time
    # Exclude past slots if the selected date is today
    query = Q(turf=turf, date=selected_date)
    if selected_date == today:
        query &= Q(end_time__gt=now_time)
    elif selected_date < today:
        # If user somehow picks a past date, show nothing or only very specific cases
        # But per requirements: (slot.date > today) OR (slot.date == today AND slot.end_time > current_time)
        # So if selected_date < today, it should definitely be empty.
        query &= Q(id__isnull=True) 

    selected_slots = Slot.objects.filter(query).order_by('start_time')
    existing_start_times = [slot.start_time for slot in selected_slots]

    # Generate available 1-hour time options (6:00 AM to 11:00 PM)
    available_times = []
    current_time_obj = time(6, 0)
    end_limit = time(23, 0)

    # We iterate and add 1 hour until we reach 11 PM
    while current_time_obj < end_limit:
        # Check if the time is actually in the future if selected_date is today
        is_future = True
        if selected_date == today:
            is_future = current_time_obj > now_time
        elif selected_date < today:
            is_future = False

        if is_future and current_time_obj not in existing_start_times:
            available_times.append(current_time_obj)
        
        # Increment by 1 hour
        temp_dt = datetime.combine(selected_date, current_time_obj) + timedelta(hours=1)
        current_time_obj = temp_dt.time()

    # Handle Slot Creation or Edit (POST)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'edit_slot':
            slot_id_to_edit = request.POST.get('slot_id')
            slot_to_update = Slot.objects.filter(id=slot_id_to_edit, turf=turf).first()
            
            if slot_to_update:
                if slot_to_update.is_booked:
                    messages.error(request, "Cannot edit a booked slot.")
                else:
                    new_start = request.POST.get('start_time')
                    new_end = request.POST.get('end_time')
                    new_price = request.POST.get('price')
                    new_label = request.POST.get('label', '')
                    
                    try:
                        slot_to_update.start_time = datetime.strptime(new_start, '%H:%M').time()
                        slot_to_update.end_time = datetime.strptime(new_end, '%H:%M').time()
                        slot_to_update.price = new_price
                        slot_to_update.label = new_label
                        
                        if slot_to_update.start_time >= slot_to_update.end_time:
                            messages.error(request, "Start time must be before end time.")
                        else:
                            slot_to_update.save()
                            messages.success(request, "Slot updated successfully.")
                            return redirect(f"{request.path}?date={selected_date}")
                    except Exception as e:
                        messages.error(request, f"Error updating slot: {str(e)}")
            return redirect(f"{request.path}?date={selected_date}")

        # Regular Add Slot Logic
        start_time_str = request.POST.get('start_time')
        price = request.POST.get('price')

        if start_time_str and price:
            try:
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                # end_time = start_time + 1 hour
                temp_end_dt = datetime.combine(selected_date, start_time_obj) + timedelta(hours=1)
                end_time_obj = temp_end_dt.time()

                # Check for duplicate
                if Slot.objects.filter(turf=turf, date=selected_date, start_time=start_time_obj).exists():
                    messages.error(request, "This time slot already exists.")
                else:
                    Slot.objects.create(
                        turf=turf,
                        date=selected_date,
                        start_time=start_time_obj,
                        end_time=end_time_obj,
                        price=price
                    )
                    messages.success(request, f"Slot created for {start_time_obj.strftime('%g %A')}.")
                    return redirect(f"{request.path}?date={selected_date}&tab=add")
            except Exception as e:
                messages.error(request, f"Error creating slot: {str(e)}")

    # Handle Bulk Generation Collection (POST)
    if request.method == 'POST' and request.POST.get('bulk_generate') == 'true':
        action = request.POST.get('action', 'preview')
        
        if action == 'confirm':
            # Retrieve parameters from session
            bulk_params = request.session.get('bulk_params')
            if not bulk_params:
                messages.error(request, "Session expired or invalid. Please try again.")
                return redirect(f"{request.path}?date={selected_date}&tab=bulk")
            
            start_date_str = bulk_params['start_date']
            end_date_str = bulk_params['end_date']
            generation_mode = bulk_params['generation_mode']
            duration = bulk_params['duration']
            conflict_strategy = bulk_params['conflict_strategy']
            time_blocks_raw = bulk_params['time_blocks'] # These have time objects as strings
            
            # Reconstruct time blocks with actual time objects
            time_blocks = []
            for block in time_blocks_raw:
                time_blocks.append({
                    'start': datetime.strptime(block['start'], '%H:%M').time(),
                    'end': datetime.strptime(block['end'], '%H:%M').time(),
                    'price': block['price']
                })
        else:
            # PREVIEW MODE
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            generation_mode = request.POST.get('generation_mode')
            duration = request.POST.get('duration')
            conflict_strategy = request.POST.get('conflict_strategy')
            
            # Collect and Validate time blocks (max 3)
            time_blocks = []
            for i in range(1, 4):
                start_str = request.POST.get(f'block_{i}_start')
                end_str = request.POST.get(f'block_{i}_end')
                price = request.POST.get(f'block_{i}_price')
                
                if start_str and end_str and price:
                    try:
                        start_t = datetime.strptime(start_str, '%H:%M').time()
                        end_t = datetime.strptime(end_str, '%H:%M').time()
                        
                        if start_t >= end_t:
                            messages.error(request, f"Block {i}: Start time must be before end time.")
                            return redirect(f"{request.path}?date={selected_date}&tab=bulk")
                        
                        time_blocks.append({
                            'start': start_t,
                            'end': end_t,
                            'price': price
                        })
                    except ValueError:
                        messages.error(request, f"Block {i}: Invalid time format.")
                        return redirect(f"{request.path}?date={selected_date}&tab=bulk")

        # Logic shared by both Preview and Confirm (Date filtering and Interval generation)
        valid_dates = []
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            curr_date = start_date
            while curr_date <= end_date:
                weekday = curr_date.weekday()
                if generation_mode == 'all':
                    valid_dates.append(curr_date)
                elif generation_mode == 'weekday' and weekday < 5:
                    valid_dates.append(curr_date)
                elif generation_mode == 'weekend' and weekday >= 5:
                    valid_dates.append(curr_date)
                curr_date += timedelta(days=1)
        except (ValueError, TypeError):
            messages.error(request, "Invalid date format or range.")
            return redirect(f"{request.path}?date={selected_date}&tab=bulk")

        generated_slots = []
        try:
            duration_min = int(duration) if duration else 60
            for d in valid_dates:
                for block in time_blocks:
                    current_start_dt = datetime.combine(d, block['start'])
                    block_end_dt = datetime.combine(d, block['end'])
                    while current_start_dt + timedelta(minutes=duration_min) <= block_end_dt:
                        slot_start = current_start_dt.time()
                        slot_end = (current_start_dt + timedelta(minutes=duration_min)).time()
                        generated_slots.append({
                            'date': d,
                            'start_time': slot_start,
                            'end_time': slot_end,
                            'price': block['price']
                        })
                        current_start_dt += timedelta(minutes=duration_min)
        except (ValueError, TypeError) as e:
            messages.error(request, f"Error calculating intervals: {str(e)}")
            return redirect(f"{request.path}?date={selected_date}&tab=bulk")

        if action == 'preview':
            # Calculate final results in-memory for preview
            preview_final_count = 0
            for slot_data in generated_slots:
                existing = Slot.objects.filter(turf=turf, date=slot_data['date'], start_time=slot_data['start_time']).first()
                if not existing or conflict_strategy == 'overwrite':
                    if existing and existing.is_booked: continue # Protected
                    preview_final_count += 1
            
            # Store serializable parameters in session
            request.session['bulk_params'] = {
                'start_date': start_date_str,
                'end_date': end_date_str,
                'generation_mode': generation_mode,
                'duration': duration,
                'conflict_strategy': conflict_strategy,
                'time_blocks': [{'start': b['start'].strftime('%H:%M'), 'end': b['end'].strftime('%H:%M'), 'price': b['price']} for b in time_blocks]
            }
            request.session['bulk_preview_count'] = preview_final_count
            messages.info(request, "Bulk generation preview updated.")
            return redirect(f"{request.path}?date={selected_date}&tab=bulk")

        elif action == 'confirm':
            # Database Execution (Atomic Transaction)
            slots_created_count = 0
            try:
                with transaction.atomic():
                    new_slot_objects = []
                    for slot_data in generated_slots:
                        existing = Slot.objects.filter(turf=turf, date=slot_data['date'], start_time=slot_data['start_time']).first()
                        if existing:
                            if conflict_strategy == 'overwrite' and not existing.is_booked:
                                existing.delete()
                                slots_created_count += 1
                                new_slot_objects.append(Slot(turf=turf, date=slot_data['date'], start_time=slot_data['start_time'], end_time=slot_data['end_time'], price=slot_data['price']))
                        else:
                            slots_created_count += 1
                            new_slot_objects.append(Slot(turf=turf, date=slot_data['date'], start_time=slot_data['start_time'], end_time=slot_data['end_time'], price=slot_data['price']))
                    if new_slot_objects:
                        Slot.objects.bulk_create(new_slot_objects)
                
                messages.success(request, f"Successfully created {slots_created_count} slots.")
                request.session.pop('bulk_params', None)
                request.session.pop('bulk_preview_count', None)
                return redirect(f"{request.path}?date={selected_date}&tab=calendar")
            except Exception as e:
                messages.error(request, f"Database error: {str(e)}")
                return redirect(f"{request.path}?date={selected_date}&tab=bulk")

    # Fetch all slots for this turf to show counts in calendar (excluding past slots)
    slot_counts_query = Slot.objects.filter(
        Q(turf=turf),
        Q(date__gt=today) | Q(date=today, end_time__gt=now_time)
    ).values('date').annotate(count=Count('id'))
    slot_counts = {item['date'].strftime('%Y-%m-%d'): item['count'] for item in slot_counts_query}

    context = {
        'turf': turf,
        'selected_date': selected_date,
        'today': today,
        'selected_slots': selected_slots,
        'available_times': available_times,
        'preview_count': preview_count,
        'slot_counts': slot_counts,
        'edit_slot_obj': edit_slot_obj,
    }
    return render(request, 'slotmanagement.html', context)

@login_required
def delete_slot(request, slot_id):
    """Deletes a time slot if it belongs to the owner and is not booked."""
    now = timezone.localtime()
    today = now.date()
    now_time = now.time()

    # Fetch slot ensuring it's not in the past
    slot = get_object_or_404(
        Slot, 
        Q(id=slot_id),
        Q(date__gt=today) | Q(date=today, end_time__gt=now_time)
    )
    
    # Check ownership
    if slot.turf.owner != request.user:
        messages.error(request, "Access denied.")
        return redirect('owner_dashboard')
        
    date_str = slot.date.strftime('%Y-%m-%d')
    turf_id = slot.turf.id
    
    if slot.is_booked:
        messages.error(request, "Cannot delete a booked slot.")
    else:
        slot.delete()
        messages.success(request, "Slot deleted successfully.")
        
    return redirect(f"{reverse('slot_management', args=[turf_id])}?date={date_str}")

@login_required
@csrf_exempt
def hold_slot(request):
    """Temporarily hold multiple slots for 5 minutes atomically and create a pending booking."""
    if request.method == 'POST':
        slot_ids_str = request.POST.get('slot_id')  # Keeping parameter name same for compatibility
        if not slot_ids_str:
            return JsonResponse({'status': 'error', 'message': 'Missing slot_id'}, status=400)
            
        # Global cleanup of expired holds before processing
        expire_pending_bookings()
        Slot.objects.filter(status="held", hold_expiry__lt=timezone.now()).update(status="available", hold_expiry=None)
        
        slot_ids = [s.strip() for s in slot_ids_str.split(',') if s.strip()]
        
        try:
            with transaction.atomic():
                # Lock the rows to prevent race conditions
                slots = list(Slot.objects.select_for_update().filter(id__in=slot_ids))
                
                # Verify we found all requested slots
                if len(slots) != len(slot_ids):
                    return JsonResponse({'status': 'error', 'message': 'One or more slots not found'}, status=404)
                
                # Validation: Maximum 3 slots
                if len(slots) > 3:
                    return JsonResponse({'status': 'error', 'message': 'Maximum 3 slots allowed.'}, status=400)
                
                # Validation: Same date and same turf
                first_date = slots[0].date
                first_turf = slots[0].turf
                for slot in slots:
                    if slot.date != first_date or slot.turf != first_turf:
                        return JsonResponse({'status': 'error', 'message': 'All selected slots must be on same date.'}, status=400)
                
                # Check availability for all slots
                for slot in slots:
                    if slot.status != 'available':
                        return JsonResponse({'status': 'error', 'message': 'One or more slots no longer available'}, status=400)
                
                # Calculate total amount
                total_amount = sum(slot.price for slot in slots)
                
                # Proceed to hold slots
                expiry_time = timezone.now() + timedelta(minutes=5)
                
                # Create Booking object
                booking = Booking.objects.create(
                    player=request.user,
                    turf=first_turf,
                    date=first_date,
                    total_amount=total_amount,
                    status="pending",
                    expires_at=expiry_time
                )
                
                # Add slots to booking
                booking.slots.set(slots)
                
                # Store booking_id in session
                request.session["booking_id"] = booking.id
                
                for slot in slots:
                    slot.status = 'held'
                    slot.hold_expiry = expiry_time
                    slot.save()
                    
                return JsonResponse({
                    'status': 'success', 
                    'message': f'{len(slot_ids)} slots held and booking {booking.id} created successfully',
                    'booking_id': booking.id,
                    'hold_expiry': expiry_time.isoformat()
                })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@login_required
def booking_summary(request):
    """Display the summary of a pending booking."""
    expire_pending_bookings()
    
    booking_id = request.session.get('booking_id')
    
    if not booking_id:
        return redirect('browse_turfs')
        
    booking = get_object_or_404(Booking, id=booking_id, player=request.user)
    
    if booking.status != "pending":
        messages.error(request, "This booking has expired.")
        return redirect('browse_turfs')
    
    return render(request, 'booking_summary.html', {'booking': booking})


@login_required
def payment_page(request):
    """Display the payment page for a pending booking."""
    expire_pending_bookings()
    
    booking_id = request.session.get('booking_id')
    
    if not booking_id:
        return redirect('browse_turfs')
        
    booking = get_object_or_404(Booking, id=booking_id, player=request.user)
    
    if booking.status != "pending":
        messages.error(request, "This booking is no longer active.")
        return redirect('browse_turfs')
        
    return render(request, 'payment.html', {'booking': booking})


@login_required
def payment_process(request):
    """Process the payment for a booking."""
    if request.method != "POST":
        return redirect('browse_turfs')

    booking_id = request.session.get('booking_id')
    if not booking_id:
        messages.error(request, "Session expired. Please try again.")
        return redirect('browse_turfs')

    booking = get_object_or_404(Booking, id=booking_id, player=request.user)

    if booking.status != "pending":
        messages.error(request, "This booking is no longer awaiting payment.")
        return redirect('browse_turfs')

    try:
        with transaction.atomic():
            # Check for expiration right before processing
            if booking.expires_at and timezone.now() > booking.expires_at:
                messages.error(request, "Booking expired.")
                return redirect('booking_summary')

            # Simulate payment success (70% success rate)
            is_success = random.random() < 0.7
            
            payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
            
            if is_success:
                # Create Payment record
                Payment.objects.create(
                    booking=booking,
                    payment_id=payment_id,
                    amount=booking.total_amount,
                    status="success"
                )
                
                # Update Booking status
                booking.status = "paid"
                booking.save()
                
                # Update Slots status
                booking.slots.select_for_update().update(status="booked", hold_expiry=None)
                
                # Clear session booking_id on success
                request.session.pop('booking_id', None)
                
                messages.success(request, f"Payment Successful! Your booking (ID: {booking.id}) is confirmed.")
                return redirect('booking_success', booking_id=booking.id)
            else:
                # Simulated failure logic
                Payment.objects.create(
                    booking=booking,
                    payment_id=payment_id,
                    amount=booking.total_amount,
                    status="failed"
                )
                messages.error(request, "Payment failed. Try again.")
                return redirect('payment_page')
                
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('payment_page')


@login_required
def booking_success(request, booking_id):
    """Show the success message after payment."""
    booking = get_object_or_404(Booking, id=booking_id, player=request.user)
    
    if booking.status != "paid":
        return redirect('browse_turfs')
    
    # Fetch the successful payment record
    payment = Payment.objects.filter(booking=booking, status='success').first()
    
    return render(request, 'booking_success.html', {
        'booking': booking,
        'payment': payment
    })
@login_required
def cancel_booking(request):
    """Allow user to cancel their pending booking and release slots."""
    booking_id = request.session.get('booking_id')
    if not booking_id:
        return redirect('browse_turfs')

    booking = get_object_or_404(Booking, id=booking_id, player=request.user)
    
    if booking.status == "pending":
        with transaction.atomic():
            # Release all slots
            booking.slots.select_for_update().update(status="available", hold_expiry=None)
            
            # Mark booking as cancelled
            booking.status = "cancelled"
            booking.save()
            
            # Clear session
            request.session.pop('booking_id', None)
            
            messages.success(request, "Booking cancelled successfully.")
    
    return redirect('browse_turfs')
