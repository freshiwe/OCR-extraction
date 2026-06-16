import os
import re
from django.conf import settings

class InvoiceOCRProcessor:
    def __init__(self, tesseract_path=None):
        """Initialize with AWS Textract + LLM processor"""
        self.aws_processor = None
        
        try:
            from .aws_services import AWSInvoiceProcessor
            self.aws_processor = AWSInvoiceProcessor()
            print("[OK] AWS Textract + LLM processor initialized")
        except ImportError:
            print("[ERROR] boto3 not installed. Install with: pip install boto3")
        except Exception as e:
            print(f"[ERROR] AWS initialization error: {e}")
        
        # Store for compatibility
        self.tesseract_path = tesseract_path
    
    def _is_pdf(self, file_path):
        """Check if file is PDF"""
        return file_path.lower().endswith('.pdf')
    
    def _convert_pdf_to_images(self, pdf_path):
        """Convert PDF to images (for Textract processing)"""
        try:
            from pdf2image import convert_from_path
            import tempfile
            
            print(f"Converting PDF to images: {pdf_path}")
            
            # Convert all PDF pages to images (300 DPI for better OCR quality)
            images = convert_from_path(
                pdf_path, 
                dpi=100,
                fmt='png'
            )
            
            print(f"[OK] Converted {len(images)} pages to images")
            
            # Save images to temporary files
            temp_files = []
            for i, image in enumerate(images):
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'_page_{i+1}.png')
                image.save(temp_file.name, 'PNG', optimize=True)
                temp_files.append(temp_file.name)
            
            return temp_files, len(images)
            
        except ImportError:
            print("[ERROR] pdf2image not installed. Install with: pip install pdf2image")
            print("  Also install poppler: https://github.com/oschwartz10612/poppler-windows/releases/")
            return None, 0
        except Exception as e:
            print(f"[ERROR] PDF conversion error: {e}")
            return None, 0
    
    def process_invoice(self, file_path):
        """Process invoice using AWS Textract + LLM"""
        
        # Check if file exists
        if not os.path.exists(file_path):
            return {
                'text': f"File not found: {file_path}",
                'data': {
                    'account_number': None,
                    'invoice_number': None,
                    'total_amount': None
                },
                'pages_processed': 0,
                'success': False
            }
        
        # Check if AWS processor is available
        if not self.aws_processor:
            return {
                'text': "AWS processor not initialized",
                'data': {
                    'account_number': None,
                    'invoice_number': None,
                    'total_amount': None
                },
                'pages_processed': 0,
                'success': False
            }
        
        # Process based on file type
        if self._is_pdf(file_path):
            return self._process_pdf(file_path)
        else:
            return self._process_image(file_path)
    
    def _process_image(self, file_path):
        """Process a single image file"""
        print(f"\n{'='*60}")
        print(f"Processing Image: {os.path.basename(file_path)}")
        print(f"{'='*60}")
        
        # Process with AWS
        result = self.aws_processor.process_invoice(file_path, os.path.basename(file_path))
        
        if result['success']:
            print(f"\n[OK] Image processed successfully")
            print(f"  - Account Number: {result['data'].get('account_number')}")
            print(f"  - Invoice Number: {result['data'].get('invoice_number')}")
            print(f"  - Total Amount: {result['data'].get('total_amount')}")
            
            return {
                'text': result.get('raw_text', ''),
                'data': result['data'],
                'pages_processed': 1,
                'success': True,
                'method': result.get('method', 'unknown')
            }
        else:
            print(f"\n[ERROR] Image processing failed: {result.get('error')}")
            return {
                'text': result.get('raw_text', '') or f"Extraction failed: {result.get('error')}",
                'data': {
                    'account_number': None,
                    'invoice_number': None,
                    'total_amount': None
                },
                'pages_processed': 0,
                'success': False
            }
    
    def _process_pdf(self, file_path):
        """Process a PDF file (convert to images first)"""
        print(f"\n{'='*60}")
        print(f"Processing PDF: {os.path.basename(file_path)}")
        print(f"{'='*60}")
        
        # Convert PDF to images
        image_paths, num_pages = self._convert_pdf_to_images(file_path)
        
        if not image_paths:
            return {
                'text': "Failed to convert PDF to images",
                'data': {
                    'account_number': None,
                    'invoice_number': None,
                    'total_amount': None
                },
                'pages_processed': 0,
                'success': False
            }
        
        print(f"\nProcessing {len(image_paths)} page(s) with Textract + LLM...")
        
        # Process each page and combine results
        page_results = []
        combined_text = []
        
        for i, image_path in enumerate(image_paths, 1):
            print(f"\nProcessing page {i}/{num_pages}...")
            
            # Process single image
            result = self.aws_processor.process_invoice(image_path, f"page_{i}.png")
            
            if result['success']:
                print(f"  [OK] Page {i} processed successfully")
                page_results.append(result)
                if result.get('raw_text'):
                    combined_text.append(f"--- Page {i} ---")
                    combined_text.append(result['raw_text'])
            else:
                print(f"  [ERROR] Page {i} failed: {result.get('error')}")
            
            # Clean up temp file
            try:
                os.unlink(image_path)
            except:
                pass
        
        # Merge results from all pages
        merged_data = self._merge_page_results(page_results)
        full_text = "\n".join(combined_text)
        
        print(f"\n{'='*60}")
        print("Extracted Data:")
        print(f"  - Account Number: {merged_data.get('account_number')}")
        print(f"  - Invoice Number: {merged_data.get('invoice_number')}")
        print(f"  - Total Amount: {merged_data.get('total_amount')}")
        print(f"{'='*60}")
        
        return {
            'text': full_text,
            'data': merged_data,
            'pages_processed': len(page_results),
            'success': len(page_results) > 0,
            'method': 'textract_llm_pdf'
        }
    
    def _merge_page_results(self, page_results):
        """Merge data from multiple pages"""
        merged = {
            'account_number': None,
            'invoice_number': None,
            'total_amount': None
        }
        
        total_candidates = []
        
        for result in page_results:
            data = result.get('data', {})
            
            # Take first non-null values for account and invoice numbers
            for key in ['account_number', 'invoice_number']:
                if merged[key] is None and data.get(key):
                    merged[key] = data[key]
            
            # Collect total amount candidates
            if data.get('total_amount'):
                total_candidates.append(data['total_amount'])
        
        # For total amount, take the largest (often the actual total)
        if total_candidates:
            merged['total_amount'] = max(total_candidates)
        
        return merged