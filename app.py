from pydantic import BaseModel
import pandas as pd
import os
import json
import shutil
from pathlib import Path
import time
import re

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Form
from fastapi.responses import FileResponse

from crewai.llm import LLM
from crewai import Crew, Process

from Tools.job_scraping_tool import JobSearchTool
from Agents.resume_parser_agent import ResumeParser
from Agents.job_matcher_agent import JobMatcher
from Agents.email_scripting_agent import EmailScriptingAgent
from Tools.email_tool import EmailSenderTool

app = FastAPI()

# ── Define upload folder ───────────────────────────────
UPLOAD_DIR = Path("uploads/resumes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)  # creates folder if not exists

class FetchJobsInput(BaseModel):
    role: str
    location: str
    min_exp: int
    max_exp: int

class AuthenticationDetils(BaseModel):
    mail_ID: str
    app_password: str

class EmailInput(BaseModel):
    mail_id        : str
    app_password   : str
    candidate_name : str
    api_key        : str
    csv_path       : str = "match_results.csv"

@app.post("/fetch_jobs")
def search_jobs(data: FetchJobsInput):
    job_search_tool = JobSearchTool()

    total_jobs = job_search_tool._run(data.role, data.location, data.min_exp, data.max_exp)

    print(type(total_jobs))

    # Save CSV here — not LLM's job
    df = pd.DataFrame(total_jobs)
    df.to_csv("job_results.csv", index=False)
    print(f"Saved {len(total_jobs)} jobs!")
    return {
        "message": f"Scraped {len(total_jobs)} job details for {data.role} in {data.location}"
    }

@app.get("/download_jobs")
def download_jobs():

    if not os.path.exists("job_results.csv"):
        raise HTTPException(status_code=404, detail="No job results found. Run /fetch_jobs first.")

    return FileResponse(
        path="job_results.csv",
        media_type="text/csv",
        filename="job_results.csv"
    )

# ── Helper: trim job fields ────────────────────────────
def trim_jobs(jobs: list) -> list:
    """Keep only fields relevant for matching — reduces tokens."""
    return [
        {
            "title"              : job.get("title", ""),
            "company"            : job.get("company", ""),
            "location"           : job.get("location", ""),
            "job_url"            : job.get("job_url", ""),
            "experience_required": job.get("experience_required", ""),
            # ✅ 500 words
            "description"        : " ".join(
                job.get("description", "").split()[:500]
            ),
        }
        for job in jobs
    ]

def chunk_jobs(jobs: list, chunk_size: int) -> list:
    """Split jobs list into chunks of chunk_size."""
    return [
        jobs[i:i + chunk_size]
        for i in range(0, len(jobs), chunk_size)
    ]

# ── Add delay between tasks ────────────────────────────
def after_task_callback(task_output):
    print(f"Task completed. Waiting 60s to respect TPM limit...")
    time.sleep(60)   # wait 60 seconds before next task

# ── Helper: parse JSON from text ───────────────────────
def extract_json_list(text: str) -> list:
    """Extract and combine all JSON arrays from text."""
    all_jobs = []
    json_blocks = re.findall(r'\[.*?\]', text, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, list):
                all_jobs.extend(parsed)
            elif isinstance(parsed, dict):
                all_jobs.append(parsed)
        except json.JSONDecodeError:
            continue

    # ── Deduplicate by job_url ─────────────────────────
    seen   = set()
    unique = []
    for job in all_jobs:
        url = job.get("job_url", "")
        if url not in seen:
            seen.add(url)
            unique.append(job)

    return unique



# ── Build crew ─────────────────────────────────────────
def build_crew(jobs: list, api_key: str, chunk_results: list) -> Crew:

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=api_key,
        temperature=0.0
    )

    # ✅ Collect results from each chunk via callback
    def collect_and_wait(task_output):
        try:
            raw   = str(task_output).strip()
            raw   = raw.removeprefix("```json").removesuffix("```").strip()
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    chunk_results.extend(parsed)
                    print(f"✅ Collected {len(parsed)} jobs. "
                          f"Total so far: {len(chunk_results)}")
                elif isinstance(parsed, dict):
                    chunk_results.append(parsed)
                    print(f"✅ Collected 1 job. "
                          f"Total so far: {len(chunk_results)}")
        except Exception as e:
            print(f"⚠️  Could not parse chunk result: {e}")

        print("Waiting 60s for Groq TPM limit...")
        time.sleep(60)

    trimmed_jobs = trim_jobs(jobs[:6])
    job_chunks   = chunk_jobs(trimmed_jobs, 3)

    # ── Resume parser ──────────────────────────────────
    resume_parser       = ResumeParser(llm)
    resume_parser_agent = resume_parser.resume_parser_agent()
    resume_parser_task  = resume_parser.resume_parser_task()

    # ── Job matcher ────────────────────────────────────
    job_matcher = JobMatcher(llm)
    job_matcher.job_matcher_agent()

    all_tasks     = [resume_parser_task]
    previous_task = resume_parser_task

    for i, chunk in enumerate(job_chunks):
        # ✅ Last chunk doesn't need delay
        cb = collect_and_wait if i < len(job_chunks) - 1 else (
            lambda task_output: _collect_only(task_output, chunk_results)
        )
        task = job_matcher.job_matcher_task(
            chunk,
            context=[previous_task],
            callback=cb
        )
        all_tasks.append(task)
        previous_task = task

    crew = Crew(
        agents=[resume_parser_agent, job_matcher.agent],
        tasks=all_tasks,
        process=Process.sequential,
        verbose=True,
        max_rpm=10
    )

    return crew

def _collect_only(task_output, chunk_results: list):
    """Collect last chunk result without delay."""
    try:
        raw   = str(task_output).strip()
        raw   = raw.removeprefix("```json").removesuffix("```").strip()
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                chunk_results.extend(parsed)
                print(f"✅ Final chunk collected {len(parsed)} jobs. "
                      f"Total: {len(chunk_results)}")
            elif isinstance(parsed, dict):
                chunk_results.append(parsed)
    except Exception as e:
        print(f"⚠️  Could not parse final chunk: {e}")

def convert_match_results_to_csv(match_results: list, csv_path: str = "match_results.csv"):
    """Flatten nested match results JSON into a CSV file."""
    rows = []

    for job in match_results:
        # ── Base fields ────────────────────────────────
        score_breakdown  = job.get("score_breakdown", {})
        job_match        = job.get("job_match_analysis", {})
        eligibility      = job.get("application_eligibility", {})
        skill_gap        = job.get("skill_gap_analysis", {})
        upskilling       = job.get("upskilling_roadmap", {})
        interview        = job.get("interview_preparation", {})

        # ── Job match analysis — handle both formats ───
        # Format 1: match_score > 75 — overall_summary
        # Format 2: match_score <= 75 — what_matches / what_doesnt_match
        what_matches     = job_match.get("what_matches", {})
        what_not         = job_match.get("what_doesnt_match", {})

        matching_reasons = job_match.get("matching_reasons", [])
        if isinstance(matching_reasons, list):
            matching_reasons = " | ".join(matching_reasons)

        what_matches_skills = what_matches.get("skills", [])
        if isinstance(what_matches_skills, list):
            what_matches_skills = ", ".join(what_matches_skills)

        what_not_skills = what_not.get("skills", [])
        if isinstance(what_not_skills, list):
            what_not_skills = ", ".join(what_not_skills)

        # ── Skill gap ──────────────────────────────────
        matching_skills = skill_gap.get("matching_skills", [])
        missing_skills  = skill_gap.get("missing_skills", [])
        bonus_skills    = skill_gap.get("bonus_skills", [])

        if isinstance(matching_skills, list):
            matching_skills = ", ".join(matching_skills)
        if isinstance(missing_skills, list):
            missing_skills  = ", ".join(missing_skills)
        if isinstance(bonus_skills, list):
            bonus_skills    = ", ".join(bonus_skills)

        # ── Next steps ─────────────────────────────────
        next_steps = eligibility.get("next_steps", "")
        if isinstance(next_steps, list):
            next_steps = " | ".join(next_steps)

        # ── Interview questions ────────────────────────
        questions = interview.get("top_5_questions", [])
        if isinstance(questions, list):
            questions = " | ".join(questions)

        projects = interview.get("projects_to_highlight", [])
        if isinstance(projects, list):
            projects = ", ".join(projects)

        # ── Upskilling roadmap ─────────────────────────
        upskilling_summary = ""
        if isinstance(upskilling, dict):
            parts = []
            for skill, details in upskilling.items():
                if isinstance(details, dict):
                    parts.append(
                        f"{skill}: {details.get('priority_level', '')} priority "
                        f"({details.get('estimated_time_to_learn', '')})"
                    )
                else:
                    parts.append(f"{skill}: {details}")
            upskilling_summary = " | ".join(parts)

        rows.append({
            # ── Job info ───────────────────────────────
            "job_title"          : job.get("job_title", ""),
            "company"            : job.get("company", ""),
            "location"           : job.get("location", ""),
            "job_url"            : job.get("job_url", ""),

            # ── Scores ────────────────────────────────
            "match_score"        : job.get("match_score", 0),
            "skills_score"       : score_breakdown.get("skills", ""),
            "experience_score"   : score_breakdown.get("experience", ""),
            "education_score"    : score_breakdown.get("education", ""),

            # ── Match analysis ─────────────────────────
            "overall_summary"    : job_match.get("overall_summary", ""),
            "overall_assessment" : job_match.get("overall_assessment", ""),
            "matching_reasons"   : matching_reasons,
            "what_matches"       : what_matches_skills,
            "what_doesnt_match"  : what_not_skills,
            "mismatch_impact"    : what_not.get("impact", ""),

            # ── Eligibility ────────────────────────────
            "verdict"            : eligibility.get("verdict", ""),
            "reason"             : eligibility.get("reason", ""),
            "next_steps"         : next_steps,

            # ── Skill gap ──────────────────────────────
            "matching_skills"    : matching_skills,
            "missing_skills"     : missing_skills,
            "bonus_skills"       : bonus_skills,

            # ── Upskilling ─────────────────────────────
            "upskilling_roadmap" : upskilling_summary,

            # ── Interview prep ─────────────────────────
            "interview_questions": questions,
            "projects_to_highlight": projects,
        })

    df = pd.DataFrame(rows)

    # ── Sort by match score descending ─────────────────
    df = df.sort_values("match_score", ascending=False).reset_index(drop=True)

    # ── Save to CSV ────────────────────────────────────
    df.to_csv(csv_path, index=False)
    print(f"✅ Saved {len(df)} jobs to {csv_path}")

@app.post("/match_resume")
async def match_resume(
    resume: UploadFile = File(...),         # ✅ file passed separately
    job_results: str = Form(...),
    api_key: str = Form(...)
):
    # ── Save resume to folder ──────────────────────────
    file_path = UPLOAD_DIR / resume.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)

    print(f"Resume saved at: {file_path}")

    jobs = json.loads(job_results)

    # --------------- Build crew -------------------------
    chunk_results = []
    crew = build_crew(jobs, api_key, chunk_results)

    # --------------- Kickoff Crew -----------------------
    response = crew.kickoff(
            inputs={"resume_path": str(file_path)}
        )
    
    convert_match_results_to_csv(chunk_results)

    return {
        "message": f"Saved {len(chunk_results)} match results to match_results.csv"
    }

@app.get("/download_match_results")
def download_match_results():

    if not os.path.exists("match_results.csv"):
        raise HTTPException(status_code=404, detail="No match results found. Run /match_resume first.")

    return FileResponse(
        path="match_results.csv",
        media_type="text/csv",
        filename="match_results.csv"
    )

@app.post("/send_emails")
def send_emails(data: EmailInput):
    try:
        # ── Read match results CSV ─────────────────────
        if not os.path.exists(data.csv_path):
            raise HTTPException(
                status_code=404,
                detail="match_results.csv not found. Run /match_resume first."
            )

        df   = pd.read_csv(data.csv_path)
        jobs = df.to_dict(orient="records")

        if not jobs:
            raise HTTPException(
                status_code=400,
                detail="No match results in CSV."
            )

        # ── Sort by match score ────────────────────────
        jobs = sorted(
            jobs,
            key=lambda x: x.get("match_score", 0),
            reverse=True
        )

        print(f"Creating email for {len(jobs)} job matches...")

        # ── Build email scripting crew ─────────────────
        llm = LLM(
            model="groq/llama-3.3-70b-versatile",
            api_key=data.api_key,
            temperature=0.7
        )

        email_agent_builder = EmailScriptingAgent(llm)
        email_agent         = email_agent_builder.email_scripting_agent()
        email_task          = email_agent_builder.email_scripting_task(
            jobs,
            data.candidate_name
        )

        email_crew = Crew(
            agents=[email_agent],
            tasks=[email_task],
            process=Process.sequential,
            verbose=True
        )

        response = email_crew.kickoff()

        # ── Parse subject and body ─────────────────────
        try:
            raw = str(response).strip()
            raw = raw.removeprefix("```json").removesuffix("```").strip()
            # ✅ Find JSON object (not array)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            email_script = json.loads(match.group()) if match else {}
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Could not parse email script: {str(e)}"
            )

        subject = email_script.get("subject", "Your Job Match Results")
        body    = email_script.get("body", "")

        print(f"Subject: {subject}")

        # ── Send email with CSV attached ───────────────
        send_input = json.dumps({
            "mail_id"       : data.mail_id,
            "app_password"  : data.app_password,
            "candidate_name": data.candidate_name,
            "subject"       : subject,
            "body"          : body,
            "csv_path"      : data.csv_path
        })

        send_result = json.loads(EmailSenderTool(send_input))

        return {
            "status"  : "success",
            "sent_to" : data.mail_id,
            "subject" : subject,
            "csv_sent": data.csv_path,
            "result"  : send_result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))