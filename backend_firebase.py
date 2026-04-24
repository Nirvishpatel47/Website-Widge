from encryption_utils import validate_client_id, hash_for_logging, get_logger, initialize_firebase, decrypt_data, encrypt_data, db
from typing import Dict
from encryption_utils import formate_number, deterministic_hash, get_logger
from typing import Optional
import fitz  # PyMuPDF
import os
import hashlib
import jwt
from datetime import datetime, timedelta
from get_secreats import load_env_from_secret
from datetime import timezone

logger = get_logger()

try:
    SECRETE_JWT_KEY = load_env_from_secret("JWT_SECRET_KEY")
except Exception as e:
    logger.log_error("SECRETE_JWT_KEY. firebase.py", e)

logger = get_logger()

def get_client(client_id: str) -> Dict | None:
    try:
        if not validate_client_id(client_id):
            logger.log_security_event(
                "INVALID_CLIENT_ID",
                {"client_id_hash": hash_for_logging(client_id)}
            )
            return None
        
        #cached = firestore_cache.get(client_id)

        #if cached is not None:
            #return cached
            
        doc = db.collection("chat_clients").document(client_id).get()
        if not doc.exists:
            logger.log_error(
                "get_client",
                f"Client not found: {hash_for_logging(client_id)}"
            )
            return None
        client_data = doc.to_dict()

        for key, value in client_data.items():
            try:
                if any(s not in key.lower() for s in ["password"]):
                    client_data[key] = decrypt_data(value)
            except Exception as e:
                logger.log_error("decrypt_data. get_client. firebase.py", e)
        
        #firestore_cache.set(client_id, client_data)

        return client_data
    
    except Exception as e:
        logger.log_error("get_client .firebase.py", e)
        return None

def add_universal_client(data: dict):
    try:
        doc_ref = db.collection("chat_clients").document()
        #Add the client's data
        unencrypted_data = ["Plan","password","WA_Phone_ID_Hash", "token_hash", "Email_hash"]
        user_id = doc_ref.id

        #Make client id
        data["client_id"] = user_id

        #Formate phone number for actual usage of what'sapp
        phone = data["Phone"]
        data["Phone"] = formate_number(phone)

        #Encryption
        encrypted_data = {}
        if data["token"]:
            data["token_hash"] = deterministic_hash(data["token"])

        if data["Email"]:
            data["Email_hash"] = deterministic_hash(data["Email"])

        for key, values in data.items():
            if any(s in key.lower() for s in unencrypted_data):
                encrypted_data[key] = values
            else:
                encrypted_data[key] = encrypt_data(values)
        if "password" in encrypted_data:
            # Use the dictionary variable 'encrypted_data' here
            encrypted_data["password"] = deterministic_hash(encrypted_data["password"])
        
        db.collection("chat_clients").document(user_id).set(encrypted_data)
        data.clear()
        logger.log_client_operation("CLient_added_to_firestore",user_id,success=True)
    except Exception as e:
        logger.log_error("add_universal_client. firebase.py", e)
    
def get_client_by_client_token(token: str) -> Optional[Dict]:
    """
    Retrieve client data by token address.
    
    Args:
        token: Client's token address
        
    Returns:
        Client data dictionary or None if not found
    """
    try:
        token = deterministic_hash(token)

        query = db.collection("chat_clients").where("token_hash", "==", token).limit(1).get()
        
        if len(query) == 0:
            logger.log_error("get_client_by_email", "Failed to get client from the firebase.")
            return None
        
        client_doc = query[0]
        client_data = client_doc.to_dict()
        
        logger.log_client_operation(
            "Client data fetched from the database by token.",
            client_data["client_id"],
            success=True
        )
        return client_data
        
    except Exception as e:
        logger.log_error("get_client_by_email", e)
        return None
def read_file_content(file, file_name: str) -> Optional[str]:
    """
    Secure high-performance file reader for menu files (PDF/TXT)
    Uses magic number validation instead of python-magic library
    """
    try:
        # ✅ SECURITY: Validate and sanitize filename
        file_name = os.path.basename(file_name)  # Prevent path traversal
        
        if not file_name or len(file_name) > 255:
            logger.log_security_event("INVALID_FILENAME", {"name": file_name})
            raise ValueError("Invalid filename")
        
        # ✅ SECURITY: Block dangerous characters in filename
        dangerous_chars = ["<", ">", ":", '"', "|", "?", "*", "\x00", "\\"]
        if any(char in file_name for char in dangerous_chars):
            logger.log_security_event("DANGEROUS_FILENAME", {"name": file_name})
            raise ValueError("Filename contains dangerous characters")
        
        ext = os.path.splitext(file_name)[1].lower()
        
        # ✅ SECURITY: Whitelist only allowed extensions
        allowed_extensions = [".txt", ".pdf"]
        if ext not in allowed_extensions:
            logger.log_security_event("INVALID_FILE_UPLOAD", {"extension": ext})
            return f"Unsupported file format: {ext}"
        
        # ✅ PERFORMANCE: Use os.fstat instead of seek operations
        file_size = os.fstat(file.fileno()).st_size
        
        # ✅ SECURITY: File size validation (prevent DoS)
        min_size = 10  # At least 10 bytes
        max_size = 10 * 1024 * 1024  # 10MB max
        
        if file_size < min_size or file_size > max_size:
            logger.log_security_event("INVALID_FILE_SIZE", {"size": file_size})
            raise ValueError(f"File size must be between {min_size} and {max_size} bytes")
        
        # ✅ SECURITY: Read file header for magic number validation
        file.seek(0)
        file_header = file.read(2048)  # Read first 2KB
        file.seek(0)
        
        # ✅ SECURITY: Validate file signature (magic numbers)
        if not validate_file_signature(file_header, ext):
            logger.log_security_event(
                "INVALID_FILE_SIGNATURE",
                {"extension": ext, "header": file_header[:20].hex()}
            )
            raise ValueError(f"File content doesn't match {ext} format")
        
        # ✅ SECURITY: Calculate file hash for logging/tracking
        file.seek(0)
        file_hash = hashlib.sha256(file.read()).hexdigest()
        file.seek(0)
        logger.logger.info("FILE_PROCESSING", {"hash": file_hash, "size": file_size})
        
        if ext == ".txt":
            # ✅ PERFORMANCE: Read in chunks for large files
            chunks = []
            chunk_size = 8192  # 8KB chunks
            
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk.decode("utf-8", errors="ignore"))
            
            content = "".join(chunks)
            
            # ✅ SECURITY: Sanitize suspicious patterns in text
            content = sanitize_text_content(content)
            
            return content[:1000000]  # Limit to 1MB
        
        elif ext == ".pdf":
            # ✅ PERFORMANCE: PyMuPDF for fast extraction
            file.seek(0)
            pdf_bytes = file.read()
            
            # ✅ SECURITY: Open PDF with error handling for malformed files
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            except Exception as e:
                logger.log_security_event("MALFORMED_PDF", {"error": str(e)})
                raise ValueError("Invalid or corrupted PDF file")
            
            # ✅ SECURITY: Validate PDF structure
            if not validate_pdf_security(doc):
                doc.close()
                logger.log_security_event("PDF_SECURITY_CHECK_FAILED", {})
                raise ValueError("PDF contains suspicious content")
            
            # ✅ SECURITY: Limit pages (prevent decompression bombs)
            max_pages = min(len(doc), 100)
            
            if len(doc) > 100:
                logger.log_security_event("PDF_TOO_MANY_PAGES", {"pages": len(doc)})
            
            # ✅ PERFORMANCE: List comprehension + join (O(n) vs O(n²))
            text_parts = []
            for page_num in range(max_pages):
                try:
                    page_text = doc[page_num].get_text("text")
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.log_error(f"Error reading page {page_num}", e)
                    continue
            
            doc.close()
            
            text = "".join(text_parts).strip()
            
            # ✅ SECURITY: Check for suspicious content
            if contains_suspicious_patterns(text):
                logger.log_security_event("SUSPICIOUS_PDF_CONTENT", {})
                raise ValueError("PDF contains potentially malicious content")
            
            return text[:1000000]  # Limit to 1MB
        
    except Exception as e:
        logger.log_error("read_file_content_error", e)
        return None


def validate_file_signature(file_header: bytes, extension: str) -> bool:
    """
    Validates file signature (magic numbers) without python-magic library
    Checks the actual file content against expected signatures
    """
    # Define magic numbers for supported file types
    file_signatures = {
        ".pdf": [
            b"%PDF-",  # Standard PDF signature
        ],
        ".txt": [
            # Text files can start with various encodings
            b"\xef\xbb\xbf",  # UTF-8 BOM
            b"\xff\xfe",      # UTF-16 LE BOM
            b"\xfe\xff",      # UTF-16 BE BOM
        ]
    }
    
    if extension == ".pdf":
        # PDF files must start with %PDF-
        if not file_header.startswith(b"%PDF-"):
            return False
        
        # Additional PDF validation - check for %%EOF at the end
        # (We only have header, so just check the start)
        return True
    
    elif extension == ".txt":
        # Text files are more flexible
        # Check if it's valid UTF-8 or ASCII
        try:
            # Try to decode as UTF-8
            file_header.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                # Try ASCII
                file_header.decode("ascii", errors="strict")
                return True
            except:
                # Check for BOM markers
                for signature in file_signatures[".txt"]:
                    if file_header.startswith(signature):
                        return True
                return False
    
    return False


def validate_pdf_security(doc: fitz.Document) -> bool:
    """
    Validates PDF for security threats: JavaScript, embedded files, large objects
    """
    try:
        # ✅ SECURITY: Check for JavaScript (common attack vector)
        metadata_str = str(doc.metadata)
        if "/JavaScript" in metadata_str or "/JS" in metadata_str:
            logger.log_security_event("PDF_JAVASCRIPT_DETECTED", {})
            return False
        
        # ✅ SECURITY: Check for embedded files (potential malware carrier)
        try:
            if doc.embfile_count() > 0:
                logger.log_security_event("PDF_EMBEDDED_FILES", {"count": doc.embfile_count()})
                return False
        except:
            pass
        
        # ✅ SECURITY: Check for excessive object count (deflate bomb indicator)
        xref_length = doc.xref_length()
        if xref_length > 10000:  # Unusually high for a menu
            logger.log_security_event("PDF_EXCESSIVE_OBJECTS", {"count": xref_length})
            return False
        
        # ✅ SECURITY: Check page dimensions (prevent memory exhaustion)
        for page_num in range(min(len(doc), 10)):  # Check first 10 pages
            page = doc[page_num]
            rect = page.rect
            
            # Unreasonably large page dimensions
            if rect.width > 50000 or rect.height > 50000:
                logger.log_security_event("PDF_OVERSIZED_PAGE", {
                    "width": rect.width,
                    "height": rect.height
                })
                return False
        
        return True
        
    except Exception as e:
        logger.log_error("validate_pdf_security_error", e)
        return False


def sanitize_text_content(text: str) -> str:
    """
    Sanitizes text content to remove potentially malicious patterns
    """
    # ✅ SECURITY: Remove null bytes
    text = text.replace("\x00", "")
    
    # ✅ SECURITY: Limit consecutive newlines (prevent formatting attacks)
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n")
    
    return text


def contains_suspicious_patterns(text: str) -> bool:
    """
    Checks for suspicious patterns in extracted text
    """
    import re
    
    # ✅ SECURITY: Check for script tags or suspicious code
    suspicious_patterns = [
        r"<script[^>]*>",
        r"javascript:",
        r"eval\s*\(",
        r"onclick\s*=",
        r"onerror\s*=",
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

def create_jwt(client_id: str, expire_minitue: int = 300):
    """
    SECURITY FIX: Enhanced JWT with additional security claims
    """
    try:
        # Try to decrypt first.
        try:
            client_id = decrypt_data(client_id)
        except Exception as e:
            logger.log_error("client_id. create_jwt. firebase.py", e)
            pass
        if not validate_client_id(client_id):
            logger.log_security_event(
                "INVALID_JWT_CLIENT_ID",
                {"client_id_hash": hash_for_logging(client_id)}
            )
            return None
        import secrets
        # ✅ SECURITY: Add jti (JWT ID) for token revocation capability
        jti = secrets.token_urlsafe(32)
        
        payload = {
            "client_id": client_id,
            "exp": datetime.utcnow() + timedelta(minutes=expire_minitue),
            "iat": datetime.utcnow(),  # Issued at
            "jti": jti,  # JWT ID for revocation
            "iss": "business_portal"  # Issuer
        }
        token = jwt.encode(payload, SECRETE_JWT_KEY, algorithm="HS256")
        
        logger.log_security_event(
            "JWT_CREATED",
            {"client_id_hash": hashlib.sha256(client_id.encode()).hexdigest()}
        )

        return token
        
    except Exception as e:
        logger.log_error("create_jwt", e)
        return None
    
def decode_jwt(token: str):
    """
    SECURITY FIX: Validate JWT with strict algorithm whitelist
    Prevents algorithm confusion attacks
    """
    try:
        if not token or not isinstance(token, str):
            logger.log_security_event("INVALID_JWT_TOKEN", {"error": "Invalid token format"})
            return None
        
        # ✅ CRITICAL: Specify algorithms to prevent algorithm confusion attack
        payload = jwt.decode(token, SECRETE_JWT_KEY, algorithms=["HS256"])
        
        # Validate payload structure
        if not payload.get("client_id"):
            logger.log_security_event("INVALID_JWT_PAYLOAD", {"error": "Missing client_id"})
            return None
        
        # Validate expiration
        exp = payload.get("exp")
        if not exp or datetime.utcnow().timestamp() > exp:
            logger.log_security_event("JWT_EXPIRED", {"error": "Token expired"})
            return None
        
        return payload
    except jwt.ExpiredSignatureError:
        logger.log_security_event("JWT_EXPIRED", {"error": "Token expired"})
        return None
    except jwt.InvalidTokenError as e:
        logger.log_security_event("JWT_INVALID", {"error": str(e)})
        return None
    except Exception as e:
        logger.log_error("decode_jwt", e)
        return None

def decrypt_client_data(data: Dict):
    try:
        for key, value in data.items():
            try:
                data[key] = decrypt_data(value)
            except Exception as e:
                logger.log_error("key_not_found. decrypt_client_data. firebase.py", e)
        return data
    except Exception as e:
        logger.log_error("decrypt_client_data. firebase.py", e)

def get_client_by_email(email: str) -> Optional[Dict]:
    """
    Retrieve client data by email address.
    
    Args:
        email: Client's email address
        
    Returns:
        Client data dictionary or None if not found
    """
    try:
        email = deterministic_hash(email)

        query = db.collection("chat_clients").where("Email_hash", "==", email).limit(1).get()
        
        if len(query) == 0:
            logger.log_error("get_client_by_email", "Failed to get client from the firebase.")
            return None
        
        client_doc = query[0]
        client_data = client_doc.to_dict()
        
        logger.log_client_operation(
            "Client data fetched from the database by email.",
            client_data["client_id"],
            success=True
        )
        return client_data
        
    except Exception as e:
        logger.log_error("get_client_by_email", e)
        return None
    
def get_client_id_by_token(token: str):
    try:
        token = deterministic_hash(token)
        query = db.collection("chat_clients").where("token_hash","==",token).limit(1).get()
        if not query:
            logger.log_error("get_client_id_by_phone_number","Failed to get client from the firebase.")
            return None
        client_doc = query[0]
        client_data = client_doc.to_dict()
        logger.log_client_operation("Client id fetched from the database from moblie number.",client_data["client_id"],success=True)
        return decrypt_data(client_data["client_id"])
    except Exception as e:
        logger.log_error("get_client_id_by_phone_number. firebase.py", e)

def update_uploaded_document(client_id: str, file, file_name: str = "Not Given", append: bool = False):
    """
    Update or append uploaded document content for a client in Firestore.

    Args:
        client_id: Client's unique ID.
        file: File-like object to read.
        file_name: Original name of the uploaded file.
        append: If True, append to existing content. If False, replace it.

    Behavior:
        - Uses read_file_content() for secure reading.
        - Encrypts content before saving.
        - Can append to or replace existing encrypted data.
        - Logs operations and errors.
    """
    try:
        if not validate_client_id(client_id):
            logger.log_security_event(
                "INVALID_CLIENT_ID_UPDATE_DOCUMENT",
                {"client_id_hash": hash_for_logging(client_id)}
            )
            raise ValueError("Invalid client ID")

        # Read file securely
        file_content = read_file_content(file, file_name)
        if not file_content:
            raise ValueError("File content could not be read or is empty")

        client_ref = db.collection("chat_clients").document(client_id)
        doc = client_ref.get()

        new_content = file_content

        # If append is True and data exists, merge contents
        if append and doc.exists:
            existing_data = doc.to_dict().get("Uploaded Document")
            if existing_data:
                try:
                    decrypted_existing = decrypt_data(existing_data)
                    new_content = decrypted_existing + "\n\n" + file_content
                except Exception as decryption_error:
                    logger.log_error("update_uploaded_document_decrypt", decryption_error)
                    # If decryption fails, just overwrite

        # Encrypt final content before saving
        encrypted_content = encrypt_data(new_content)

        # Save back to Firestore
        client_ref.set(
            {
                "Uploaded Document": encrypted_content,
                "updated_at": datetime.now(timezone.utc)
            },
            merge=True
        )

        logger.log_client_operation(
            "Client_uploaded_document_updated",
            client_id,
            success=True
        )
        return True

    except Exception as e:
        logger.log_error("update_uploaded_document", e)
        return False
    
if __name__ == "__main__":
    text = {'Owner Name': 'gAAAAABpQVmgbTMG1P7uBvd1F4r5WTSidV6rvC4RTmAhCJ9HurgNVyCPc72cQFVpth6jZa5CBG_uogPRaEIMQU9dMyybD2-f9g==', 'Phone': 'gAAAAABpQVzRj_cVIAICuLaZnp7ru9nOhH7vfGogoLpsp8O3E4e4zobawutZBvsqPF2wKBPdJr7hKcS_2APr94w0DRsixD7i_A==', 'token_hash': '5d8e675680e6e10a5ca6085d6fd72c9699e78f4d3766c32176f951ba6aeca8cd', 'Business Name': 'gAAAAABpQVmgTu6ng_oBGQSuhqbN_1uLREr_5_4LBoyhiQhbPKcdirwXVkNrOtlvgTAMDS7nlDZQFGWw762buIiKC53uNaYD0g==', 'client_id': 'gAAAAABpQVmg_7_NaKX7AGhKFMr2EMshJMCFpxM4U9Wpp9CtHujLzOb6fOT4BMd3y1HYRr34ykFcclPMdre38E6mK9aqpcJZRbUeQVWDcfdc45RNnQyBT54=', 'status': 'gAAAAABpQVzRWpvzd-tfTmpf0f7us7xKLbY2fww9IrYXAZXIAy_FQZfnviGiWEADmLjar0m-FzBN1Ssur98B2cyfrWT1EORBJw==', 'Email': 'gAAAAABpQVmg5uojkSxrDDqzSbsbz9wc-J-7AhechauaUT9Tc8sRbODCcmzAaX9pkV29Ts-HT_wQQJg7cT0ITqCHmI3Rm-rRp2nr8KghrxPcrEYomY_b5XA=', 'password': 'b4dc17cb079c40f4956b8de981a8d337511f84773d5f17075131d16ebf27477e', 'Uploaded Document': 'gAAAAABpQVmgO7q1tKvmLR0RiUd8BkCbtFXtGEB5xYIjJLg9hOz1RoqrU6zFgQpF2d114R7mPt7plZuvJVh5VhmTpjrkMcYDRtSJ_yo1rCmcQLB0uVsOtggpZ5605Wr_N0IeI-Ko88P2gB41B3-SG0CwZMuNS1PwLyxQp0Cf6XVxAS-Dy3X6qAbRayZpc_78srrUEuo4XJyU', 'token': 'gAAAAABpQVmgMFoxwL90fB2imPCDx9EB926ydsgnXiZ-Rj_bP3kr01vCluYaYEnDZ_vGSXCbXb6fCjUD01JYS826KQII-_ErF3nvZhoH_LckT25fQ-L6fF1_Bht85iMhxgb-yVGmwLU0', 'Email_hash': '67a59ab4d07b439ca081fafe8f78167d546464cad8664ba7ca3ae0c4c701a268', 'Business Type': 'gAAAAABpQVmgjQNI1VpAj_0l9zwSMFGmQkaE2gSaKuR1hH5quNx2zhhMViW6osUVZYNkGxOaAFIM3Ku-FiitkpZqZ8PKKzh0EA==', 'Plan Start Date': 'gAAAAABpQVmgAaBX3HL2DpagtzcvtLmRFNDkOgrG-Axe3JfyPdgCVTwBvptp-XZBvobc6mmAlw9R7etc0QmU9V5g0m2oA8HgOcQGDosw6P27q4GqxiKS_Lk=', 'Plan': 'gAAAAABpQVzRHI4ARVRgYTIlxqCbUtmD2sWUHV9nX-DEUtQ_K519KocmPzYqD6I2hEL0JEmncgWblS0yH5_H6k7_UXDWyLHoVA=='}
    print(decrypt_client_data(text))