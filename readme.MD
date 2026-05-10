# 🎯 ResuMatch — AI-Powered Resume and Job Matching System

> Multi-agent AI system that scrapes jobs from top platforms such as Linkedin, Indeed, 
> Foundit and jobstreet, scores them against your resume and delivers ranked results with 
> interview tips directly to your inbox.

---

## 📌 Overview

ResuMatch is an end-to-end AI-powered job matching system built using
**CrewAI**, **FastAPI** and **Streamlit**. It automates the entire job
search workflow — from scraping live job listings to parsing your resume,
scoring each job match and sending a personalized email report with
interview tips.

---

## ✨ Features

- 🔍 **Multi-platform Job Scraping** — scrapes jobs from LinkedIn,
  Indeed, JobStreet and Foundit
- 📄 **Resume Parsing** — extracts skills, experience, education and
  projects from PDF and DOCX files
- 🤖 **AI-Powered Matching** — scores each job against your resume
  with detailed skill gap analysis
- 📧 **Automated Email Delivery** — sends match results with CSV
  attached via SMTP
- 🖥️ **Interactive UI** — multi-step Streamlit interface for seamless
  experience

  ---

## 🤖 Agents

### 1. Resume Parser Agent
- Reads PDF or DOCX resume using `pdfminer` and `python-docx`
- Extracts skills, experience, education, certifications and projects
- Returns structured JSON candidate profile

### 2. Job Matcher Agent
- Receives parsed resume and job listings
- Scores each job using weighted algorithm:
  - Skills: 50%
  - Experience: 30%
  - Education: 20%
- Generates per-job output:
  - Match score (0-100)
  - Skill gap analysis (matching, missing, bonus skills)
  - Application eligibility verdict

### 3. Email Scripting Agent
- Reads match results from CSV
- Generates personalized email subject and body with interview tips
- Sends email via SMTP with CSV attached as tool call
- Supports Gmail, Yahoo, Outlook, iCloud and Zoho

---

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| AI Framework | CrewAI |
| LLM | LLaMA 3.3 70B (Groq) |
| Backend | FastAPI |
| Frontend | Streamlit |
| Resume Parsing | pdfminer, python-docx |
| Email | SMTP (smtplib) |
| Data Processing | pandas |
| Version Control | Git / GitHub |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Groq API key (free at [console.groq.com](https://console.groq.com))
- Gmail App Password (or other provider)

### Installation

```bash
# Clone the repository
git clone https://github.com/Rakshithasrinivas37/ResuMatch.git
cd ResuMatch

# Create virtual environment
conda create -n <env_name> python=3.10

# Install dependencies
pip install -r requirements.txt
```

### Running the App

```bash
# Terminal 1 — Start FastAPI backend
uvicorn app:app --reload --port 8000

# Terminal 2 — Start Streamlit frontend
streamlit run frontend.py
```

Open `http://localhost:8501` in your browser.
Provide Groq API to start with the process in configurations.

---

## ⚠️ **Current Limitations**
- 🌏 Job scraping is supported for **Singapore only**
- 📋 Match results are generated for the **top 6 jobs** per run

---

## 🔮 Future Enhancements

- [ ] Expand job scraping to support multiple countries and regions
- [ ] **User-based system** — register and login with personal profile
      to track match history, saved jobs and application status
      across sessions
- [ ] Add support for more resume formats (TXT, LinkedIn PDF)

---

## 👩‍💻 Author

**Rakshitha S**
- GitHub: https://github.com/Rakshithasrinivas37
- LinkedIn: https://www.linkedin.com/in/rakshithasrinivas-a548601a9

---

> Built with ❤️ using CrewAI, FastAPI and Streamlit


