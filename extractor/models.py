from django.db import models

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    # The three main fields you want to extract
    account_number = models.CharField(max_length=100, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Additional useful fields
    vendor_name = models.CharField(max_length=200, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # File storage
    invoice_file = models.FileField(upload_to='invoices/%Y/%m/%d/')
    extracted_text = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Account: {self.account_number} - Invoice: {self.invoice_number} - Amount: ${self.total_amount}"
    
    class Meta:
        ordering = ['-created_at']


class UploadHistory(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='history')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(help_text="File size in bytes")
    
    def __str__(self):
        return f"{self.file_name} - {self.uploaded_at}"