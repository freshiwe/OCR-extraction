from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.conf import settings
from .forms import InvoiceUploadForm
from .models import Invoice, UploadHistory
from .ocr_processor import InvoiceOCRProcessor
import os
from datetime import datetime

def home(request):
    """Home page with upload interface"""
    form = InvoiceUploadForm()
    recent_invoices = Invoice.objects.all()[:5]
    
    context = {
        'form': form,
        'recent_invoices': recent_invoices,
    }
    return render(request, 'extractor/home.html', context)

def upload_invoice(request):
    """Handle invoice upload and OCR processing"""
    if request.method == 'POST':
        form = InvoiceUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Save the uploaded file
                invoice = form.save(commit=False)
                invoice.status = 'pending'
                invoice.save()
                
                # Save upload history
                UploadHistory.objects.create(
                    invoice=invoice,
                    file_name=request.FILES['invoice_file'].name,
                    file_size=request.FILES['invoice_file'].size
                )
                
                # Process with OCR
                ocr_processor = InvoiceOCRProcessor(settings.TESSERACT_PATH)
                file_path = invoice.invoice_file.path
                
                result = ocr_processor.process_invoice(file_path)
                
                # Update invoice with extracted data (only the 3 fields)
                extracted_data = result['data']
                
                if extracted_data.get('account_number'):
                    invoice.account_number = extracted_data['account_number']
                
                if extracted_data.get('invoice_number'):
                    invoice.invoice_number = extracted_data['invoice_number']
                
                if extracted_data.get('total_amount'):
                    invoice.total_amount = extracted_data['total_amount']
                
                invoice.extracted_text = result['text']
                invoice.save()
                
                # Return JSON response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'invoice': {
                            'id': invoice.id,
                            'account_number': invoice.account_number or 'Not found',
                            'invoice_number': invoice.invoice_number or 'Not found',
                            'total_amount': str(invoice.total_amount) if invoice.total_amount else '0.00',
                            'status': invoice.status
                        }
                    })
                
                messages.success(request, 'Invoice processed successfully!')
                return redirect('invoice_detail', invoice_id=invoice.id)
                
            except Exception as e:
                print(f"Error: {e}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': str(e)})
                
                messages.error(request, f'Error processing invoice: {str(e)}')
                return redirect('home')
    
    return redirect('home')

def invoice_detail(request, invoice_id):
    """Display invoice details for verification"""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    if request.method == 'POST':
        # Manual verification
        invoice.invoice_number = request.POST.get('invoice_number', invoice.invoice_number)
        invoice.vendor_name = request.POST.get('vendor_name', invoice.vendor_name)
        invoice.date = request.POST.get('date', invoice.date)
        invoice.amount = request.POST.get('amount', invoice.amount)
        invoice.status = request.POST.get('status', invoice.status)
        invoice.save()
        
        messages.success(request, 'Invoice details updated successfully!')
        return redirect('invoice_detail', invoice_id=invoice.id)
    
    context = {
        'invoice': invoice,
    }
    return render(request, 'extractor/invoice_detail.html', context)

def upload_history(request):
    """View upload history"""
    history = UploadHistory.objects.select_related('invoice').all()
    
    context = {
        'history': history,
    }
    return render(request, 'extractor/upload_history.html', context)

def verify_invoice(request, invoice_id):
    """AJAX endpoint for quick verification"""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    # Simulate PO cross-referencing
    # In production, you would check against actual purchase orders
    
    if request.method == 'POST':
        invoice.status = 'verified'
        invoice.save()
        
        return JsonResponse({'success': True, 'status': 'verified'})
    
    return JsonResponse({'success': False})