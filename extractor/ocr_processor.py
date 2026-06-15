import os
from django.conf import settings

class InvoiceOCRProcessor:
    def __init__(self, tesseract_path=None):
        """Initialize with AWS as the primary OCR engine"""
        self.aws_processor = None
        
        try:
            from .aws_services import AWSInvoiceProcessor
            self.aws_processor = AWSInvoiceProcessor()
            print("AWS Textract processor initialized")
        except ImportError:
            print("boto3 not installed. Install with: pip install boto3")
        except Exception as e:
            print(f"AWS initialization error: {e}")
    
    def process_invoice(self, file_path):
        """Process invoice using AWS Textract"""
        file_name = os.path.basename(file_path)
        
        if self.aws_processor:
            result = self.aws_processor.process_invoice(file_path, file_name)
            
            if result['success']:
                extracted_data = result['data']
                return {
                    'text': result['raw_text'],
                    'data': {
                        'account_number': extracted_data.get('account_number'),
                        'invoice_number': extracted_data.get('invoice_number'),
                        'total_amount': extracted_data.get('total_amount')
                    }
                }
            else:
                print(f"AWS processing failed: {result.get('error')}")
        
        return {
            'text': "AWS extraction failed. Please try again.",
            'data': {
                'account_number': None,
                'invoice_number': None,
                'total_amount': None
            }
        }