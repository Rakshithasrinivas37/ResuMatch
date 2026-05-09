import streamlit as st
import requests
import pandas as pd
import io
import json

st.title("ResuMatch - AI Powered Resume and Job Matching System")

st.sidebar.title("⚙️ Configurations")
api_key = st.sidebar.text_input("Enter your API Key: ", type="password")

# ✅ Initialize session state
if "jobs_fetched" not in st.session_state:
    st.session_state.jobs_fetched = False

if "job_results" not in st.session_state:
    st.session_state.job_results = None

if "jobs_csv_data" not in st.session_state:
    st.session_state.jobs_csv_data = None

if "resume_matched" not in st.session_state:
    st.session_state.resume_matched = False

if "match_results" not in st.session_state:
    st.session_state.match_results = None

if "match_csv_data" not in st.session_state:
    st.session_state.match_csv_data = None

if api_key:
    role     = st.text_input("Role:")
    location = st.text_input("Location:")
    min_exp  = st.slider("Minimum Experience", 0, 20, 1)
    max_exp  = st.slider("Maximum Experience", 0, 20, 1)

    if st.button("Search Jobs"):
        if not role:
            st.warning("Please enter a Role.")
        elif not location:
            st.warning("Please enter a Location.")
        elif min_exp > max_exp:
            st.warning("Min experience cannot be greater than Max experience.")
        else:
            payload = {
                "role": role,
                "location": location,
                "min_exp": min_exp,
                "max_exp": max_exp
            }

            with st.spinner("Fetching jobs..."):
                try:
                    response = requests.post(
                        "http://localhost:8000/fetch_jobs",
                        json=payload,
                        headers={"x-api-key": api_key}
                    )

                    if response.status_code == 200:
                        result = response.json()
                        st.success(result["message"])
                        
                        csv_response = csv_response = requests.get(
                            "http://localhost:8000/download_jobs",
                        )

                        if csv_response.status_code == 200:
                            csv_data = csv_response.content    # raw bytes

                            st.session_state.jobs_csv_data = csv_data

                            # ✅ Save to session state for later use (resume matching)
                            df = pd.read_csv(io.BytesIO(csv_data))
                            st.session_state.jobs_fetched = True
                            st.session_state.job_results = df.to_dict(orient="records")

                    else:
                        st.error(f"Error {response.status_code}: {response.text}")
                        st.session_state.jobs_fetched = False  # Reset on failure

                except requests.exceptions.ConnectionError:
                    st.error("❌ Could not connect to FastAPI. Is it running?")
                    st.session_state.jobs_fetched = False  # Reset on failure

    if st.session_state.jobs_csv_data is not None:
        st.download_button(
            label    = "📥 Download Match Results CSV",
            data     = st.session_state.jobs_csv_data,
            file_name= "job_results.csv",
            mime     = "text/csv",
            key      = "download_jobs_csv"
    )

    # ✅ Show resume upload ONLY if jobs were fetched successfully
    if st.session_state.jobs_fetched:
        st.markdown("---")
        st.subheader("Step 2: Upload Your Resume")

        resume_file = st.file_uploader("Upload Resume", type=["pdf", "docx"])

        if st.button("Match Jobs and Resume"):
            if not resume_file:
                st.warning("Please upload your resume.")
            else:
                with st.spinner("Matching resume with jobs..."):
                    try:
                        # ✅ Pass file to FastAPI using multipart/form-data
                        files = {
                            "resume": (
                                resume_file.name,        # filename
                                resume_file.getvalue(),  # raw bytes
                                resume_file.type         # MIME type e.g. application/pdf
                            )
                        }

                        data = {
                            "job_results": json.dumps(st.session_state.job_results),
                            "api_key": api_key
                        }

                        response = requests.post(
                            "http://localhost:8000/match_resume",
                            files=files,                          # ✅ file goes here
                            data=data
                        )

                        if response.status_code == 200:
                            result = response.json()
                            st.success(result["message"])
                            st.json(result)

                            csv_response = csv_response = requests.get(
                            "http://localhost:8000/download_match_results",
                        )

                            if csv_response.status_code == 200:
                                csv_data = csv_response.content    # raw bytes

                                # ✅ Store in session state — persists across reruns
                                st.session_state.match_csv_data = csv_data

                                df = pd.read_csv(io.BytesIO(csv_data))
                                st.session_state.match_results  = df.to_dict(orient="records")
                                st.session_state.resume_matched = True

                        else:
                            st.error(f"Error {response.status_code}: {response.text}")
                            st.session_state.resume_matched = False

                    except requests.exceptions.ConnectionError:
                        st.error("❌ Could not connect to FastAPI. Is it running?")
                        st.session_state.resume_matched = False     

        if st.session_state.match_csv_data is not None and len(st.session_state.match_csv_data) > 0:
            st.download_button(
                label    = "📥 Download Match Results CSV",
                data     = st.session_state.match_csv_data,
                file_name= "match_results.csv",
                mime     = "text/csv",
                key      = "download_match_csv"
            )
        
        if st.session_state.resume_matched:
            st.markdown("---")
            st.subheader("Step 3: Send Results via Email")

            # ✅ Provider config
            EMAIL_PROVIDERS = {
                "Gmail": {
                    "smtp": "smtp.gmail.com",
                    "port": 587,
                    "app_password_url": "https://myaccount.google.com/apppasswords",
                    "instructions": """
                        1. Go to [myaccount.google.com](https://myaccount.google.com)
                        2. Navigate to **Security** → **2-Step Verification** (must be ON)
                        3. Scroll down → click **App Passwords**
                        4. Select **Mail** → **Other (Custom name)**
                        5. Click **Generate** → copy the 16-character password
                                    """
                },
                "Yahoo": {
                    "smtp": "smtp.mail.yahoo.com",
                    "port": 587,
                    "app_password_url": "https://login.yahoo.com/account/security",
                    "instructions": """
                        1. Go to [Yahoo Account Security](https://login.yahoo.com/account/security)
                        2. Enable **Two-Step Verification** if not already ON
                        3. Scroll down → click **Generate app password**
                        4. Select **Other App** → give it a name
                        5. Copy the generated password
                    """
                },
                "Outlook": {
                    "smtp": "smtp.office365.com",
                    "port": 587,
                    "app_password_url": "https://account.microsoft.com/security",
                    "instructions": """
                        1. Go to [Microsoft Account Security](https://account.microsoft.com/security)
                        2. Click **Advanced Security Options**
                        3. Enable **Two-Step Verification** if not already ON
                        4. Scroll to **App Passwords** → click **Create a new app password**
                        5. Copy the generated password
                    """
                },
                "iCloud": {
                    "smtp": "smtp.mail.me.com",
                    "port": 587,
                    "app_password_url": "https://appleid.apple.com/account/manage",
                    "instructions": """
                        1. Go to [appleid.apple.com](https://appleid.apple.com)
                        2. Sign in → go to **Security** section
                        3. Click **Generate Password** under App-Specific Passwords
                        4. Enter a label → click **Create**
                        5. Copy the generated password
                    """
                },
                "Zoho": {
                    "smtp": "smtp.zoho.com",
                    "port": 587,
                    "app_password_url": "https://accounts.zoho.com/home#security",
                    "instructions": """
                        1. Go to [Zoho Account Security](https://accounts.zoho.com/home#security)
                        2. Enable **Two-Factor Authentication** if not already ON
                        3. Scroll to **App-Specific Passwords** → click **Generate New Password**
                        4. Enter a name → click **Generate**
                        5. Copy the generated password
                                    """
                }
            }

            # ✅ Provider selector
            provider = st.selectbox("Select Email Provider", list(EMAIL_PROVIDERS.keys()))
            selected = EMAIL_PROVIDERS[provider]

            email_id = st.text_input("Enter Email-ID:")

            # ✅ App password field + create button side by side
            col1, col2 = st.columns([3, 1])
            with col1:
                app_password = st.text_input("App Password", type="password")
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.link_button("🔑 Create App Password", selected["app_password_url"])

            # ✅ Dynamic instructions per provider
            with st.expander(f"ℹ️ How to create an App Password for {provider}?"):
                st.markdown(selected["instructions"])
                st.warning("⚠️ 2-Step Verification must be enabled before generating an App Password.")

            if st.button("Send Mail"):
                if not email_id:
                    st.warning("Please enter your Email-ID.")
                elif not app_password:
                    st.warning("Please enter your App Password.")
                else:
                    with st.spinner("Sending mail..."):
                        try:
                            payload = {
                                "mail_ID": email_id,
                                "app_password": app_password,
                                "smtp_server": selected["smtp"],   # ✅ pass SMTP details
                                "smtp_port": selected["port"],
                                "provider": provider
                            }

                            response = requests.post(
                                "http://localhost:8000/send_mail",
                                json=payload,
                                headers={"x-api-key": api_key}
                            )

                            if response.status_code == 200:
                                result = response.json()
                                st.success(result["message"])
                            else:
                                st.error(f"Error {response.status_code}: {response.text}")

                        except requests.exceptions.ConnectionError:
                            st.error("❌ Could not connect to FastAPI. Is it running?")

else:
    st.warning("Please provide API Key!!!")