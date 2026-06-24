"""
File: app.py
Description: Streamlit interactive web dashboard for the QA Pilot system. Exposes controls to trigger user story ticket generation and run the multi-agent orchestration workflow.
Role in Architecture: Serves as the user interface layer interacting with QAOrchestrator and rendering output reports.
"""

import streamlit as st
import asyncio
import os
import re
from agent.orchestrator import QAOrchestrator
from agent.skills.create_jira_ticket import create_jira_ticket
from agent.guardrails import validate_ticket_id, validate_feature_input

# Set page configuration for professional layout
st.set_page_config(
    page_title="QA Pilot — Jira Test Generator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "created_ticket" not in st.session_state:
    st.session_state.created_ticket = None

if "story_input_value" not in st.session_state:
    st.session_state.story_input_value = ""

# Custom CSS styling to align the main layout style with the sidebar
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;800&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif !important;
    }
    .main-title {
        font-size: 22px;
        font-weight: 500;
        color: #000000;
        margin-top: 10px;
        margin-bottom: 2px;
    }
    .main-subtitle {
        font-size: 9px;
        color: #94A3B8;
        margin-top: 0px;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    /* Reduce spacing around the main divider */
    .stApp hr {
        margin-top: 8px !important;
        margin-bottom: 24px !important;
    }
    .section-header {
        font-size: 15px;
        font-weight: 500;
        color: #000000;
        border-bottom: 1px solid #E2E8F0;
        padding-bottom: 0.4rem;
        margin-top: 1.5rem;
        margin-bottom: 0.8rem;
    }
    .main-label {
        font-size: 10px;
        color: #94A3B8;
        margin-bottom: 5px;
    }
    /* Style main action button similar to sidebar but main context color */
    div.stButton > button:not([key*="clear_feature_input_btn"]) {
        background-color: #BFDBFE !important;
        color: #1D4ED8 !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1rem !important;
        transition: background-color 0.2s ease;
    }
    div.stButton > button:not([key*="clear_feature_input_btn"]):hover {
        background-color: #93C5FD !important;
        color: #1D4ED8 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">QA Pilot</p>', unsafe_allow_html=True)
st.markdown('<p class="main-subtitle">AI-powered test generation</p>', unsafe_allow_html=True)
st.divider()

# SIDEBAR — story creator panel
st.sidebar.markdown("""
<style>
    /* Target the sidebar container specifically */
    section[data-testid="stSidebar"] {
        padding-top: 1rem;
    }
    .sb-header {
        font-size: 22px;
        font-weight: 500;
        color: #000000;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    .sb-subtitle {
        font-size: 7px;
        color: #94A3B8;
        margin-top: 0px;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    /* Reduce spacing around the sidebar divider and add 24px margin bottom */
    section[data-testid="stSidebar"] hr {
        margin-top: 8px !important;
        margin-bottom: 24px !important;
    }
    .sb-section-title {
        font-size: 22px;
        font-weight: 500;
        color: #000000;
        margin-top: 10px;
        margin-bottom: 0px;
    }
    .sb-helper {
        font-size: 7px;
        color: #94A3B8;
        margin-top: 0px;
        margin-bottom: 15px;
    }
    .sb-label {
        font-size: 7px;
        color: #94A3B8;
        margin-bottom: 5px;
    }
    /* Style Streamlit Button inside Sidebar */
    section[data-testid="stSidebar"] div.stButton > button {
        background-color: #BFDBFE !important;
        color: #1D4ED8 !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 13px !important;
        height: auto !important;
        padding: 0.5rem 1rem !important;
        transition: background-color 0.2s ease;
    }
    section[data-testid="stSidebar"] div.stButton > button:hover {
        background-color: #93C5FD !important;
        color: #1D4ED8 !important;
    }
    /* Hide Streamlit text input helper instructions ('Press Enter to apply') */
    section[data-testid="stSidebar"] div[data-testid="InputInstructions"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown('<p class="sb-header">QA Pilot</p>', unsafe_allow_html=True)
st.sidebar.markdown('<p class="sb-subtitle">AI-powered test generation</p>', unsafe_allow_html=True)
st.sidebar.divider()

st.sidebar.markdown('<p class="sb-section-title">Create sample story</p>', unsafe_allow_html=True)
st.sidebar.markdown('<p class="sb-helper">Generate a formatted Jira user story with ACs</p>', unsafe_allow_html=True)

# Initialize text input value if not present in state
if "story_input_value" not in st.session_state:
    st.session_state.story_input_value = ""

# Track if we need to reset the text input after a rerun
if st.session_state.get("clear_story_input", False):
    st.session_state.story_input_value = ""
    st.session_state["clear_story_input"] = False

st.sidebar.markdown('<p class="sb-label">Feature name</p>', unsafe_allow_html=True)
feature_name = st.sidebar.text_input(
    "Feature Name", 
    value=st.session_state.story_input_value,
    placeholder="e.g. User login with email", 
    label_visibility="collapsed"
)
create_btn = st.sidebar.button("Create story ticket", use_container_width=True)

if create_btn and feature_name:
    if not feature_name.strip() or len(feature_name.strip()) < 5:
        st.sidebar.error("Validation Error: Feature name must be at least 5 characters long.")
    else:
        # Security Guardrail Check 2: Validate feature input name size, prompt injections & vagueness before triggering skill
        is_valid_feat, err_feat = validate_feature_input(feature_name)
        if not is_valid_feat:
            st.sidebar.error(f"Validation Error: {err_feat}")
        else:
            with st.sidebar.spinner("Creating story in Jira..."):
                try:
                    orchestrator = QAOrchestrator()
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result_text = loop.run_until_complete(orchestrator.create_story_with_skill(feature_name))
                    
                    if not result_text.startswith("Success:") and not re.search(r"[A-Z]+-\d+", result_text):
                        st.sidebar.error(f"Could not create story. Response details: {result_text}")
                    else:
                        match = re.search(r"[A-Z]+-\d+", result_text)
                        created_id = match.group(0) if match else "SCRUM-UNKNOWN"
                        
                        if created_id == "SCRUM-UNKNOWN":
                            st.sidebar.error(f"Could not parse created issue key. Response details: {result_text}")
                        else:
                            # Clean title from response text
                            title_clean = result_text.split("with title:")[-1].strip() if "with title:" in result_text else feature_name
                            if title_clean.startswith("'") and title_clean.endswith("'"):
                                title_clean = title_clean[1:-1]
                            
                            site_url = os.getenv("ATLASSIAN_SITE_URL", "https://irinasha.atlassian.net").rstrip("/")
                            
                            # Flag the text input to be cleared on next render
                            st.session_state.story_input_value = ""
                            st.session_state.clear_story_input = True
                            
                            st.session_state.created_ticket = {
                                "id": created_id,
                                "title": title_clean,
                                "url": f"{site_url}/browse/{created_id}"
                            }
                            st.session_state["ticket_id_input"] = created_id
                            st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Could not create story. Error details: {str(e)}")

# Success card — shown after ticket creation
if st.session_state.created_ticket:
    st.sidebar.markdown("""
    <div style="
        background-color: #F0FDF4;
        border: 0.5px solid #86EFAC;
        border-radius: 8px;
        padding: 12px;
        margin-top: 12px;
    ">
        <p style="font-size:13px;font-weight:500;
           color:#16A34A;margin:0 0 6px">
           Story created
        </p>
        <a href="{url}" target="_blank" 
           style="font-size:12px;color:#16A34A;font-weight:500">
           {id} →
        </a>
    </div>
    """.format(
        url=st.session_state.created_ticket["url"],
        id=st.session_state.created_ticket["id"]
    ), unsafe_allow_html=True)

# Main interaction flow
st.markdown('<div style="margin-top: 84px;"></div>', unsafe_allow_html=True)
st.markdown('<p class="sb-label">Jira Ticket ID</p>', unsafe_allow_html=True)
ticket_id_default = st.session_state.get("ticket_id_input", "")
ticket_id = st.text_input("Jira Ticket ID", value=ticket_id_default, placeholder="e.g. SCRUM-11", label_visibility="collapsed")
gen_btn = st.button("Generate Test Cases", use_container_width=True)

if gen_btn and ticket_id:
    # Security Guardrail Check 1: Validate Ticket ID pattern, project key & emptiness before launching orchestrator
    is_valid_id, err_id = validate_ticket_id(ticket_id)
    if not is_valid_id:
        st.error(f"Validation Error: {err_id}")
    else:
        with st.spinner(f"Agent running: Fetching ticket {ticket_id} and generating test cases..."):
            orchestrator = QAOrchestrator()
            try:
                # Run async orchestrator using event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                results = loop.run_until_complete(orchestrator.run_orchestration(ticket_id))
                
                st.success(f"🎉 Success! Created and linked **Manual Test ({results['manual_test_key']})** and **Cucumber Test ({results['cucumber_test_key']})** as 'Tested by' to Story {ticket_id}!")
                
                # Divide into columns for display
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown('<h2 class="section-header">Fetched Ticket Details</h2>', unsafe_allow_html=True)
                    st.text_area("Jira Ticket Context", results["ticket_details"], height=300)
                    
                with col2:
                    st.markdown('<h2 class="section-header">Generated BDD Scenarios</h2>', unsafe_allow_html=True)
                    st.markdown(results["bdd_scenarios"])
                    
                st.markdown('<h2 class="section-header">Generated Edge Cases & Negative Scenarios</h2>', unsafe_allow_html=True)
                st.markdown(results["edge_cases"])
                
            except Exception as e:
                st.error(f"Error generating test plan: {e}")
