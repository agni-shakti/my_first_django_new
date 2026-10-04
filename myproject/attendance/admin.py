from django.contrib import admin
from .models import Employee, AttendanceRecord, CheckOutRecord


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'employee_id', 'created_at')
    search_fields = ('name', 'email')
    readonly_fields = ('employee_id', 'created_at')


class CheckOutInline(admin.TabularInline):
    model = CheckOutRecord
    extra = 0
    readonly_fields = ('check_out_time', 'check_out_photo')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'check_in_time', 'status')
    list_filter = ('status', 'date')
    search_fields = ('employee__name', 'employee__email')
    inlines = [CheckOutInline]


@admin.register(CheckOutRecord)
class CheckOutRecordAdmin(admin.ModelAdmin):
    list_display = ('attendance', 'check_out_time')
    list_filter = ('check_out_time',)
