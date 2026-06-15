from django import forms
from .models import Invoice

class InvoiceUploadForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['invoice_file']
        widgets = {
            'invoice_file': forms.FileInput(attrs={
                'accept': '.pdf,.jpg,.jpeg,.png',
                'class': 'file-input'
            })
        }
    
    def clean_invoice_file(self):
        file = self.cleaned_data.get('invoice_file')
        if file:
            # Check file size (max 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size must be under 10MB')
            
            # Check file extension
            ext = file.name.split('.')[-1].lower()
            if ext not in ['pdf', 'jpg', 'jpeg', 'png']:
                raise forms.ValidationError('Only PDF, JPG, JPEG, and PNG files are allowed')
        
        return file