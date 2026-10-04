import io
import json
import base64
import qrcode
from datetime import time

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.contrib import messages

from .models import Employee, AttendanceRecord, CheckOutRecord


# ─── Configuration ────────────────────────────────────────────────────────────
CHECKIN_CUTOFF_HOUR = 11  # After 11:00 AM local time, check-in is blocked


def home(request):
    """Landing page with navigation."""
    return render(request, 'attendance/index.html')


def signup(request):
    """
    Employee registration.
    On POST: creates employee, generates QR code containing the employee UUID,
    and redirects to a success page showing the QR code.
    """
    if request.method == 'POST':
        name = request.POST.get('your_name', '').strip()
        email = request.POST.get('email_official', '').strip()

        if not name or not email:
            messages.error(request, 'Name and email are required.')
            return render(request, 'attendance/signup.html')

        # Check if employee already exists
        if Employee.objects.filter(email=email).exists():
            messages.error(request, 'An employee with this email already exists.')
            return render(request, 'attendance/signup.html')

        employee = Employee.objects.create(name=name, email=email)

        # Generate QR code with the employee UUID
        qr_data = str(employee.employee_id)
        qr_img = qrcode.make(qr_data, box_size=10, border=4)

        # Save QR code to model
        buffer = io.BytesIO()
        qr_img.save(buffer, format='PNG')
        buffer.seek(0)
        filename = f"qr_{employee.employee_id}.png"
        employee.qr_code.save(filename, ContentFile(buffer.read()), save=True)

        return render(request, 'attendance/signup_success.html', {
            'employee': employee,
        })

    return render(request, 'attendance/signup.html')


def scan(request):
    """Page for scanning QR codes using the device camera."""
    return render(request, 'attendance/scan.html')


@csrf_exempt
def verify_qr(request):
    """
    API endpoint: receives scanned QR data (employee UUID).
    Returns employee info and current attendance status for today.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        qr_data = body.get('qr_data', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not qr_data:
        return JsonResponse({'error': 'No QR data provided'}, status=400)

    try:
        employee = Employee.objects.get(employee_id=qr_data)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found. Invalid QR code.'}, status=404)

    today = timezone.localdate()
    now = timezone.localtime()
    current_time = now.time()

    # Check if already checked in today
    record = AttendanceRecord.objects.filter(employee=employee, date=today).first()

    can_checkin = False
    can_checkout = False
    is_past_cutoff = current_time >= time(CHECKIN_CUTOFF_HOUR, 0)

    if record:
        if record.check_in_time:
            can_checkout = True
        else:
            # Record exists but no check-in (absent record)
            if not is_past_cutoff:
                can_checkin = True
    else:
        if not is_past_cutoff:
            can_checkin = True

    checkouts = []
    if record:
        checkouts = list(record.checkouts.values('check_out_time').order_by('-check_out_time'))
        for co in checkouts:
            co['check_out_time'] = timezone.localtime(co['check_out_time']).strftime('%I:%M:%S %p')

    return JsonResponse({
        'success': True,
        'employee': {
            'name': employee.name,
            'email': employee.email,
            'id': str(employee.employee_id),
        },
        'attendance': {
            'checked_in': record is not None and record.check_in_time is not None,
            'check_in_time': timezone.localtime(record.check_in_time).strftime('%I:%M:%S %p') if record and record.check_in_time else None,
            'status': record.status if record else None,
            'checkouts': checkouts,
        },
        'can_checkin': can_checkin,
        'can_checkout': can_checkout,
        'is_past_cutoff': is_past_cutoff,
        'cutoff_hour': CHECKIN_CUTOFF_HOUR,
    })


@csrf_exempt
def checkin(request):
    """
    API endpoint: check in an employee.
    Receives employee_id and base64-encoded photo.
    After 11 AM, check-in is blocked and employee is auto-marked absent.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        employee_id = body.get('employee_id', '').strip()
        photo_data = body.get('photo', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not employee_id:
        return JsonResponse({'error': 'Employee ID required'}, status=400)

    try:
        employee = Employee.objects.get(employee_id=employee_id)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)

    today = timezone.localdate()
    now = timezone.localtime()
    current_time = now.time()

    # Check cutoff
    if current_time >= time(CHECKIN_CUTOFF_HOUR, 0):
        # Auto-mark absent
        record, created = AttendanceRecord.objects.get_or_create(
            employee=employee,
            date=today,
            defaults={'status': 'absent'}
        )
        if created or record.status != 'absent':
            record.status = 'absent'
            record.save()
        return JsonResponse({
            'error': f'Check-in not allowed after {CHECKIN_CUTOFF_HOUR}:00 AM. You are marked absent.',
            'status': 'absent'
        }, status=403)

    # Check if already checked in
    existing = AttendanceRecord.objects.filter(employee=employee, date=today, check_in_time__isnull=False).first()
    if existing:
        return JsonResponse({'error': 'Already checked in today.'}, status=400)

    # Create or update attendance record
    record, created = AttendanceRecord.objects.get_or_create(
        employee=employee,
        date=today,
    )
    record.check_in_time = now
    record.status = 'present'

    # Save photo
    if photo_data:
        # Remove data URL prefix if present
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]
        try:
            photo_bytes = base64.b64decode(photo_data)
            filename = f"checkin_{employee.employee_id}_{today}.png"
            record.check_in_photo.save(filename, ContentFile(photo_bytes), save=False)
        except Exception:
            pass  # Continue even if photo save fails

    record.save()

    return JsonResponse({
        'success': True,
        'message': f'Check-in successful at {now.strftime("%I:%M:%S %p")}',
        'check_in_time': now.strftime('%I:%M:%S %p'),
        'status': 'present',
    })


@csrf_exempt
def checkout(request):
    """
    API endpoint: check out an employee.
    Multiple check-outs allowed per day.
    Receives employee_id and base64-encoded photo.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        employee_id = body.get('employee_id', '').strip()
        photo_data = body.get('photo', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not employee_id:
        return JsonResponse({'error': 'Employee ID required'}, status=400)

    try:
        employee = Employee.objects.get(employee_id=employee_id)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)

    today = timezone.localdate()

    # Must have checked in first
    record = AttendanceRecord.objects.filter(
        employee=employee, date=today, check_in_time__isnull=False
    ).first()

    if not record:
        return JsonResponse({'error': 'You must check in before checking out.'}, status=400)

    # Create checkout record
    checkout_record = CheckOutRecord(attendance=record)

    # Save photo
    if photo_data:
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]
        try:
            photo_bytes = base64.b64decode(photo_data)
            now = timezone.localtime()
            filename = f"checkout_{employee.employee_id}_{today}_{now.strftime('%H%M%S')}.png"
            checkout_record.check_out_photo.save(filename, ContentFile(photo_bytes), save=False)
        except Exception:
            pass

    checkout_record.save()

    checkout_time = timezone.localtime(checkout_record.check_out_time)

    return JsonResponse({
        'success': True,
        'message': f'Check-out recorded at {checkout_time.strftime("%I:%M:%S %p")}',
        'check_out_time': checkout_time.strftime('%I:%M:%S %p'),
        'total_checkouts': record.checkouts.count(),
    })


def dashboard(request):
    """Admin dashboard showing all attendance records for today."""
    today = timezone.localdate()
    records = AttendanceRecord.objects.filter(date=today).select_related('employee').prefetch_related('checkouts')

    # Auto-mark absent for employees who haven't checked in after cutoff
    now = timezone.localtime()
    if now.time() >= time(CHECKIN_CUTOFF_HOUR, 0):
        all_employees = Employee.objects.all()
        for emp in all_employees:
            record, created = AttendanceRecord.objects.get_or_create(
                employee=emp,
                date=today,
                defaults={'status': 'absent'}
            )
            if created:
                pass  # Already set to absent by default

    # Re-fetch after auto-marking
    records = AttendanceRecord.objects.filter(date=today).select_related('employee').prefetch_related('checkouts')

    stats = {
        'total': Employee.objects.count(),
        'present': records.filter(status='present').count(),
        'absent': records.filter(status='absent').count(),
    }

    return render(request, 'attendance/dashboard.html', {
        'records': records,
        'stats': stats,
        'today': today,
    })
