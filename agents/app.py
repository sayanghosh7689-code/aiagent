"""Streamlit dashboard + playground for AI Agent API Platform."""
import os, html, requests, streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
# URL shown in copy-paste snippets; inside Docker API_URL is an internal hostname
PUBLIC_API = os.getenv("PUBLIC_API_URL", API)
st.set_page_config(
    page_title="AI Agent API Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for polished developer UI
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #6c757d;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }
    .stMetric {
        background-color: rgba(128, 128, 128, 0.05);
        padding: 12px 16px;
        border-radius: 8px;
        border: 1px solid rgba(128, 128, 128, 0.15);
    }
    .badge-active {
        background-color: #d1e7dd;
        color: #0f5132;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-revoked {
        background-color: #f8d7da;
        color: #842029;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

def api_call(method, path, **kw):
    token = st.session_state.get("token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if "headers" in kw:
        headers.update(kw.pop("headers"))
    try:
        r = requests.request(method, f"{API}{path}", headers=headers, timeout=60, **kw)
        if r.status_code >= 400:
            err_msg = r.text
            try:
                err_data = r.json()
                err_msg = err_data.get("detail", r.text)
            except Exception:
                pass
            if r.status_code == 401 and token and not path.startswith("/auth/"):
                st.session_state.clear()
                st.session_state["_notice"] = "Your session expired. Please log in again."
                st.rerun()
            st.error(f"API Error ({r.status_code}): {err_msg}")
            return None
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Could not connect to FastAPI backend at {API}. Ensure `uvicorn main:app` is running.")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None

# ---------- Authentication Screen ----------
if "token" not in st.session_state:
    if st.session_state.get("_notice"):
        st.warning(st.session_state.pop("_notice"))
    st.markdown('<div class="main-header">🤖 AI Agent API Platform</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Build customized AI agents, ground them in your documentation via RAG, and access them via protected REST APIs.</div>', unsafe_allow_html=True)
    
    col_auth, _ = st.columns([1, 1])
    with col_auth:
        mode = st.radio("Choose action", ["Log in", "Sign up"], horizontal=True, label_visibility="collapsed")
        with st.form("auth_form"):
            st.subheader(mode)
            email = st.text_input("Work Email", placeholder="developer@company.com")
            password = st.text_input("Password (min 8 characters)", type="password")
            submitted = st.form_submit_button(mode, use_container_width=True, type="primary")
            
            if submitted:
                if not email or not password:
                    st.warning("Please provide both email and password.")
                elif len(password) < 8:
                    st.warning("Password must be at least 8 characters long.")
                else:
                    endpoint = "/auth/login" if mode == "Log in" else "/auth/signup"
                    res = api_call("POST", endpoint, json={"email": email, "password": password})
                    if res and "token" in res:
                        st.session_state.token = res["token"]
                        st.session_state.email = email
                        st.session_state.user_id = res.get("user_id")
                        st.success(f"Welcome{' back' if mode == 'Log in' else ''}!")
                        st.rerun()
    st.stop()

# ---------- Authenticated Sidebar Navigation ----------
with st.sidebar:
    st.markdown("### 🤖 Agent Platform")
    st.caption(f"Logged in as: **{st.session_state.get('email', 'User')}**")
    
    usage_info = api_call("GET", "/usage")
    if usage_info:
        plan_name = usage_info.get("plan", "free").upper()
        used = usage_info.get("used_this_month", 0)
        quota = usage_info.get("quota", 100)
        st.metric("Plan", plan_name, f"{used} / {quota} reqs this month")
        pct = min(1.0, used / quota) if quota > 0 else 0.0
        st.progress(pct)
        st.divider()

    # Projects Selection
    st.subheader("📁 Projects")
    projects = api_call("GET", "/projects") or []
    project_dict = {p["name"]: p for p in projects}
    proj_choices = list(project_dict.keys()) + ["➕ New Project"]
    selected_proj_name = st.selectbox("Current Project", proj_choices)

    if selected_proj_name == "➕ New Project":
        st.write("---")
        with st.form("create_proj_form"):
            st.write("**Create New Project**")
            new_p_name = st.text_input("Project Name")
            new_p_desc = st.text_area("Description (optional)")
            if st.form_submit_button("Create Project", type="primary") and new_p_name:
                p_res = api_call("POST", "/projects", json={"name": new_p_name, "description": new_p_desc})
                if p_res:
                    st.success("Project created!")
                    st.rerun()
        st.stop()
    
    current_project = project_dict.get(selected_proj_name)
    current_proj_id = current_project["id"] if current_project else None

    # Agents Selection
    st.subheader("🤖 Agents")
    all_agents = api_call("GET", f"/agents?project_id={current_proj_id}" if current_proj_id else "/agents") or []
    agent_dict = {a["name"]: a for a in all_agents}
    agent_choices = ["➕ New Agent"] + list(agent_dict.keys())
    agent_choice = st.selectbox("Select Agent", agent_choices)

    st.write("---")
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ---------- Agent Creation View ----------
if agent_choice == "➕ New Agent":
    st.markdown('<div class="main-header">Create a New AI Agent</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Project: <b>{html.escape(selected_proj_name)}</b></div>', unsafe_allow_html=True)
    
    with st.form("new_agent_form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            name = st.text_input("Agent Name", placeholder="e.g. Customer Support FAQ Agent")
            instructions = st.text_area(
                "System Instructions & Persona",
                value="You are a professional customer support assistant. Answer questions accurately using only the uploaded reference documents.",
                height=150
            )
        with col2:
            model = st.selectbox("Model Provider / LLM", [
                "Qwen/Qwen2.5-7B-Instruct",
                "meta-llama/Llama-3.1-8B-Instruct",
                "mistralai/Mistral-7B-Instruct-v0.3",
                "google/gemma-2-9b-it"
            ])
            temp_slider = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.3, step=0.1)
        
        submitted = st.form_submit_button("🚀 Create Agent", type="primary")
        if submitted:
            if not name:
                st.warning("Please provide an agent name.")
            else:
                payload = {
                    "name": name,
                    "instructions": instructions,
                    "model": model,
                    "temperature": int(temp_slider * 10),
                    "project_id": current_proj_id
                }
                res = api_call("POST", "/agents", json=payload)
                if res:
                    st.success(f"Agent '{name}' created successfully!")
                    st.rerun()
    st.stop()

# ---------- Selected Agent Dashboard View ----------
curr_agent = agent_dict[agent_choice]
agent_id = curr_agent["id"]

st.markdown(f'<div class="main-header">🤖 {html.escape(curr_agent["name"])}</div>', unsafe_allow_html=True)
st.caption(f"Agent ID: `{agent_id}` | Model: `{curr_agent['model']}` | Temp: `{curr_agent['temperature'] / 10.0}`")

tab_chat, tab_settings, tab_rag, tab_keys, tab_analytics, tab_billing = st.tabs([
    "💬 Playground",
    "⚙️ Settings",
    "📚 Knowledge Base (RAG)",
    "🔑 API Keys",
    "📊 Analytics & Logs",
    "💳 Billing & Plans"
])

# ==================== TAB 1: PLAYGROUND ====================
with tab_chat:
    col_chat, col_code = st.columns([3, 2])
    
    with col_chat:
        st.subheader("Test your Agent")
        
        # Initialize conversation session
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = {}
        if agent_id not in st.session_state.chat_history:
            st.session_state.chat_history[agent_id] = []
        if "conv_id" not in st.session_state:
            st.session_state.conv_id = {}
        if agent_id not in st.session_state.conv_id:
            st.session_state.conv_id[agent_id] = None

        history = st.session_state.chat_history[agent_id]
        
        # Display chat messages
        for item in history:
            with st.chat_message(item["role"]):
                st.write(item["content"])
                if item.get("sources"):
                    st.caption("🔍 Sources: " + ", ".join(item["sources"]))
                if item.get("latency_ms"):
                    st.caption(f"⚡ {item['latency_ms']} ms | req: `{item.get('request_id', '')[:10]}`")

        # User chat input
        prompt = st.chat_input("Ask your agent a question...")
        if prompt:
            # Display user message immediately
            with st.chat_message("user"):
                st.write(prompt)
            
            # Send to backend
            with st.spinner("Agent is thinking..."):
                payload = {
                    "message": prompt,
                    "conversation_id": st.session_state.conv_id[agent_id]
                }
                resp = api_call("POST", f"/agents/{agent_id}/playground", json=payload)
                if resp:
                    st.session_state.conv_id[agent_id] = resp.get("conversation_id")
                    bot_response = resp.get("response", "")
                    sources = resp.get("sources", [])
                    req_id = resp.get("request_id", "")
                    
                    history.append({"role": "user", "content": prompt})
                    history.append({
                        "role": "assistant",
                        "content": bot_response,
                        "sources": sources,
                        "request_id": req_id,
                        "latency_ms": resp.get("latency_ms")
                    })
                    st.rerun()

        if history:
            if st.button("🧹 Clear Conversation", type="secondary"):
                if st.session_state.conv_id[agent_id]:
                    api_call("DELETE", f"/agents/{agent_id}/conversations/{st.session_state.conv_id[agent_id]}")
                st.session_state.chat_history[agent_id] = []
                st.session_state.conv_id[agent_id] = None
                st.rerun()

    with col_code:
        st.subheader("Integration Snippets")
        st.write("Integrate this agent into your website or backend application:")
        
        # Sample API key placeholder
        sample_key = "YOUR_API_KEY"  # raw keys are only shown once, at creation
        
        c_tab1, c_tab2, c_tab3 = st.tabs(["cURL", "Python", "JavaScript"])
        
        with c_tab1:
            st.code(f"""curl -X POST "{PUBLIC_API}/api/v1/agents/{agent_id}/chat" \\
  -H "Authorization: Bearer {sample_key}" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "message": "What is the return policy?",
    "conversation_id": "session-101"
  }}'""", language="bash")

        with c_tab2:
            st.code(f"""import requests

url = "{PUBLIC_API}/api/v1/agents/{agent_id}/chat"
headers = {{
    "Authorization": "Bearer {sample_key}",
    "Content-Type": "application/json"
}}
payload = {{
    "message": "What is the return policy?",
    "conversation_id": "session-101"
}}

response = requests.post(url, json=payload, headers=headers)
data = response.json()
print("Agent:", data["response"])
print("Sources:", data.get("sources"))""", language="python")

        with c_tab3:
            st.code(f"""const response = await fetch('{PUBLIC_API}/api/v1/agents/{agent_id}/chat', {{
  method: 'POST',
  headers: {{
    'Authorization': 'Bearer {sample_key}',
    'Content-Type': 'application/json'
  }},
  body: JSON.stringify({{
    message: 'What is the return policy?',
    conversation_id: 'session-101'
  }})
}});

const data = await response.json();
console.log('Answer:', data.response);""", language="javascript")

# ==================== TAB 2: SETTINGS ====================
with tab_settings:
    st.subheader("Agent Settings")
    with st.form("edit_agent_form"):
        new_name = st.text_input("Agent Name", value=curr_agent["name"])
        new_instructions = st.text_area("System Instructions & Persona", value=curr_agent["instructions"], height=160)
        
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            models_list = [
                "Qwen/Qwen2.5-7B-Instruct",
                "meta-llama/Llama-3.1-8B-Instruct",
                "mistralai/Mistral-7B-Instruct-v0.3",
                "google/gemma-2-9b-it"
            ]
            default_idx = models_list.index(curr_agent["model"]) if curr_agent["model"] in models_list else 0
            new_model = st.selectbox("Model", models_list, index=default_idx)
        with c_s2:
            new_temp = st.slider("Temperature", 0.0, 1.0, curr_agent["temperature"] / 10.0, step=0.1)
        
        save_btn = st.form_submit_button("💾 Save Changes", type="primary")
        if save_btn:
            update_payload = {
                "name": new_name,
                "instructions": new_instructions,
                "model": new_model,
                "temperature": int(new_temp * 10),
                "project_id": curr_agent.get("project_id")
            }
            res = api_call("PUT", f"/agents/{agent_id}", json=update_payload)
            if res:
                st.success("Agent settings updated successfully!")
                st.rerun()

    st.write("---")
    st.subheader("Danger Zone")
    st.write("Deleting this agent will permanently remove its RAG documents, API keys, and conversation history.")
    confirm_del = st.checkbox("I understand that deleting this agent cannot be undone.")
    if st.button("🗑️ Delete Agent", type="secondary", disabled=not confirm_del):
        res = api_call("DELETE", f"/agents/{agent_id}")
        if res:
            st.success("Agent deleted.")
            st.rerun()

# ==================== TAB 3: KNOWLEDGE BASE (RAG) ====================
with tab_rag:
    st.subheader("📚 Grounding & Knowledge Base (PDF RAG)")
    st.write("Upload company policies, FAQ documentation, or technical manuals. The system will extract text, chunk it into 800-character segments with 100-character overlap, generate vector embeddings, and store them in ChromaDB for high-precision semantic retrieval.")

    col_upload, col_privacy = st.columns([2, 1])
    with col_upload:
        uploaded_pdf = st.file_uploader("Upload FAQ or Documentation (PDF)", type=["pdf"])
        if uploaded_pdf is not None:
            if st.button("⚡ Index PDF into ChromaDB", type="primary"):
                with st.spinner("Extracting text, chunking, and indexing into vector database..."):
                    files = {"file": (uploaded_pdf.name, uploaded_pdf.getvalue(), "application/pdf")}
                    r = api_call("POST", f"/agents/{agent_id}/documents", files=files)
                    if r:
                        st.success(f"Successfully indexed '{r.get('filename')}' ({r.get('chunks_indexed')} chunks generated)!")
                        st.rerun()
    
    with col_privacy:
        st.info("""
        **🔒 Data Retention & Privacy**
        - Documents are parsed server-side and stored in isolated agent collections.
        - Embeddings are indexed locally in ChromaDB.
        - You can remove any document anytime using the controls below.
        """)

    st.write("---")
    st.subheader("Indexed Documents")
    docs = api_call("GET", f"/agents/{agent_id}/documents") or []
    if not docs:
        st.write("No documents uploaded yet. Upload a PDF above to enable Retrieval-Augmented Generation (RAG).")
    else:
        for d in docs:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.write(f"📄 **{d['filename']}**")
            c2.write(f"{d['chunks_count']} chunks")
            c3.write(f"{round(d['file_size_bytes'] / 1024, 1)} KB")
            if c4.button("🗑️ Delete", key=f"del_doc_{d['id']}"):
                del_r = api_call("DELETE", f"/agents/{agent_id}/documents/{d['id']}")
                if del_r:
                    st.success(f"Removed {d['filename']}")
                    st.rerun()

# ==================== TAB 4: API KEYS ====================
with tab_keys:
    st.subheader("🔑 Protected API Keys")
    st.write("API keys allow your backend servers or web applications to authenticate and query this agent via REST.")

    if st.button("➕ Generate New API Key", type="primary"):
        res = api_call("POST", f"/agents/{agent_id}/keys")
        if res:
            st.session_state["new_key_generated"] = res["api_key"]
            st.rerun()

    if "new_key_generated" in st.session_state:
        st.warning("⚠️ **Save your secret API key now!** It will not be shown again.")
        st.code(st.session_state["new_key_generated"], language="text")
        if st.button("I have copied my key"):
            del st.session_state["new_key_generated"]
            st.rerun()

    st.write("---")
    st.subheader("Active & Revoked Keys")
    keys = api_call("GET", f"/agents/{agent_id}/keys") or []
    if not keys:
        st.write("No API keys generated yet. Click above to create one.")
    else:
        for k in keys:
            col_k1, col_k2, col_k3 = st.columns([3, 2, 1])
            col_k1.write(f"`{k['prefix']}...`")
            if k["revoked"]:
                col_k2.markdown('<span class="badge-revoked">🚫 Revoked</span>', unsafe_allow_html=True)
            else:
                col_k2.markdown('<span class="badge-active">✅ Active</span>', unsafe_allow_html=True)
                if col_k3.button("Revoke", key=f"rev_{k['id']}"):
                    rev_res = api_call("DELETE", f"/keys/{k['id']}")
                    if rev_res:
                        st.success("API key revoked.")
                        st.rerun()

    st.caption("Security note: Keys are authenticated with Bearer tokens and rate-limited to 60 requests/minute per key.")

# ==================== TAB 5: ANALYTICS & LOGS ====================
with tab_analytics:
    st.subheader("📊 Usage Analytics & Request Logs")
    u_data = api_call("GET", "/usage") or {}
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Requests Used", f"{u_data.get('used_this_month', 0)} / {u_data.get('quota', 100)}")
    m2.metric("Remaining Quota", u_data.get("remaining", 0))
    m3.metric("Success Rate", f"{u_data.get('success_rate', 100)}%")
    m4.metric("Average Latency", f"{u_data.get('avg_latency_ms', 0)} ms")

    st.write("---")
    st.subheader("Recent Request Logs (Last 100 calls)")
    recent_logs = u_data.get("recent", [])
    if recent_logs:
        log_rows = []
        for r in recent_logs:
            status_symbol = "✅ 200 OK" if r["status"] == 200 else f"❌ {r['status']}"
            log_rows.append({
                "Request ID": r["request_id"][:12],
                "Agent": r["agent"][:12],
                "Status": status_symbol,
                "Latency": f"{r['latency_ms']} ms",
                "Error": r["error"] or "-",
                "Timestamp": r["time"].replace("T", " ")[:19]
            })
        st.dataframe(log_rows, use_container_width=True)
    else:
        st.write("No API requests recorded yet. Make calls in the Playground or via cURL to see real-time logs.")

# ==================== TAB 6: BILLING & PLANS ====================
with tab_billing:
    st.subheader("💳 Subscription & Quota Management")
    b_data = api_call("GET", "/billing") or {}
    current_plan = b_data.get("plan", "free")
    
    st.info(f"Your account is currently on the **{current_plan.upper()}** plan with a quota of **{b_data.get('quota', 100):,}** requests/month.")

    st.write("### Choose a Plan")
    p1, p2, p3 = st.columns(3)
    
    with p1:
        st.markdown("""
        ### Free Tier
        ### ₹0 / mo
        - 1 Active Chat Agent
        - 100 API requests / month
        - Standard community support
        - PDF RAG vector indexing
        """)
        if current_plan == "free":
            st.button("Current Plan", disabled=True, key="free_curr")
        elif b_data.get("sandbox_billing"):
            if st.button("Downgrade to Free (sandbox)", key="btn_free"):
                api_call("POST", "/billing/test-upgrade", json={"plan": "free"})
                st.rerun()
        else:
            st.caption("To cancel a paid plan, cancel the subscription in Razorpay; your account reverts to Free automatically.")

    with p2:
        st.markdown("""
        ### Starter Plan
        ### ₹299 / mo
        - Up to 5 Active Agents
        - 2,000 API requests / month
        - Priority vector search
        - Per-key rate limits (60/min)
        """)
        if current_plan == "starter":
            st.button("Current Plan", disabled=True, key="starter_curr")
        else:
            if st.button("Upgrade to Starter (₹299)", type="primary", key="btn_starter"):
                sub_res = api_call("POST", "/billing/subscribe", json={"plan": "starter"})
                if sub_res and sub_res.get("checkout_url"):
                    st.link_button("Open Razorpay Checkout", sub_res["checkout_url"])
                elif sub_res:
                    st.success(sub_res.get("message", "Upgraded to Starter!"))
                    st.rerun()

    with p3:
        st.markdown("""
        ### Pro Plan
        ### ₹999 / mo
        - Unlimited Agents
        - 10,000 API requests / month
        - High-throughput concurrency
        - Priority support & webhooks
        """)
        if current_plan == "pro":
            st.button("Current Plan", disabled=True, key="pro_curr")
        else:
            if st.button("Upgrade to Pro (₹999)", type="primary", key="btn_pro"):
                sub_res = api_call("POST", "/billing/subscribe", json={"plan": "pro"})
                if sub_res and sub_res.get("checkout_url"):
                    st.link_button("Open Razorpay Checkout", sub_res["checkout_url"])
                elif sub_res:
                    st.success(sub_res.get("message", "Upgraded to Pro!"))
                    st.rerun()

    st.write("---")
    st.caption("🔒 Payments are processed securely via Razorpay. Webhooks automatically upgrade accounts upon payment confirmation.")
