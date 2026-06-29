import boto3
import os
import json
import re
import requests
from botocore.exceptions import ClientError
from django.conf import settings

class AWSInvoiceProcessor:
    def __init__(self):
        """Initialize AWS clients with Groq for LLM extraction"""
        self.textract_client = boto3.client(
            'textract',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        self.bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME')
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        # Groq API configuration
        self.groq_api_key = os.environ.get('GROQ_API_KEY')
        self.groq_api_url = os.environ.get('GROQ_API_URL')
        self.groq_model = os.environ.get('GROQ_MODEL')  
        
        if not self.groq_api_key:
            print("[WARNING] Groq API key not found in environment variables")
    
    def extract_text_with_detect_document_text(self, file_path):
        """Extract raw text using AWS Textract Detect Document Text API only"""
        try:
            with open(file_path, 'rb') as file:
                response = self.textract_client.detect_document_text(
                    Document={'Bytes': file.read()}
                )
            
            # Extract all detected text with line and page information
            text_blocks = []
            full_text = []
            
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    text_blocks.append({
                        'text': block['Text'],
                        'confidence': block.get('Confidence', 0),
                        'page': block.get('Page', 1)
                    })
                    full_text.append(block['Text'])
            
            return {
                'success': True,
                'raw_text': '\n'.join(full_text),
                'text_blocks': text_blocks,
                'pages': max([block.get('Page', 1) for block in response['Blocks'] if block.get('Page')], default=1)
            }
            
        except ClientError as e:
            print(f"Textract Detect Document Text error: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            print(f"Error: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_with_groq(self, raw_text, file_name):
        """Use Groq API to intelligently extract invoice fields"""
        if not self.groq_api_key:
            print("[ERROR] Groq API key not configured")
            return {'success': False, 'error': 'Groq API key not configured'}
        
        try:
            # Prepare the prompt
            prompt = f"""
You are an expert multilingual invoice data extraction system. Extract the following fields from the invoice text below.

FIELD DEFINITIONS (recognize these in ANY language or format):

1. account_number: Any identifier for the customer/buyer or vendor/seller
   - Look for: account, customer, client, member, user, vendor, merchant, subscriber, policy, membership
   - Common labels: Account #, Customer ID, Client Code, Member No, User ID, Vendor Code
   - In other languages: 账户号码, 顧客番号, cuenta, compte, konto, حساب, खाता
   - Can be alphanumeric, 4-25 characters, may contain hyphens or slashes
   - Often appears near customer/vendor information section

2. invoice_number: Any unique identifier for this bill
   - Look for: invoice, bill, receipt, statement, document, reference, order, purchase order
   - Common labels: Invoice #, Bill No, Receipt #, Doc ID, Ref No, PO Number
   - In other languages: 发票号码, 請求書番号, factura, fattura, rechnung, فاتورة, ಬಿಲ್
   - Often starts with prefixes like INV-, BILL-, DOC-, REF-, PO-
   - Usually 5-20 characters, alphanumeric

3. total_amount: The final amount to be paid
   - Look for: total, grand total, amount due, balance due, net amount, sum, payment due
   - In other languages: 总计, 合計, total, montant, totale, gesamt, المجموع, ಕೂಡು
   - Usually found at the bottom, in a summary section, or highlighted
   - Often the largest number on the invoice
   - May be preceded by currency symbols ($, €, £, ¥, ₦, ₹, etc.)
   - May use currency codes (USD, EUR, GBP, NGN, INR, JPY, etc.)
   - May have decimals (both . and , as decimal separators)
   - May have thousand separators (commas, spaces, or dots)

GENERAL RULES:
- Work with ANY language - English, Spanish, French, German, Chinese, Japanese, Arabic, Hindi, etc.
- Work with ANY currency - USD, EUR, GBP, NGN, INR, JPY, and many more
- Work with ANY date format - MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD, etc.
- Be flexible with label variations, abbreviations, and translations
- Search the ENTIRE text, don't assume positions
- If you see a field labeled differently, use your understanding of invoice structure
- Use contextual clues - amounts near "total" are likely the total amount
- If multiple values appear, choose the most logical one

IMPORTANT:
- Return ONLY valid JSON with these exact keys: account_number, invoice_number, total_amount
- If a field is not found with reasonable confidence, set to null
- For total_amount, return as a number (e.g., 1234.56) without currency symbols
- For account_number and invoice_number, return as strings


Invoice Text:
{raw_text[:15000]}

Return JSON in this exact format:
{{
    "account_number": "value or null",
    "invoice_number": "value or null",
    "total_amount": null or number
}}
"""
            
            # Prepare the request payload for Groq (OpenAI-compatible)
            payload = {
                "model": self.groq_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert invoice data extraction system. Always respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0,
                "max_tokens": 500,
                "top_p": 0.9
            }
            
            # Make the API request
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                self.groq_api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Extract the completion text
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    completion = response_data['choices'][0]['message']['content']
                    
                    # Parse the JSON response
                    return self._parse_llm_response(completion)
                else:
                    return {'success': False, 'error': 'Invalid response from Groq API'}
            else:
                print(f"Groq API error: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'Groq API error: {response.status_code}'}
                
        except requests.exceptions.Timeout:
            print("Groq API timeout")
            return {'success': False, 'error': 'Groq API timeout'}
        except requests.exceptions.RequestException as e:
            print(f"Groq API request error: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            print(f"Groq extraction error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _parse_llm_response(self, completion):
        """Parse LLM response to extract JSON"""
        try:
            # Find JSON in the response
            json_match = re.search(r'\{.*\}', completion, re.DOTALL)
            if json_match:
                extracted_data = json.loads(json_match.group())
                
                # Clean amount if present
                if extracted_data.get('total_amount'):
                    try:
                        if isinstance(extracted_data['total_amount'], str):
                            # Remove currency symbols and commas
                            cleaned = re.sub(r'[$,€£¥]', '', extracted_data['total_amount'])
                            extracted_data['total_amount'] = float(cleaned)
                    except:
                        extracted_data['total_amount'] = None
                
                return {
                    'success': True,
                    'data': extracted_data
                }
            else:
                return {'success': False, 'error': 'No JSON found in LLM response'}
                
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return {'success': False, 'error': f'Invalid JSON: {e}'}
    
    def process_invoice(self, file_path, file_name):
        """Main processing method using Detect Document Text + Groq LLM"""
        print(f"\n--- Processing invoice with Textract + Groq: {file_name} ---")
        
        # Step 1: Extract raw text using Detect Document Text API
        textract_result = self.extract_text_with_detect_document_text(file_path)
        
        if not textract_result['success']:
            return {
                'success': False,
                'error': textract_result.get('error', 'Textract extraction failed'),
                'data': None,
                'raw_text': None
            }
        
        print(f"[OK] Textract extracted {len(textract_result['text_blocks'])} text lines from {textract_result['pages']} page(s)")
        
        # Step 2: Use Groq to extract structured data
        llm_result = self.extract_with_groq(
            textract_result['raw_text'],
            file_name
        )
        
        if not llm_result.get('success', False):
            # Fallback: Use regex extraction if LLM fails
            print("[WARNING] Groq extraction failed, using regex fallback")
            fallback_data = self._fallback_extraction(textract_result['raw_text'])
            return {
                'success': True,
                'data': fallback_data,
                'raw_text': textract_result['raw_text'],
                'method': 'regex_fallback'
            }
        
        # Step 3: Return combined results
        print(f"[OK] Groq extracted - Account: {llm_result['data'].get('account_number')}")
        print(f"[OK] Groq extracted - Invoice: {llm_result['data'].get('invoice_number')}")
        print(f"[OK] Groq extracted - Amount: ${llm_result['data'].get('total_amount')}")
        
        return {
            'success': True,
            'data': llm_result['data'],
            'raw_text': textract_result['raw_text'],
            'method': 'groq_llm',
            'text_blocks': textract_result['text_blocks']
        }
    
    def _fallback_extraction(self, text):
        """Fallback regex extraction if LLM fails"""
        data = {
            'account_number': None,
            'invoice_number': None,
            'total_amount': None
        }
        
        # Account number patterns (with synonyms)
        account_patterns = [
            r'(?:account\s+(?:number|no|#|id)|acct\s+(?:number|no|#)|customer\s+(?:id|number|account)|client\s+(?:id|number)|member\s+(?:id|number))\s*:?\s*([A-Z0-9][A-Z0-9\-/ ]{4,20})',
            r'(?:acc|acct|account)\s*[#:]\s*([A-Z0-9\-/ ]{4,20})',
            r'(?:customer|client|member)\s*(?:id|number)\s*:?\s*([A-Z0-9\-/ ]{4,20})',
        ]
        
        # Invoice number patterns
        invoice_patterns = [
            r'(?:invoice\s+(?:number|no|#|id)|inv\s+(?:no|#)|bill\s+(?:number|no))\s*:?\s*([A-Z0-9][A-Z0-9\-/ ]{4,20})',
            r'(?:invoice|inv|bill)\s*[#:]\s*([A-Z0-9\-/ ]{4,20})',
            r'(?:reference|document)\s+(?:number|id)\s*:?\s*([A-Z0-9\-/ ]{5,20})',
            r'(?:INV|DOC|REF|BILL)[\-/]?\s*([A-Z0-9]{4,15})',
        ]
        
        # Total amount patterns
        total_patterns = [
            r'(?:grand\s+total|total\s+amount\s+due|amount\s+due|balance\s+due|total\s+due|invoice\s+total|total\s+invoice|net\s+amount)\s*:?\s*[$€£¥]?\s*([\d,]+\.?\d*)',
            r'(?:total|sum|amount)\s*[=:]\s*[$€£¥]?\s*([\d,]+\.?\d*)',
            r'^total\s*:?\s*(?:USD|EUR|GBP|JPY|NGN)?\s*[$€£¥₦]?\s*([\d,]+\.?\d*)',
        ]
        
        # Extract account number
        for pattern in account_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data['account_number'] = match.group(1).strip()
                break
        
        # Extract invoice number
        for pattern in invoice_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data['invoice_number'] = match.group(1).strip()
                break
        
        # Extract total amount
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    cleaned = re.sub(r'[,]', '', match.group(1))
                    data['total_amount'] = float(cleaned)
                    break
                except:
                    continue
        
        return data
