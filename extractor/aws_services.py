import boto3
import os
import json
from botocore.exceptions import ClientError
from django.conf import settings
import base64

class AWSInvoiceProcessor:
    def __init__(self):
        """Initialize AWS clients"""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        self.textract_client = boto3.client(
            'textract',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        self.bedrock_enabled = os.environ.get('AWS_BEDROCK_ENABLED', 'False') == 'True'
        
        if self.bedrock_enabled:
            self.bedrock_client = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=os.environ.get('AWS_REGION', 'us-east-1')
            )
        
        self.bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    
    def upload_to_s3(self, file_path, file_name):
        """Upload invoice to S3 bucket"""
        try:
            # Generate unique S3 key
            s3_key = f"invoices/{file_name}"
            
            # Upload file
            with open(file_path, 'rb') as file:
                self.s3_client.upload_fileobj(
                    file,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ContentType': 'application/pdf' if file_name.lower().endswith('.pdf') else 'image/jpeg'}
                )
            
            print(f" Uploaded to S3: {s3_key}")
            return s3_key
        except ClientError as e:
            print(f" S3 upload error: {e}")
            return None
    
    def extract_with_textract(self, file_path, file_name):
        """Extract invoice data using AWS Textract"""
        try:
            # Upload to S3 first
            s3_key = self.upload_to_s3(file_path, file_name)
            
            if not s3_key:
                return None
            
            # Call Textract AnalyzeExpense API (specifically for invoices)
            response = self.textract_client.analyze_expense(
                Document={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                }
            )
            
            # Parse the response
            extracted_data = self._parse_textract_response(response)
            
            # Also get raw text
            raw_text = self._get_raw_text_from_textract(file_path)
            
            return {
                'success': True,
                'data': extracted_data,
                'raw_text': raw_text
            }
            
        except ClientError as e:
            print(f" Textract error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _parse_textract_response(self, response):
        """Parse Textract AnalyzeExpense response for your 3 fields"""
        data = {
            'account_number': None,
            'invoice_number': None,
            'total_amount': None,
            'vendor_name': None,
            'invoice_date': None
        }
        
        # Process expense documents
        for expense_doc in response.get('ExpenseDocuments', []):
            # Extract summary fields (key-value pairs)
            for summary_field in expense_doc.get('SummaryFields', []):
                label = summary_field.get('LabelDetection', {}).get('Text', '')
                value = summary_field.get('ValueDetection', {}).get('Text', '')
                
                # Match to our fields
                label_lower = label.lower()
                
                if 'invoice' in label_lower and 'number' in label_lower:
                    data['invoice_number'] = value
                elif 'account' in label_lower or 'customer' in label_lower or 'merchant' in label_lower:
                    data['account_number'] = value
                elif 'total' in label_lower or 'amount' in label_lower:
                    # Clean up amount (remove $, commas)
                    data['total_amount'] = self._clean_amount(value)
                elif 'vendor' in label_lower or 'merchant' in label_lower or 'seller' in label_lower:
                    data['vendor_name'] = value
                elif 'date' in label_lower:
                    data['invoice_date'] = value
            
            # Also check line item groups for totals
            for line_item_group in expense_doc.get('LineItemGroups', []):
                for line_item in line_item_group.get('LineItems', []):
                    for item in line_item.get('LineItemExpenseFields', []):
                        label = item.get('LabelDetection', {}).get('Text', '')
                        if 'total' in label.lower():
                            value = item.get('ValueDetection', {}).get('Text', '')
                            if value and not data['total_amount']:
                                data['total_amount'] = self._clean_amount(value)
        
        return data
    
    def _get_raw_text_from_textract(self, file_path):
        """Get raw OCR text from Textract (as fallback)"""
        try:
            with open(file_path, 'rb') as file:
                response = self.textract_client.detect_document_text(
                    Document={'Bytes': file.read()}
                )
            
            # Extract all detected text
            text_blocks = []
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    text_blocks.append(block['Text'])
            
            return '\n'.join(text_blocks)
        except:
            return ""
    
    def _clean_amount(self, amount_str):
        """Clean amount string to float"""
        if not amount_str:
            return None
        # Remove currency symbols and spaces
        cleaned = amount_str.replace('$', '').replace('€', '').replace('£', '')
        cleaned = cleaned.replace(',', '').strip()
        try:
            return float(cleaned)
        except:
            return None
    
    def extract_with_bedrock(self, file_path, file_name):
        """Advanced extraction using AWS Bedrock Data Automation"""
        if not self.bedrock_enabled:
            print("Bedrock not enabled, falling back to Textract only")
            return self.extract_with_textract(file_path, file_name)
        
        try:
            # First get raw text from Textract
            textract_result = self.extract_with_textract(file_path, file_name)
            
            if not textract_result['success']:
                return textract_result
            
            # Use Bedrock to intelligently extract the 3 fields
            prompt = f"""
            You are an invoice extraction system. From the following invoice text, extract exactly these fields:
            1. account_number (customer/merchant account ID)
            2. invoice_number (invoice ID/reference)
            3. total_amount (final total amount due)
            
            Return ONLY valid JSON in this format:
            {{
                "account_number": "value or null",
                "invoice_number": "value or null", 
                "total_amount": null or number
            }}
            
            Invoice text:
            {textract_result['raw_text'][:8000]}  # Limit length
            """
            
            # Call Bedrock (using Claude model)
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-v2',
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    "prompt": prompt,
                    "max_tokens_to_sample": 300,
                    "temperature": 0,
                    "top_p": 0.9
                })
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            bedrock_data = json.loads(response_body.get('completion', '{}'))
            
            # Merge with Textract data (prefer Bedrock for the 3 fields)
            final_data = textract_result['data']
            if bedrock_data.get('account_number'):
                final_data['account_number'] = bedrock_data['account_number']
            if bedrock_data.get('invoice_number'):
                final_data['invoice_number'] = bedrock_data['invoice_number']
            if bedrock_data.get('total_amount'):
                final_data['total_amount'] = bedrock_data['total_amount']
            
            return {
                'success': True,
                'data': final_data,
                'raw_text': textract_result['raw_text']
            }
            
        except Exception as e:
            print(f"Bedrock error: {e}")
            return self.extract_with_textract(file_path, file_name)
    
    def process_invoice(self, file_path, file_name):
        """Main processing method"""
        print(f"\n--- Processing with AWS: {file_name} ---")
        
        if self.bedrock_enabled:
            print("Using Bedrock Data Automation")
            result = self.extract_with_bedrock(file_path, file_name)
        else:
            print("Using Textract AnalyzeExpense")
            result = self.extract_with_textract(file_path, file_name)
        
        if result['success']:
            print(f"Extracted - Account: {result['data']['account_number']}")
            print(f"Extracted - Invoice: {result['data']['invoice_number']}")
            print(f"Extracted - Amount: ${result['data']['total_amount']}")
        else:
            print(f"Extraction failed: {result.get('error')}")
        
        return result