from get_secreats import load_env_from_secret
from backend_firebase import get_client
import requests
from encryption_utils import safe_firestore_key, sanitize_input, initialize_firebase, hash_for_FB, formate_number, encrypt_data, decrypt_data, get_logger, hash_for_logging, extract_name_regex, extract_language, db
from datetime import datetime, timezone
import re
from cachetools import TTLCache

logger = get_logger()

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

# Keywords
BUY_KEYWORDS = [
    "price", "pricing", "cost", "charges", "fee",
    "how much", "rate", "plan", "plans", "subscription",
    "payment", "pay", "trial", "buy", "purchase"
]

CONTACT_KEYWORDS = [
    "contact", "call", "phone", "number", "mobile",
    "whatsapp", "email", "reach", "connect",
    "meeting", "demo", "appointment", "book"
]

DECISION_KEYWORDS = [
    "interested", "want", "need", "can you help",
    "is this available", "does this work",
    "tell me more", "details", "order"
]

COMPLAINT_KEYWORDS = [
    "complain", "complaint", "issue", "problem", "bad",
    "poor", "terrible", "wrong", "mistake", "unhappy",
    "disappointed", "not satisfied", "refund"
]

ALL_KEYWORDS = BUY_KEYWORDS + CONTACT_KEYWORDS + DECISION_KEYWORDS


def contains_keyword(message: str, keywords: list) -> bool:
    """Check if message contains any keyword"""
    msg = message.lower()
    return any(k in msg for k in keywords)


def extract_phone(text: str) -> Optional[str]:
    """Extract phone number with better pattern matching"""
    patterns = [
        r'\+?\d{1,3}[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}',  # International
        r'\d{10}',  # 10 digits
        r'\+\d{12}',  # +919876543210
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group().strip()
    return None


def extract_email(text: str) -> Optional[str]:
    """Extract email with improved regex"""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, text)
    return match.group().strip() if match else None


def extract_name_from_message(text: str, phone: str = None, email: str = None) -> Optional[str]:
    """Extract name by removing phone/email from text"""
    cleaned = text
    if phone:
        cleaned = cleaned.replace(phone, "")
    if email:
        cleaned = cleaned.replace(email, "")
    
    # Remove common phrases
    cleaned = re.sub(r'(my name is|i am|this is|call me)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    
    # Get first 2-3 words as name
    words = cleaned.split()
    if 1 <= len(words) <= 3:
        return ' '.join(words).title()
    elif len(words) > 3:
        return ' '.join(words[:1]).title()
    return None


def detect_intent(message: str) -> Optional[str]:
    """Detect user intent from message"""
    msg_lower = message.lower()
    
    if contains_keyword(msg_lower, COMPLAINT_KEYWORDS):
        return "complaint"
    elif contains_keyword(msg_lower, BUY_KEYWORDS):
        return "buying"
    elif contains_keyword(msg_lower, CONTACT_KEYWORDS):
        return "contact"
    elif contains_keyword(msg_lower, DECISION_KEYWORDS):
        return "decision"
    return None

cache_counter = TTLCache(maxsize=1000, ttl=300)

async def chat(client_id: str, message: str, visitor_id: str, rag):
    """
    Psychologically optimized chat function using:
    - Value-first responses (answer before asking)
    - Reciprocity principle (give value → get contact)
    - Empathy-driven complaint handling
    - Contextual feedback collection
    """
    try:
        client_id = safe_firestore_key(client_id)
        message = sanitize_input(message)
        
        # Single Firestore read for performance
        doc_id = hash_for_FB(visitor_id)
        user_ref = db.collection("chat_clients").document(client_id).collection("customer_list").document(doc_id)
        user_doc = user_ref.get()
        
        # --- NEW VISITOR: Value-First Welcome ---
        if not user_doc.exists:
            user_ref.set({
                "status": "active",
                "created_at": datetime.now(timezone.utc),
                "visitor_id": encrypt_data(visitor_id),
                "language": encrypt_data("English"),
                "lead_captured": False,
                "refused": False
            })
            
            logger.log_client_operation(client_id=hash_for_logging(client_id), operation="new_customer", success=True)
            
            # Answer immediately - no barriers
            result = await rag.invoke(message, "English")
            return result + "\n\nI'm your assistant today. Type 'help' to see what I can do. 😊"
        
        # --- EXISTING USER ---
        user_data = user_doc.to_dict()
        status = user_data.get("status", "active")
        language = decrypt_data(user_data.get("language", encrypt_data("English")))
        lead_captured = user_data.get("lead_captured", False)

        if visitor_id not in cache_counter:
            cache_counter[visitor_id] = {"interactions": 1}
        else:
            cache_counter[visitor_id]["interactions"] += 1

        visitor_cache = cache_counter[visitor_id]
        interaction_count = visitor_cache["interactions"]
        
        msg_lower = message.lower().strip()
        
        if message.lower() in ["ok", "thanks", "thank", "thank you", "thank you"]:
            feedback = "You're welcome. I'm here whenever you need help. "
            reply = await rag.invoke_translation(feedback, language)
            return reply
        
        # --- COMMAND HANDLERS ---
        if msg_lower == "help":
            help_text = (
                "👋 *How can I assist you today?*\n\n"
                "• Ask anything about our services\n"
                "• Type 'complain' to report an issue\n"
                "• Type 'change_language' to switch \n"
                "• Type 'ask_for' to provide your contact.\n"
                "• Type 'feedback' to share your experience"
            )
            result = await rag.invoke_translation(help_text, language)
            return result
        
        if msg_lower == "ask_for":
            user_ref.update({"refused": False, "status": "awaiting_language"})
            reply = await rag.invoke_translation("Great! Please provide your name and either your email or phone number so our team can follow up with you. 😊", language)
            return reply
        
        # --- LANGUAGE CHANGE FLOW ---
        if msg_lower == "change_language":
            user_ref.update({"status": "awaiting_language", "last_updated": datetime.now(timezone.utc), "interaction_count": interaction_count})
            return (
                "🌍 *Which language do you prefer?*\n\n"
                "• English\n"
                "• हिंदी (Hindi)\n"
                "• ગુજરાતી (Gujarati)\n"
                "• Hinglish\n\n"
                "Just type your choice! 😊"
            )
        
        if status == "awaiting_language":
            new_lang = extract_language(message)
            if new_lang:
                user_ref.update({
                    "status": "active",
                    "language": encrypt_data(new_lang),
                    "last_updated": datetime.now(timezone.utc),
                    "interaction_count": interaction_count
                })
                response = await rag.invoke_translation(
                    f"✅ Perfect! I'll communicate in {new_lang} from now on. How can I help?",
                    new_lang
                )
                return response
            else:
                user_ref.update({"status": "active", "interaction_count": interaction_count})
                reply = await rag.invoke(message, language)
                return reply

        # --- COMPLAINT HANDLING (Empathy-First Approach) ---
        if msg_lower == "complain" or contains_keyword(msg_lower, COMPLAINT_KEYWORDS):
            if status != "handling_complaint":
                user_ref.update({
                    "status": "handling_complaint",
                    "last_updated": datetime.now(timezone.utc),
                    "interaction_count": interaction_count
                })
                response = await rag.invoke_translation(
                    "I'm really sorry to hear you're facing an issue 😔\n\n"
                    "Please share the details, and I'll make sure our team addresses this. Your satisfaction matters to us! 🙏",
                    language
                )
                return response
        
        if status == "handling_complaint":
            # Store complaint
            user_ref.update({"complaint": encrypt_data(message), "interaction_count": interaction_count})
            
            logger.log_client_operation(client_id=hash_for_logging(client_id), operation="complaint_received", success=True)
            
            # Check if lead already captured
            lead_data = user_data.get("lead_data")
            if not lead_data:
                user_ref.update({"status": "awaiting_contact"})
                response = await rag.invoke_translation(
                    "✅ Thank you for sharing this. Our support team will review it within 24 hours.\n\n"
                    "📩 To ensure we can reach you, please share your *phone number or email*.",
                    language
                )
                return response
            else:
                user_ref.update({"status": "active", "last_updated": datetime.now(timezone.utc), "interaction_count": interaction_count})
                response = await rag.invoke_translation(
                    "✅ Your complaint has been recorded. Our team will contact you soon to resolve this. Thank you for your patience! 🙏",
                    language
                )
                return response
        
        # --- FEEDBACK COLLECTION (Open-Ended & Simple) ---
        if msg_lower in ["feedback", "review"]:
            user_ref.update({"status": "collecting_feedback", "last_updated": datetime.now(timezone.utc), "interaction_count": interaction_count})
            response = await rag.invoke_translation(
                "🌟 *We'd love to hear from you!*\n\n"
                "Share your thoughts about your experience with us. "
                "Your feedback helps us improve! 💭",
                language
            )
            return response
        
        if status == "collecting_feedback":
            feed_back = extract_feedback(message)
            
            user_ref.update({
                "status": "active",
                "feedback_given": True,
                "last_updated": datetime.now(timezone.utc),
                "feedback": encrypt_data(feed_back),
                "interaction_count": interaction_count
            })
            
            response = await rag.invoke_translation(
                "🙏 Thank you so much for sharing! Your feedback is valuable to us.\n\n"
                "Anything else I can help you with today?",
                language
            )
            return response
        
        # --- CONTACT COLLECTION FLOW (After Complaint or High Intent) ---
        if status == "awaiting_contact":
            phone = extract_phone(message)
            email = extract_email(message)
            name = extract_name_from_message(message, phone, email)
            
            if phone or email:
                lead_data = {
                    "name": encrypt_data(name if name else "Not provided"),
                    "phone": encrypt_data(phone if phone else "Not provided"),
                    "email": encrypt_data(email if email else "Not provided"),
                    "intent": user_data.get("intent", "general"),
                    "captured_at": datetime.now(timezone.utc),
                    "status": "new"
                }
                
                user_ref.update({
                    "status": "active",
                    "lead_captured": True,
                    "lead_data": lead_data,
                    "last_updated": datetime.now(timezone.utc),
                    "interaction_count": interaction_count
                })
                
                logger.log_client_operation(client_id=hash_for_logging(client_id), operation="lead_captured", success=True)
                
                thank_you = (
                    f"Thank you{', ' + name if name else ''}! 🙌\n\n"
                    "Our team will reach out shortly. Feel free to ask anything else in the meantime!"
                )
                return await rag.invoke_translation(thank_you, language)
            else:
                if not refused_contact(message):
                    response = await rag.invoke_translation(
                        "I'd need your phone number or email to have our team contact you. Could you share that? 📞✉️",
                        language
                    )
                    return response
                else:
                    user_ref.update({"refused": True, "status": "active"})
                    response = await rag.invoke_translation(
                        "Ok, no problem! We completely respect your privacy. You can continue asking questions here anytime. 😊",
                        language
                    )
                    return response
        
        # --- INTENT DETECTION & VALUE-FIRST CAPTURE ---
        intent = detect_intent(message)
        if intent and not lead_captured and status == "active" and not user_data.get("refused", False):
            # CRITICAL: Answer first (reciprocity principle)
            answer = await rag.invoke(message, language)
            
            user_ref.update({
                "status": "awaiting_contact",
                "intent": intent,
                "last_updated": datetime.now(timezone.utc),
                "interaction_count": interaction_count
            })
            
            trust_ask = (
                f"{answer}\n"
                "---\n"
                "I can connect you with our specialist who can send "
                "you a detailed quote/guide on this. What's the best *email or phone number* "
                "to reach you? (We respect your privacy! 🔒)"
            )
            return trust_ask
        
        # --- CONTEXTUAL FEEDBACK TRIGGER (After 5rd+ Interaction) ---
        if interaction_count % 5 == 0 and not user_data.get("feedback_given", False):
            answer = await rag.invoke(message, language)
            feedback_prompt = (
                f"{answer}\n\n"
                "---\n"
                "😊 *Quick question:* How's your experience so far? (Type 'feedback' to share, or just continue chatting!)"
            )
            return feedback_prompt
        
        # --- DEFAULT RAG RESPONSE ---
        result = await rag.invoke(message, language)
        
        # Engagement hooks (psychological retention)
        hooks = [
            "\n\n*Would you like to know about our pricing or see examples?*",
            "\n\n*I'm here if you have more questions! 😊*",
            "\n\n*Feel free to ask about our current offers!*",
            "\n\n*Would you like to see our pricing or some real-world examples?*",
            "\n\n*I can show you a quick 'Before & After' of our recent work. Interested?*",
            
            # Curiosity (Medium Weight)
            "\n\n*Most people ask about our current seasonal offers—want to see them?* 🎁",
            "\n\n*I have a 1-minute 'Getting Started' guide. Should I share it?*",
            
            # Service/Helpful (Lower Weight)
            "\n\n*Feel free to ask about our process or how we compare to others!*",
            "\n\n*I'm here for any follow-up questions, no matter how small! 😊*",

            # Trust & Clarity
            "\n\n*What matters most to you right now: price, speed, or quality?*",
            "\n\n*Are you exploring options or ready to move forward?*",
            "\n\n*Would it help to see how this works step by step?*",

            # Decision Support
            "\n\n*Want a quick recommendation based on your needs?*",
            "\n\n*Not sure if this is the right fit? I can help you figure that out.*",
            "\n\n*Would a quick comparison help you decide?*",

            # Risk Reduction
            "\n\n*Want to know what most people ask before getting started?*",
            "\n\n*I can walk you through common mistakes people avoid with us.*",
            "\n\n*Curious how long this usually takes from start to finish?* ⏱️",

            # Social Proof Without Bragging
            "\n\n*Want to see what others typically start with?*",
            "\n\n*I can share how similar businesses usually use this.*",
            "\n\n*Interested in a real example from someone like you?*",

            # Engagement Over Time
            "\n\n*Would you like updates when something new or useful comes up?* 🔔",
            "\n\n*Want tips that help even if you don’t start today?*",
            "\n\n*Should I check back later when it’s more convenient?*",

            # Gentle Call to Action
            "\n\n*Would you like to take the next step, or just explore a bit more?*",
            "\n\n*Want to start small and see how it goes?*"

        ]
        
        # Only add hooks after 3+ interactions to avoid overwhelming new users
        if interaction_count % 3 == 0:
            import random
            return result + random.choice(hooks)
        
        if interaction_count % 5 == 0:
            user_ref.update({"interaction_count": interaction_count})

        return result
        
    except Exception as e:
        logger.log_client_operation(client_id=hash_for_logging(client_id), operation="chat_error", success=False, error=str(e))
        return "I'm having a small hiccup! 🙏 Could you try asking that again?"

def extract_feedback(feedback):
    """
    Extracts rating (1-5) and reason from user feedback with comprehensive validation.
    
    Features:
    - Input validation & sanitization
    - Multiple rating formats (1-5, 1/5, 1 stars, ⭐⭐⭐, etc.)
    - Flexible reason extraction with 15+ keyword triggers
    - Length limits to prevent DOS attacks
    - Type coercion for non-string inputs
    - Always returns valid dict (never None)
    
    Args:
        feedback: User feedback text (str, int, or None)
        
    Returns:
        dict: {'rating': int|None, 'reason': str|None}
    """
    import re
    from typing import Dict, Optional
    
    # Default return - always valid dict
    default_result = {'rating': None, 'reason': None}
    
    try:
        # === INPUT VALIDATION ===
        if not feedback:
            return default_result
        
        # Type coercion - handle non-string inputs
        if not isinstance(feedback, str):
            feedback = str(feedback)
        
        # Sanitize - remove control characters & normalize whitespace
        feedback = ' '.join(feedback.split())
        feedback = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', feedback)
        
        # DOS prevention - limit input length
        MAX_LENGTH = 2000
        if len(feedback) > MAX_LENGTH:
            feedback = feedback[:MAX_LENGTH]
        
        # === RATING EXTRACTION (Multiple Formats) ===
        rating_patterns = [
            r'(?<!\d)([1-5])\s*(?:/|out\s+of)\s*5(?!\d)',      # "4/5" or "4 out of 5"
            r'(?<!\d)([1-5])\s*stars?(?!\d)',                   # "4 stars"
            r'(?:rating|rate|score)[\s:]*([1-5])(?!\d)',        # "rating: 4"
            r'([⭐★✨]{1,5})',                                    # "⭐⭐⭐⭐" (emoji stars)
            r'(?<!\d)([1-5])(?!\d)'                             # Standalone "4"
        ]
        
        rating = None
        rating_end_pos = 0
        
        # Try patterns in order of specificity
        for pattern in rating_patterns:
            match = re.search(pattern, feedback, re.IGNORECASE)
            if match:
                matched_value = match.group(1)
                
                # Handle emoji stars (count them)
                if matched_value[0] in '⭐★✨':
                    rating = min(len(matched_value), 5)
                else:
                    rating = int(matched_value)
                
                # Validate range
                if 1 <= rating <= 5:
                    rating_end_pos = match.end()
                    break
                else:
                    rating = None
        
        # No valid rating found
        if rating is None:
            return default_result
        
        # === REASON EXTRACTION ===
        post_rating = feedback[rating_end_pos:].strip()
        
        if not post_rating:
            return {'rating': rating, 'reason': None}
        
        # Reason trigger keywords/punctuation
        reason_keywords = [
            'because', 'as', 'since', 'cause', 'cuz', 'coz',
            'for', 'due to', 'owing to',
            'so', 'that', 'reason', 'why',
            '-', '–', '—', ':'
        ]
        
        # Build pattern from keywords
        keyword_pattern = '|'.join(re.escape(kw) for kw in reason_keywords)
        split_pattern = rf'\b(?:{keyword_pattern})\b'
        
        # Split on reason keywords
        parts = re.split(split_pattern, post_rating, maxsplit=1, flags=re.IGNORECASE)
        
        reason = None
        if len(parts) > 1:
            # Found keyword - extract text after it
            reason = parts[-1].strip()
        elif len(post_rating.strip(' .,!?;:')) > 3:
            # No keyword but meaningful text exists
            reason = post_rating
        
        # Clean reason
        if reason:
            reason = re.sub(r'^[^\w\s]+', '', reason)  # Remove leading punctuation
            reason = re.sub(r'[^\w\s]+$', '', reason)  # Remove trailing punctuation
            reason = ' '.join(reason.split())           # Normalize whitespace
            
            # Validate length
            if len(reason) < 2:
                reason = None
            elif len(reason) > 500:
                # Truncate at word boundary
                reason = reason[:500].rsplit(' ', 1)[0] + '...'
        
        return {'rating': rating, 'reason': reason}
    
    except ValueError as e:
        logger.log_error("extract_feedback.ValueError", f"{e}")
        return default_result
    
    except re.error as e:
        logger.log_error("extract_feedback.RegexError", f"{e}")
        return default_result
    
    except Exception as e:
        logger.log_error("extract_feedback.handle_all_things.py", f"{type(e).__name__}: {e}")
        return default_result

import re

# ---------- REFUSAL KEYWORDS ----------
REFUSAL_KEYWORDS = [
    r"\bno\b",
    r"\bnot now\b",
    r"\blater\b",
    r"\bdon't want\b",
    r"\bdo not want\b",
    r"\bnever\b",
    r"\bskip\b",
    r"\bno thanks\b",
    r"\bnot sharing\b",
    r"\bprefer not\b",
    r"\bkeep it private\b"
]

# Compile regex for efficiency
REFUSAL_PATTERN = re.compile("|".join(REFUSAL_KEYWORDS), re.IGNORECASE)

# ---------- FUNCTION ----------
def refused_contact(text: str) -> bool:
    """
    Detects if user is refusing to provide email or phone.

    Returns:
        True  -> user refuses to give contact
        False -> user does not refuse
    """
    text = text.lower().strip()

    # Quick pattern match for refusal phrases
    if REFUSAL_PATTERN.search(text):
        return True

    # Optional: detect polite declines with emojis or context
    polite_decline_patterns = [
        r"\bnot comfortable\b",
        r"\bi'd rather not\b",
        r"\bno need\b"
    ]
    if re.search("|".join(polite_decline_patterns), text):
        return True

    return False


if __name__ == "__main__":
    def msg(message):
        phone = extract_phone(message)
        name = extract_name_regex(message)
        email = extract_email(message)
        return phone, email, name
    while True:
        print(msg(input("Enter: ")))