import fastapi
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from encryption_utils import get_logger, hash_for_logging, verify_password, decrypt_data
from backend_firebase import add_universal_client
from datetime import datetime, timedelta
from pydantic import EmailStr, BaseModel
from typing import Optional, Tuple
from backend_firebase import read_file_content
from fastapi.responses import HTMLResponse
from backend_firebase import create_jwt, decode_jwt, get_client_by_email, decrypt_client_data, get_client, get_client_by_client_token, get_client_id_by_token, update_uploaded_document
import logging
import time
from threading import Lock
from get_secreats import unwrap_secret
from Rag import RAGBot
from backend_chat import chat
import secrets
from fastapi.templating import Jinja2Templates
from rate_limiter import RateLimiter

rate_limiter = RateLimiter()

logger = get_logger()

log = logging.getLogger(__name__)

app = FastAPI(title="Simple WhatsApp Bot")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="static")

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ChatRequest(BaseModel):
    client_token: str
    visitor_id: str
    message: str

from fastapi.middleware.cors import CORSMiddleware

# Add this right after creating your FastAPI app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RAGCacheManager:
    """
    Secure RAG bot caching with TTL and thread-safe operations.
    Avoids logging sensitive data and ensures safe Firebase queries.
    """
    def __init__(self, ttl_minutes: int = 30, max_cache_size: int = 100):
        self._cache = {}  # {client_id: {'rag': RAGBot, 'client_data': dict, 'expires_at': timestamp}}
        self._ttl_seconds = ttl_minutes * 60
        self._max_cache_size = max_cache_size
        self._hits = 0
        self._misses = 0
        self._lock = Lock()  # ✅ CRITICAL: This creates the lock object, don't call it

    def get_or_create_rag(self, client_id: str) -> Tuple[RAGBot, dict]:
        """Safely get RAG bot from cache or create new one."""
        try:
            current_time = time.time()
           
            # ✅ CORRECT: Use 'with self._lock:' NOT 'self._lock()'
            with self._lock:
                cached_item = self._cache.get(client_id)
                
                if cached_item and current_time < cached_item['expires_at']:
                    self._hits += 1
                    log.info(f"✓ Cache HIT - hits: {self._hits}, misses: {self._misses}")
                    return cached_item['rag'], cached_item['client_data']
                
                self._misses += 1
                log.info(f"✗ Cache MISS - hits: {self._hits}, misses: {self._misses}")
            
            # Fetch client data OUTSIDE the lock
            client_data = get_client(client_id)
    
            if not client_data or client_data == None:
                logger.log_error("client_data. get_or_create_rag. whatsapp.py", "Client_data not found.")
                return None, None
            
            try:
                str_client_data = {}

                for key, value in client_data.items():
                    unwrap_values = unwrap_secret(value)
                    str_client_data[key] = unwrap_values

                client_data.clear()

                client_data = str_client_data
            
            except Exception as e:
                logger.log_error("str_client_data. get_or_create_rag. RAGCacheManager. app.py", e)
            
            uploaded_doc = client_data.get("Uploaded Document")
         
            if not uploaded_doc or not isinstance(uploaded_doc, str):
                logger.log_error("uploaded_doc. get_or_create_rag. whatsapp.py", "Invalid or missing Uploaded Document")
                return None, None

            if len(uploaded_doc.strip()) < 10:
                logger.log_error("uploaded_doc. get_or_create_rag. whatsapp.py", "Document too short or empty after processing")
                return None, None
            
            uploaded_doc = uploaded_doc #Add your details after
           
            # Initialize RAG bot
            rag = RAGBot(client_id=str(client_id), document_text=str(uploaded_doc))
            
            if not rag:
                logger.log_error("rag. get_or_create_rag. whatsapp.py", "Failed to create RAG.")
                return None, None

            # ✅ CORRECT: Store in cache using context manager
            with self._lock:
                self._cache[client_id] = {
                    'rag': rag,
                    'client_data': client_data,
                    'expires_at': current_time + self._ttl_seconds
                }

                if len(self._cache) > self._max_cache_size:
                    self._evict_oldest()
           
            return rag, client_data
        except Exception as e:
            logger.log_error("get_or_create_rag. whatsapp.py", e)
            return None, None

    def _evict_oldest(self):
        """Evict the oldest cache entry safely."""
        try:
            if not self._cache:
                return
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]['expires_at'])
            del self._cache[oldest_key]
        except Exception as e:
            logger.log_error("_evict_oldest. whatsapp.py", e)

    def invalidate(self, client_id: str):
        """Invalidate cache safely."""
        try:
            # ✅ CORRECT: Use context manager
            with self._lock:
                if client_id in self._cache:
                    del self._cache[client_id]
        except Exception as e:
            logger.log_error("invalidate. whatsapp.py", e)

    def cleanup_expired(self):
        """Remove expired entries safely."""
        try:
            current_time = time.time()
            # ✅ CORRECT: Use context manager
            with self._lock:
                expired_keys = [k for k, v in self._cache.items() if current_time >= v['expires_at']]
                for k in expired_keys:
                    del self._cache[k]
        except Exception as e:
            logger.log_error("cleanup_expired. whatsapp.py", e)

    def get_stats(self) -> dict:
        """Get cache statistics safely."""
        try:
            # ✅ CORRECT: Use context manager for thread-safe read
            with self._lock:
                total_requests = self._hits + self._misses
                hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
                return {
                    'cache_size': len(self._cache),
                    'hits': self._hits,
                    'misses': self._misses,
                    'hit_rate': f"{hit_rate:.2f}%",
                    'total_requests': total_requests
                }
        except Exception as e:
            logger.log_error("get_stats. whatsapp.py", e)
            return {}

# Global cache manager instance
rag_cache = RAGCacheManager(ttl_minutes=30, max_cache_size=100)

@app.post("/api/register")
async def register_endpoint(request: Request, business_name: str = Form(...), business_type: str = Form(...), owner_name: str = Form(...), phone: str = Form(...), email: EmailStr = Form(...),password: str = Form(...), uploaded_file: Optional[UploadFile] = File(None)):
    """Register a new business."""
    try:
        if not all([business_name, business_type, owner_name, phone, email, password]):
            raise HTTPException(status_code=400, detail="All required fields must be filled")
        
        doc_info = "None uploaded"
        if uploaded_file:
            doc_info = read_file_content(uploaded_file.file, uploaded_file.filename)
            if not doc_info:
                raise HTTPException(status_code=400, detail="Failed to process uploaded document")
        
        token = secrets.token_urlsafe(32)

        business_data = {
            "Business Name": business_name,
            "Owner Name": owner_name,
            "Business Type": business_type,
            "Phone": phone,
            "Email": email,
            "password": password,
            "Uploaded Document": doc_info,
            "Plan": "free",
            "Plan Start Date": datetime.now().isoformat(),
            "token": token
        }
        
        try:
            add_universal_client(business_data)
        except Exception as e:
            logger.log_error("add_universal_client. resister_endpoint. app.py", e)
        
        logger.log_client_operation("REGISTRATION_SUCCESS", email, success=True)

        return {
            "status": "success",
            "message": f"Registration for {business_name} completed successfully",
            "code": token  # Return the client token
        }
        """ return {
            "status": "success",
            "message": f"Registration for {business_name} completed successfully"
        } """
    
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("register_endpoint", e)
        raise HTTPException(status_code=500, detail="Registration failed")

# The login endpoint modification (around line 250)
@app.post("/api/login")
async def login_endpoint(request: LoginRequest):
    """Authenticate user and return JWT token."""
    try:
        client_data = get_client_by_email(request.email)
        if not client_data:
            logger.log_security_event(
                "LOGIN_FAILED_NO_USER",
                {"email_hash": hash_for_logging(request.email)}
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        stored_password = (
            client_data.get("password") or 
            client_data.get("Password") or 
            client_data.get("hashed_password")
        )
        
        if not stored_password:
            logger.log_error("login_endpoint", f"No password field found. Available fields: {list(client_data.keys())}")
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not isinstance(stored_password, str):
            logger.log_error("login_endpoint", f"Password is not a string after decryption: {type(stored_password)}")
            raise HTTPException(status_code=500, detail="Invalid password format")

        try:
            password_matches = verify_password(stored_password, request.password)
        except Exception as verify_error:
            logger.log_error("login_endpoint_verify", str(verify_error))
            raise HTTPException(status_code=500, detail="Password verification failed")

        if not password_matches:
            logger.log_security_event(
                "LOGIN_FAILED_WRONG_PASSWORD",
                {"email_hash": hash_for_logging(request.email)}
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        decrypted_data = decrypt_client_data(client_data)
        if not decrypted_data:
            logger.log_error("login_endpoint", "Failed to decrypt client data")
            raise HTTPException(status_code=500, detail="Failed to decrypt client data")

        client_id = (
            decrypted_data.get("Client_ID") or 
            decrypted_data.get("client_id")
        )
        
        if not client_id:
            logger.log_error("login_endpoint", f"No client_id found. Available fields: {list(decrypted_data.keys())}")
            raise HTTPException(status_code=500, detail="Invalid client data")

        jwt_token = create_jwt(client_id, expire_minitue=480)
        if not jwt_token:
            raise HTTPException(status_code=500, detail="Failed to create authentication token")

        logger.log_client_operation("LOGIN_SUCCESS", client_id, success=True)
        
        logger.logger.info(decrypted_data)
        return {
            "status": "success",
            "token": jwt_token,
            "client_data": decrypted_data  # This should include the 'token' field
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("login_endpoint", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

    
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend HTML page."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Frontend not found. Please create static/index.html</h1>", 
            status_code=404
        )
    
@app.post("/health")
async def get_health():
    return {"status": "OK"}

@app.post("/chat")
async def handle_incoming_request(req: ChatRequest):  
    client_token = req.client_token
    message = req.message
    visitor_id = req.visitor_id

    if not client_token or len(client_token) < 30:
        logger.log_error("client_token. handle_incoming_message. frontend_fastapi.py","Failed to get client_token")

    client_id = get_client_id_by_token(client_token)
    
    allowed, reason, retry_after = rate_limiter.check_rate_limit(
                visitor_id,
                client_id,
                message
            )
    
    if not allowed:
        rate_limit_msg = f"⚠️ {reason}"
        if retry_after:
            rate_limit_msg += f" Please try again in {retry_after} seconds."
            return{"reply": rate_limit_msg}

    if not client_id:
        logger.log_error("client_id. handle_incoming_request. frontend_fastapi.py", "Failed to get client_id.")
        return{"reply": "Sorry for inconvinience 😓. Please try again later."}

    result = rag_cache.get_or_create_rag(client_id=client_id)
    if not result or result == (None, None):
        logger.log_error("result. handle_incoming_message. frontend_fastapi.py", "Failed to get result.")
        return{"reply": "Service unavailable 😓. Please try again later."}
    
    rag, client_data = result

    if not client_data:
        return {"reply": "Invalid Client."}

    if client_data["Plan"] != "paid":
        return {"reply": "Service unavailable for now. "}
    
    result = await chat(client_id=client_id, message=req.message, visitor_id=req.visitor_id, rag=rag)

    return {"reply": result}

from fastapi.responses import FileResponse

@app.get("/widget.js")
async def serve_widget():
    return FileResponse("static/widget.js", media_type="application/javascript")

@app.post("/api/upload-document")
async def upload_document(client_id: str, document_file: UploadFile = File(...), document_name: Optional[str] = Form(None)):
    """
    Handles document upload for a specific client and processes it via the RAG Bot.
    """
    try:
        if not document_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid filename"
            )
        
        update_uploaded_document(client_id, document_file.file, document_file.filename)

        logger.log_client_operation("update_uploaded_document", client_id, success=True)
    except Exception as e:
        logger.log_error("upload_document. app.py", e)