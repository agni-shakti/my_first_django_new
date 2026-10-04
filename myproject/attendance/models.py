import uuid
from django.db import models
from django.utils import timezone


class Employee(models.Model):
    """Employee registered in the attendance system."""
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    employee_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"


class AttendanceRecord(models.Model):
    """
    Single check-in per day per employee.
    After 11 AM, check-in is blocked and status is automatically 'absent'.
    """
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.localdate)
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_in_photo = models.ImageField(upload_to='checkin_photos/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date', '-check_in_time']

    def __str__(self):
        return f"{self.employee.name} - {self.date} - {self.status}"


class CheckOutRecord(models.Model):
    """
    Multiple check-outs allowed per attendance record.
    Each check-out captures a timestamp and photo.
    """
    attendance = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='checkouts')
    check_out_time = models.DateTimeField(auto_now_add=True)
    check_out_photo = models.ImageField(upload_to='checkout_photos/', blank=True, null=True)

    class Meta:
        ordering = ['-check_out_time']

    def __str__(self):
        return f"{self.attendance.employee.name} - checkout at {self.check_out_time}"