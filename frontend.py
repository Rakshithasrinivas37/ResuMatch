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

if "resume_matched" not in st.session_state:
    st.session_state.resume_matched = False

if "match_results" not in st.session_state:
    st.session_state.match_results = None

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

                            # ✅ Show download button in Streamlit
                            st.download_button(
                                label="📥 Download Job Results CSV",
                                data=csv_data,
                                file_name="job_results.csv",
                                mime="text/csv"
                            )

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

                            st.session_state.match_results = result
                            st.session_state.resume_matched = True
                        else:
                            st.error(f"Error {response.status_code}: {response.text}")
                            st.session_state.resume_matched = False

                    except requests.exceptions.ConnectionError:
                        st.error("❌ Could not connect to FastAPI. Is it running?")
                        st.session_state.resume_matched = False       
else:
    st.warning("Please provide API Key!!!")