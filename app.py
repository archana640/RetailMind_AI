import streamlit as st
import sqlite3
import pandas as pd
import re
import random
import string
import smtplib

from email.message import EmailMessage
from datetime import datetime, timedelta

from email_validator import validate_email, EmailNotValidError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="RetailMind_AI",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CONSTANTS
# ============================================================

DB_NAME = "retailmind_ai.db"

OTP_EXPIRY_MINUTES = 5

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ============================================================
# GMAIL SETTINGS
# ============================================================

try:
    SMTP_SENDER = st.secrets["gmail"]["sender"]
    SMTP_PASSWORD = st.secrets["gmail"]["app_password"]
    SMTP_ENABLED = True
except Exception:
    SMTP_SENDER = ""
    SMTP_PASSWORD = ""
    SMTP_ENABLED = False


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "logged_in": False,
    "role": None,
    "customer_username": "",
    "otp": None,
    "otp_email": None,
    "otp_created": None,
    "gmail_verified": False,
    "last_analysis": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background: linear-gradient(
            135deg,
            #fff7ed 0%,
            #eff6ff 50%,
            #f5f3ff 100%
        );
    }

    .main-title {
        font-size: 42px;
        font-weight: 800;
        color: #4f46e5;
        text-align: center;
        margin-bottom: 5px;
    }

    .main-subtitle {
        text-align: center;
        color: #64748b;
        font-size: 17px;
        margin-bottom: 30px;
    }

    .top-banner {
        padding: 25px;
        border-radius: 20px;
        background: linear-gradient(
            135deg,
            #ff6b6b,
            #845ec2,
            #00b4d8
        );
        color: white;
        text-align: center;
        margin-bottom: 25px;
    }

    .top-banner h1 {
        font-size: 40px;
        margin: 0;
    }

    .top-banner p {
        font-size: 16px;
        margin-top: 8px;
    }

    .section-title {
        color: #4f46e5;
        font-size: 22px;
        font-weight: 700;
        margin-top: 15px;
    }

    .success-box {
        padding: 20px;
        border-radius: 15px;
        background: #dcfce7;
        border-left: 6px solid #16a34a;
    }

    .warning-box {
        padding: 20px;
        border-radius: 15px;
        background: #ffedd5;
        border-left: 6px solid #ea580c;
    }

    .danger-box {
        padding: 20px;
        border-radius: 15px;
        background: #fee2e2;
        border-left: 6px solid #dc2626;
    }

    .score-number {
        font-size: 55px;
        font-weight: 800;
        color: #4f46e5;
        text-align: center;
    }

    .footer-text {
        text-align: center;
        color: #64748b;
        padding: 30px;
        font-size: 14px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )


def init_database():

    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # CUSTOMERS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            gmail TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            customer_gmail TEXT,
            product TEXT,
            category TEXT,
            platform TEXT,
            price REAL DEFAULT 0,
            purchase_date TEXT
        )
        """
    )

    # --------------------------------------------------------
    # FEEDBACK
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            gmail TEXT NOT NULL,
            product TEXT NOT NULL,
            category TEXT,
            platform TEXT NOT NULL,
            order_id TEXT NOT NULL,
            price REAL DEFAULT 0,
            purchase_date TEXT,
            rating INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            gmail_verified INTEGER DEFAULT 0,
            purchase_verified INTEGER DEFAULT 0,
            sentiment TEXT,
            review_quality TEXT,
            similarity REAL DEFAULT 0,
            authenticity_score REAL DEFAULT 0,
            result TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()

    # ========================================================
    # ORDER TABLE MIGRATION
    # ========================================================

    cursor.execute("PRAGMA table_info(orders)")
    columns = [row[1] for row in cursor.fetchall()]

    required_columns = {
        "customer_gmail": "TEXT",
        "product": "TEXT",
        "category": "TEXT",
        "platform": "TEXT",
        "price": "REAL DEFAULT 0",
        "purchase_date": "TEXT"
    }

    for column, datatype in required_columns.items():

        if column not in columns:

            cursor.execute(
                f"""
                ALTER TABLE orders
                ADD COLUMN {column} {datatype}
                """
            )

    conn.commit()

    # ========================================================
    # DEMO ORDERS
    # ========================================================

    demo_orders = [
        (
            "ORD1001",
            "rahul@gmail.com",
            "iPhone 16",
            "Electronics",
            "Amazon",
            69999,
            "2026-09-20"
        ),
        (
            "ORD1002",
            "priya@gmail.com",
            "Nike Air Max",
            "Footwear",
            "Myntra",
            7999,
            "2026-09-22"
        ),
        (
            "ORD1003",
            "arjun@gmail.com",
            "Sony Headphones",
            "Electronics",
            "Flipkart",
            4999,
            "2026-09-25"
        ),
        (
            "ORD1004",
            "rahul@gmail.com",
            "Samsung TV",
            "Home Appliances",
            "Amazon",
            45999,
            "2026-09-15"
        ),
        (
            "ORD1005",
            "meena@gmail.com",
            "Face Serum",
            "Beauty",
            "Nykaa",
            899,
            "2026-09-27"
        )
    ]

    for order in demo_orders:

        cursor.execute(
            """
            INSERT OR IGNORE INTO orders
            (
                order_id,
                customer_gmail,
                product,
                category,
                platform,
                price,
                purchase_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            order
        )

    conn.commit()
    conn.close()


init_database()


# ============================================================
# GMAIL VALIDATION
# ============================================================

def validate_gmail(email):

    email = email.strip().lower()

    if not email.endswith("@gmail.com"):
        return False, "Only Gmail addresses are accepted."

    try:

        validate_email(
            email,
            check_deliverability=False
        )

        return True, "Valid Gmail address."

    except EmailNotValidError:

        return False, "Invalid Gmail address."


# ============================================================
# OTP
# ============================================================

def generate_otp():

    return "".join(
        random.choices(
            string.digits,
            k=6
        )
    )


def send_otp_email(receiver, otp):

    if not SMTP_ENABLED:
        return False

    try:

        message = EmailMessage()

        message["Subject"] = (
            "RetailMind_AI - Gmail Verification OTP"
        )

        message["From"] = SMTP_SENDER
        message["To"] = receiver

        message.set_content(
            f"""
Hello,

Your RetailMind_AI verification OTP is:

{otp}

This OTP will expire in {OTP_EXPIRY_MINUTES} minutes.

RetailMind_AI
"""
        )

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465
        ) as server:

            server.login(
                SMTP_SENDER,
                SMTP_PASSWORD
            )

            server.send_message(message)

        return True

    except Exception as e:

        st.error(
            f"Unable to send email: {e}"
        )

        return False


def request_otp(email):

    otp = generate_otp()

    st.session_state.otp = otp
    st.session_state.otp_email = email.strip().lower()
    st.session_state.otp_created = datetime.now()
    st.session_state.gmail_verified = False

    if SMTP_ENABLED:

        if send_otp_email(email, otp):

            st.success(
                "📧 OTP sent successfully to your Gmail."
            )

    else:

        st.info(
            f"🧪 DEMO MODE - Your OTP is: {otp}"
        )


def verify_otp(email, entered_otp):

    if not st.session_state.otp:

        return False, "Please request an OTP first."

    if (
        email.strip().lower()
        !=
        st.session_state.otp_email
    ):

        return False, "This OTP belongs to another Gmail."

    if not st.session_state.otp_created:

        return False, "Please request a new OTP."

    difference = (
        datetime.now()
        -
        st.session_state.otp_created
    )

    if difference > timedelta(
        minutes=OTP_EXPIRY_MINUTES
    ):

        return False, "OTP expired. Please request a new OTP."

    if str(entered_otp).strip() != st.session_state.otp:

        return False, "Incorrect OTP."

    st.session_state.gmail_verified = True

    return True, "Gmail ownership verified successfully."


# ============================================================
# PURCHASE VERIFICATION
# ============================================================

def verify_purchase(
    order_id,
    gmail,
    product,
    platform
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            order_id,
            customer_gmail,
            product,
            platform,
            price,
            purchase_date
        FROM orders
        WHERE LOWER(order_id) = LOWER(?)
        """,
        (order_id.strip(),)
    )

    order = cursor.fetchone()

    conn.close()

    if not order:

        return (
            False,
            "Order ID was not found.",
            None
        )

    (
        found_order,
        order_email,
        order_product,
        order_platform,
        order_price,
        purchase_date
    ) = order

    if not order_email:

        return (
            False,
            "Order does not contain customer Gmail information.",
            order
        )

    if order_email.lower() != gmail.lower():

        return (
            False,
            "Gmail does not match the purchaser.",
            order
        )

    if (
        not order_product
        or
        order_product.lower()
        !=
        product.lower()
    ):

        return (
            False,
            "Product does not match the order.",
            order
        )

    if (
        not order_platform
        or
        order_platform.lower()
        !=
        platform.lower()
    ):

        return (
            False,
            "Platform does not match the order.",
            order
        )

    return (
        True,
        "Purchase verified successfully.",
        order
    )


# ============================================================
# SENTIMENT
# ============================================================

positive_words = {
    "excellent",
    "amazing",
    "good",
    "great",
    "nice",
    "love",
    "loved",
    "perfect",
    "fast",
    "quality",
    "useful",
    "comfortable",
    "happy",
    "satisfied",
    "awesome",
    "worth",
    "recommend",
    "recommended"
}


negative_words = {
    "bad",
    "poor",
    "terrible",
    "worst",
    "hate",
    "hated",
    "broken",
    "damaged",
    "slow",
    "late",
    "useless",
    "waste",
    "disappointed",
    "disappointing",
    "fake",
    "problem",
    "problems",
    "refund"
}


def sentiment_analysis(text):

    words = re.findall(
        r"[a-zA-Z]+",
        text.lower()
    )

    positive = sum(
        word in positive_words
        for word in words
    )

    negative = sum(
        word in negative_words
        for word in words
    )

    if positive > negative:

        sentiment = "Positive"

    elif negative > positive:

        sentiment = "Negative"

    else:

        sentiment = "Neutral"

    total = positive + negative

    if total == 0:

        confidence = 50

    else:

        confidence = min(
            95,
            50 + abs(positive - negative) * 12
        )

    return sentiment, confidence


# ============================================================
# REVIEW QUALITY
# ============================================================

def review_quality(text):

    words = text.split()

    if len(words) < 5:
        return "Low"

    if len(words) < 12:
        return "Medium"

    return "High"


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def calculate_similarity(text):

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT feedback
        FROM feedback
        """,
        conn
    )

    conn.close()

    if df.empty:
        return 0, None

    previous_reviews = (
        df["feedback"]
        .dropna()
        .tolist()
    )

    if not previous_reviews:
        return 0, None

    all_reviews = previous_reviews + [text]

    try:

        vectorizer = TfidfVectorizer(
            stop_words="english"
        )

        vectors = vectorizer.fit_transform(
            all_reviews
        )

        similarities = cosine_similarity(
            vectors[-1],
            vectors[:-1]
        )[0]

        index = similarities.argmax()

        highest = float(
            similarities[index]
        )

        return highest, previous_reviews[index]

    except Exception:

        return 0, None


# ============================================================
# RATING CONSISTENCY
# ============================================================

def check_rating_consistency(
    rating,
    sentiment
):

    if rating >= 4 and sentiment == "Negative":

        return (
            False,
            "High rating but negative feedback."
        )

    if rating <= 2 and sentiment == "Positive":

        return (
            False,
            "Low rating but positive feedback."
        )

    return (
        True,
        "Rating and feedback are consistent."
    )


# ============================================================
# FEEDBACK ANALYSIS
# ============================================================

def analyze_feedback(
    feedback,
    rating,
    gmail_verified,
    purchase_verified
):

    words = feedback.split()

    score = 0

    positive_points = []
    risk_points = []

    # --------------------------------------------------------
    # GMAIL
    # --------------------------------------------------------

    if gmail_verified:

        score += 25

        positive_points.append(
            "Gmail ownership verified."
        )

    else:

        risk_points.append(
            "Gmail ownership not verified."
        )

    # --------------------------------------------------------
    # PURCHASE
    # --------------------------------------------------------

    if purchase_verified:

        score += 30

        positive_points.append(
            "Purchase record verified."
        )

    else:

        risk_points.append(
            "Purchase record not verified."
        )

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    quality = review_quality(feedback)

    if quality == "High":

        score += 10

        positive_points.append(
            "Review contains useful details."
        )

    elif quality == "Medium":

        score += 5

    else:

        risk_points.append(
            "Feedback is very short."
        )

    # --------------------------------------------------------
    # SENTIMENT
    # --------------------------------------------------------

    sentiment, confidence = sentiment_analysis(
        feedback
    )

    # --------------------------------------------------------
    # REPEATED CHARACTERS
    # --------------------------------------------------------

    if re.search(
        r"(.)\1{4,}",
        feedback.lower()
    ):

        score -= 15

        risk_points.append(
            "Repeated characters detected."
        )

    # --------------------------------------------------------
    # REPEATED WORDS
    # --------------------------------------------------------

    if len(words) > 5:

        unique_ratio = (
            len(
                set(
                    word.lower()
                    for word in words
                )
            )
            /
            len(words)
        )

        if unique_ratio < 0.45:

            score -= 15

            risk_points.append(
                "Too many repeated words."
            )

    # --------------------------------------------------------
    # DUPLICATE
    # --------------------------------------------------------

    similarity, similar_review = calculate_similarity(
        feedback
    )

    if similarity >= 0.85:

        score -= 25

        risk_points.append(
            f"Very similar review detected ({similarity * 100:.0f}%)."
        )

    elif similarity >= 0.70:

        score -= 10

        risk_points.append(
            f"Moderately similar review detected ({similarity * 100:.0f}%)."
        )

    else:

        score += 10

        positive_points.append(
            "No strong duplicate-review pattern."
        )

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    consistent, rating_reason = check_rating_consistency(
        rating,
        sentiment
    )

    if consistent:

        score += 10

        positive_points.append(
            rating_reason
        )

    else:

        score -= 15

        risk_points.append(
            rating_reason
        )

    score = max(
        0,
        min(100, score)
    )

    if score >= 75:

        result = "Genuine"

    elif score >= 50:

        result = "Needs Review"

    else:

        result = "Suspicious"

    return {
        "score": score,
        "result": result,
        "sentiment": sentiment,
        "confidence": confidence,
        "quality": quality,
        "similarity": similarity,
        "similar_review": similar_review,
        "positive_points": positive_points,
        "risk_points": risk_points
    }


# ============================================================
# SAVE FEEDBACK
# ============================================================

def save_feedback(record):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO feedback (
            customer_name,
            gmail,
            product,
            category,
            platform,
            order_id,
            price,
            purchase_date,
            rating,
            feedback,
            gmail_verified,
            purchase_verified,
            sentiment,
            review_quality,
            similarity,
            authenticity_score,
            result,
            reason,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            record["customer_name"],
            record["gmail"],
            record["product"],
            record["category"],
            record["platform"],
            record["order_id"],
            record["price"],
            record["purchase_date"],
            record["rating"],
            record["feedback"],
            int(record["gmail_verified"]),
            int(record["purchase_verified"]),
            record["sentiment"],
            record["review_quality"],
            record["similarity"],
            record["authenticity_score"],
            record["result"],
            record["reason"],
            record["created_at"]
        )
    )

    record_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return record_id


# ============================================================
# LOGIN PAGE
# ============================================================

def show_login_page():

    st.write("")
    st.write("")

    st.title("🛍️ RetailMind_AI")

    st.caption(
        "AI-Assisted Customer Feedback Verification System"
    )

    st.divider()

    st.header("🔐 Login")

    role = st.selectbox(
        "Login As",
        [
            "Customer",
            "Admin"
        ]
    )

    username = st.text_input(
        "Username",
        placeholder="Enter username"
    )

    password = st.text_input(
        "Password",
        type="password",
        placeholder="Enter password"
    )

    login = st.button(
        "🔓 Login",
        use_container_width=True,
        type="primary"
    )

    if login:

        # ----------------------------------------------------
        # ADMIN
        # ----------------------------------------------------

        if role == "Admin":

            if (
                username.strip()
                ==
                ADMIN_USERNAME
                and
                password
                ==
                ADMIN_PASSWORD
            ):

                st.session_state.logged_in = True
                st.session_state.role = "admin"

                st.success(
                    "✅ Admin login successful."
                )

                st.rerun()

            else:

                st.error(
                    "❌ Invalid admin username or password."
                )

        # ----------------------------------------------------
        # CUSTOMER
        # ----------------------------------------------------

        else:

            if (
                username.strip()
                and
                password.strip()
            ):

                st.session_state.logged_in = True
                st.session_state.role = "customer"
                st.session_state.customer_username = (
                    username.strip()
                )

                st.success(
                    "✅ Customer login successful."
                )

                st.rerun()

            else:

                st.error(
                    "Please enter username and password."
                )

    st.divider()

    st.info(
        "Demo Admin Login  |  Username: admin  |  Password: admin123"
    )


# ============================================================
# CUSTOMER PAGE
# ============================================================

def customer_page():

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    st.markdown(
        '<div class="top-banner">'
        '<h1>🛍️ RetailMind_AI</h1>'
        '<p>AI-Assisted Customer Feedback Verification & Fake Review Detection</p>'
        '</div>',
        unsafe_allow_html=True
    )

    col1, col2 = st.columns([6, 1])

    with col1:

        st.write(
            f"👤 Logged in as: **{st.session_state.customer_username}**"
        )

    with col2:

        if st.button(
            "🚪 Logout",
            use_container_width=True
        ):

            st.session_state.logged_in = False
            st.session_state.role = None
            st.session_state.customer_username = ""
            st.session_state.gmail_verified = False

            st.rerun()

    # --------------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------------

    page = st.radio(
        "Customer Module",
        [
            "📝 Verify Feedback",
            "👤 Customer Trust"
        ],
        horizontal=True
    )

    st.divider()

    # ========================================================
    # VERIFY FEEDBACK
    # ========================================================

    if page == "📝 Verify Feedback":

        st.info(
            "💡 RetailMind_AI verifies Gmail ownership, "
            "purchase information, review quality, "
            "duplicate patterns and rating consistency."
        )

        # ----------------------------------------------------
        # PRODUCT
        # ----------------------------------------------------

        st.subheader("🛍️ Product Information")

        col1, col2, col3 = st.columns(3)

        with col1:

            product_name = st.text_input(
                "Product Name",
                placeholder="Example: iPhone 16"
            )

        with col2:

            category = st.selectbox(
                "Product Category",
                [
                    "Electronics",
                    "Clothing",
                    "Footwear",
                    "Home Appliances",
                    "Beauty",
                    "Grocery",
                    "Books",
                    "Other"
                ]
            )

        with col3:

            platform = st.selectbox(
                "Purchase Platform",
                [
                    "Amazon",
                    "Flipkart",
                    "Myntra",
                    "Meesho",
                    "Ajio",
                    "Nykaa",
                    "Other"
                ]
            )

        # ----------------------------------------------------
        # ORDER
        # ----------------------------------------------------

        st.subheader("📦 Purchase Information")

        col1, col2 = st.columns(2)

        with col1:

            order_id = st.text_input(
                "Order ID",
                placeholder="Example: ORD1001"
            )

        with col2:

            price = st.number_input(
                "Product Price (₹)",
                min_value=0.0,
                step=100.0
            )

        # ----------------------------------------------------
        # CUSTOMER
        # ----------------------------------------------------

        st.subheader("👤 Customer Information")

        col1, col2 = st.columns(2)

        with col1:

            customer_name = st.text_input(
                "Customer Name",
                placeholder="Example: Rahul"
            )

        with col2:

            gmail = st.text_input(
                "Customer Gmail",
                placeholder="example@gmail.com"
            )

        # ----------------------------------------------------
        # OTP
        # ----------------------------------------------------

        st.subheader("📧 Gmail Ownership Verification")

        if st.session_state.gmail_verified:

            st.success(
                "🟢 Gmail ownership verified."
            )

        else:

            st.warning(
                "Gmail must be verified before checking feedback."
            )

        col1, col2 = st.columns([3, 1])

        with col1:

            if st.button(
                "📨 Send OTP",
                use_container_width=True
            ):

                if not gmail:

                    st.error(
                        "Enter Gmail first."
                    )

                else:

                    valid, message = validate_gmail(
                        gmail
                    )

                    if valid:

                        request_otp(gmail)

                    else:

                        st.error(message)

        with col2:

            if st.button(
                "🔄 Reset",
                use_container_width=True
            ):

                st.session_state.otp = None
                st.session_state.otp_email = None
                st.session_state.otp_created = None
                st.session_state.gmail_verified = False

                st.rerun()

        entered_otp = st.text_input(
            "Enter 6-Digit OTP",
            max_chars=6,
            placeholder="Enter OTP"
        )

        if st.button(
            "✅ Verify OTP",
            use_container_width=True
        ):

            if not gmail:

                st.error(
                    "Enter Gmail first."
                )

            else:

                verified, message = verify_otp(
                    gmail,
                    entered_otp
                )

                if verified:

                    st.success(message)

                else:

                    st.error(message)

        # ----------------------------------------------------
        # RATING
        # ----------------------------------------------------

        st.subheader("⭐ Product Rating")

        rating = st.select_slider(
            "How would you rate this product?",
            options=[1, 2, 3, 4, 5],
            value=5
        )

        st.write(
            f"Your rating: {'⭐' * rating}"
        )

        # ----------------------------------------------------
        # FEEDBACK
        # ----------------------------------------------------

        st.subheader("💬 Customer Feedback")

        feedback = st.text_area(
            "Write your product experience",
            placeholder=(
                "Example: The product quality is excellent. "
                "The delivery was fast and packaging was good."
            ),
            height=160
        )

        # ----------------------------------------------------
        # VERIFY
        # ----------------------------------------------------

        if st.button(
            "🔍 Verify Customer Feedback",
            use_container_width=True,
            type="primary"
        ):

            if not product_name:

                st.error(
                    "Please enter product name."
                )

                return

            if not customer_name:

                st.error(
                    "Please enter customer name."
                )

                return

            if not gmail:

                st.error(
                    "Please enter Gmail."
                )

                return

            if not order_id:

                st.error(
                    "Please enter Order ID."
                )

                return

            if not feedback.strip():

                st.error(
                    "Please enter feedback."
                )

                return

            if not st.session_state.gmail_verified:

                st.error(
                    "Please verify Gmail ownership first."
                )

                return

            # ------------------------------------------------
            # PURCHASE
            # ------------------------------------------------

            (
                purchase_verified,
                purchase_message,
                order
            ) = verify_purchase(
                order_id,
                gmail,
                product_name,
                platform
            )

            if purchase_verified:

                st.success(
                    "🛒 " + purchase_message
                )

            else:

                st.warning(
                    "🛒 " + purchase_message
                )

            # ------------------------------------------------
            # ANALYSIS
            # ------------------------------------------------

            analysis = analyze_feedback(
                feedback,
                rating,
                st.session_state.gmail_verified,
                purchase_verified
            )

            st.session_state.last_analysis = analysis

            # ------------------------------------------------
            # ORDER DATA
            # ------------------------------------------------

            if order:

                purchase_date = order[5]
                actual_price = order[4]

            else:

                purchase_date = ""
                actual_price = price

            # ------------------------------------------------
            # SAVE
            # ------------------------------------------------

            record = {
                "customer_name": customer_name,
                "gmail": gmail.lower(),
                "product": product_name,
                "category": category,
                "platform": platform,
                "order_id": order_id,
                "price": actual_price,
                "purchase_date": purchase_date,
                "rating": rating,
                "feedback": feedback,
                "gmail_verified":
                    st.session_state.gmail_verified,
                "purchase_verified":
                    purchase_verified,
                "sentiment":
                    analysis["sentiment"],
                "review_quality":
                    analysis["quality"],
                "similarity":
                    analysis["similarity"],
                "authenticity_score":
                    analysis["score"],
                "result":
                    analysis["result"],
                "reason":
                    " | ".join(
                        analysis["risk_points"]
                    ),
                "created_at":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            }

            save_feedback(record)

            st.divider()

            # ------------------------------------------------
            # RESULT
            # ------------------------------------------------

            if analysis["result"] == "Genuine":

                st.success(
                    "🟢 GENUINE FEEDBACK"
                )

                st.write(
                    "The feedback achieved a high authenticity score."
                )

            elif analysis["result"] == "Needs Review":

                st.warning(
                    "🟡 NEEDS MANUAL REVIEW"
                )

                st.write(
                    "The feedback contains mixed verification signals."
                )

            else:

                st.error(
                    "🔴 SUSPICIOUS FEEDBACK"
                )

                st.write(
                    "Multiple suspicious patterns were detected."
                )

            # ------------------------------------------------
            # SCORE
            # ------------------------------------------------

            st.subheader(
                "🤖 Customer Feedback Authenticity Score"
            )

            st.markdown(
                f'<div class="score-number">'
                f'{analysis["score"]}/100'
                f'</div>',
                unsafe_allow_html=True
            )

            st.write(
                f"### Result: {analysis['result']}"
            )

            # ------------------------------------------------
            # METRICS
            # ------------------------------------------------

            col1, col2, col3, col4 = st.columns(4)

            with col1:

                st.metric(
                    "📧 Gmail",
                    "Verified"
                )

            with col2:

                st.metric(
                    "🛒 Purchase",
                    "Verified"
                    if purchase_verified
                    else
                    "Not Verified"
                )

            with col3:

                st.metric(
                    "😊 Sentiment",
                    analysis["sentiment"]
                )

            with col4:

                st.metric(
                    "📝 Quality",
                    analysis["quality"]
                )

            # ------------------------------------------------
            # EXPLANATION
            # ------------------------------------------------

            st.subheader(
                "🔎 Verification Explanation"
            )

            col1, col2 = st.columns(2)

            with col1:

                st.write(
                    "### ✅ Positive Signals"
                )

                if analysis["positive_points"]:

                    for point in analysis["positive_points"]:

                        st.success(point)

                else:

                    st.info(
                        "No strong positive signals."
                    )

            with col2:

                st.write(
                    "### ⚠️ Risk Signals"
                )

                if analysis["risk_points"]:

                    for point in analysis["risk_points"]:

                        st.warning(point)

                else:

                    st.success(
                        "No major suspicious signals."
                    )

            # ------------------------------------------------
            # SIMILAR REVIEW
            # ------------------------------------------------

            if analysis["similar_review"]:

                st.subheader(
                    "🔁 Similar Review Detection"
                )

                st.write(
                    f"Similarity: "
                    f"{analysis['similarity'] * 100:.1f}%"
                )

                st.info(
                    analysis["similar_review"]
                )

            # ------------------------------------------------
            # RECOMMENDATION
            # ------------------------------------------------

            st.subheader(
                "🤖 AI Recommendation"
            )

            if analysis["result"] == "Genuine":

                st.success(
                    "The review can be considered for publication."
                )

            elif analysis["result"] == "Needs Review":

                st.warning(
                    "Perform manual verification before publishing."
                )

            else:

                st.error(
                    "Do not automatically publish this review. "
                    "Manual verification is recommended."
                )

    # ========================================================
    # CUSTOMER TRUST
    # ========================================================

    else:

        st.subheader(
            "👤 Customer Trust Profile"
        )

        st.write(
            "Search a Gmail address to view customer "
            "verification history."
        )

        search_gmail = st.text_input(
            "Customer Gmail",
            placeholder="example@gmail.com"
        )

        if st.button(
            "🔎 Search Customer",
            use_container_width=True
        ):

            if not search_gmail:

                st.error(
                    "Enter Gmail address."
                )

            else:

                conn = get_connection()

                customer_df = pd.read_sql_query(
                    """
                    SELECT *
                    FROM feedback
                    WHERE LOWER(gmail) = LOWER(?)
                    ORDER BY id DESC
                    """,
                    conn,
                    params=(search_gmail,)
                )

                conn.close()

                if customer_df.empty:

                    st.info(
                        "No customer history found."
                    )

                else:

                    total_reviews = len(customer_df)

                    genuine = int(
                        (
                            customer_df["result"]
                            ==
                            "Genuine"
                        ).sum()
                    )

                    suspicious = int(
                        (
                            customer_df["result"]
                            ==
                            "Suspicious"
                        ).sum()
                    )

                    trust_score = round(
                        customer_df[
                            "authenticity_score"
                        ].mean(),
                        1
                    )

                    st.subheader(
                        "📊 Customer Overview"
                    )

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:

                        st.metric(
                            "Reviews",
                            total_reviews
                        )

                    with col2:

                        st.metric(
                            "Genuine",
                            genuine
                        )

                    with col3:

                        st.metric(
                            "Suspicious",
                            suspicious
                        )

                    with col4:

                        st.metric(
                            "Trust Score",
                            f"{trust_score}%"
                        )

                    if trust_score >= 75:

                        st.success(
                            "🟢 Trusted Customer"
                        )

                    elif trust_score >= 50:

                        st.warning(
                            "🟡 Customer Needs Monitoring"
                        )

                    else:

                        st.error(
                            "🔴 High Risk Customer"
                        )

                    st.subheader(
                        "📋 Customer Review History"
                    )

                    display_columns = [
                        "product",
                        "platform",
                        "order_id",
                        "rating",
                        "sentiment",
                        "authenticity_score",
                        "result",
                        "created_at"
                    ]

                    st.dataframe(
                        customer_df[display_columns],
                        use_container_width=True,
                        hide_index=True
                    )


# ============================================================
# ADMIN PAGE
# ============================================================

def admin_page():

    st.markdown(
        '<div class="top-banner">'
        '<h1>👨‍💼 RetailMind_AI Admin Panel</h1>'
        '<p>Monitor customers, reviews, verification and authenticity</p>'
        '</div>',
        unsafe_allow_html=True
    )

    col1, col2 = st.columns([6, 1])

    with col1:

        st.write(
            "🔐 Logged in as: **Administrator**"
        )

    with col2:

        if st.button(
            "🚪 Logout",
            use_container_width=True
        ):

            st.session_state.logged_in = False
            st.session_state.role = None

            st.rerun()

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM feedback
        ORDER BY id DESC
        """,
        conn
    )

    conn.close()

    if df.empty:

        st.info(
            "📭 No feedback has been submitted yet."
        )

        return

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    total = len(df)

    genuine = int(
        (
            df["result"]
            ==
            "Genuine"
        ).sum()
    )

    suspicious = int(
        (
            df["result"]
            ==
            "Suspicious"
        ).sum()
    )

    needs_review = int(
        (
            df["result"]
            ==
            "Needs Review"
        ).sum()
    )

    average_score = round(
        df["authenticity_score"].mean(),
        1
    )

    st.subheader(
        "📊 System Overview"
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:

        st.metric(
            "📝 Total Reviews",
            total
        )

    with col2:

        st.metric(
            "🟢 Genuine",
            genuine
        )

    with col3:

        st.metric(
            "🔴 Suspicious",
            suspicious
        )

    with col4:

        st.metric(
            "🟡 Needs Review",
            needs_review
        )

    with col5:

        st.metric(
            "🤖 Avg Score",
            f"{average_score}%"
        )

    st.divider()

    # --------------------------------------------------------
    # VERIFICATION
    # --------------------------------------------------------

    st.subheader(
        "🔐 Verification Statistics"
    )

    gmail_verified = int(
        df["gmail_verified"].sum()
    )

    purchase_verified = int(
        df["purchase_verified"].sum()
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "📧 Gmail Verified",
            gmail_verified,
            f"{gmail_verified / total * 100:.1f}%"
        )

    with col2:

        st.metric(
            "🛒 Purchase Verified",
            purchase_verified,
            f"{purchase_verified / total * 100:.1f}%"
        )

    with col3:

        st.metric(
            "⭐ Average Rating",
            f"{df['rating'].mean():.2f}/5"
        )

    st.divider()

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    st.subheader(
        "🔎 Feedback Filters"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        product_filter = st.selectbox(
            "Product",
            ["All"]
            +
            sorted(
                df["product"]
                .dropna()
                .unique()
                .tolist()
            )
        )

    with col2:

        platform_filter = st.selectbox(
            "Platform",
            ["All"]
            +
            sorted(
                df["platform"]
                .dropna()
                .unique()
                .tolist()
            )
        )

    with col3:

        result_filter = st.selectbox(
            "Result",
            [
                "All",
                "Genuine",
                "Needs Review",
                "Suspicious"
            ]
        )

    filtered_df = df.copy()

    if product_filter != "All":

        filtered_df = filtered_df[
            filtered_df["product"]
            ==
            product_filter
        ]

    if platform_filter != "All":

        filtered_df = filtered_df[
            filtered_df["platform"]
            ==
            platform_filter
        ]

    if result_filter != "All":

        filtered_df = filtered_df[
            filtered_df["result"]
            ==
            result_filter
        ]

    # --------------------------------------------------------
    # RECORDS
    # --------------------------------------------------------

    st.subheader(
        "📋 Customer Feedback Records"
    )

    display_columns = [
        "customer_name",
        "gmail",
        "product",
        "platform",
        "order_id",
        "rating",
        "sentiment",
        "gmail_verified",
        "purchase_verified",
        "authenticity_score",
        "result",
        "created_at"
    ]

    st.dataframe(
        filtered_df[display_columns],
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    csv_file = (
        filtered_df
        .to_csv(index=False)
        .encode("utf-8")
    )

    st.download_button(
        "📥 Download Verification Report",
        data=csv_file,
        file_name="retailmind_verification_report.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.divider()

    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------

    st.subheader(
        "📈 Feedback Analytics"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "⭐ Rating Distribution"
        )

        rating_counts = (
            df["rating"]
            .value_counts()
            .sort_index()
        )

        st.bar_chart(
            rating_counts
        )

    with col2:

        st.write(
            "🛒 Feedback by Platform"
        )

        platform_counts = (
            df["platform"]
            .value_counts()
        )

        st.bar_chart(
            platform_counts
        )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "🤖 Verification Result"
        )

        result_counts = (
            df["result"]
            .value_counts()
        )

        st.bar_chart(
            result_counts
        )

    with col2:

        st.write(
            "😊 Sentiment Distribution"
        )

        sentiment_counts = (
            df["sentiment"]
            .value_counts()
        )

        st.bar_chart(
            sentiment_counts
        )

    st.divider()

    # --------------------------------------------------------
    # PRODUCT SUMMARY
    # --------------------------------------------------------

    st.subheader(
        "🛍️ Product Authenticity Summary"
    )

    product_summary = (
        df
        .groupby("product")
        .agg(
            Reviews=("id", "count"),
            Average_Rating=("rating", "mean"),
            Average_Authenticity=(
                "authenticity_score",
                "mean"
            ),
            Genuine=(
                "result",
                lambda x:
                (x == "Genuine").sum()
            ),
            Needs_Review=(
                "result",
                lambda x:
                (x == "Needs Review").sum()
            ),
            Suspicious=(
                "result",
                lambda x:
                (x == "Suspicious").sum()
            )
        )
        .reset_index()
    )

    product_summary["Average_Rating"] = (
        product_summary["Average_Rating"]
        .round(2)
    )

    product_summary["Average_Authenticity"] = (
        product_summary["Average_Authenticity"]
        .round(1)
    )

    st.dataframe(
        product_summary,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# MAIN ROUTING
# ============================================================

if not st.session_state.logged_in:

    show_login_page()

else:

    if st.session_state.role == "admin":

        admin_page()

    elif st.session_state.role == "customer":

        customer_page()

    else:

        st.session_state.logged_in = False
        st.session_state.role = None

        st.rerun()


# ============================================================
# FOOTER
# ============================================================

if st.session_state.logged_in:

    st.divider()

    st.caption(
        "🛍️ RetailMind_AI | "
        "Gmail Ownership • Purchase Verification • "
        "Authenticity Scoring • Duplicate Detection • Analytics"
    )