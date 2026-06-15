from django.contrib import admin
from .models import Invoice, UploadHistory

class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['account_number', 'invoice_number', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['account_number', 'invoice_number']
    readonly_fields = ['extracted_text', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Extracted Information', {
            'fields': ('account_number', 'invoice_number', 'total_amount', 'status')
        }),
        ('File Information', {
            'fields': ('invoice_file', 'extracted_text')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(UploadHistory)