"""Streamlit web UI for Mastercard Spec Advisor — a RAG assistant over the
Mastercard Authorization System Guide, with login and role-based content
restriction.

Two demo roles:
  - General User       (username: analyst,    password: analyst123)
  - Compliance Officer  (username: compliance, password: compliance123)

General Users only retrieve "general" content. Compliance Officers also
see "restricted" (security-sensitive) content such as PIN handling, key
management, and data-compromise procedures.

Usage: streamlit run app.py
"""
import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

import auth
import rag

load_dotenv(override=True)

APP_NAME = "Mastercard Spec Advisor"

st.set_page_config(page_title=APP_NAME, page_icon="💳", layout="centered")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"]  {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Hide default Streamlit chrome for a cleaner look */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}

/* Brand header */
.msa-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px 22px;
    border-radius: 14px;
    background: linear-gradient(120deg, #EB001B 0%, #D1193E 45%, #F79E1B 100%);
    color: white;
    margin-bottom: 22px;
    box-shadow: 0 4px 18px rgba(209, 25, 62, 0.25);
}
.msa-header .msa-logo {
    display: flex;
    align-items: center;
}
.msa-header .msa-logo .circle {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: inline-block;
}
.msa-header .msa-logo .circle.red { background: #EB001B; margin-right: -10px; z-index: 1; border: 2px solid white; }
.msa-header .msa-logo .circle.yellow { background: #F79E1B; opacity: 0.95; border: 2px solid white; }
.msa-header .msa-title {
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.1;
}
.msa-header .msa-subtitle {
    font-size: 0.85rem;
    opacity: 0.92;
    font-weight: 400;
    margin-top: 2px;
}

/* Login card */
.msa-login-card {
    background: white;
    border: 1px solid #ECECF2;
    border-radius: 16px;
    padding: 8px 4px 2px 4px;
}

/* Role badge pills */
.msa-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 4px;
}
.msa-badge.general {
    background: #FFF4E5;
    color: #B8650F;
    border: 1px solid #F7D9AE;
}
.msa-badge.compliance {
    background: #E8F5E9;
    color: #1E7D32;
    border: 1px solid #BFE6C2;
}

/* Restriction notice */
.msa-restricted-note {
    background: #FFF8EC;
    border: 1px solid #F3DCA8;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 0.88rem;
    color: #7A5200;
    margin-top: 8px;
}

/* Footer disclaimer */
.msa-disclaimer {
    text-align: center;
    font-size: 0.75rem;
    color: #9A9AA6;
    margin-top: 28px;
    padding-top: 14px;
    border-top: 1px solid #ECECF2;
}

div[data-testid="stChatMessage"] {
    border-radius: 14px;
}

.stButton button {
    border-radius: 8px;
    font-weight: 600;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

HEADER_HTML = f"""
<div class="msa-header">
    <div class="msa-logo">
        <span class="circle red"></span><span class="circle yellow"></span>
    </div>
    <div>
        <div class="msa-title">{APP_NAME}</div>
        <div class="msa-subtitle">RAG assistant for the Mastercard Authorization System Guide</div>
    </div>
</div>
"""

DISCLAIMER_HTML = (
    '<div class="msa-disclaimer">'
    "Independent demo project. Not affiliated with, endorsed by, or sponsored by Mastercard. "
    '"Mastercard" references are to the public specification document used as the knowledge base.'
    "</div>"
)


@st.cache_resource(show_spinner="Loading embedding model and vector store...")
def init_backend():
    collection = rag.get_collection()
    return collection.count()


def login_screen():
    st.markdown(HEADER_HTML, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 3, 1])
    with center:
        st.markdown('<div class="msa-login-card">', unsafe_allow_html=True)
        st.subheader("Sign in")
        st.caption("Role-based access demo — your role determines what content you can retrieve.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="e.g. analyst")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if submitted:
            role = auth.verify_login(username, password)
            if role:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = role
                st.session_state.messages = []
                st.rerun()
            else:
                st.error("Invalid username or password.")

        with st.expander("Demo credentials"):
            st.markdown(
                "| Role | Username | Password |\n"
                "|---|---|---|\n"
                "| General User | `analyst` | `analyst123` |\n"
                "| Compliance Officer | `compliance` | `compliance123` |"
            )

    st.markdown(DISCLAIMER_HTML, unsafe_allow_html=True)


def chat_screen():
    role = st.session_state.role
    allow_restricted = role == auth.ROLE_COMPLIANCE

    with st.sidebar:
        st.markdown(f"**Signed in as** `{st.session_state.username}`")
        badge_class = "compliance" if allow_restricted else "general"
        st.markdown(
            f'<span class="msa-badge {badge_class}">{auth.ROLE_LABELS[role]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")
        if allow_restricted:
            st.success("Full access: general + restricted (security-sensitive) content")
        else:
            st.warning("Restricted access: general content only")
        st.divider()
        if st.button("Log out", use_container_width=True):
            for key in ("logged_in", "username", "role", "messages"):
                st.session_state.pop(key, None)
            st.rerun()

    st.markdown(HEADER_HTML, unsafe_allow_html=True)

    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ["ANTHROPIC_API_KEY"] == "sk-ant-your-key-here":
        st.error("ANTHROPIC_API_KEY is not set. Edit the .env file and add your key, then restart the app.")
        st.stop()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a question about the Authorization System Guide...")
    if not question:
        st.markdown(DISCLAIMER_HTML, unsafe_allow_html=True)
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving context and generating answer..."):
            results, hidden_count = rag.retrieve(question, allow_restricted=allow_restricted)

            if not results["documents"][0]:
                answer = (
                    "No matching content found at your access level. "
                    "This question may only be answerable by a Compliance Officer."
                    if hidden_count > 0 and not allow_restricted
                    else "No relevant content found in the knowledge base for this question."
                )
                st.markdown(answer)
            else:
                context = rag.format_context(results)
                try:
                    answer = rag.generate_answer(question, context)
                except anthropic.AuthenticationError:
                    answer = "Error: Invalid ANTHROPIC_API_KEY. Check your credentials."
                except anthropic.RateLimitError:
                    answer = "Error: Rate limit hit. Wait a moment and try again."
                except anthropic.APIStatusError as e:
                    answer = f"Error: API returned an error ({e.status_code}): {e.message}"
                except anthropic.APIConnectionError:
                    answer = "Error: Could not connect to the Anthropic API. Check your network."

                st.markdown(answer)

                if not allow_restricted and hidden_count > 0:
                    st.markdown(
                        f'<div class="msa-restricted-note">🔒 {hidden_count} additional relevant '
                        "section(s) exist in restricted (security-sensitive) content, hidden at your "
                        "access level. A Compliance Officer would also see those results.</div>",
                        unsafe_allow_html=True,
                    )

    st.session_state.messages.append({"role": "assistant", "content": answer})


def main():
    chunk_count = init_backend()

    if not st.session_state.get("logged_in"):
        login_screen()
        return

    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_screen()
    st.sidebar.caption(f"Knowledge base: {chunk_count} chunks")


if __name__ == "__main__":
    main()
