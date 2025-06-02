import pdfplumber
import json
import os
import google.generativeai as genai
import fitz
import requests
import tempfile
import hashlib
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging

# Enhanced Configuration
cache_dir = '/cache'
API_KEY = "AIzaSyCLXIu6Bf4WYsUDJTzjNqIHRzih5CN5Ngc"
genai.configure(api_key=API_KEY)

# Enhanced model configuration for reduced hallucination
model = genai.GenerativeModel(
    'gemini-2.5-flash-preview-04-17',
    generation_config={
        "temperature": 0.1,  # Lower temperature for more deterministic output
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 4096,
    }
)

# Schema validation configuration
ALLOW_NULL_FIELDS = ["revision_number", "contact_name", "email"]
STRICT_FIELDS = ["certificate_number", "policy_number", "effective_date", "expiration_date"]
OPTIONAL_LIMITS = ["damage_to_rented_premises", "medical_expense_any_one_person"]

# Optimized extraction settings
PDFPLUMBER_SETTINGS = {
    "horizontal_strategy": "text", 
    "vertical_strategy": "lines",
    "snap_tolerance": 4,
    "join_tolerance": 10,
    "edge_min_length": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1
}

FITZ_SETTINGS = {
    "flags": fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_MEDIABOX_CLIP,
    "sort": True,
    "textpage": True
}

# Validation Exception Classes
class ValidationError(Exception):
    pass

class MissingFieldError(ValidationError):
    pass

class TemporalError(ValidationError):
    pass

class FormatError(ValidationError):
    pass

class ConsensusError(ValidationError):
    pass

# Enhanced logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """Normalize text to handle differences between extraction libraries"""
    if not text:
        return ""
    
    # Normalize whitespace while preserving meaningful structure
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Standardize address formatting
    text = re.sub(r'\n+', ' ', text)
    
    # Clean up common OCR artifacts
    text = re.sub(r'[^\w\s\-.,@()$#]', '', text)
    
    return text

def extract_text_pdfplumber_enhanced(pdf_path: str) -> str:
    """Enhanced pdfplumber extraction with optimized settings"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Use optimized settings for better text extraction
                page_text = page.extract_text(**PDFPLUMBER_SETTINGS)
                if page_text:
                    text += normalize_text(page_text) + "\n"
    except Exception as e:
        logger.error(f"pdfplumber enhanced extraction error: {e}")
    return text

def extract_text_fitz_enhanced(pdf_path: str) -> str:
    """Enhanced PyMuPDF extraction with optimized settings"""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            # Use optimized flags for better text extraction
            page_text = page.get_text(**FITZ_SETTINGS)
            if page_text:
                text += normalize_text(page_text) + "\n"
        doc.close()
    except Exception as e:
        logger.error(f"fitz enhanced extraction error: {e}")
    return text

def extract_tables_enhanced(pdf_path: str) -> List[Dict]:
    """Enhanced table extraction with better configuration"""
    all_tables = []
    
    # Enhanced pdfplumber table extraction
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Use enhanced table extraction settings
                table_settings = {
                    "vertical_strategy": "lines_strict",
                    "horizontal_strategy": "lines_strict",
                    "snap_tolerance": 3,
                    "join_tolerance": 3
                }
                tables = page.extract_tables(table_settings)
                if tables:
                    for table_idx, table in enumerate(tables):
                        if table and len(table) > 1 and any(any(cell for cell in row if cell) for row in table):
                            all_tables.append({
                                'page': page_num + 1,
                                'table_index': table_idx,
                                'source': 'pdfplumber_enhanced',
                                'data': table,
                                'confidence': calculate_table_confidence(table)
                            })
    except Exception as e:
        logger.error(f"Enhanced pdfplumber table extraction error: {e}")
    
    # Enhanced fitz table extraction
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            tabs = page.find_tables(
                snap_tolerance=3,
                strategy="lines_strict"
            )
            if tabs.tables:
                for table_idx, table in enumerate(tabs.tables):
                    extracted = table.extract()
                    if extracted and len(extracted) > 1:
                        all_tables.append({
                            'page': page_num + 1,
                            'table_index': table_idx,
                            'source': 'fitz_enhanced',
                            'data': extracted,
                            'confidence': calculate_table_confidence(extracted)
                        })
        doc.close()
    except Exception as e:
        logger.error(f"Enhanced fitz table extraction error: {e}")
    
    return sorted(all_tables, key=lambda x: x['confidence'], reverse=True)

def calculate_table_confidence(table: List[List]) -> float:
    """Calculate confidence score for extracted table"""
    if not table:
        return 0.0
    
    total_cells = sum(len(row) for row in table)
    filled_cells = sum(1 for row in table for cell in row if cell and str(cell).strip())
    
    if total_cells == 0:
        return 0.0
    
    fill_ratio = filled_cells / total_cells
    structure_score = min(1.0, len(table) / 5)  # Prefer tables with reasonable row count
    
    return (fill_ratio * 0.7) + (structure_score * 0.3)

def intelligent_chunking(text: str, max_chars: int = 6000) -> str:
    """Smart chunking that preserves document structure and key sections"""
    if len(text) <= max_chars:
        return text
    
    # Priority sections for insurance documents
    priority_patterns = [
        r'certificate\s+number[:\s]+\w+',
        r'policy\s+number[:\s]+[\w\-]+',
        r'effective\s+date[:\s]+\d+',
        r'expiration\s+date[:\s]+\d+',
        r'general\s+aggregate[:\s]+[\$\d,]+',
        r'each\s+occurrence[:\s]+[\$\d,]+',
        r'workers\s+compensation',
        r'liability\s+limits?',
        r'certificate\s+holder'
    ]
    
    # Find all priority sections
    priority_sections = []
    for pattern in priority_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 200)
            priority_sections.append((start, end, match.group()))
    
    # Build optimized chunk
    if priority_sections:
        # Sort by position and merge overlapping sections
        priority_sections.sort()
        merged_sections = []
        current_start, current_end = priority_sections[0][:2]
        
        for start, end, _ in priority_sections[1:]:
            if start <= current_end + 50:  # Merge if close
                current_end = max(current_end, end)
            else:
                merged_sections.append((current_start, current_end))
                current_start, current_end = start, end
        merged_sections.append((current_start, current_end))
        
        # Build chunk from merged sections
        chunk_parts = []
        total_length = 0
        
        for start, end in merged_sections:
            section = text[start:end]
            if total_length + len(section) <= max_chars:
                chunk_parts.append(section)
                total_length += len(section)
            else:
                # Add partial section if space remains
                remaining = max_chars - total_length
                if remaining > 100:
                    chunk_parts.append(section[:remaining])
                break
        
        return " ... ".join(chunk_parts)
    
    # Fallback: take first max_chars with sentence boundary
    truncated = text[:max_chars]
    last_sentence = truncated.rfind('.')
    if last_sentence > max_chars * 0.7:  # If found in last 30%
        return truncated[:last_sentence + 1]
    
    return truncated

def validate_required_fields(data: Dict[str, Any]) -> bool:
    """Validate that all required fields are present and non-empty"""
    required_paths = [
        "certificate_number",
        "certificate_information.certificate_type",
        "certificate_information.issued_date",
        "policies.commercial_general_liability.policy_number",
        "policies.workers_compensation_and_employers_liability.policy_number"
    ]
    
    for path in required_paths:
        if not get_nested_value(data, path):
            logger.warning(f"Missing required field: {path}")
            return False
    return True

def get_nested_value(data: Dict, path: str) -> Any:
    """Get value from nested dictionary using dot notation"""
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    
    return current if current and str(current).strip() else None

def validate_date_sequence(data: Dict[str, Any]) -> bool:
    """Validate temporal consistency in dates"""
    try:
        # Extract dates
        issued_date = get_nested_value(data, "certificate_information.issued_date")
        cgl_effective = get_nested_value(data, "policies.commercial_general_liability.effective_date")
        cgl_expiration = get_nested_value(data, "policies.commercial_general_liability.expiration_date")
        wc_effective = get_nested_value(data, "policies.workers_compensation_and_employers_liability.effective_date")
        wc_expiration = get_nested_value(data, "policies.workers_compensation_and_employers_liability.expiration_date")
        
        # Parse dates
        dates = {}
        for name, date_str in [
            ("issued", issued_date),
            ("cgl_effective", cgl_effective),
            ("cgl_expiration", cgl_expiration),
            ("wc_effective", wc_effective),
            ("wc_expiration", wc_expiration)
        ]:
            if date_str:
                try:
                    dates[name] = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    logger.warning(f"Invalid date format for {name}: {date_str}")
                    return False
        
        # Validate sequences
        if "cgl_effective" in dates and "cgl_expiration" in dates:
            if dates["cgl_effective"] >= dates["cgl_expiration"]:
                return False
        
        if "wc_effective" in dates and "wc_expiration" in dates:
            if dates["wc_effective"] >= dates["wc_expiration"]:
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Date validation error: {e}")
        return False

def validate_certificate_number_format(cert_number: str) -> bool:
    """Validate certificate number format"""
    if not cert_number:
        return False
    
    # Common certificate number patterns
    patterns = [
        r'^[A-Z0-9]{8,20}$',  # Alphanumeric 8-20 chars
        r'^[A-Z]{2,4}-\d{6,12}$',  # Letter prefix with dash and numbers
        r'^\d{8,15}$',  # Numeric only
        r'^[A-Z0-9]{2,6}-[A-Z0-9]{6,12}$'  # Alphanumeric with dash
    ]
    
    return any(re.match(pattern, cert_number.strip()) for pattern in patterns)

def calculate_extraction_confidence(data: Dict[str, Any], pdf_text: str) -> float:
    """Calculate overall confidence score for the extraction"""
    confidence_factors = []
    
    # 1. Field completeness (30% weight)
    required_fields = [
        "certificate_number",
        "policies.commercial_general_liability.policy_number",
        "policies.workers_compensation_and_employers_liability.policy_number"
    ]
    
    filled_required = sum(1 for field in required_fields if get_nested_value(data, field))
    completeness_score = filled_required / len(required_fields)
    confidence_factors.append(("completeness", completeness_score, 0.3))
    
    # 2. Date validity (25% weight)
    date_valid = validate_date_sequence(data)
    confidence_factors.append(("dates", 1.0 if date_valid else 0.3, 0.25))
    
    # 3. Certificate number format (20% weight)
    cert_number = data.get("certificate_number", "")
    cert_valid = validate_certificate_number_format(cert_number)
    confidence_factors.append(("cert_format", 1.0 if cert_valid else 0.2, 0.2))
    
    # 4. Text extraction quality (15% weight)
    text_quality = min(1.0, len(pdf_text.strip()) / 1000)  # Normalize by expected length
    confidence_factors.append(("text_quality", text_quality, 0.15))
    
    # 5. Policy limits consistency (10% weight)
    limits_valid = validate_policy_limits(data)
    confidence_factors.append(("limits", 1.0 if limits_valid else 0.5, 0.1))
    
    # Calculate weighted average
    total_score = sum(score * weight for _, score, weight in confidence_factors)
    
    logger.info(f"Confidence breakdown: {confidence_factors}")
    return total_score

def validate_policy_limits(data: Dict[str, Any]) -> bool:
    """Validate that policy limits are reasonable"""
    try:
        # Check CGL limits
        cgl_limits = get_nested_value(data, "policies.commercial_general_liability.limits")
        if cgl_limits:
            occurrence = cgl_limits.get("each_occurrence", "")
            aggregate = cgl_limits.get("general_aggregate", "")
            
            if occurrence and aggregate:
                try:
                    occurrence_val = int(re.sub(r'[^\d]', '', occurrence))
                    aggregate_val = int(re.sub(r'[^\d]', '', aggregate))
                    
                    # Aggregate should typically be >= occurrence
                    if occurrence_val > 0 and aggregate_val > 0:
                        if aggregate_val < occurrence_val:
                            return False
                        
                        # Reasonable ranges (e.g., $100k to $10M)
                        if not (100000 <= occurrence_val <= 10000000):
                            return False
                            
                except ValueError:
                    return False
        
        return True
        
    except Exception as e:
        logger.error(f"Limits validation error: {e}")
        return False

def consensus_check(extracted_data: Dict[str, Any], fitz_text: str, plumber_text: str) -> bool:
    """Check consensus between extraction methods for key fields"""
    try:
        # Key fields to cross-validate
        cert_number = extracted_data.get("certificate_number", "")
        
        if cert_number:
            # Check if certificate number appears in both text sources
            cert_in_fitz = cert_number in fitz_text
            cert_in_plumber = cert_number in plumber_text
            
            if not (cert_in_fitz or cert_in_plumber):
                logger.warning(f"Certificate number {cert_number} not found in source text")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Consensus check error: {e}")
        return False

def validate_extraction(raw_data: Dict[str, Any], pdf_text: str, fitz_text: str, plumber_text: str) -> Dict[str, Any]:
    """Multi-stage validation pipeline"""
    
    # Stage 1: Schema Completeness Check
    if not validate_required_fields(raw_data):
        raise MissingFieldError("Required fields missing from extraction")
    
    # Stage 2: Cross-Library Consensus
    if not consensus_check(raw_data, fitz_text, plumber_text):
        raise ConsensusError("Extraction consensus check failed")
    
    # Stage 3: Temporal Logic Validation
    if not validate_date_sequence(raw_data):
        raise TemporalError("Date sequence validation failed")
    
    # Stage 4: Format Pattern Matching
    cert_number = raw_data.get("certificate_number", "")
    if cert_number and not validate_certificate_number_format(cert_number):
        raise FormatError(f"Invalid certificate number format: {cert_number}")
    
    # Stage 5: Calculate confidence score
    confidence = calculate_extraction_confidence(raw_data, pdf_text)
    
    # Add metadata
    validated_data = raw_data.copy()
    validated_data["_metadata"] = {
        "confidence_score": confidence,
        "validation_passed": True,
        "extraction_timestamp": datetime.now().isoformat()
    }
    
    return validated_data

def is_url(path):
    """Check if the given path is a URL"""
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_url_hash(url):
    """Generate a hash for URL to use as cache filename"""
    return hashlib.md5(url.encode()).hexdigest()

def download_pdf_from_url(url, timeout=30):
    """Download PDF from URL with caching support"""
    try:
        # Check cache first
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{get_url_hash(url)}.pdf")
        
        if os.path.exists(cache_file):
            print(f"Using cached PDF: {cache_file}")
            return cache_file
        
        print(f"Downloading PDF from URL: {url}")
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Write to cache file
        with open(cache_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"PDF downloaded and cached: {cache_file}")
        return cache_file
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading PDF from URL: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during download: {e}")
        return None

def process_pdf_optimized(pdf_path):
    """Optimized PDF processing using parallel extraction with enhanced validation"""
    start_time = time.time()
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit enhanced extraction tasks
        text_pdfplumber_future = executor.submit(extract_text_pdfplumber_enhanced, pdf_path)
        text_fitz_future = executor.submit(extract_text_fitz_enhanced, pdf_path)
        tables_future = executor.submit(extract_tables_enhanced, pdf_path)
        
        # Get results
        text_pdfplumber = text_pdfplumber_future.result()
        text_fitz = text_fitz_future.result()
        tables = tables_future.result()
    
    # Combine text from both sources with confidence-based selection
    if text_pdfplumber and text_fitz:
        # Use both texts for validation, but prefer the longer/more complete one
        if len(text_pdfplumber.strip()) > len(text_fitz.strip()) * 1.2:
            combined_text = text_pdfplumber
            logger.info("Using pdfplumber text (primary)")
        elif len(text_fitz.strip()) > len(text_pdfplumber.strip()) * 1.2:
            combined_text = text_fitz
            logger.info("Using fitz text (primary)")
        else:
            # Similar lengths - combine smartly
            combined_text = f"{text_pdfplumber}\n\n--- ALTERNATIVE EXTRACTION ---\n\n{text_fitz}"
            logger.info("Using combined text from both sources")
    else:
        combined_text = text_pdfplumber or text_fitz or ""
        logger.info("Using single source text extraction")
    
    # Add high-confidence table data
    if tables:
        high_confidence_tables = [t for t in tables if t['confidence'] > 0.6]
        if high_confidence_tables:
            table_text = "\n\nEXTRACTED TABLES (High Confidence):\n"
            for table_info in high_confidence_tables[:3]:  # Limit to top 3 tables
                table_text += f"\nPage {table_info['page']} ({table_info['source']}, confidence: {table_info['confidence']:.2f}):\n"
                for row in table_info['data'][:10]:  # Limit rows for speed
                    if row:
                        table_text += " | ".join(str(cell) if cell else "" for cell in row) + "\n"
            combined_text += table_text
    
    processing_time = time.time() - start_time
    logger.info(f"Enhanced PDF processing completed in {processing_time:.2f} seconds")
    logger.info(f"Extracted {len(combined_text)} characters, {len(tables)} tables")
    
    return combined_text, text_fitz, text_pdfplumber

def process_insurance_certificate(file_path):
    """
    Enhanced main function to process insurance certificate with comprehensive validation
    Returns: dict with success status and data or error message
    """
    temp_file_path = None
    actual_file_path = file_path
    
    try:
        # Determine if file_path is URL or local file
        if is_url(file_path):
            # Download the PDF from URL (with caching)
            cached_file_path = download_pdf_from_url(file_path)
            if cached_file_path:
                actual_file_path = cached_file_path
                temp_file_path = None  # Don't delete cached files
            else:
                return {
                    "success": False,
                    "error": "Failed to download PDF from URL",
                    "file_path": file_path
                }
        else:
            # Check if local file exists
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"Local file not found: {file_path}",
                    "file_path": file_path
                }
        
        # Process the PDF with enhanced method
        pdf_text, fitz_text, plumber_text = process_pdf_optimized(actual_file_path)
        
        # Use intelligent chunking instead of simple truncation
        optimized_text = intelligent_chunking(pdf_text, max_chars=6000)
        
        # Enhanced prompt with hallucination mitigation strategies
        prompt = f"""
You are an expert insurance document analyzer. Extract data ONLY from the provided text. Do NOT invent or guess any information.

CRITICAL RULES:
1. If a field is not clearly present in the text, use empty string "" (NEVER make up values)
2. For monetary amounts, extract numbers only (no $, commas, or text like "per occurrence")
3. Use YYYY-MM-DD format for all dates
4. Certificate numbers must be exactly as shown in the document
5. If dates seem incorrect or impossible, use empty string ""
6. Policy numbers must be exactly as shown (no guessing)

VALIDATION REQUIREMENTS:
- Effective dates must be before expiration dates
- Certificate numbers typically 8-20 characters, alphanumeric
- Insurance limits are typically between $100,000 and $10,000,000
- If you're uncertain about ANY field, leave it empty rather than guessing

Extract to this EXACT JSON structure:

{{
  "certificate_number": "string (exact from document or empty)",
  "certificate_information": {{
    "certificate_type": "string (exact from document or empty)",
    "issued_date": "YYYY-MM-DD (exact from document or empty)",
    "certificate_number": "string (exact from document or empty)",
    "revision_number": "string (exact from document or empty)"
  }},
  "producer_information": {{
    "name": "string (exact from document or empty)",
    "address": "string (exact from document or empty)",
    "contact_name": "string (exact from document or empty)",
    "phone": "string (exact from document or empty)",
    "email": "string (exact from document or empty)"
  }},
  "insured_information": {{
    "name": "string (exact from document or empty)",
    "address": "string (exact from document or empty)"
  }},
  "policies": {{
    "commercial_general_liability": {{
      "policy_number": "string (exact from document or empty)",
      "effective_date": "YYYY-MM-DD (exact from document or empty)",
      "expiration_date": "YYYY-MM-DD (exact from document or empty)",
      "limits": {{
        "each_occurrence": "string (numbers only, no $ or commas)",
        "damage_to_rented_premises": "string (numbers only, no $ or commas)",
        "medical_expense_any_one_person": "string (numbers only, no $ or commas)",
        "personal_and_advertising_injury": "string (numbers only, no $ or commas)",
        "general_aggregate": "string (numbers only, no $ or commas)",
        "products_completed_operations_aggregate": "string (numbers only, no $ or commas)"
      }}
    }},
    "workers_compensation_and_employers_liability": {{
      "policy_number": "string (exact from document or empty)",
      "effective_date": "YYYY-MM-DD (exact from document or empty)",
      "expiration_date": "YYYY-MM-DD (exact from document or empty)",
      "limits": {{
        "each_accident": "string (numbers only, no $ or commas)",
        "disease_each_employee": "string (numbers only, no $ or commas)",
        "disease_policy_limit": "string (numbers only, no $ or commas)"
      }}
    }}
  }},
  "certificate_holder": {{
    "name": "string (exact from document or empty)",
    "address": "string (exact from document or empty)"
  }},
  "reminders_sent_1_month": false,
  "reminders_sent_1_week": false
}}

Document Text:
{optimized_text}
"""

        # Call Gemini API with enhanced configuration
        gemini_start = time.time()
        try:
            response = model.generate_content(prompt)
            gemini_response_text = response.text
            gemini_time = time.time() - gemini_start
            logger.info(f"Gemini API call completed in {gemini_time:.2f} seconds")

        except Exception as e:
            return {
                "success": False,
                "error": f"Gemini API error: {str(e)}",
                "file_path": file_path
            }
        
        # Parse and validate response
        structured_data = {}
        if gemini_response_text:
            try:
                # Clean response (remove markdown if present)
                clean_response = gemini_response_text.strip()
                if clean_response.startswith('```'):
                    clean_response = clean_response.split('\n', 1)[1].rsplit('\n```', 1)[0]
                
                structured_data = json.loads(clean_response)
                logger.info("JSON parsing successful")
                
                # Apply multi-stage validation
                try:
                    validated_data = validate_extraction(structured_data, pdf_text, fitz_text, plumber_text)
                    confidence_score = validated_data["_metadata"]["confidence_score"]
                    
                    # Determine if human review is needed
                    needs_review = confidence_score < 0.7
                    
                    return {
                        "success": True,
                        "data": validated_data,
                        "file_path": file_path,
                        "processing_info": {
                            "text_length": len(pdf_text),
                            "optimized_text_length": len(optimized_text),
                            "extraction_method": "enhanced_hybrid",
                            "gemini_processing_time": gemini_time,
                            "confidence_score": confidence_score,
                            "needs_human_review": needs_review
                        }
                    }
                    
                except (ValidationError, MissingFieldError, TemporalError, FormatError, ConsensusError) as ve:
                    logger.warning(f"Validation failed: {ve}")
                    # Return data with validation warnings
                    return {
                        "success": True,
                        "data": structured_data,
                        "file_path": file_path,
                        "validation_warnings": [str(ve)],
                        "needs_human_review": True,
                        "processing_info": {
                            "text_length": len(pdf_text),
                            "extraction_method": "enhanced_hybrid_unvalidated",
                            "gemini_processing_time": gemini_time
                        }
                    }
                
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"JSON decode error: {str(e)}",
                    "raw_response": gemini_response_text,
                    "file_path": file_path,
                    "needs_human_review": True
                }
        
        return {
            "success": False,
            "error": "Empty response from Gemini API",
            "file_path": file_path
        }

    except Exception as e:
        logger.error(f"Processing error for {file_path}: {e}")
        return {
            "success": False,
            "error": f"Processing error: {str(e)}",
            "file_path": file_path
        }
    
    finally:
        # Only clean up temporary files (not cached files)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(f"Temporary file cleaned up: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")


# For standalone testing
if __name__ == "__main__":
    test_file_path = 'docs/COI3.pdf'  # Change this to test
    result = process_insurance_certificate(test_file_path)
    
    if result["success"]:
        print("\n" + "="*50)
        print("EXTRACTED INSURANCE CERTIFICATE DATA:")
        print("="*50)
        print(json.dumps(result["data"], indent=2))
        print("="*50)
    else:
        print(f"Error: {result['error']}")